"""The per-sample evaluation table of one recording.

One row per valid gaze sample inside a unit, with:
  looked      which cued target the driver looked at (T, or L / R for two
              pedestrians; none = gaze beyond the look gate)
  input_state how the looked-at target reached the mapping: 3d / 2d
              (camera-only) / absent
  off_box     exact angular distance (deg) from the gaze ray to the target's box
              (0 = the ray hits it); err_total = angle to the box centre; dist
  other_off / other_dist   the best competing candidate (smallest off_box)
  att         what the system attended: target / other_target / other / none
  phase       standing / walking / approach;  unit;  band_dist (for bands)
  clean       not a saccade or blink sample

A standing target that drops out of the 3D list keeps its unit-median 3D box
(it stands still), or its camera-only box if it was never in 3D in that unit.
A moving target takes its camera-only box, or, when it is in neither list, its
3D box interpolated over gaps up to interp_max_s. The baselines see the same
candidates as the system: every 3D object and every camera-only detection.
"""
import numpy as np
import pandas as pd

from . import geom as G
from . import segment as S
from .config import params as _params
from .io import objects_at_samples
from .signals import sample_table

BOX_COLS = ["obj_x", "obj_y", "obj_z", "obj_sx", "obj_sy", "obj_sz", "obj_yaw_deg"]
VIEW_COLS = ["off_box", "err_total", "dist", "in3d", "repr", "band_dist", "input_state", "az0", "az1", "el0", "el1"]


def _exact(view):
    eye = view[["eye_x", "eye_y", "eye_z"]].values.astype(float)
    g = G.gaze_dir(view.gaze_yaw_deg.values.astype(float), view.gaze_pitch_deg.values.astype(float))
    c = view[["obj_x", "obj_y", "obj_z"]].values.astype(float)
    sz = view[["obj_sx", "obj_sy", "obj_sz"]].values.astype(float)
    return G.angle_to_box(eye, g, c, sz, np.radians(view.obj_yaw_deg.values.astype(float)))


def _extent(view):
    return G.angular_extent(view[["eye_x", "eye_y", "eye_z"]].values.astype(float),
                            view[["obj_x", "obj_y", "obj_z"]].values.astype(float),
                            view[["obj_sx", "obj_sy", "obj_sz"]].values.astype(float),
                            np.radians(view.obj_yaw_deg.values.astype(float)))


def _angles(view):
    """Angle from the gaze to the box centre (deg) and the eye-to-centre distance."""
    g = G.gaze_dir(view.gaze_yaw_deg.values, view.gaze_pitch_deg.values)
    v = view[["obj_x", "obj_y", "obj_z"]].values - view[["eye_x", "eye_y", "eye_z"]].values
    d = np.linalg.norm(v, axis=1)
    c = np.clip((g * v).sum(1) / np.maximum(d, 1e-9), -1, 1)
    return np.degrees(np.arccos(c)), d


def prepare(rec, P):
    """Internal tables: df (3D objects at valid samples), samples, head (eye and
    gaze per valid sample), cam (camera-only objects at valid samples)."""
    samples = sample_table(rec, P)
    g = rec.gaze
    head = g.loc[g.valid == 1, ["t_s", "eye_x", "eye_y", "eye_z", "gaze_yaw_deg", "gaze_pitch_deg"]]
    df = objects_at_samples(rec, "3d", P).join(head, on="sample")
    cam = objects_at_samples(rec, "camera", P)
    return df, samples, head, cam


def candidates(df, head, cam):
    """Every candidate object of every valid sample: 3D objects and camera-only
    detections, with off_box (deg), dist_m and angular extent."""
    o3 = df[["sample", "obj_id", "obj_class"] + BOX_COLS].assign(repr="3d")
    o2 = cam[["sample", "obj_id", "obj_class"] + BOX_COLS].assign(repr="2d")
    o = pd.concat([o3, o2], ignore_index=True)
    o["obj_id"] = o.obj_id.astype(int)
    o = o.join(head, on="sample")
    o["off_box"] = _exact(o)
    v = o[["obj_x", "obj_y", "obj_z"]].values - o[["eye_x", "eye_y", "eye_z"]].values
    o["dist_m"] = np.linalg.norm(v, axis=1)
    o["az0"], o["az1"], o["el0"], o["el1"] = _extent(o)
    return o


def same_as_target(objs, s, P):
    """(sample, obj_id) of camera-only candidates that are the target itself or
    hidden behind it: at least dup_cover of their angular box inside the target's."""
    c2 = objs[objs["repr"] == "2d"].join(s[["az0", "az1", "el0", "el1"]], on="sample", rsuffix="_t", how="inner")
    cov = G.coverage((c2.az0.values, c2.az1.values, c2.el0.values, c2.el1.values),
                     (c2.az0_t.values, c2.az1_t.values, c2.el0_t.values, c2.el1_t.values))
    d = c2[cov >= P["dup_cover"]]
    return set(zip(d["sample"].astype(int), d.obj_id.astype(int)))


def best_other(objs, exclude_ids, index, exclude_pairs=frozenset()):
    """Per sample: the candidate (not excluded) with the smallest (off_box, distance)."""
    o = objs[~objs.obj_id.isin(list(exclude_ids))]
    if exclude_pairs:
        key = pd.Series(list(zip(o["sample"].astype(int), o.obj_id.astype(int))), index=o.index)
        o = o[~key.isin(exclude_pairs)]
    o = o.sort_values(["sample", "off_box", "dist_m"]).groupby("sample").head(1).set_index("sample")
    out = pd.DataFrame(index=index)
    out["other_off"] = o.off_box.reindex(index).fillna(np.inf)
    out["other_dist"] = o.dist_m.reindex(index).fillna(np.inf)
    out["other_id"] = o.obj_id.reindex(index)
    return out


def target_view(samples, head, ids, units, cands, P, static=True):
    """Per valid sample inside a unit: the target's box and the gaze's angular
    distance to it. static: 3D box, else the unit-median 3D box, else camera-only
    box; band_dist = unit-median 3D distance. moving: 3D box, else camera-only,
    else 3D interpolated over gaps <= interp_max_s; band_dist = 3D distance
    interpolated in time within the 3D span, else the camera's distance."""
    ids = list(ids)
    s = samples[samples.valid == 1][["t_s", "gaze_yaw_deg", "gaze_pitch_deg", "attended_id", "saccade", "blink"]].copy()
    s = s.join(head[["eye_x", "eye_y", "eye_z"]])
    s["unit"] = None
    for _, u in units.iterrows():
        s.loc[(s.t_s >= u.start_s) & (s.t_s <= u.end_s), "unit"] = u.unit
    s = s[s.unit.notna()].copy()
    t = cands[cands.obj_id.isin(ids) & cands["sample"].isin(s.index)].copy()
    first_seen = t.groupby("obj_id")["sample"].min()
    t["seg"] = -t.obj_id.map(first_seen)                    # several IDs at once -> the most recent one
    pick = lambda q: q.sort_values(["sample", "seg"]).groupby("sample").head(1).set_index("sample")
    t3, t2 = pick(t[t["repr"] == "3d"]), pick(t[t["repr"] == "2d"])
    for c in BOX_COLS:
        s[c] = t3[c].reindex(s.index)
    s["repr"] = np.where(s.obj_x.notna(), "3d", None)
    s["in3d"] = s["repr"] == "3d"
    has2d = t2.index.intersection(s.index)
    s["input_state"] = np.where(s.in3d, "3d", np.where(s.index.isin(has2d), "2d", "absent"))
    s["band_dist"] = np.nan
    if static:
        for _, u in units.iterrows():
            m = s.unit == u.unit
            have = m & s.in3d
            miss = m & s.obj_x.isna()
            if have.any():
                d3 = np.linalg.norm(s.loc[have, ["obj_x", "obj_y", "obj_z"]].values
                                    - s.loc[have, ["eye_x", "eye_y", "eye_z"]].values, axis=1)
                s.loc[m, "band_dist"] = float(np.median(d3))
                if miss.any():
                    med = s.loc[have, BOX_COLS].median()
                    for c in BOX_COLS:
                        s.loc[miss, c] = med[c]
                    s.loc[miss, "repr"] = "fallback"
    miss = s.obj_x.isna()
    for c in BOX_COLS:
        s.loc[miss, c] = t2[c].reindex(s.index)[miss]
    s.loc[miss & s.obj_x.notna(), "repr"] = "2d"
    if not static:
        for _, g in s.groupby("unit"):
            k = g["repr"].eq("3d").values
            gap = g.obj_x.isna().values
            if not k.any() or not gap.any():
                continue
            tt, t3_ = g.t_s.values, g.t_s.values[k]
            prev = np.searchsorted(t3_, tt, side="right") - 1
            nxt = np.clip(prev + 1, 0, len(t3_) - 1)
            span = t3_[nxt] - t3_[np.clip(prev, 0, None)]
            ok = gap & (prev >= 0) & (prev + 1 < len(t3_)) & (span <= P["interp_max_s"])
            if ok.any():
                for c in BOX_COLS:
                    s.loc[g.index[ok], c] = np.interp(tt[ok], t3_, g[c].values[k])
                s.loc[g.index[ok], "repr"] = "interp"
    s = s[s.obj_x.notna()].copy()
    s["off_box"] = _exact(s)
    s["err_total"], s["dist"] = _angles(s)
    s["az0"], s["az1"], s["el0"], s["el1"] = _extent(s)
    if not static:
        s["band_dist"] = s.dist
        for _, g in s.groupby("unit"):
            k = g.in3d.values
            if not k.any():
                continue
            t3_ = g.t_s.values[k]
            inside = (g.t_s.values >= t3_.min()) & (g.t_s.values <= t3_.max())
            s.loc[g.index[inside], "band_dist"] = np.interp(g.t_s.values[inside], t3_, g.dist.values[k])
    return s


def _views(samples, head, ids, stand, objs, P, walking=True):
    v = [target_view(samples, head, ids, stand, objs, P).assign(phase="standing")]
    w = S.walk_units(stand, P)
    if walking and len(w):
        wv = target_view(samples, head, ids, w, objs, P, static=False).assign(phase="walking")
        v.append(wv[~wv.index.isin(v[0].index)])        # a sample on a unit boundary belongs to the standing unit
    return pd.concat(v).sort_index()


def _att_dup(s, dups):
    """True where the system attended a camera-only duplicate of the target."""
    return np.array([pd.notna(a) and (int(i), int(a)) in dups for i, a in zip(s.index, s.attended_id)])


def _single_target(s, objs, chain, P):
    s["looked"] = np.where(s.err_total < P["look_gate_deg"], "T", "none")
    dups = same_as_target(objs, s, P)
    s = s.join(best_other(objs, chain, s.index, dups))
    s["other_is_target2"] = False
    a = s.attended_id
    s["att"] = np.where(a.isin(chain) | _att_dup(s, dups), "target", np.where(a.notna(), "other", "none"))
    return s


def _target_chain(df, rec, P, cls="pedestrian"):
    if "target_ids" in rec.meta:
        return [int(i) for i in rec.meta["target_ids"]], ["target IDs given in recording.json"]
    return S.stitch_target(df, S.infer_target(df, cls), P)


def build(rec, params=None):
    """The per-sample table of one recording and a dict with the target IDs,
    the units and notes."""
    P = _params(params)
    df, samples, head, cam = prepare(rec, P)
    objs = candidates(df, head, cam)
    notes = [f"blinks from: {samples.attrs['blink_source']}"]
    extra = {}
    if rec.protocol in ("walkaway", "crossing"):
        chain, n = _target_chain(df, rec, P)
        notes += n
        tr = S.target_track(df, chain)
        stops = S.detect_stops(tr, P)
        if rec.protocol == "walkaway":
            units = pd.DataFrame(dict(unit=[f"{r.dist_m:.0f} m #{int(r.stop)}" for _, r in stops.iterrows()],
                                      start_s=stops.start_s, end_s=stops.end_s))
        else:
            pos = S.positions_of(tr, stops, P)
            units = pd.DataFrame(dict(unit=[f"{r.position} #{int(r['repeat'])}" for _, r in pos.iterrows()],
                                      start_s=pos.start_s, end_s=pos.end_s))
            extra["positions"] = pos
        s = _views(samples, head, chain, units, objs, P)
        s = _single_target(s, objs, chain, P)
        targets = chain
    elif rec.protocol == "two_pedestrians":
        if "target_ids" in rec.meta:
            ids = {"L": [int(i) for i in rec.meta["target_ids"]["left"]],
                   "R": [int(i) for i in rec.meta["target_ids"]["right"]]}
        else:
            ids = S.lr_targets(df, P)
        st = S.lr_stations(S.target_track(df, ids["L"]), S.target_track(df, ids["R"]), P)
        units = pd.DataFrame(dict(unit=st.label.values, start_s=st.start_s.values, end_s=st.end_s.values))
        vL = _views(samples, head, ids["L"], units, objs, P)
        vR = _views(samples, head, ids["R"], units, objs, P)
        both = vL.index.union(vR.index)
        base = vL.reindex(both).combine_first(vR.reindex(both))
        vL, vR = vL.reindex(both), vR.reindex(both)
        # a pedestrian never in 3D at a station takes the other one's distance for the band
        bL, bR = vL.band_dist.copy(), vR.band_dist.copy()
        vL["band_dist"], vR["band_dist"] = bL.fillna(bR), bR.fillna(bL)
        for v in (vL, vR):
            for c in ["off_box", "err_total", "dist"]:
                v[c] = v[c].fillna(np.inf)          # no box at this sample: cannot be the looked-at one
            for c in base.columns:
                if c not in tuple(VIEW_COLS) + tuple(BOX_COLS):
                    v[c] = base[c]
            v["in3d"] = v["in3d"].fillna(False).astype(bool)
        lookL = (vL.err_total < P["look_gate_deg"]) & (vL.err_total <= vR.err_total)
        lookR = (vR.err_total < P["look_gate_deg"]) & (vR.err_total < vL.err_total)
        s = vL.copy()
        for c in VIEW_COLS + BOX_COLS:
            s[c] = np.where(lookR, vR[c], vL[c])
        s["looked"] = np.where(lookL, "L", np.where(lookR, "R", "none"))
        other_ped_off = np.where(lookR, vL.off_box, vR.off_box)
        other_ped_dist = np.where(lookR, vL.dist, vR.dist)
        allped = set(ids["L"]) | set(ids["R"])
        dups = same_as_target(objs, s[s.looked != "none"], P)
        oth = best_other(objs, allped, s.index, dups)
        use_ped = (other_ped_off < oth.other_off) | ((other_ped_off == oth.other_off) & (other_ped_dist <= oth.other_dist))
        s["other_off"] = np.where(use_ped, other_ped_off, oth.other_off)
        s["other_dist"] = np.where(use_ped, other_ped_dist, oth.other_dist)
        s["other_is_target2"] = use_ped
        s["other_id"] = np.where(use_ped, np.nan, oth.other_id)
        a = s.attended_id
        mine = np.where(lookR, a.isin(ids["R"]), a.isin(ids["L"])) | _att_dup(s, dups)
        theirs = np.where(lookR, a.isin(ids["L"]), a.isin(ids["R"]))
        s["att"] = np.where(mine, "target", np.where(theirs, "other_target", np.where(a.notna(), "other", "none")))
        targets = ids
        extra["stations"] = st
    elif rec.protocol == "car_approach":
        if "target_ids" in rec.meta:
            raise ValueError("car_approach: target_ids override is not supported; the car is found from the ego lane")
        chain, units = S.car_units(df, rec.objects, rec.rate_hz, P)
        s = target_view(samples, head, chain, units, objs, P, static=False).assign(phase="approach")
        s = _single_target(s, objs, chain, P)
        targets = chain
    else:
        raise ValueError(f"unknown protocol {rec.protocol}")
    s["recording"], s["protocol"], s["condition"] = rec.name, rec.protocol, rec.condition
    s["clean"] = ~s.saccade.fillna(False).astype(bool) & ~s.blink.fillna(False).astype(bool)
    s.attrs["rate_hz"] = rec.rate_hz
    return s, dict(targets=targets, units=units, notes=notes, objs=objs, samples=samples, head=head, **extra)


def looking(s):
    """Clean samples with the gaze inside the look gate of a cued target."""
    return s[s.clean & (s.looked != "none")].copy()


def band_of(dist, P):
    b = P["bands_m"]
    return pd.cut(dist, b, right=False, labels=[f"{x}-{y} m" for x, y in zip(b[:-1], b[1:])])
