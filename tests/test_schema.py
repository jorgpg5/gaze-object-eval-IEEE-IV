import json
import os
import shutil

import pandas as pd

from _helpers import TMP, goeval, synthetic


def _copy(name, new):
    src, _ = synthetic(name)
    dst = os.path.join(TMP, new)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    return dst


def _errors(path):
    return [m for lvl, m in goeval.check_recording(path) if lvl == "error"]


def test_synthetic_recordings_pass():
    for name in ("SYN-WALK", "SYN-CROSS", "SYN-TWO", "SYN-CAR"):
        path, _ = synthetic(name)
        assert _errors(path) == [], name


def test_missing_column_is_an_error():
    d = _copy("SYN-WALK", "bad-col")
    g = pd.read_csv(os.path.join(d, "gaze.csv")).drop(columns="attended_id")
    g.to_csv(os.path.join(d, "gaze.csv"), index=False)
    assert any("attended_id" in e for e in _errors(d))


def test_time_must_increase():
    d = _copy("SYN-WALK", "bad-time")
    g = pd.read_csv(os.path.join(d, "gaze.csv"))
    g.loc[10, "t_s"] = g.loc[9, "t_s"]
    g.to_csv(os.path.join(d, "gaze.csv"), index=False)
    assert any("increase" in e for e in _errors(d))


def test_repeated_id_in_one_list_is_an_error():
    d = _copy("SYN-WALK", "bad-dup")
    o = pd.read_csv(os.path.join(d, "objects.csv"))
    o = pd.concat([o, o[o.id.notna()].iloc[:1]], ignore_index=True)
    o.to_csv(os.path.join(d, "objects.csv"), index=False)
    assert any("repeat an id" in e for e in _errors(d))


def test_unknown_protocol_is_an_error():
    d = _copy("SYN-WALK", "bad-protocol")
    m = json.load(open(os.path.join(d, "recording.json")))
    m["protocol"] = "slalom"
    json.dump(m, open(os.path.join(d, "recording.json"), "w"))
    assert any("protocol" in e for e in _errors(d))
    try:
        goeval.read_recording(d)
    except goeval.SchemaError:
        return
    raise AssertionError("read_recording accepted a bad recording")
