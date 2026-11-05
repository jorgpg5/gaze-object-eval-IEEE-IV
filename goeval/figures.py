"""Figures: mapping by distance per recording, and the cone tolerance sweep."""
import os

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import baselines as BL  # noqa: E402
from . import table as T  # noqa: E402

C_SYS, C_CONE, C_RAY = "#2a78d6", "#eb6834", "#1baf7a"
C_3D, C_2D = "#b9b8b1", "#e4e3dd"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e1e0d9"
COND_COLOURS = [C_SYS, C_CONE, C_RAY, "#7a5af8", "#c2410c"]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 7.5, "axes.labelsize": 7.5, "axes.titlesize": 8,
    "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 6.8,
    "axes.edgecolor": "#c3c2b7", "axes.linewidth": 0.6, "xtick.color": INK2, "ytick.color": INK2,
    "axes.labelcolor": INK, "pdf.fonttype": 42, "ps.fonttype": 42,
})


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.grid(True, color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    ax.set_ylim(0, 104)
    ax.set_yticks([0, 25, 50, 75, 100])


def _pct(x):
    return 100.0 * float(np.mean(x)) if len(x) else np.nan


def by_distance(lk, P, rate):
    """Rows per distance group: input state shares and the % mapped by each rule."""
    car = lk.protocol.iloc[0] == "car_approach"
    if car:
        top = np.ceil(lk.band_dist.max() / P["car_bin_m"]) * P["car_bin_m"]
        edges = np.arange(P["car_bin_m"], top + 1e-9, P["car_bin_m"])
        cut = pd.cut(lk.band_dist, edges, right=False)
        x = (edges[:-1] + edges[1:]) / 2
    else:
        cut = T.band_of(lk.band_dist.fillna(lk.dist), P)
        x = np.arange(len(cut.cat.categories))
    n_min = P["fig_min_s"] * rate
    rows = []
    for xi, iv in zip(x, cut.cat.categories):
        g = lk[cut == iv]
        g3, g2 = g[g.input_state == "3d"], g[g.input_state == "2d"]
        ok = len(g) >= n_min
        rows.append(dict(x=xi, label=str(iv), seconds=len(g) / rate, in3d=_pct(g.input_state == "3d"),
                         in2d=_pct(g.input_state == "2d"),
                         centre_ray=_pct(BL.cone(g, 0.0) == "target") if ok else np.nan,
                         cone=_pct(BL.cone(g, P["cone_tol_deg"]) == "target") if ok else np.nan,
                         system_3d=_pct(g3.att == "target") if len(g3) >= n_min else np.nan,
                         system_camera_only=_pct(g2.att == "target") if len(g2) >= n_min else np.nan))
    return pd.DataFrame(rows), car


def fig_by_distance(s, P, path):
    rate = s.attrs["rate_hz"]
    lk = T.looking(s)
    d, car = by_distance(lk, P, rate)
    fig, ax = plt.subplots(figsize=(3.5 if not car else 5.0, 3.0 if not car else 2.7))
    w = 0.62 if not car else P["car_bin_m"] * 0.78
    ax.bar(d.x, d.in3d, w, color=C_3D, label="object in 3D", zorder=1)
    ax.bar(d.x, d.in2d, w, bottom=d.in3d + 0.8, color=C_2D, label="object camera-only", zorder=1)
    ax.plot(d.x, d.centre_ray, color=C_RAY, lw=1.3, marker="^", ms=3.5, mec="white", mew=0.5, label="centre ray", zorder=3)
    ax.plot(d.x, d.cone, color=C_CONE, lw=1.3, marker="s", ms=3.5, mec="white", mew=0.5,
            label=f"{P['cone_tol_deg']:g}° cone", zorder=3)
    ax.plot(d.x, d.system_3d, color=C_SYS, lw=1.5, marker="o", ms=3.8, mec="white", mew=0.5,
            label="system (object in 3D)", zorder=4)
    ax.plot(d.x, d.system_camera_only, color=C_SYS, lw=0, marker="o", ms=3.8, mfc="white", mec=C_SYS, mew=1.0,
            label="system (object camera-only)", zorder=4)
    if not car:
        ax.set_xticks(d.x)
        ax.set_xticklabels([l.replace(" m", "") for l in d.label])
    ax.set_xlabel("distance from the eye (m)")
    ax.set_ylabel("% of looking samples")
    ax.set_title(f"{s.recording.iloc[0]} ({s.condition.iloc[0]})", loc="left", color=INK)
    _style(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.2), ncol=3 if car else 2, frameon=False, handlelength=1.6)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    d.to_csv(path.rsplit(".", 1)[0] + ".csv", index=False)
    return path


def fig_sweep(sw, P, path):
    if sw.empty:
        return None
    fig, ax = plt.subplots(figsize=(3.5, 2.45))
    conds = list(dict.fromkeys(sw.condition))
    top = P["sweep_max_deg"]
    for ci, cond in enumerate(conds):
        c = COND_COLOURS[ci % len(COND_COLOURS)]
        recs = list(dict.fromkeys(sw[sw.condition == cond].recording))
        for k, r in enumerate(recs):
            g = sw[sw.recording == r]
            ls = "--" if g.protocol.iloc[0] == "car_approach" else "-"
            ax.plot(g.tol_deg, g.cone_target, color=c, lw=1.2, ls=ls, zorder=2)
            ax.plot([top * 1.11], [g.system_target.iloc[0]], marker="o", ms=4.0, color=c, mec="white", mew=0.6,
                    clip_on=False, zorder=3)
        ax.plot([], [], color=c, lw=1.2, label=f"{cond} ({len(recs)} recording{'s' if len(recs) > 1 else ''})")
    ax.text(top * 1.11, 104, "system", fontsize=6.3, ha="center", va="bottom", color=INK2)
    ax.set_xlim(0, top * 1.18)
    ax.set_xticks(np.arange(0, top + 1e-9, 1.0))
    ax.set_xlabel("nearest-box cone tolerance (deg)")
    ax.set_ylabel("% mapped to the\nlooked-at target")
    _style(ax)
    ax.spines["bottom"].set_bounds(0, top)
    if (sw.protocol == "car_approach").any() and (sw.protocol != "car_approach").any():
        ax.plot([], [], color=INK2, lw=1.2, ls="--", label="car approach")
    ax.legend(loc="lower right", frameon=False, bbox_to_anchor=(0.9, 0.02))
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def all_figures(tables, D, P, out):
    figs = []
    for name, s in tables.items():
        if len(T.looking(s)):
            figs.append(fig_by_distance(s, P, os.path.join(out, f"fig_distance_{name}.png")))
    f = fig_sweep(D.get("sweep", pd.DataFrame()), P, os.path.join(out, "fig_sweep.png"))
    if f:
        figs.append(f)
    return figs
