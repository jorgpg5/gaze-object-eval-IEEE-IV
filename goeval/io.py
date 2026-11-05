"""Reading and checking a recording (see docs/schema.md).

A recording is a folder with three files:
  recording.json  name, protocol, condition (and optional target IDs)
  gaze.csv        one row per gaze sample, with the system's attended object
  objects.csv     the object lists the system mapped against (3D and camera-only)
"""
import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import params as _params

PROTOCOLS = ("walkaway", "crossing", "two_pedestrians", "car_approach")
SOURCES = ("3d", "camera")

GAZE_COLUMNS = {
    "t_s": "time (s), increasing",
    "valid": "1 = the DMS has a gaze estimate for this sample, else 0",
    "eye_x": "eye position, vehicle frame (m)",
    "eye_y": "",
    "eye_z": "",
    "gaze_yaw_deg": "gaze direction, vehicle frame (deg; yaw + = left, pitch + = up)",
    "gaze_pitch_deg": "",
    "attended_id": "ID of the object the system maps the gaze to; empty = none",
}
GAZE_OPTIONAL = {
    "blink_count": "cumulative blink counter from the DMS (preferred blink signal)",
    "blink": "1 = blink at this sample (if the DMS flags blinks instead of counting them)",
}
OBJECT_COLUMNS = {
    "t_s": "time of the object list (s); all rows of one list share it",
    "source": "3d (box placed in 3D) or camera (camera-only detection, box at its estimated depth)",
    "id": "integer track ID; empty = an empty list at this time",
    "class": "pedestrian, car, cyclist, ... or unknown",
    "x": "box centre, vehicle frame (m)",
    "y": "",
    "z": "",
    "length": "box size along its heading, across it, and vertically (m)",
    "width": "",
    "height": "",
    "yaw_deg": "box heading about the vertical axis (deg, + = left)",
}


class SchemaError(ValueError):
    pass


@dataclass
class Recording:
    path: str
    name: str
    protocol: str
    condition: str
    meta: dict
    gaze: pd.DataFrame
    objects: pd.DataFrame
    rate_hz: float = field(default=np.nan)

    def seconds(self, n):
        """Samples -> seconds at this recording's sample rate."""
        return n / self.rate_hz


def _read(path, fname, **kw):
    p = os.path.join(path, fname)
    if not os.path.exists(p):
        raise SchemaError(f"{path}: missing {fname}")
    return pd.read_csv(p, low_memory=False, **kw)


def check_recording(path):
    """All problems found in a recording folder: list of (level, message), level = error / warning / info."""
    out = []
    try:
        meta = json.load(open(os.path.join(path, "recording.json")))
    except FileNotFoundError:
        return [("error", "missing recording.json")]
    except json.JSONDecodeError as e:
        return [("error", f"recording.json is not valid JSON: {e}")]
    for k in ("name", "protocol", "condition"):
        if k not in meta:
            out.append(("error", f"recording.json: missing '{k}'"))
    if meta.get("protocol") not in PROTOCOLS:
        out.append(("error", f"recording.json: protocol must be one of {PROTOCOLS}"))
    try:
        g = _read(path, "gaze.csv")
        o = _read(path, "objects.csv", dtype={"class": str, "source": str})
    except SchemaError as e:
        return out + [("error", str(e))]
    for name, df, cols in (("gaze.csv", g, GAZE_COLUMNS), ("objects.csv", o, OBJECT_COLUMNS)):
        miss = [c for c in cols if c not in df.columns]
        if miss:
            out.append(("error", f"{name}: missing columns {miss}"))
    if any(lvl == "error" for lvl, _ in out):
        return out
    # ---- gaze
    if not np.all(np.diff(g.t_s.values) > 0):
        out.append(("error", "gaze.csv: t_s must increase strictly"))
    if not set(g.valid.dropna().unique()) <= {0, 1}:
        out.append(("error", "gaze.csv: valid must be 0 or 1"))
    v = g[g.valid == 1]
    for c in ("eye_x", "eye_y", "eye_z", "gaze_yaw_deg", "gaze_pitch_deg"):
        if v[c].isna().any():
            out.append(("error", f"gaze.csv: {c} empty on {int(v[c].isna().sum())} valid samples"))
    if (v.gaze_yaw_deg.abs() > 180).any() or (v.gaze_pitch_deg.abs() > 90).any():
        out.append(("error", "gaze.csv: yaw must be within +-180 deg and pitch within +-90 deg"))
    if (v[["eye_x", "eye_y", "eye_z"]].abs() > 5).any().any():
        out.append(("warning", "gaze.csv: eye position more than 5 m from the vehicle origin; check units (m) and frame"))
    if len(v) and v.gaze_yaw_deg.abs().median() > 60:
        out.append(("warning", "gaze.csv: median |yaw| above 60 deg; check the yaw convention (0 = straight ahead)"))
    if "blink_count" not in g.columns and "blink" not in g.columns:
        out.append(("info", "gaze.csv: no blink_count or blink column; blinks are found from pitch dips and dropouts"))
    rate = (len(g) - 1) / (g.t_s.iloc[-1] - g.t_s.iloc[0]) if len(g) > 1 else np.nan
    out.append(("info", f"gaze.csv: {len(g)} samples, {100 * g.valid.mean():.1f}% valid, {rate:.2f} Hz"))
    # ---- objects
    bad_src = set(o.source.dropna().unique()) - set(SOURCES)
    if bad_src:
        out.append(("error", f"objects.csv: unknown source {sorted(bad_src)}; use {SOURCES}"))
    oo = o[o.id.notna()]
    if not np.allclose(oo.id, np.round(oo.id)):
        out.append(("error", "objects.csv: id must be an integer"))
    dup = oo.duplicated(["t_s", "source", "id"]).sum()
    if dup:
        out.append(("error", f"objects.csv: {dup} rows repeat an id within one object list"))
    for c in ("x", "y", "z", "length", "width", "height", "yaw_deg"):
        if oo[c].isna().any():
            out.append(("error", f"objects.csv: {c} empty on {int(oo[c].isna().sum())} object rows"))
    if ((oo[["length", "width", "height"]] <= 0).any(axis=1)).any():
        out.append(("error", "objects.csv: box sizes must be positive"))
    if oo["class"].isna().any():
        out.append(("warning", "objects.csv: some rows have no class; they are treated as unknown"))
    for src in SOURCES:
        fr = np.sort(o[o.source == src].t_s.unique())
        if not len(fr):
            out.append(("info" if src == "camera" else "error", f"objects.csv: no {src} object lists"))
            continue
        P = _params()
        i = np.searchsorted(fr, v.t_s.values, side="right") - 1
        ok = (i >= 0) & ((v.t_s.values - fr[np.clip(i, 0, None)]) <= P["max_frame_age_s"])
        out.append(("info" if ok.mean() > 0.9 else "warning",
                    f"objects.csv: {100 * ok.mean():.1f}% of valid gaze samples have a {src} list at most "
                    f"{P['max_frame_age_s']} s old"))
    # ---- the system's output
    att = g.attended_id.dropna()
    if len(att) and not np.allclose(att, np.round(att)):
        out.append(("error", "gaze.csv: attended_id must be an integer ID or empty"))
    elif len(att):
        known = att.astype(int).isin(oo.id.astype(int))
        if known.mean() < 0.99:
            out.append(("warning", f"gaze.csv: {100 * (1 - known.mean()):.1f}% of attended IDs never appear in objects.csv"))
    out.append(("info", f"gaze.csv: the system attends an object on {100 * g.attended_id.notna().mean():.1f}% of samples"))
    return out


def read_recording(path):
    problems = check_recording(path)
    errors = [m for lvl, m in problems if lvl == "error"]
    if errors:
        raise SchemaError(f"{path}:\n  " + "\n  ".join(errors))
    meta = json.load(open(os.path.join(path, "recording.json")))
    g = _read(path, "gaze.csv").sort_values("t_s").reset_index(drop=True)
    o = _read(path, "objects.csv", dtype={"class": str, "source": str})
    o["class"] = o["class"].fillna("unknown")
    rate = (len(g) - 1) / (g.t_s.iloc[-1] - g.t_s.iloc[0])
    return Recording(path=path, name=str(meta["name"]), protocol=meta["protocol"], condition=str(meta["condition"]),
                     meta=meta, gaze=g, objects=o, rate_hz=rate)


def objects_at_samples(rec, source, P):
    """Object rows of one source joined to each VALID gaze sample: the latest list
    at or before the sample, at most max_frame_age_s old. Columns renamed to the
    internal names (obj_id, obj_class, obj_x .. obj_yaw_deg); 'sample' = gaze row."""
    o = rec.objects[rec.objects.source == source]
    v = rec.gaze[rec.gaze.valid == 1]
    if o.empty or v.empty:
        return pd.DataFrame(columns=["sample", "obj_id"])
    fr = np.sort(o.t_s.unique())
    i = np.searchsorted(fr, v.t_s.values, side="right") - 1
    ft = fr[np.clip(i, 0, None)]
    ok = (i >= 0) & ((v.t_s.values - ft) <= P["max_frame_age_s"])
    m = pd.DataFrame({"sample": v.index.values[ok], "frame_t": ft[ok]})
    rows = m.merge(o.rename(columns={"t_s": "frame_t"}), on="frame_t", how="inner")
    rows = rows[rows.id.notna()].rename(columns={
        "id": "obj_id", "class": "obj_class", "x": "obj_x", "y": "obj_y", "z": "obj_z",
        "length": "obj_sx", "width": "obj_sy", "height": "obj_sz", "yaw_deg": "obj_yaw_deg"})
    rows["obj_id"] = rows.obj_id.astype(int)
    return rows.drop(columns=["frame_t", "source"])
