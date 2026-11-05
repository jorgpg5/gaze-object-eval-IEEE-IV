"""Exact gaze-to-box geometry, vectorised.

angle_to_box: angular distance (deg) from the gaze ray to the nearest point of
an oriented 3D box (yaw about z): 0 when the ray hits the box, otherwise the
minimum over the box's 12 edges (for a convex box seen from outside, the
nearest point to a ray that misses it lies on the silhouette, i.e. on an edge).
inf when the whole box is behind the eye.

image_box_to_vehicle: a camera-only detection (image box + estimated depth) as
a thin box in the vehicle frame, for systems that log image boxes.
"""
import numpy as np
import pandas as pd

_SIGNS = np.array([[i, j, k] for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)], float)   # 8 corners
_EDGES = [(a, b) for a in range(8) for b in range(a + 1, 8)
          if np.sum(_SIGNS[a] != _SIGNS[b]) == 1]                                        # 12 edges


def gaze_dir(yaw_deg, pitch_deg):
    Y, P = np.radians(yaw_deg), np.radians(pitch_deg)
    return np.stack([np.cos(P) * np.cos(Y), np.cos(P) * np.sin(Y), np.sin(P)], -1)


def corners(c, s, yaw):
    """c, s: (N,3) centre and full size; yaw (N,) rad -> (N,8,3)."""
    h = s[:, None, :] / 2 * _SIGNS[None]
    cy, sn = np.cos(yaw)[:, None], np.sin(yaw)[:, None]
    x = c[:, None, 0] + h[..., 0] * cy - h[..., 1] * sn
    y = c[:, None, 1] + h[..., 0] * sn + h[..., 1] * cy
    z = c[:, None, 2] + h[..., 2]
    return np.stack([x, y, z], -1)


def ray_hits(eye, g, c, s, yaw):
    """Slab test in the box frame: does the ray eye + t g (t > 0) hit the box?"""
    co, sn = np.cos(-yaw), np.sin(-yaw)
    lo = eye - c
    ro = np.stack([lo[:, 0] * co - lo[:, 1] * sn, lo[:, 0] * sn + lo[:, 1] * co, lo[:, 2]], 1)
    rd = np.stack([g[:, 0] * co - g[:, 1] * sn, g[:, 0] * sn + g[:, 1] * co, g[:, 2]], 1)
    h = s / 2
    tmin = np.zeros(len(eye))
    tmax = np.full(len(eye), np.inf)
    ok = np.ones(len(eye), bool)
    for k in range(3):
        par = np.abs(rd[:, k]) < 1e-12
        ok &= ~(par & ((ro[:, k] < -h[:, k]) | (ro[:, k] > h[:, k])))
        with np.errstate(divide="ignore", invalid="ignore"):
            t1 = (-h[:, k] - ro[:, k]) / rd[:, k]
            t2 = (h[:, k] - ro[:, k]) / rd[:, k]
        lo_, hi_ = np.minimum(t1, t2), np.maximum(t1, t2)
        lo_ = np.where(par, -np.inf, lo_)
        hi_ = np.where(par, np.inf, hi_)
        tmin = np.maximum(tmin, lo_)
        tmax = np.minimum(tmax, hi_)
    return ok & (tmin <= tmax) & (tmax > 0)


def angle_to_box(eye, g, c, s, yaw):
    """Angular distance (deg) from the gaze ray to the box; 0 when it hits."""
    P = corners(c, s, yaw) - eye[:, None, :]
    best = np.full(len(eye), -1.0)                       # max cos over the edges
    for a, b in _EDGES:
        q0, w = P[:, a], P[:, b] - P[:, a]
        A = (g * q0).sum(1)
        B = (g * w).sum(1)
        C = (q0 * q0).sum(1)
        D = (q0 * w).sum(1)
        Ee = (w * w).sum(1)
        with np.errstate(divide="ignore", invalid="ignore"):
            ts = (A * D - B * C) / (B * D - A * Ee)
        for t in (np.zeros(len(eye)), np.ones(len(eye)), np.clip(np.nan_to_num(ts, nan=0.0), 0, 1)):
            p = q0 + t[:, None] * w
            cs = (g * p).sum(1) / np.maximum(np.linalg.norm(p, axis=1), 1e-9)
            best = np.maximum(best, cs)
    ang = np.degrees(np.arccos(np.clip(best, -1, 1)))
    behind = (P * g[:, None, :]).sum(2).max(1) <= 0     # whole box behind the eye
    ang = np.where(behind, np.inf, ang)
    return np.where(ray_hits(eye, g, c, s, yaw), 0.0, ang)


def angular_extent(eye, c, s, yaw):
    """Azimuth / elevation extent (deg) of a box seen from the eye: (az0, az1, el0, el1)."""
    P = corners(c, s, yaw) - eye[:, None, :]
    az = np.degrees(np.arctan2(P[..., 1], P[..., 0]))
    el = np.degrees(np.arctan2(P[..., 2], np.hypot(P[..., 0], P[..., 1])))
    return az.min(1), az.max(1), el.min(1), el.max(1)


def coverage(a, b):
    """Share of box a's angular area that lies inside box b; a, b = (az0, az1, el0, el1)."""
    w = np.clip(np.minimum(a[1], b[1]) - np.maximum(a[0], b[0]), 0, None)
    h = np.clip(np.minimum(a[3], b[3]) - np.maximum(a[2], b[2]), 0, None)
    area = np.maximum((a[1] - a[0]) * (a[3] - a[2]), 1e-12)
    return w * h / area


# --------------------------------------------------------------------------
# camera-only detections -> boxes
# --------------------------------------------------------------------------
def image_box_to_vehicle(u1, v1, u2, v2, depth_m, fx, fy, cx, cy, cam_x, cam_y, cam_z, thin_m=0.3):
    """Pinhole camera looking along +x of the vehicle frame (image u to the
    right, v down; principal point cx, cy; focal lengths fx, fy in pixels;
    camera at cam_x, cam_y, cam_z in the vehicle frame). depth_m = forward
    distance from the camera to the object's near face. Arguments broadcast.
    Returns x, y, z, length, width, height, yaw_deg of a box thin_m deep (the
    depth extent of a camera-only object is unknown)."""
    u1, v1, u2, v2, d = (np.asarray(a, float) for a in (u1, v1, u2, v2, depth_m))
    x = cam_x + d + thin_m / 2
    return pd.DataFrame(dict(
        x=np.broadcast_to(x, d.shape),
        y=cam_y - d * (((u1 + u2) / 2 - cx) / fx),
        z=cam_z - d * (((v1 + v2) / 2 - cy) / fy),
        length=np.full(d.shape, thin_m),
        width=d * (u2 - u1) / fx,
        height=d * (v2 - v1) / fy,
        yaw_deg=np.zeros(d.shape)))
