"""Per-sample gaze table: saccade and blink flags (samples removed before scoring)."""
import numpy as np
import pandas as pd


def mask_runs(mask):
    """(start, end) index positions of consecutive True runs."""
    m = np.asarray(mask, bool)
    if not m.any():
        return []
    d = np.diff(np.concatenate(([0], m.astype(int), [0])))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0] - 1))


def flag_blinks(s, P):
    """Blink flag per sample (bool). Cores, in order of preference: the DMS blink
    counter incrementing (window blink_before_s .. blink_after_s around each
    increment); the DMS's own blink flag; short downward pitch dips and short
    dropouts. Cores closer than blink_merge_s are merged."""
    n = len(s)
    ts = s.t_s.values
    valid = (s.valid == 1).values
    cores = []
    if "blink_count" in s.columns and s.blink_count.notna().any():
        c = s.blink_count.ffill().values
        for i in np.where(np.diff(c) > 0)[0] + 1:
            a = int(np.searchsorted(ts, ts[i] - P["blink_before_s"]))
            b = int(np.searchsorted(ts, ts[i] + P["blink_after_s"], side="right")) - 1
            cores.append((a, max(a, b)))
        source = "DMS blink counter"
    elif "blink" in s.columns and s.blink.notna().any():
        cores = mask_runs(s.blink.fillna(0).values.astype(bool))
        source = "DMS blink flag"
    else:
        pitch = s.gaze_pitch_deg.where(s.valid == 1).values
        med = pd.Series(pitch, index=pd.to_timedelta(ts, unit="s")).rolling(
            f"{int(P['blink_median_window_s'] * 1000)}ms", center=True, min_periods=5).median().values
        dip = valid & ((pitch - med) < -P["blink_pitch_drop_deg"])
        n_min = max(1, int(round(P["blink_min_s"] * _rate(ts))))
        for a, b in mask_runs(dip):
            if b - a + 1 >= n_min and ts[b] - ts[a] <= P["blink_max_s"]:
                cores.append((a, b))
        for a, b in mask_runs(~valid):
            if ts[b] - ts[a] <= P["blink_max_s"]:
                cores.append((a, b))
        source = "pitch dips and dropouts"
    cores.sort()
    merged = []
    for a, b in cores:
        if merged and ts[a] - ts[merged[-1][1]] < P["blink_merge_s"]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    blink = np.zeros(n, bool)
    for a, b in merged:
        blink[a:b + 1] = True
    return blink, source


def _rate(ts):
    return (len(ts) - 1) / (ts[-1] - ts[0]) if len(ts) > 1 else np.nan


def sample_table(rec, P):
    """One row per gaze sample (index = gaze row): t_s, valid, gaze, attended ID,
    saccade, blink."""
    g = rec.gaze
    cols = ["t_s", "valid", "gaze_yaw_deg", "gaze_pitch_deg", "attended_id"]
    cols += [c for c in ("blink_count", "blink") if c in g.columns]
    s = g[cols].copy()
    v = s[s.valid == 1]
    speed = np.hypot(v.gaze_yaw_deg.diff(), v.gaze_pitch_deg.diff()) / v.t_s.diff()
    sacc = (speed > P["saccade_deg_s"]) | (speed.shift(-1) > P["saccade_deg_s"])
    s["saccade"] = False
    s.loc[v.index, "saccade"] = sacc.fillna(False).values
    s["blink"], source = flag_blinks(s, P)
    s.attrs["blink_source"] = source
    return s
