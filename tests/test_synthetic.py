"""End-to-end checks on synthetic recordings whose answers are known (examples/synthetic/generate.py)."""
import os

import numpy as np
import pandas as pd

from _helpers import TMP, GEN, built, goeval, synthetic, variant
from goeval import metrics as M
from goeval.config import params

P = params()


def _main_all(s):
    a = M.mapping_scores(s, P)
    return a[(a.phase == "main") & (a.band == "all")].iloc[0]


def _oracle(target_of):
    """A system that always attends the cued target."""
    def f(g, res):
        ids = target_of(g.t_s.values, res)
        out = pd.array(ids, dtype="Int64")
        out[g.valid.values == 0] = pd.NA
        return out
    return f


def test_walkaway_stops_found():
    rec, s, info = built("SYN-WALK")
    st = s[s.phase == "standing"].groupby("unit").band_dist.median().sort_values().values
    assert len(st) == 4
    assert np.allclose(st, [7, 17, 27, 37], atol=0.5), st


def test_target_followed_across_id_switch():
    rec, s, info = built("SYN-WALK")
    assert info["targets"] == [1, 11]


def test_gaze_input_recovers_known_bias_and_noise():
    for name in ("SYN-WALK", "SYN-CROSS", "SYN-TWO", "SYN-CROSS-DEG"):
        spec = next(r for r in GEN.RECORDINGS if r[0] == name)
        bias, noise = spec[3], spec[4]
        rec, s, info = built(name)
        U, summ = M.gaze_input(s, P)
        # per-unit bias carries the slow (correlated) part of the noise: allow a share of the noise SD
        assert abs(summ["yaw_abs_bias_median"] - abs(bias[0])) < 0.15 + 0.35 * noise[0], (name, summ)
        assert abs(summ["yaw_precision_median"] - noise[0]) < 0.35 * noise[0], (name, summ)
        assert abs(summ["pitch_precision_median"] - noise[1]) < 0.35 * noise[1], (name, summ)


def test_oracle_system_scores_100():
    path = variant("SYN-WALK", "SYN-WALK-ORACLE", _oracle(lambda t, res: res[0][0].id_at(t)))
    s, _ = goeval.build(goeval.read_recording(path))
    lk = goeval.looking(s)
    assert (lk.att == "target").mean() == 1.0


def test_null_system_scores_0_baselines_unchanged():
    path = variant("SYN-WALK", "SYN-WALK-NULL", lambda g, res: pd.array([pd.NA] * len(g), dtype="Int64"))
    s0, _ = goeval.build(goeval.read_recording(path))
    a0 = _main_all(s0)
    _, s, _ = built("SYN-WALK")
    a = _main_all(s)
    assert a0.system == 0.0 and a0.system_none == 100.0
    assert a0.cone == a.cone and a0.centre_ray == a.centre_ray


def test_two_pedestrians_looked_at_follows_the_cue():
    path, (g, o, meta, res) = synthetic("SYN-TWO")
    rec, s, info = built("SYN-TWO")
    lk = goeval.looking(s)
    L = res[0][0]
    cue = np.array(["L" if res[3](t) is L else "R" for t in lk.t_s.values])
    assert (lk.looked.values == cue).mean() > 0.98


def test_two_pedestrians_wrong_pedestrian_is_other_target():
    def other(t, res):
        L, R = res[0][0], res[0][1]
        return np.array([R.ids[0][1] if res[3](tt) is L else L.ids[0][1] for tt in t])
    path = variant("SYN-TWO", "SYN-TWO-SWAP", _oracle(other))
    s, _ = goeval.build(goeval.read_recording(path))
    lk = goeval.looking(s)
    assert (lk.att == "other_target").mean() > 0.98


def test_crossings_found():
    rec, s, info = built("SYN-CROSS")
    c, cr = M.crossing_table(rec, s, info, P)
    assert len(cr) == 6
    assert sorted(cr.direction.value_counts().values) == [3, 3]
    assert sorted(cr.depth_m.round().unique()) == [13, 23, 33]


def test_crossing_along_track_error_carries_the_bias():
    # yaw bias b shows as +b (ahead) walking one way and -b the other
    spec = next(r for r in GEN.RECORDINGS if r[0] == "SYN-CROSS-DEG")
    rec, s, info = built("SYN-CROSS-DEG")
    c, cr = M.crossing_table(rec, s, info, P)
    d = M.crossing_summary(c, ["direction"], P).set_index("direction").along_track_err_median_deg
    b = spec[3][0]
    assert abs(d["L->R"] + b) < 0.6 and abs(d["R->L"] - b) < 0.6, d


def test_car_approaches():
    rec, s, info = built("SYN-CAR")
    assert len(info["units"]) == 2
    ph = M.car_phases(s, P)
    assert ((ph.enters_3d_at_m > 55) & (ph.enters_3d_at_m < 66)).all(), ph
    assert (ph.lead_in_camera_only_s > 0).all()


def test_sweep_matches_table():
    for name in ("SYN-WALK", "SYN-CROSS", "SYN-TWO", "SYN-CAR"):
        rec, s, info = built(name)
        a = _main_all(s)
        sw, _, _ = M.sweep(s, P)
        at = sw.set_index("tol_deg")
        assert abs(at.loc[P["cone_tol_deg"], "cone_target"] - a.cone) < 1e-9
        assert abs(at.loc[0.0, "cone_target"] - a.centre_ray) < 1e-9
        assert abs(at.loc[0.0, "system_target"] - a.system) < 1e-9
        assert np.all(np.diff(sw.sort_values("tol_deg").cone_none.values) <= 1e-9)


def test_evaluate_writes_everything():
    paths = [synthetic(n)[0] for n in ("SYN-WALK", "SYN-CAR")]
    out = os.path.join(TMP, "eval_out")
    goeval.evaluate(paths, out, log=lambda *a: None)
    for f in ("report.md", "tables.md", "tables.tex", "mapping.csv", "gaze_input.csv", "sweep.csv",
              "car_phases.csv", "robust_gate.csv", "fig_sweep.png", "fig_distance_SYN-WALK.png"):
        assert os.path.exists(os.path.join(out, f)), f
