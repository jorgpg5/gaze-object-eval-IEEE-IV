#!/usr/bin/env python3
"""Synthetic recordings in the log format of docs/schema.md, with known answers.

Each protocol is simulated with:
  - a cued target that stands and walks as in the protocol (docs/protocol.md);
  - object lists at 10 Hz (3D) and 15 Hz (camera-only), with 3D detection that
    fades with distance, camera-only detections at an estimated depth when the
    object is not in 3D, and one tracker ID switch;
  - gaze at 50 Hz aimed at the target's upper body plus a known yaw / pitch bias
    and Gaussian noise correlated in time, blinks (with a DMS blink counter), and glances away;
  - a stand-in "system under test": the nearest 3D box within 1.5 deg of the
    gaze, else the nearest camera-only box within 1.5 deg, else nothing. It is
    only there so the example produces a full report; replace attended_id
    with your own system's output.

usage: generate.py [OUT_DIR]   (default: examples/synthetic/data)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from goeval import geom as G  # noqa: E402

RATE, LIDAR_HZ, CAM_HZ = 50.0, 10.0, 15.0
EYE = np.array([1.0, -0.35, 1.2])
CAM = np.array([1.8, 0.0, 1.3])
PED = (0.5, 0.6, 1.75)                      # length, width, height (m)
CAR = (4.5, 1.8, 1.5)
WALK_M_S = 1.4
SYSTEM_TOL_DEG = 1.5


# ------------------------------------------------------------------ motion
class Track:
    """Piecewise-linear motion from a plan of ('stand', s) / ('walk', (x, y)) steps."""

    def __init__(self, xy, plan, t0=0.0, speed=WALK_M_S):
        self.k = [(t0, xy[0], xy[1])]
        t, (x, y) = t0, xy
        for step, arg in plan:
            if step == "stand":
                t += arg
            else:
                d = float(np.hypot(arg[0] - x, arg[1] - y))
                t += d / speed
                x, y = arg
            self.k.append((t, x, y))
        self.k = np.array(self.k)

    @property
    def end(self):
        return self.k[-1, 0]

    def at(self, t):
        t = np.asarray(t, float)
        return np.interp(t, self.k[:, 0], self.k[:, 1]), np.interp(t, self.k[:, 0], self.k[:, 2])

    def present(self, t):
        return (np.asarray(t) >= self.k[0, 0]) & (np.asarray(t) <= self.k[-1, 0])


class Obj:
    def __init__(self, ids, cls, size, track, r_full=35.0, r_max=55.0, yaw_deg=0.0):
        """ids: [(t_from, id)] -- the tracker ID changes at t_from (a switch)."""
        self.ids, self.cls, self.size, self.track = ids, cls, size, track
        self.r_full, self.r_max, self.yaw = r_full, r_max, yaw_deg

    def id_at(self, t):
        out = np.full(np.shape(t), self.ids[0][1])
        for t_from, i in self.ids[1:]:
            out = np.where(np.asarray(t) >= t_from, i, out)
        return out

    def centre(self, t):
        x, y = self.track.at(t)
        return x, y, np.full(np.shape(x), self.size[2] / 2)


def p_3d(d, r_full, r_max):
    return np.clip(1 - (d - r_full) / (r_max - r_full), 0, 1)


# ------------------------------------------------------------------ object lists
def object_lists(objs, t_end, rng, switch_gap_s=0.3):
    rows = []
    for t in np.arange(0.0, t_end, 1 / LIDAR_HZ):            # 3D lists (empty lists written too)
        n = 0
        for o in objs:
            if not o.track.present(t):
                continue
            i = int(o.id_at(t))
            if any(abs(t - tf) < switch_gap_s and t >= tf for tf, _ in o.ids[1:]):
                continue                                      # the tracker drops the object briefly at a switch
            x, y, z = o.centre(t)
            d = np.linalg.norm(np.array([x, y, z]) - EYE)
            if rng.random() < p_3d(d, o.r_full, o.r_max):
                rows.append(dict(t_s=round(t, 6), source="3d", id=i, **{"class": o.cls}, x=x + rng.normal(0, 0.03),
                                 y=y + rng.normal(0, 0.03), z=z, length=o.size[0], width=o.size[1], height=o.size[2],
                                 yaw_deg=o.yaw))
                n += 1
        if n == 0:
            rows.append(dict(t_s=round(t, 6), source="3d"))
    in3d = {(r["t_s"], r.get("id")) for r in rows if r["source"] == "3d"}
    for t in np.arange(0.0, t_end, 1 / CAM_HZ):              # camera-only detections of objects not in 3D
        last3d = np.floor(t * LIDAR_HZ) / LIDAR_HZ
        n = 0
        for o in objs:
            if not o.track.present(t):
                continue
            i = int(o.id_at(t))
            if (round(last3d, 6), i) in in3d:
                continue
            x, y, z = o.centre(t)
            near = x - o.size[0] / 2 - CAM[0]
            if near <= 2 or abs(np.degrees(np.arctan2(y - CAM[1], x - CAM[0]))) > 30 or near > 120:
                continue
            est = near * (1 + rng.normal(0, 0.05))            # camera depth estimate
            r = est / near
            rows.append(dict(t_s=round(t, 6), source="camera", id=i, **{"class": o.cls},
                             x=CAM[0] + est + 0.15, y=CAM[1] + (y - CAM[1]) * r, z=CAM[2] + (z - CAM[2]) * r,
                             length=0.3, width=o.size[1] * r, height=o.size[2] * r, yaw_deg=0.0))
            n += 1
        if n == 0:
            rows.append(dict(t_s=round(t, 6), source="camera"))
    o = pd.DataFrame(rows)
    o["id"] = o["id"].astype("Int64")
    for c in ("x", "y", "z", "length", "width", "height", "yaw_deg"):
        o[c] = o[c].astype(float)
    return o.sort_values(["t_s", "source"], kind="stable").reset_index(drop=True)


# ------------------------------------------------------------------ gaze
def ar1(n, sd, rng, rho=0.9):
    """Noise correlated from sample to sample (as a DMS gaze estimate is), marginal SD sd."""
    e = rng.normal(0, sd * np.sqrt(1 - rho ** 2), n)
    x = np.empty(n)
    x[0] = rng.normal(0, sd)
    for k in range(1, n):
        x[k] = rho * x[k - 1] + e[k]
    return x


def gaze(t, aim, bias, noise, rng, glance_every_s=25.0, glance_s=1.5, blink_every_s=4.0):
    """aim(t) -> (x, y, z) of the cued point, or None (no cue). Returns the gaze table."""
    n = len(t)
    yaw, pitch = np.empty(n), np.empty(n)
    for k, tk in enumerate(t):
        p = aim(tk)
        v = np.asarray(p) - EYE
        yaw[k] = np.degrees(np.arctan2(v[1], v[0]))
        pitch[k] = np.degrees(np.arctan2(v[2], np.hypot(v[0], v[1])))
    yaw += bias[0] + ar1(n, noise[0], rng)
    pitch += bias[1] + ar1(n, noise[1], rng)
    away = (t % glance_every_s) > glance_every_s - glance_s     # glances at the instrument cluster
    yaw[away] = -12 + rng.normal(0, 0.5, away.sum())
    pitch[away] = -22 + rng.normal(0, 0.5, away.sum())
    valid = np.ones(n, int)
    count = np.zeros(n)
    blinks = np.arange(2.0, t[-1], blink_every_s) + rng.uniform(-0.8, 0.8, len(np.arange(2.0, t[-1], blink_every_s)))
    for tb in blinks:
        valid[(t >= tb) & (t < tb + 0.12)] = 0
        pitch[(t >= tb + 0.12) & (t < tb + 0.32)] -= 3.0        # the lid still hides the pupil's top
        count[t >= tb + 0.15] += 1
    eye = EYE + rng.normal(0, 0.001, (n, 3))
    g = pd.DataFrame(dict(t_s=np.round(t, 6), valid=valid, eye_x=eye[:, 0], eye_y=eye[:, 1], eye_z=eye[:, 2],
                          gaze_yaw_deg=yaw, gaze_pitch_deg=pitch, blink_count=count.astype(int)))
    g.loc[g.valid == 0, ["eye_x", "eye_y", "eye_z", "gaze_yaw_deg", "gaze_pitch_deg"]] = np.nan
    return g


def upper_body(o):
    def f(t):
        x, y = o.track.at(t)
        return x, y, 0.75 * o.size[2]
    return f


# ------------------------------------------------------------------ stand-in system
def stand_in_system(g, objects):
    """Nearest 3D box within SYSTEM_TOL_DEG, else nearest camera-only box, else none."""
    att = pd.array([pd.NA] * len(g), dtype="Int64")
    v = g[g.valid == 1]
    eye = v[["eye_x", "eye_y", "eye_z"]].values
    d = G.gaze_dir(v.gaze_yaw_deg.values, v.gaze_pitch_deg.values)
    best_id = np.full(len(v), -1)
    for src in ("3d", "camera"):
        o = objects[(objects.source == src) & objects.id.notna()]
        fr = np.sort(objects[objects.source == src].t_s.unique())
        i = np.searchsorted(fr, v.t_s.values, side="right") - 1
        ft = fr[np.clip(i, 0, None)]
        ok = (i >= 0) & (v.t_s.values - ft <= 0.1)
        m = pd.DataFrame(dict(k=np.arange(len(v))[ok], t_s=ft[ok])).merge(o, on="t_s")
        if m.empty:
            continue
        k = m.k.values
        c = m[["x", "y", "z"]].values.astype(float)
        a = G.angle_to_box(eye[k], d[k], c, m[["length", "width", "height"]].values.astype(float),
                           np.radians(m.yaw_deg.values.astype(float)))
        m["a"] = a
        m["dist"] = np.linalg.norm(c - eye[k], axis=1)
        m = m[m.a <= SYSTEM_TOL_DEG].sort_values(["k", "a", "dist"]).groupby("k").head(1)
        free = best_id[m.k.values] < 0
        best_id[m.k.values[free]] = m.id.values[free].astype(int)
    att[np.where(g.valid.values == 1)[0][best_id >= 0]] = best_id[best_id >= 0]
    g["attended_id"] = att
    return g


# ------------------------------------------------------------------ protocols
def walkaway(rng):
    stops = [8.0, 18.0, 28.0, 38.0]
    plan = []
    for k, x in enumerate(stops):
        plan += [("stand", 8.0)] + ([("walk", (stops[k + 1], 0.0))] if k + 1 < len(stops) else [])
    plan += [("walk", (48.0, 0.0)), ("stand", 6.0)]
    tr = Track((stops[0], 0.0), plan)
    t_switch = tr.k[4, 0] + 3.0                                  # an ID switch half-way through the 2nd walk
    ped = Obj([(0, 1), (t_switch, 11)], "pedestrian", PED, tr)
    parked = Obj([(0, 2)], "car", CAR, Track((14.0, -4.5), [("stand", tr.end)]), r_full=60, r_max=80)
    return [ped, parked], upper_body(ped), tr.end


def crossing(rng):
    seq = [(13, -3), (13, 3), (13, -3), (23, -3), (23, 3), (23, -3), (33, -3), (33, 3), (33, -3)]
    plan = []
    for k in range(len(seq)):
        plan.append(("stand", 6.0))
        if k + 1 < len(seq):
            plan.append(("walk", seq[k + 1]))
    tr = Track(seq[0], plan)
    ped = Obj([(0, 1)], "pedestrian", PED, tr)
    parked = Obj([(0, 2)], "car", CAR, Track((25.0, -4.5), [("stand", tr.end)]), r_full=60, r_max=80)
    return [ped, parked], upper_body(ped), tr.end


def two_pedestrians(rng, switch_s=3.0):
    depths = [13.0, 23.0, 33.0, 43.0]
    objs = []
    for side, y, pid in (("L", 2.5, 1), ("R", -2.5, 2)):
        plan = []
        for k in range(len(depths)):
            plan.append(("stand", 12.0))
            if k + 1 < len(depths):
                plan.append(("walk", (depths[k + 1], y)))
        objs.append(Obj([(0, pid)], "pedestrian", PED, Track((depths[0], y), plan)))
    L, R = objs
    cue = lambda t: L if int(t // switch_s) % 2 == 0 else R      # the driver is told to switch every switch_s
    aim = lambda t: upper_body(cue(t))(t)
    return objs, aim, L.track.end, cue


def car_approach(rng):
    objs = []
    t = 0.0
    for k in range(2):
        tr = Track((85.0, 0.0), [("walk", (8.0, 0.0)), ("stand", 0.5)], t0=t, speed=4.0)
        objs.append(Obj([(0, 10 + k)], "car", CAR, tr, r_full=58.0, r_max=63.0, yaw_deg=180.0))
        t = tr.end + 8.0
    far = Obj([(0, 30)], "car", CAR, Track((110.0, 6.0), [("stand", t)]), r_full=60, r_max=80)

    def aim(tt):
        for o in objs:
            if o.track.present(tt):
                x, y = o.track.at(tt)
                return x, y, 0.75 * o.size[2]
        return 40.0, 0.0, 1.2                                    # between approaches: looking down the road
    return objs + [far], aim, t - 4.0


PROTOCOLS = {"walkaway": walkaway, "crossing": crossing, "two_pedestrians": two_pedestrians, "car_approach": car_approach}

RECORDINGS = [
    # name, protocol, condition, yaw / pitch bias (deg), yaw / pitch noise (deg), seed
    ("SYN-WALK", "walkaway", "standard", (0.8, 0.4), (0.3, 0.5), 1),
    ("SYN-CROSS", "crossing", "standard", (-0.6, 0.3), (0.3, 0.5), 2),
    ("SYN-TWO", "two_pedestrians", "standard", (0.5, -0.3), (0.3, 0.5), 3),
    ("SYN-CAR", "car_approach", "standard", (0.4, 0.2), (0.3, 0.5), 4),
    ("SYN-CROSS-DEG", "crossing", "degraded", (2.5, 1.5), (1.2, 1.5), 5),
]


def make(name, protocol, condition, bias, noise, seed):
    rng = np.random.default_rng(seed)
    res = PROTOCOLS[protocol](rng)
    objs, aim, t_end = res[:3]
    t = np.arange(0.0, t_end, 1 / RATE)
    t = t + rng.uniform(-0.002, 0.002, len(t))                   # DMS timestamps jitter
    objects = object_lists(objs, t_end, rng)
    g = stand_in_system(gaze(t, aim, bias, noise, rng), objects)
    meta = dict(name=name, protocol=protocol, condition=condition,
                synthetic=dict(yaw_bias_deg=bias[0], pitch_bias_deg=bias[1], yaw_noise_deg=noise[0],
                               pitch_noise_deg=noise[1], seed=seed,
                               system="stand-in: nearest 3D box within 1.5 deg, else nearest camera-only box"))
    return g, objects, meta, res


def write(out, g, objects, meta):
    d = os.path.join(out, meta["name"])
    os.makedirs(d, exist_ok=True)
    g[["t_s", "valid", "eye_x", "eye_y", "eye_z", "gaze_yaw_deg", "gaze_pitch_deg", "attended_id", "blink_count"]].to_csv(
        os.path.join(d, "gaze.csv"), index=False, float_format="%.6f")
    objects.to_csv(os.path.join(d, "objects.csv"), index=False, float_format="%.4f")
    json.dump(meta, open(os.path.join(d, "recording.json"), "w"), indent=2)
    return d


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    for spec in RECORDINGS:
        g, o, meta, _ = make(*spec)
        print(write(out, g, o, meta), f"{len(g)} gaze samples, {o.id.notna().sum()} object rows")
