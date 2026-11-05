"""Finding the cued target and cutting a recording into units.

Units: stops (walk-away), standing positions and their repeats (crossing),
stations (two pedestrians), the walks between them, and car approaches.
Everything is found from the target's own 3D track, so the protocol does not
need hand-made time stamps.

df (internal): one row per (valid gaze sample, 3D object) with the sample's
t_s and eye position and the object's obj_id, obj_class, obj_x .. obj_yaw_deg.
"""
import numpy as np
import pandas as pd


def target_track(df, ids):
    """The target's 3D row per valid sample (several IDs at one sample: the most
    recently started one), with dist_m (eye to box centre) and bearing_deg."""
    ids = list(ids)
    t = df[df.obj_id.isin(ids)].copy()
    if len(ids) > 1:
        seg_start = t.groupby("obj_id").t_s.min()
        t["seg_start"] = t.obj_id.map(seg_start)
        t = t.sort_values(["sample", "seg_start"]).groupby("sample").tail(1).drop(columns="seg_start")
    v = t[["obj_x", "obj_y", "obj_z"]].values - t[["eye_x", "eye_y", "eye_z"]].values
    t["dist_m"] = np.linalg.norm(v, axis=1)
    t["bearing_deg"] = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    return t.sort_values("t_s")


def infer_target(df, cls):
    """The cued target = the object of class cls seen at the most samples."""
    o = df[df.obj_class == cls]
    if o.empty:
        raise ValueError(f"no 3D objects of class '{cls}'")
    counts = o.groupby("obj_id")["sample"].nunique().sort_values(ascending=False)
    return int(counts.index[0])


def stitch_target(df, target, P):
    """Follow the target across tracker ID changes. A new ID continues it if it
    starts within stitch_max_gap_s after the previous one ends (or up to
    stitch_overlap_s before), within stitch_base_m + stitch_speed_m_s x gap of
    its last position, with the same class or 'unknown'. Returns the IDs in
    time order and notes on ambiguous links."""
    o = df.sort_values("t_s")
    first = o.groupby("obj_id").first()
    last = o.groupby("obj_id").last()
    cls = o.groupby("obj_id").obj_class.agg(lambda c: c.mode().iloc[0])
    allowed = {cls.loc[target], "unknown"}
    chain, notes = [target], []

    def link(cur, forward):
        ref = last.loc[cur] if forward else first.loc[cur]
        cands = []
        for oid in first.index:
            if oid in chain or cls.loc[oid] not in allowed:
                continue
            row = first.loc[oid] if forward else last.loc[oid]
            gap = (row.t_s - ref.t_s) if forward else (ref.t_s - row.t_s)
            if gap < -P["stitch_overlap_s"] or gap > P["stitch_max_gap_s"]:
                continue
            d = float(np.hypot(row.obj_x - ref.obj_x, row.obj_y - ref.obj_y))
            if d <= P["stitch_base_m"] + P["stitch_speed_m_s"] * max(gap, 0.0):
                cands.append((d, oid, gap))
        if not cands:
            return None
        cands.sort(key=lambda c: (round(max(c[2], 0.0), 1), c[0]))     # earliest continuation, then nearest
        if len(cands) > 1:
            notes.append(f"ambiguous link {'after' if forward else 'before'} ID {int(cur)}: "
                         + ", ".join(f"ID {int(c[1])} ({c[0]:.1f} m)" for c in cands[:3]) + f" -> took ID {int(cands[0][1])}")
        return cands[0][1]

    for forward in (True, False):
        cur = target
        while True:
            nxt = link(cur, forward)
            if nxt is None:
                break
            chain.append(nxt)
            cur = nxt
    chain.sort(key=lambda i: first.loc[i].t_s)
    return [int(i) for i in chain], notes


def detect_stops(t, P):
    """Stretches where the target's position (x, y) holds still for >= min_stop_s,
    trimmed by stop_trim_s at both ends. Speed is measured between stop_bin_s bins
    after a median over stop_smooth_bins bins (object positions update per tracker
    frame, so row-to-row speeds read 0 even while the target walks)."""
    B = P["stop_bin_s"]
    d = t[["t_s", "dist_m", "obj_x", "obj_y"]].copy()
    d["bin"] = (d.t_s // B).astype(int)
    b = d.groupby("bin").agg(t_s=("t_s", "median"), dist_m=("dist_m", "median"),
                             x=("obj_x", "median"), y=("obj_y", "median"))
    b = b.reindex(range(b.index.min(), b.index.max() + 1))            # empty bins = target not in 3D
    k = P["stop_smooth_bins"]
    sx = b.x.rolling(k, center=True, min_periods=2).median()
    sy = b.y.rolling(k, center=True, min_periods=2).median()
    speed = np.hypot(sx.diff(2), sy.diff(2)) / (2 * B)
    still = (speed < P["stop_speed_m_s"]) & b.dist_m.notna()
    stops, start = [], None
    idx = list(b.index)
    for j, i in enumerate(idx):
        ok = bool(still.loc[i])
        if ok and start is None:
            start = i
        if (not ok or j == len(idx) - 1) and start is not None:
            end = i if ok else idx[j - 1]
            seg = b.loc[start:end]
            s0, s1 = float(seg.t_s.min()) + P["stop_trim_s"], float(seg.t_s.max()) - P["stop_trim_s"]
            if s1 - s0 >= P["min_stop_s"]:
                inner = seg[(seg.t_s >= s0) & (seg.t_s <= s1)]
                stops.append(dict(start_s=s0, end_s=s1, duration_s=s1 - s0, dist_m=float(inner.dist_m.median())))
            start = None
    out = pd.DataFrame(stops, columns=["start_s", "end_s", "duration_s", "dist_m"])
    out.insert(0, "stop", range(1, len(out) + 1))
    return out


def positions_of(t, stops, P):
    """Each stop -> a standing position: depth (stops within depth_gap_m in x) and
    side (L / C / R by y). Repeats of a position share its label, e.g. '13 m L'."""
    rows = []
    for _, r in stops.iterrows():
        g = t[(t.t_s >= r.start_s) & (t.t_s <= r.end_s)]
        if g.empty:
            continue
        y = g.obj_y.median()
        side = "L" if y > P["side_m"] else "R" if y < -P["side_m"] else "C"
        rows.append(dict(stop=int(r.stop), start_s=r.start_s, end_s=r.end_s, duration_s=r.duration_s,
                         x_m=g.obj_x.median(), y_m=y, dist_m=g.dist_m.median(), bearing_deg=g.bearing_deg.median(),
                         side=side))
    pos = pd.DataFrame(rows)
    if pos.empty:
        return pos
    order = pos.sort_values("x_m")
    band = (order.x_m.diff() > P["depth_gap_m"]).cumsum()
    pos["depth_band"] = band.reindex(pos.index)
    pos["depth_m"] = pos.groupby("depth_band").x_m.transform("median")
    pos["position"] = pos.depth_m.round(0).astype(int).astype(str) + " m " + pos.side
    pos["repeat"] = pos.groupby("position").cumcount() + 1
    return pos


def crossings_of(pos, P):
    """Walks between consecutive positions that change side (|dy| >= cross_min_dy_m)."""
    out = []
    p = pos.sort_values("start_s").reset_index(drop=True)
    for k in range(len(p) - 1):
        a, b = p.iloc[k], p.iloc[k + 1]
        if abs(b.y_m - a.y_m) < P["cross_min_dy_m"]:
            continue
        out.append(dict(crossing=len(out) + 1, start_s=a.end_s, end_s=b.start_s, depth_m=(a.depth_m + b.depth_m) / 2,
                        from_pos=a.position, to_pos=b.position, dy_m=b.y_m - a.y_m, duration_s=b.start_s - a.end_s))
    return pd.DataFrame(out, columns=["crossing", "start_s", "end_s", "depth_m", "from_pos", "to_pos", "dy_m", "duration_s"])


def lr_targets(df, P):
    """Two pedestrians: every pedestrian ID on each side of the lane. A far
    pedestrian breaks into many short IDs, so membership is by side, not by ID
    chain. Valid when the scene holds exactly these two pedestrians."""
    o = df[df.obj_class == "pedestrian"]
    life = o.groupby("obj_id").agg(y=("obj_y", "median"))
    L = sorted(int(i) for i in life.index[life.y > P["side_m"]])
    R = sorted(int(i) for i in life.index[life.y < -P["side_m"]])
    return {"L": L, "R": R}


def lr_stations(tL, tR, P):
    """Depth steps where the two pedestrians stand: the overlap of their stops (a
    stop of only one of them is kept as a station too)."""
    sL, sR = detect_stops(tL, P), detect_stops(tR, P)
    rows = []
    for _, a in sR.iterrows():
        ov = sL[(sL.start_s < a.end_s) & (sL.end_s > a.start_s)]
        if len(ov):
            b = ov.iloc[0]
            rows.append(dict(start_s=max(a.start_s, b.start_s), end_s=min(a.end_s, b.end_s), both=True))
        else:
            rows.append(dict(start_s=a.start_s, end_s=a.end_s, both=False))
    for _, b in sL.iterrows():
        if not any((r["start_s"] < b.end_s) and (r["end_s"] > b.start_s) for r in rows):
            rows.append(dict(start_s=b.start_s, end_s=b.end_s, both=False))
    st = pd.DataFrame(rows).sort_values("start_s").reset_index(drop=True)
    out = []
    for k, r in st.iterrows():
        row = dict(station=k + 1, start_s=r.start_s, end_s=r.end_s, both_standing=r.both)
        for side, t in (("L", tL), ("R", tR)):
            g = t[(t.t_s >= r.start_s) & (t.t_s <= r.end_s)]
            row[f"x_{side}"] = g.obj_x.median() if len(g) else np.nan
        row["depth_m"] = np.nanmedian([row["x_L"], row["x_R"]])
        row["label"] = f"{row['depth_m']:.0f} m"
        out.append(row)
    return pd.DataFrame(out)


def walk_units(stand, P):
    """The walks between consecutive standing units (the driver keeps following the target)."""
    st = stand.sort_values("start_s").reset_index(drop=True)
    rows = []
    for k in range(len(st) - 1):
        a, b = st.iloc[k], st.iloc[k + 1]
        if b.start_s - a.end_s > P["walk_min_s"]:
            rows.append(dict(unit=f"walk {a.unit} -> {b.unit}", start_s=a.end_s, end_s=b.start_s))
    return pd.DataFrame(rows, columns=["unit", "start_s", "end_s"])


def car_units(df, objects, rate_hz, P):
    """Car approach: the car IDs are the car / unknown-class 3D tracks seen in the
    ego lane; each approach is a run of in-lane rows split at gaps longer than
    approach_gap_s, extended back by the first track's own camera-only rows (up
    to car_lead_in_s before it enters 3D)."""
    r = df[df.obj_class.isin(["car", "unknown"]) & (df.obj_y.abs() < P["lane_half_m"])]
    n = r.groupby("obj_id")["sample"].nunique()
    ids = sorted(int(i) for i in n.index[n >= int(round(P["min_track_s"] * rate_hz))])
    if not ids:
        raise ValueError("no car track in the ego lane")
    ts = np.sort(r[r.obj_id.isin(ids)].t_s.unique())
    cut = np.where(np.diff(ts) > P["approach_gap_s"])[0]
    starts = np.concatenate(([ts[0]], ts[cut + 1]))
    ends = np.concatenate((ts[cut], [ts[-1]]))
    units = pd.DataFrame(dict(unit=[f"approach {k + 1}" for k in range(len(starts))], start_s=starts, end_s=ends))
    units["start_3d_s"] = units.start_s
    cam = objects[objects.source == "camera"]
    for k, u in units.iterrows():
        first = r[(r.t_s >= u.start_s) & r.obj_id.isin(ids)].sort_values("t_s").obj_id.iloc[0]
        q = cam[(cam.id == first) & (cam.t_s < u.start_s) & (cam.t_s >= u.start_s - P["car_lead_in_s"])]
        if len(q):
            units.loc[k, "start_s"] = q.t_s.min()
    return ids, units
