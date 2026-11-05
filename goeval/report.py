"""Run the whole evaluation on a set of recordings and write tables, figures and a report."""
import json
import os

import numpy as np
import pandas as pd

from . import __version__
from . import metrics as M
from . import table as T
from .config import params as _params
from .io import read_recording


def _f0(x):
    return "" if pd.isna(x) else f"{x:.0f}"


def evaluate(paths, out, params=None, figures=True, robustness=True, log=print):
    """Evaluate every recording folder in paths; write everything to out. Returns a dict of DataFrames."""
    P = _params(params)
    os.makedirs(out, exist_ok=True)
    R = {k: [] for k in ("gaze_input_units", "gaze_input", "mapping", "mapping_units", "sweep",
                         "sweep_by_band", "offbox", "crossing_per_crossing", "crossing_summary", "car_phases",
                         "robust_gate", "robust_saccades", "robust_unscored", "robust_cone_3d_first", "recordings")}
    tables = {}
    for path in paths:
        rec = read_recording(path)
        s, info = T.build(rec, P)
        tables[rec.name] = s
        n_units = info["units"].unit.nunique()
        R["recordings"].append(dict(recording=rec.name, protocol=rec.protocol, condition=rec.condition,
                                    rate_hz=round(rec.rate_hz, 2), units=n_units,
                                    target_ids=json.dumps(info["targets"]), notes=" | ".join(info["notes"])))
        if rec.protocol != "car_approach":
            U, summ = M.gaze_input(s, P)
            R["gaze_input_units"].append(U)
            if summ:
                R["gaze_input"].append(pd.DataFrame([summ]))
        sw, swb, dist = M.sweep(s, P)
        R["sweep"].append(sw.assign(protocol=rec.protocol))
        R["sweep_by_band"].append(swb)
        R["offbox"].append(pd.DataFrame([dist]))
        R["mapping"].append(M.mapping_scores(s, P))
        R["mapping_units"].append(M.per_unit(s, P))
        if rec.protocol == "crossing":
            c, cr = M.crossing_table(rec, s, info, P)
            if c is not None and len(cr):
                R["crossing_per_crossing"].append(M.crossing_summary(c, ["recording", "condition", "unit", "depth_m", "direction"], P))
                parts = [M.crossing_summary(c, ["recording", "condition"], P).assign(depth_m="all", direction="all"),
                         M.crossing_summary(c, ["recording", "condition", "depth_m"], P).assign(direction="all"),
                         M.crossing_summary(c, ["recording", "condition", "direction"], P).assign(depth_m="all")]
                R["crossing_summary"].append(pd.concat(parts, ignore_index=True))
        if rec.protocol == "car_approach":
            R["car_phases"].append(M.car_phases(s, P))
        if robustness:
            rb = M.robustness(rec, s, info, P)
            for k, v in (("robust_gate", "gate"), ("robust_saccades", "saccades"), ("robust_unscored", "unscored"),
                         ("robust_cone_3d_first", "cone_3d_first")):
                R[k].append(pd.DataFrame(rb[v]))
        log(f"{rec.name}: {rec.protocol}, {rec.condition}, {n_units} units, "
            f"{len(T.looking(s)) / rec.rate_hz:.1f} s of looking")
    D = {k: (pd.concat([x for x in v if x is not None and len(x)], ignore_index=True)
             if any(x is not None and len(x) for x in v) else pd.DataFrame())
         for k, v in R.items() if k != "recordings"}
    D["recordings"] = pd.DataFrame(R["recordings"])
    for k, d in D.items():
        if len(d):
            d.to_csv(os.path.join(out, f"{k}.csv"), index=False)
    pd.to_pickle(tables, os.path.join(out, "samples.pkl"))
    md, tex = paper_tables(D, P)
    open(os.path.join(out, "tables.md"), "w").write(md)
    open(os.path.join(out, "tables.tex"), "w").write(tex)
    figs = []
    if figures:
        from . import figures as F
        figs = F.all_figures(tables, D, P, out)
    open(os.path.join(out, "report.md"), "w").write(report_md(D, P, md, figs))
    log(f"written to {out}")
    return D


def paper_tables(D, P):
    md, tex = [], []
    bands = [f"{a}-{b} m" for a, b in zip(P["bands_m"][:-1], P["bands_m"][1:])]
    order = list(D["recordings"].recording)
    t1 = D.get("gaze_input", pd.DataFrame())
    if len(t1):
        md.append("**Gaze input to the mapping** (per recording; units = stops, repeats or looks; "
                  "median absolute yaw bias over units, its maximum, and median precision over units, deg)\n")
        md.append("| Recording | Condition | Units | Median abs. yaw bias | Max abs. yaw bias | Yaw precision | Pitch precision |")
        md.append("|---|---|---|---|---|---|---|")
        tex.append("% Gaze input table\n\\begin{tabular}{llrrrrr}\n\\toprule\nRec. & Cond. & $n$ & $|b_\\psi|$ med & "
                   "$|b_\\psi|$ max & $\\sigma_\\psi$ & $\\sigma_\\theta$ \\\\\n\\midrule")
        for rec in [r for r in order if r in set(t1.recording)]:
            r = t1[t1.recording == rec].iloc[0]
            vals = f"{r.yaw_abs_bias_median:.2f} | {r.yaw_abs_bias_max:.2f} | {r.yaw_precision_median:.2f} | {r.pitch_precision_median:.2f}"
            md.append(f"| {rec} | {r.condition} | {r.units} | {vals} |")
            tex.append(f"{rec} & {r.condition} & {r.units} & " + vals.replace(" | ", " & ") + " \\\\")
        tex.append("\\bottomrule\n\\end{tabular}\n")
    t2 = D["mapping"]
    main = t2[t2.phase == "main"]
    tol = P["cone_tol_deg"]
    md.append(f"\n**Looking samples mapped to the looked-at object (%): system / {tol:g}° cone / centre ray**, "
              f"by distance from the eye (all phases). Cells with less than {P['min_cell_s']:g} s of looking are left out.\n")
    md.append("| Recording | Condition | " + " | ".join(bands) + f" | Competitor within {tol:g}° (% of samples) |")
    md.append("|---|---|" + "---|" * len(bands) + "---|")
    tex.append("% Mapping table\n\\begin{tabular}{ll" + "c" * len(bands) + "r}\n\\toprule\nRec. & Cond. & "
               + " & ".join(b.replace("-", "--").replace(" m", "") for b in bands) + " & Comp. \\\\\n\\midrule")
    for rec in order:
        g = main[main.recording == rec].set_index("band")
        if "all" not in g.index:
            continue
        cells, tcells = [], []
        for b in bands:
            if b in g.index and g.loc[b, "seconds"] >= P["min_cell_s"]:
                r = g.loc[b]
                cells.append(f"{_f0(r.system)} / {_f0(r.cone)} / {_f0(r.centre_ray)}")
                tcells.append(f"{_f0(r.system)}/{_f0(r.cone)}/{_f0(r.centre_ray)}")
            else:
                cells.append("–")
                tcells.append("--")
        a = g.loc["all"]
        md.append(f"| {rec} | {a.condition} | " + " | ".join(cells) + f" | {a.competitor_pct:.0f} |")
        tex.append(f"{rec} & {a.condition} & " + " & ".join(tcells) + f" & {a.competitor_pct:.0f} \\\\")
    tex.append("\\bottomrule\n\\end{tabular}\n")
    md.append("\n**Standing vs walking** (all distances): system / cone / centre ray, and seconds of looking.\n")
    md.append("| Recording | Condition | Standing | s | Walking | s |")
    md.append("|---|---|---|---|---|---|")
    for rec in order:
        g = t2[(t2.recording == rec) & (t2.band == "all")].set_index("phase")
        if "walking" not in g.index or "standing" not in g.index:
            continue
        st, wk = g.loc["standing"], g.loc["walking"]
        md.append(f"| {rec} | {st.condition} | {_f0(st.system)} / {_f0(st.cone)} / {_f0(st.centre_ray)} | {st.seconds:.1f} | "
                  f"{_f0(wk.system)} / {_f0(wk.cone)} / {_f0(wk.centre_ray)} | {wk.seconds:.1f} |")
    md.append(f"\n**Samples with another object within {tol:g}° of the gaze**: % mapped to the looked-at object.\n")
    md.append("| Recording | Looking time with a competitor (s) | Share of looking samples (%) | System | Cone |")
    md.append("|---|---|---|---|---|")
    for rec in order:
        a = main[(main.recording == rec) & (main.band == "all")]
        if a.empty:
            continue
        a = a.iloc[0]
        s = a.seconds * a.competitor_pct / 100
        if s < 1.0:
            continue
        md.append(f"| {rec} | {s:.1f} | {a.competitor_pct:.0f} | {a.system_with_competitor:.1f} | {a.cone_with_competitor:.1f} |")
    return "\n".join(md) + "\n", "\n".join(tex) + "\n"


def _mdtable(d, cols=None, digits=1):
    if d is None or not len(d):
        return "_none_\n"
    d = d[cols] if cols else d
    out = ["| " + " | ".join(map(str, d.columns)) + " |", "|" + "---|" * len(d.columns)]
    for _, r in d.iterrows():
        out.append("| " + " | ".join(f"{v:.{digits}f}" if isinstance(v, (float, np.floating)) else str(v) for v in r) + " |")
    return "\n".join(out) + "\n"


def report_md(D, P, tables_md, figs):
    r = [f"# Gaze-to-object mapping evaluation\n\ngoeval {__version__}. Settings that differ from the defaults: "
         + (", ".join(f"{k} = {v}" for k, v in P.items() if v != _params()[k]) or "none") + ".\n",
         "## Recordings\n", _mdtable(D["recordings"]), "\n## Tables\n", tables_md]
    if len(D.get("crossing_summary", [])):
        r += ["\n## Crossings\n", _mdtable(D["crossing_summary"])]
    if len(D.get("car_phases", [])):
        r += ["\n## Car approach phases\n", _mdtable(D["car_phases"])]
    if len(D.get("robust_gate", [])):
        r += ["\n## Robustness\n", "Look gate:\n\n", _mdtable(D["robust_gate"]),
              "\nSaccades kept (blinks still removed):\n\n", _mdtable(D["robust_saccades"]),
              "\nTime inside the units that is not scored:\n\n", _mdtable(D["robust_unscored"]),
              "\n3D-first cone (3D candidates first, camera-only only if no 3D box is within the tolerance):\n\n",
              _mdtable(D["robust_cone_3d_first"])]
    if figs:
        r += ["\n## Figures\n"] + [f"![{os.path.basename(f)}]({os.path.basename(f)})\n" for f in figs]
    return "\n".join(r)
