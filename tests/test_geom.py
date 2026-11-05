import numpy as np

from _helpers import goeval  # noqa: F401
from goeval import geom as G


def brute_angle(eye, g, c, s, yaw, n=40):
    """Smallest angle from the gaze ray to points sampled on the box surface."""
    u = np.linspace(-0.5, 0.5, n)
    pts = []
    for ax in range(3):
        a, b = [k for k in range(3) if k != ax]
        for sgn in (-0.5, 0.5):
            A, B = np.meshgrid(u, u)
            p = np.zeros((A.size, 3))
            p[:, ax] = sgn
            p[:, a], p[:, b] = A.ravel(), B.ravel()
            pts.append(p)
    p = np.concatenate(pts) * s
    cy, sn = np.cos(yaw), np.sin(yaw)
    w = np.stack([c[0] + p[:, 0] * cy - p[:, 1] * sn, c[1] + p[:, 0] * sn + p[:, 1] * cy, c[2] + p[:, 2]], 1) - eye
    cosang = (w @ g) / np.linalg.norm(w, axis=1)
    return np.degrees(np.arccos(np.clip(cosang.max(), -1, 1)))


def test_ray_through_centre_is_zero():
    eye = np.array([[0.0, 0.0, 1.2]])
    g = G.gaze_dir(np.array([0.0]), np.array([0.0]))
    a = G.angle_to_box(eye, g, np.array([[20.0, 0.0, 1.2]]), np.array([[0.5, 0.6, 1.8]]), np.array([0.0]))
    assert a[0] == 0.0


def test_box_behind_eye_is_inf():
    eye = np.array([[0.0, 0.0, 1.2]])
    g = G.gaze_dir(np.array([0.0]), np.array([0.0]))
    a = G.angle_to_box(eye, g, np.array([[-10.0, 0.0, 1.2]]), np.array([[0.5, 0.6, 1.8]]), np.array([0.0]))
    assert np.isinf(a[0])


def test_matches_brute_force_on_random_boxes():
    rng = np.random.default_rng(0)
    n = 60
    eye = np.tile([1.0, -0.35, 1.2], (n, 1))
    yaw_g, pitch_g = rng.uniform(-20, 20, n), rng.uniform(-8, 5, n)
    g = G.gaze_dir(yaw_g, pitch_g)
    c = np.stack([rng.uniform(6, 60, n), rng.uniform(-8, 8, n), rng.uniform(0.5, 1.5, n)], 1)
    s = np.stack([rng.uniform(0.3, 5, n), rng.uniform(0.3, 2, n), rng.uniform(0.5, 2, n)], 1)
    yaw = rng.uniform(-np.pi, np.pi, n)
    exact = G.angle_to_box(eye, g, c, s, yaw)
    for k in range(n):
        b = brute_angle(eye[k], g[k], c[k], s[k], yaw[k])
        assert exact[k] <= b + 1e-6                 # never larger than any point on the box
        assert b - exact[k] < 0.05                  # and the sampled surface gets within sampling error


def test_known_offset_thin_box():
    # thin box 1 m wide, 20 m ahead, centred 3 m to the left: its right edge is at atan(2.5/20)
    eye = np.array([[0.0, 0.0, 1.0]])
    g = G.gaze_dir(np.array([0.0]), np.array([0.0]))
    a = G.angle_to_box(eye, g, np.array([[20.0, 3.0, 1.0]]), np.array([[0.001, 1.0, 2.0]]), np.array([0.0]))
    assert abs(a[0] - np.degrees(np.arctan2(2.5, 20.0))) < 1e-3


def test_image_box_round_trip():
    fx = fy = 1000.0
    cx, cy = 960.0, 540.0
    cam = (1.8, 0.0, 1.3)
    # a 0.6 m wide, 1.75 m tall object whose near face is 20 m ahead of the camera, 2 m to the left
    y0, z0, w, h, d = 2.0, 0.875, 0.6, 1.75, 20.0
    u1 = cx - fx * (y0 + w / 2 - cam[1]) / d
    u2 = cx - fx * (y0 - w / 2 - cam[1]) / d
    v1 = cy - fy * (z0 + h / 2 - cam[2]) / d
    v2 = cy - fy * (z0 - h / 2 - cam[2]) / d
    b = G.image_box_to_vehicle([u1], [v1], [u2], [v2], [d], fx, fy, cx, cy, *cam)
    assert np.allclose([b.y[0], b.z[0], b.width[0], b.height[0]], [y0, z0, w, h])
    assert abs(b.x[0] - (cam[0] + d + 0.15)) < 1e-9
