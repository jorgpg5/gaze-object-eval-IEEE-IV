"""Reference mappings scored on the same samples and candidates as the system.

cone(s, tol)         nearest box to the gaze ray (exact angular distance), accepted
                     if within tol deg; ties (both boxes contain the gaze) go to the
                     nearer object. cone(s, 0) = the centre ray: the gaze ray hits a box.
cone_3d_first(...)   the same rule over 3D candidates first; camera-only candidates
                     only when no 3D box is within tol.
"""
import numpy as np
import pandas as pd


def cone(s, tol):
    tgt_first = (s.off_box < s.other_off) | ((s.off_box == s.other_off) & (s.dist <= s.other_dist))
    best_off = np.where(tgt_first, s.off_box, s.other_off)
    hit = best_off <= tol + 1e-9
    other_label = np.where(s.other_is_target2, "other_target", "other")
    return pd.Series(np.where(hit & tgt_first, "target", np.where(hit, other_label, "none")), index=s.index)


def cone_3d_first(lk, o3, o2, tol):
    """o3 / o2: best other 3D / camera-only candidate per sample (table.best_other)."""
    t3 = lk.input_state.values == "3d"
    toff = lk.off_box.values
    c_t = np.where(t3, toff, np.inf)
    c_o = o3.other_off.reindex(lk.index).fillna(np.inf).values
    d_t, d_o = lk.dist.values, o3.other_dist.reindex(lk.index).fillna(np.inf).values
    pick_t = (c_t < c_o) | ((c_t == c_o) & (d_t <= d_o))
    best = np.where(pick_t, c_t, c_o)
    out = np.where(best <= tol, np.where(pick_t, "target", "other"), "")
    c_t2 = np.where(~t3, toff, np.inf)
    c_o2 = o2.other_off.reindex(lk.index).fillna(np.inf).values
    d_o2 = o2.other_dist.reindex(lk.index).fillna(np.inf).values
    pick_t2 = (c_t2 < c_o2) | ((c_t2 == c_o2) & (d_t <= d_o2))
    best2 = np.where(pick_t2, c_t2, c_o2)
    out2 = np.where(best2 <= tol, np.where(pick_t2, "target", "other"), "none")
    return pd.Series(np.where(out == "", out2, out), index=lk.index)
