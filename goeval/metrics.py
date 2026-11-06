"""Metrics, each kept separate by layer (see docs/metrics.md).

gaze_input      the gaze estimate against the cued target: yaw bias and yaw /
                pitch precision per unit (gaze input table)
mapping         % of looking samples mapped to the looked-at target by the
                system, the nearest-box cone and the centre ray, by distance band
                and phase, with how the target reached the mapping (mapping table)
sweep           the cone's score against its tolerance
crossings       the target walking across the lane: mapping and along-track error
car_phases      the approaching car: camera-only lead-in, in 3D beyond the range
                where the system attends it, in 3D within it
competitors     the competitor subset (another candidate within the cone
                tolerance) split into episodes, with what each rule chose
robustness      look gate, saccades kept, a 3D-first cone
"""
import numpy as np
import pandas as pd

from . import baselines as BL
from . import segment as S
from . import table as T
from .config import params as _params


def pct(x):
    return 100.0 * float(np.mean(x)) if len(x) else np.nan


def mad_sd(x):
    x = np.asarray(x, float)
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if len(x) else np.nan


def _sec(n, rate):
    return round(n / rate, 1)


# ---------------------------------------------------------------- gaze input
def angle_errors(lk, P):
    """Yaw error (gaze minus the bearing of the box centre) and pitch error
    (against upper_body_frac of the box height), deg."""
    v = lk[["obj_x", "obj_y"]].values - lk[["eye_x", "eye_y"]].values
    bearing = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    z_up = lk.obj_z - lk.obj_sz / 2 + P["upper_body_frac"] * lk.obj_sz - lk.eye_z
    elev = np.degrees(np.arctan2(z_up, np.hypot(v[:, 0], v[:, 1])))
    yaw = (lk.gaze_yaw_deg - bearing + 180) % 360 - 180
    return yaw, lk.gaze_pitch_deg - elev


def gaze_input(s, P):
    """Per unit (stop / repeat / station x pedestrian) on clean looking samples
    with the target in 3D while standing, and the recording summary."""
    rate = s.attrs["rate_hz"]
    prot = s.protocol.iloc[0]
    lk = T.looking(s)
    lk = lk[(lk["repr"] == "3d") & (lk.phase == "standing")].copy()
    lk["yaw_err"], lk["pitch_err"] = angle_errors(lk, P)
    key = lk.unit + (" " + lk.looked if prot == "two_pedestrians" else "")
    n_min = int(round(P["min_unit_s"] * rate))
    units = []
    for u, g in lk.groupby(key):
        if len(g) < n_min:
            continue
        look_pct = 100 * (s[s.unit == u].looked != "none").mean() if prot == "crossing" else np.nan
        units.append(dict(recording=s.recording.iloc[0], unit=u, seconds=_sec(len(g), rate), looking_pct=look_pct,
                          yaw_bias=g.yaw_err.median(), yaw_prec=mad_sd(g.yaw_err), pitch_prec=mad_sd(g.pitch_err),
                          dist_m=g.band_dist.median()))
    U = pd.DataFrame(units)
    if U.empty:
        return U, None
    k = U[~(U.looking_pct < P["repeat_min_looking_pct"])]
    summary = dict(recording=s.recording.iloc[0], condition=s.condition.iloc[0], units=len(k),
                   yaw_abs_bias_median=k.yaw_bias.abs().median(), yaw_abs_bias_max=k.yaw_bias.abs().max(),
                   yaw_precision_median=k.yaw_prec.median(), pitch_precision_median=k.pitch_prec.median(),
                   units_left_out=int((~U.index.isin(k.index)).sum()))
    return U, summary


# ---------------------------------------------------------------- mapping, sweep
def banded(s, P):
    """Looking samples with their distance band (all distances; band NaN outside the bands)."""
    lk = T.looking(s)
    lk["band"] = T.band_of(lk.band_dist.fillna(lk.dist), P)
    return lk


def mapping_scores(s, P):
    """Long table: per phase (main = all phases) and band (all = 5-55 m pooled)."""
    rate = s.attrs["rate_hz"]
    tol = P["cone_tol_deg"]
    lk = banded(s, P)
    lk = lk[lk.band.notna()]
    two = s.protocol.iloc[0] == "two_pedestrians"
    sel = {"main": lk}
    for ph in lk.phase.unique():
        sel[ph] = lk[lk.phase == ph]
    rows = []
    for phase, q in sel.items():
        if q.empty:
            continue
        c0, c2 = BL.cone(q, 0.0), BL.cone(q, tol)
        groups = [("all", q.index)] + [(str(b), g.index) for b, g in q.groupby("band", observed=True)]
        for band, ix in groups:
            g = q.loc[ix]
            comp = g.other_off <= tol
            rows.append(dict(recording=s.recording.iloc[0], condition=s.condition.iloc[0], phase=phase, band=band,
                             seconds=_sec(len(g), rate), units=g.unit.nunique(),
                             target_in_3d_pct=pct(g.input_state == "3d"), target_camera_only_pct=pct(g.input_state == "2d"),
                             target_absent_pct=pct(g.input_state == "absent"),
                             system=pct(g.att == "target"), cone=pct(c2.loc[ix] == "target"),
                             centre_ray=pct(c0.loc[ix] == "target"),
                             system_other_target=pct(g.att == "other_target") if two else np.nan,
                             cone_other_target=pct(c2.loc[ix] == "other_target") if two else np.nan,
                             system_other_object=pct(g.att == "other"), system_none=pct(g.att == "none"),
                             competitor_pct=pct(comp),
                             system_with_competitor=pct(g.att[comp] == "target"),
                             cone_with_competitor=pct(c2.loc[ix][comp] == "target")))
    return pd.DataFrame(rows)


def per_unit(s, P):
    rate = s.attrs["rate_hz"]
    lk = banded(s, P)
    lk = lk[lk.band.notna()]
    rows = []
    for u, g in lk.groupby("unit"):
        rows.append(dict(recording=s.recording.iloc[0], unit=u, phase=g.phase.iloc[0], seconds=_sec(len(g), rate),
                         dist_m=g.dist.median(), system=pct(g.att == "target"),
                         cone=pct(BL.cone(g, P["cone_tol_deg"]) == "target"),
                         centre_ray=pct(BL.cone(g, 0.0) == "target")))
    return pd.DataFrame(rows)


def sweep(s, P):
    rate = s.attrs["rate_hz"]
    lk = banded(s, P)
    lk = lk[lk.band.notna()]
    tols = np.round(np.arange(0.0, P["sweep_max_deg"] + 1e-9, P["sweep_step_deg"]), 3)
    rows, by_band = [], []
    for tol in tols:
        c = BL.cone(lk, tol)
        rows.append(dict(recording=s.recording.iloc[0], condition=s.condition.iloc[0], tol_deg=tol,
                         cone_target=pct(c == "target"), cone_other=pct((c != "target") & (c != "none")),
                         cone_none=pct(c == "none"), system_target=pct(lk.att == "target"),
                         gaze_on_or_within=pct(lk.off_box <= tol + 1e-9)))
        for b, g in lk.groupby("band", observed=True):
            by_band.append(dict(recording=s.recording.iloc[0], band=str(b), tol_deg=tol, seconds=_sec(len(g), rate),
                                cone_target=pct(c.loc[g.index] == "target"), system_target=pct(g.att == "target")))
    q = np.quantile(lk.off_box, [0.5, 0.9, 0.95, 0.99]) if len(lk) else [np.nan] * 4
    dist = dict(recording=s.recording.iloc[0], offbox_p50=q[0], offbox_p90=q[1], offbox_p95=q[2], offbox_p99=q[3],
                on_box_pct=pct(lk.off_box == 0), other_within_4deg_pct=pct(lk.other_off <= 4.0))
    return pd.DataFrame(rows), pd.DataFrame(by_band), dist


# ---------------------------------------------------------------- crossings
def crossing_table(rec, s, info, P):
    """Per-sample table of the crossings: walks between a left and a right position at one depth."""
    pos = info["positions"]
    cr = S.crossings_of(pos, P)
    if cr.empty:
        return None, cr
    dep = pos.set_index("position").depth_m.groupby(level=0).first()
    cr = cr[(dep.loc[cr.from_pos].values - dep.loc[cr.to_pos].values) == 0].copy()
    cr["direction"] = np.where(cr.dy_m < 0, "L->R", "R->L")             # y + = left
    cr["unit"] = [f"{d:.0f} m {k} #{int(c)}" for d, k, c in zip(cr.depth_m, cr.direction, cr.crossing)]
    samples, head = info["samples"], info["head"]
    objs, chain = info["objs"], info["targets"]
    c = T.target_view(samples, head, chain, cr[["unit", "start_s", "end_s"]], objs, P, static=False)
    c = T._single_target(c, objs, chain, P)
    c["clean"] = ~c.saccade.fillna(False).astype(bool) & ~c.blink.fillna(False).astype(bool)
    v = c[["obj_x", "obj_y"]].values - c[["eye_x", "eye_y"]].values
    c["bearing"] = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    c["yaw_err"] = (c.gaze_yaw_deg - c.bearing + 180) % 360 - 180
    c["lat_speed"] = np.nan
    B = P["lat_speed_bin_s"]
    for u, g in c.groupby("unit"):
        b = (g.t_s // B).astype(int)
        yb = g.groupby(b).obj_y.median()
        yb = yb.reindex(range(yb.index.min(), yb.index.max() + 1)).interpolate(limit_area="inside")
        ys = yb.rolling(P["lat_speed_smooth_bins"], center=True, min_periods=2).median()
        sp = pd.Series(np.gradient(ys.values, B), index=ys.index).abs()
        c.loc[g.index, "lat_speed"] = sp.reindex(b.values).values
    c["moving"] = c.lat_speed >= P["walk_min_lat_speed_m_s"]
    dsign = c.unit.map(cr.set_index("unit").direction.map({"L->R": -1.0, "R->L": 1.0}))
    c["along_err"] = c.yaw_err * dsign                                  # + = gaze ahead of the pedestrian
    c = c.join(cr.set_index("unit")[["depth_m", "direction"]], on="unit")
    c["recording"], c["condition"] = rec.name, rec.condition
    c.attrs["rate_hz"] = rec.rate_hz
    return c, cr


def crossing_summary(c, keys, P):
    rate = c.attrs["rate_hz"]
    lk = c[c.clean & (c.looked != "none")]
    rows = []
    tol = P["cone_tol_deg"]
    for k, g in lk.groupby(keys):
        k = k if isinstance(k, tuple) else (k,)
        comp = g.other_off <= tol
        rows.append(dict(zip(keys, k), crossings=g.unit.nunique(), seconds=_sec(len(g), rate),
                         target_in_3d_pct=pct(g.input_state == "3d"), target_camera_only_pct=pct(g.input_state == "2d"),
                         system=pct(g.att == "target"), cone=pct(BL.cone(g, tol) == "target"),
                         centre_ray=pct(BL.cone(g, 0.0) == "target"), system_other=pct(g.att == "other"),
                         system_none=pct(g.att == "none"),
                         along_track_err_median_deg=g[g.moving].along_err.median(),
                         lateral_speed_median_m_s=g.lat_speed.median(),
                         competitor_pct=pct(comp), system_with_competitor=pct(g.att[comp] == "target"),
                         cone_with_competitor=pct(BL.cone(g, tol)[comp] == "target")))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- car
def car_phases(s, P):
    rate = s.attrs["rate_hz"]
    lk = T.looking(s)
    rows = []
    for u, g in lk.groupby("unit"):
        d3 = g[g.input_state == "3d"]
        if d3.empty:
            continue
        start_att = d3[d3.att == "target"].band_dist.max()
        lead = g[(g.input_state == "2d") & (g.t_s < d3.t_s.min())]
        beyond = d3[d3.band_dist > start_att] if pd.notna(start_att) else d3
        within = d3[d3.band_dist <= start_att] if pd.notna(start_att) else d3.iloc[:0]
        rows.append(dict(recording=s.recording.iloc[0], condition=s.condition.iloc[0], approach=u,
                         enters_3d_at_m=d3.band_dist.max(), mapped_in_3d_from_m=start_att,
                         lead_in_camera_only_s=len(lead) / rate,
                         lead_in_attended_pct=pct(lead.att == "target"),
                         in3d_beyond_s=len(beyond) / rate, in3d_beyond_attended_pct=pct(beyond.att == "target"),
                         in3d_beyond_cone_pct=pct(BL.cone(beyond, P["cone_tol_deg"]) == "target") if len(beyond) else np.nan,
                         in3d_within_s=len(within) / rate, in3d_within_attended_pct=pct(within.att == "target")))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- competitors
def others_by_source(lk, info, P):
    """Per looking sample of lk, the nearest 3D and the nearest camera-only candidate
    other than the looked-at target (with two pedestrians, the other pedestrian is
    a candidate): two frames as table.best_other, aligned with lk.index."""
    objs, tg = info["objs"], info["targets"]
    o3s, o2s = [], []
    groups = ({"L": lk[lk.looked == "L"], "R": lk[lk.looked == "R"]} if isinstance(tg, dict) else {"T": lk})
    for side, g in groups.items():
        if g.empty:
            continue
        mine = tg[side] if isinstance(tg, dict) else tg
        dups = T.same_as_target(objs, g, P)
        o3s.append(T.best_other(objs[objs["repr"] == "3d"], mine, g.index, dups))
        o2s.append(T.best_other(objs[objs["repr"] == "2d"], mine, g.index, dups))
    if not o3s:
        empty = T.best_other(objs.iloc[:0], [], lk.index)
        return empty, empty
    return pd.concat(o3s).reindex(lk.index), pd.concat(o2s).reindex(lk.index)


def cone_3d_first_of(lk, info, P):
    """The 3D-first cone on looking samples lk; its competitors are every candidate
    except the looked-at target (with two pedestrians, the other one competes)."""
    o3, o2 = others_by_source(lk, info, P)
    return BL.cone_3d_first(lk, o3, o2, P["cone_tol_deg"])


def _box_gap(lk):
    """Angular gap (deg) between the target's box and the competitor's (comp_az0 ..
    comp_el1), as seen from the eye; 0 = the two boxes overlap in view."""
    gaz = np.maximum(0.0, np.maximum(lk.comp_az0 - lk.az1, lk.az0 - lk.comp_az1))
    gel = np.maximum(0.0, np.maximum(lk.comp_el0 - lk.el1, lk.el0 - lk.comp_el1))
    return np.hypot(gaz, gel)


def _mode(x):
    m = x.dropna().mode()
    return m.iloc[0] if len(m) else np.nan


def competitor_episodes(rec, s, info, P):
    """The competitor subset, split into episodes: looking samples (5-55 m) with
    another candidate within cone_tol_deg of the gaze, grouped by unit (and
    looked-at pedestrian) and by the competitor's source, and split where samples
    are more than episode_gap_s apart.

    A sample's competitor is the nearest other 3D object if one is within the
    tolerance (source 3D, or other target for the other pedestrian), else the
    nearest other candidate (camera-only, or the other pedestrian's box). Each
    episode names its main competitor and gives what the system and each
    reference rule chose."""
    rate = rec.rate_hz
    tol = P["cone_tol_deg"]
    lk = banded(s, P)
    lk = lk[lk.band.notna()]
    if lk.empty:
        return pd.DataFrame()
    o3, o2 = others_by_source(lk, info, P)
    c3 = BL.cone_3d_first(lk, o3, o2, tol)
    comp = (lk.other_off <= tol).values
    lk, o3 = lk[comp].copy(), o3[comp]
    if lk.empty:
        return pd.DataFrame()
    lk["c3"], lk["c2"], lk["c0"] = c3[comp], BL.cone(lk, tol), BL.cone(lk, 0.0)
    has3 = (o3.other_off <= tol).values
    tg = info["targets"]
    if isinstance(tg, dict):
        other_ids = lk.looked.map({"L": set(tg["R"]), "R": set(tg["L"])})
        ped3 = np.array([i in ids if pd.notna(i) else False for i, ids in zip(o3.other_id, other_ids)])
    else:
        ped3 = np.zeros(len(lk), bool)
    lk["source"] = np.where(has3, np.where(ped3, "other target", "3D"),
                            np.where(lk.other_is_target2, "other target", "camera-only"))
    for c in ["off", "dist", "id", "class"] + T.EXTENT_COLS:
        lk[f"comp_{c}"] = np.where(has3, o3[f"other_{c}"], lk[f"other_{c}"])
    lk.loc[lk.source == "other target", "comp_id"] = np.nan
    oid = pd.to_numeric(lk.comp_id).astype("Int64").astype(str)
    lk["comp_key"] = np.where(lk.source == "other target", "other target", oid + " " + lk.source)
    lk["box_gap"] = _box_gap(lk.astype({c: float for c in ["comp_az0", "comp_az1", "comp_el0", "comp_el1"]}))
    two = s.protocol.iloc[0] == "two_pedestrians"
    lk["ep_unit"] = lk.unit + (" " + lk.looked if two else "")
    lk = lk.sort_values("t_s")
    new = ((lk.ep_unit != lk.ep_unit.shift()) | (lk.source != lk.source.shift())
           | (lk.t_s.diff() > P["episode_gap_s"] + 1e-6))
    lk["episode"] = new.cumsum()
    rows = []
    for _, g in lk.groupby("episode"):
        key = g.comp_key.value_counts().index[0]
        m = g[g.comp_key == key]
        rows.append(dict(
            recording=rec.name, condition=rec.condition, unit=g.ep_unit.iloc[0], phase=_mode(g.phase),
            start_s=round(float(g.t_s.min()), 2), samples=len(g), seconds=round(len(g) / rate, 2),
            target_dist_m=round(float(g.band_dist.fillna(g.dist).median()), 1), target_input=_mode(g.input_state),
            competitor_id=m.comp_id.iloc[0], competitor_source=m.source.iloc[0],
            competitor_class=m.comp_class.iloc[0], competitor_share_pct=pct(g.comp_key == key),
            competitors=g.comp_key.nunique(), competitor_dist_m=round(float(m.comp_dist.astype(float).median()), 1),
            box_gap_deg=round(float(m.box_gap.median()), 2),
            gaze_to_target_deg=round(float(g.off_box.median()), 2),
            gaze_to_competitor_deg=round(float(g.comp_off.astype(float).median()), 2),
            system=pct(g.att == "target"), system_other_object=pct(g.att.isin(["other", "other_target"])),
            system_none=pct(g.att == "none"), cone=pct(g.c2 == "target"),
            cone_3d_first=pct(g.c3 == "target"), centre_ray=pct(g.c0 == "target")))
    return pd.DataFrame(rows)


EPISODE_SCORES = ["system", "cone", "cone_3d_first", "centre_ray", "system_other_object", "system_none"]


def competitor_summary(E):
    """Per recording: all competitor samples, then by the competitor's source
    (3D, camera-only, other target); scores weighted by samples."""
    if E is None or not len(E):
        return pd.DataFrame()
    rows = []
    for (rec, cond), g in E.groupby(["recording", "condition"], sort=False):
        parts = [("all", g)] + [(src, q) for src, q in g.groupby("competitor_source")]
        for src, q in parts:
            w = q.samples.values
            row = dict(recording=rec, condition=cond, competitor_source=src, episodes=len(q),
                       samples=int(w.sum()), seconds=round(float(q.seconds.sum()), 2),
                       episodes_over_1s=int((q.seconds >= 1.0).sum()))
            for c in EPISODE_SCORES:
                row[c] = float(np.average(q[c].values, weights=w))
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- robustness
def robustness(rec, s, info, P):
    """Does the result hinge on the analysis choices? Look gate, saccades kept,
    unscored time, and a 3D-first cone (3D candidates before camera-only)."""
    rate = rec.rate_hz
    name = rec.name
    out = {}
    # look gate: the whole table rebuilt with each gate
    rows = []
    for gate in P["gate_sensitivity_deg"]:
        if gate == P["look_gate_deg"]:
            sg = s
        else:
            sg, _ = T.build(rec, dict(P, look_gate_deg=gate))
        lk = banded(sg, P)
        lk = lk[lk.band.notna()]
        rows.append(dict(recording=name, gate_deg=gate, seconds=_sec(len(lk), rate), system=pct(lk.att == "target"),
                         cone=pct(BL.cone(lk, P["cone_tol_deg"]) == "target")))
    out["gate"] = rows
    # saccades kept (blinks still removed)
    lk = banded(s, P)
    lk = lk[lk.band.notna()]
    q = s[~s.blink.fillna(False).astype(bool) & (s.looked != "none")].copy()
    q = q[T.band_of(q.band_dist.fillna(q.dist), P).notna()]
    out["saccades"] = [dict(recording=name, seconds_clean=_sec(len(lk), rate), system_clean=pct(lk.att == "target"),
                            cone_clean=pct(BL.cone(lk, P["cone_tol_deg"]) == "target"),
                            seconds_with_saccades=_sec(len(q), rate), system_with_saccades=pct(q.att == "target"),
                            cone_with_saccades=pct(BL.cone(q, P["cone_tol_deg"]) == "target"))]
    # unscored: clean valid samples inside the units with no box or beyond the gate
    samples = info["samples"]
    spans = pd.concat([s.groupby("unit").t_s.min(), s.groupby("unit").t_s.max()], axis=1)
    sm = samples[(samples.valid == 1) & ~samples.saccade & ~samples.blink]
    inside = np.zeros(len(sm), bool)
    for _, (a, b) in spans.iterrows():
        inside |= (sm.t_s.values >= a) & (sm.t_s.values <= b)
    n_in = max(int(inside.sum()), 1)
    with_box = s[s.clean]
    out["unscored"] = [dict(recording=name, clean_in_units_s=_sec(n_in, rate),
                            no_box_pct=100 * (1 - len(with_box) / n_in),
                            beyond_gate_pct=100 * (with_box.looked == "none").sum() / n_in,
                            scored_pct=100 * len(T.looking(s)) / n_in)]
    # 3D-first cone: competitors = every candidate except the looked-at target;
    # also on the samples with another 3D object within the tolerance, where it can go wrong
    tol = P["cone_tol_deg"]
    o3, o2 = others_by_source(lk, info, P)
    c3 = BL.cone_3d_first(lk, o3, o2, tol)
    c2 = BL.cone(lk, tol)
    comp = lk.other_off <= tol
    comp3 = o3.other_off <= tol
    out["cone_3d_first"] = [dict(recording=name, system=pct(lk.att == "target"), cone=pct(c2 == "target"),
                                 cone_3d_first=pct(c3 == "target"), competitor_s=_sec(int(comp.sum()), rate),
                                 system_with_competitor=pct(lk.att[comp] == "target"),
                                 cone_with_competitor=pct(c2[comp] == "target"),
                                 cone_3d_first_with_competitor=pct(c3[comp] == "target"),
                                 competitor_3d_s=_sec(int(comp3.sum()), rate),
                                 system_with_3d_competitor=pct(lk.att[comp3] == "target"),
                                 cone_with_3d_competitor=pct(c2[comp3] == "target"),
                                 cone_3d_first_with_3d_competitor=pct(c3[comp3] == "target"))]
    return out
