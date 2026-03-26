#!/usr/bin/env python3
"""
Figure 2: Barrier curves + Ed summary for InP.

Panel A (top-left):  Energy vs displacement distance for each sampled
                     direction for In — from the dirs=10, pts=9 run.
Panel B (top-right): Same for P.
Panel C (bottom):    Ed comparison bar chart — DFT values from our best
                     converged run vs literature / experimental references.

Usage:
    python3 plot_barrier_curves.py
    python3 plot_barrier_curves.py --summary-json path/to/InP_summary.json
"""
from __future__ import annotations
import argparse, json, glob, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D

# ── pick best available summary JSON ─────────────────────────────────────────
def find_best_json(base: str) -> str | None:
    # Prefer the best run, then dirs=10 pts=09, then any available
    for pattern in [
        "best_run_results/InP_JVASP-1183_summary.json",
        "conv_results_d10_p09/InP_JVASP-1183_summary.json",
        "conv_results_d10_p07/InP_JVASP-1183_summary.json",
        "screen_outputs_batch_20260309_mid/InP_JVASP-1183_summary.json",
    ]:
        p = os.path.join(base, pattern)
        if os.path.exists(p):
            return p
    hits = glob.glob(os.path.join(base, "**/InP_JVASP-1183_summary.json"), recursive=True)
    return sorted(hits)[-1] if hits else None

parser = argparse.ArgumentParser()
parser.add_argument("--summary-json", default=None)
parser.add_argument("--out", default=None)
args = parser.parse_args()

BASE = os.path.dirname(__file__)
json_path = args.summary_json or find_best_json(BASE)
if not json_path:
    raise FileNotFoundError("No summary JSON found.")

print(f"Using: {json_path}")
with open(json_path) as f:
    data = json.load(f)

run_label = (
    f"DFT-PBE  ·  {data.get('ed_mode','?')} mode  ·  "
    f"{data.get('direction_count','?')} dirs  ·  "
    f"{data.get('ed_scan_supercell_atoms','?')} atoms"
)

# ── literature / reference values ────────────────────────────────────────────
LIT = {
    "In": {"value": 3.5,  "label": "Exp. min\n(Beserman 1986)", "range": (3, 4)},
    "P":  {"value": 8.0,  "label": "Exp.\n(Beserman 1986)",    "range": None},
}
NIEL_EFF = {"In": 8.5, "P": 8.5}   # approximate NIEL-community effective Ed

# ── colours ──────────────────────────────────────────────────────────────────
C_SOFT   = "#d32f2f"     # softest (minimum Ed) direction
C_HARD   = "#1565c0"     # hardest direction
C_MED    = "#888888"     # everything else
C_IN     = "#1565c0"
C_P      = "#b71c1c"
C_LIT    = "#2e7d32"
C_NIEL   = "#e65100"

fig = plt.figure(figsize=(15, 11))
fig.patch.set_facecolor("#f8f9fa")
gs = gridspec.GridSpec(2, 2, hspace=0.42, wspace=0.32,
                       height_ratios=[1.15, 1])

# ─────────────────────────────────────────────────────────────────────────────
# Panels A & B — barrier curves per element
# ─────────────────────────────────────────────────────────────────────────────
def plot_barrier_panel(ax, site_result, elem_color, title):
    directions = site_result["direction_results"]
    if not directions:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes)
        return

    best_ev   = site_result["ed_eV"]
    best_dir  = site_result["best_direction"]

    all_energies = [pt["energy_ev"]
                    for dr in directions
                    for pt in dr["scan"]]
    y_max = min(max(all_energies) * 1.05, best_ev * 4) if all_energies else 20
    y_max = max(y_max, best_ev * 1.6)

    for dr in sorted(directions, key=lambda d: d["best_energy_ev"], reverse=True):
        pts   = sorted(dr["scan"], key=lambda p: p["distance_angstrom"])
        xs    = [p["distance_angstrom"] for p in pts]
        ys    = [p["energy_ev"]         for p in pts]
        is_best = (dr["direction"] == best_dir)
        is_art  = (dr["status"] == "ignored" or dr["best_energy_ev"] < 0.4)

        if is_art:
            color, lw, zo, alpha = "#cccccc", 0.8, 1, 0.5
        elif is_best:
            color, lw, zo, alpha = C_SOFT, 2.5, 4, 1.0
        else:
            # shade by barrier height
            frac  = min(dr["best_energy_ev"] / (y_max + 1e-9), 1.0)
            color = plt.cm.Blues(0.35 + 0.55 * frac)
            lw, zo, alpha = 1.2, 2, 0.75

        ax.plot(xs, ys, color=color, linewidth=lw, alpha=alpha, zorder=zo)
        if is_best:
            # mark the Ed point
            ax.scatter([dr["best_distance_angstrom"]], [dr["best_energy_ev"]],
                       color=C_SOFT, s=60, zorder=5)
            ax.annotate(
                f"  Ed = {best_ev:.2f} eV\n  ({best_dir})",
                xy=(dr["best_distance_angstrom"], dr["best_energy_ev"]),
                fontsize=8.5, color=C_SOFT, fontweight="bold",
                xytext=(5, 4), textcoords="offset points"
            )

    ax.axhline(0, color="#999", linewidth=0.8, linestyle="--")
    ax.set_xlim(left=0)
    ax.set_ylim(-1, y_max)
    ax.set_xlabel("Displacement distance  (Å)", fontsize=10)
    ax.set_ylabel("ΔE  (eV)", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_facecolor("#ffffff")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.spines[["top","right"]].set_visible(False)

    legend_elements = [
        Line2D([0],[0], color=C_SOFT,   lw=2.5, label=f"Softest dir → Ed = {best_ev:.2f} eV"),
        Line2D([0],[0], color=C_MED,    lw=1.2, label="Other directions"),
        Line2D([0],[0], color="#cccccc", lw=0.8, label="Ignored / artifact"),
    ]
    ax.legend(handles=legend_elements, fontsize=8, loc="upper left")

for site in data["site_results"]:
    elem = site["element"]
    if elem == "In":
        ax = fig.add_subplot(gs[0, 0])
        plot_barrier_panel(ax, site, C_IN,
            f"In  —  displacement barrier curves\n{run_label}")
    elif elem == "P":
        ax = fig.add_subplot(gs[0, 1])
        plot_barrier_panel(ax, site, C_P,
            f"P  —  displacement barrier curves\n{run_label}")

# ─────────────────────────────────────────────────────────────────────────────
# Panel C — Ed comparison bar chart
# ─────────────────────────────────────────────────────────────────────────────
ax3 = fig.add_subplot(gs[1, :])

dft_in = data["ed_values_eV"]["In"]
dft_p  = data["ed_values_eV"]["P"]

categories = [
    "Ed(In)\nThis work\n(DFT-PBE)",
    "Ed(In)\nExp. min\n(Beserman 1986)",
    "Ed(In)\nNIEL eff.\n(community)",
    "Ed(P)\nThis work\n(DFT-PBE)",
    "Ed(P)\nExp.\n(Beserman 1986)",
    "Ed(P)\nNIEL eff.\n(community)",
]
values  = [dft_in, LIT["In"]["value"], NIEL_EFF["In"],
           dft_p,  LIT["P"]["value"],  NIEL_EFF["P"]]
colors  = [C_IN, C_LIT, C_NIEL,
           C_P,  C_LIT, C_NIEL]
alphas  = [1.0, 0.75, 0.6,
           1.0, 0.75, 0.6]

x = np.arange(len(categories))
bars = ax3.bar(x, values, color=colors,
               alpha=1.0, width=0.6, zorder=3,
               edgecolor="white", linewidth=1.2)
for bar, alpha in zip(bars, alphas):
    bar.set_alpha(alpha)

# error bar for experimental In range
ax3.errorbar([1], [LIT["In"]["value"]],
             yerr=[[LIT["In"]["value"] - LIT["In"]["range"][0]],
                   [LIT["In"]["range"][1] - LIT["In"]["value"]]],
             fmt="none", color="#1b5e20", capsize=6, linewidth=2, zorder=5)

for bar, val in zip(bars, values):
    ax3.text(bar.get_x() + bar.get_width()/2, val + 0.15,
             f"{val:.2f}", ha="center", va="bottom",
             fontsize=9, fontweight="bold")

ax3.set_xticks(x)
ax3.set_xticklabels(categories, fontsize=9)
ax3.set_ylabel("Displacement threshold  Ed  (eV)", fontsize=11)
ax3.set_title(
    "Ed summary — InP (JVASP-1183)  vs  literature",
    fontsize=12, fontweight="bold"
)
ax3.set_ylim(0, max(values) * 1.35)
ax3.set_facecolor("#ffffff")
ax3.grid(True, axis="y", linestyle="--", alpha=0.35)
ax3.spines[["top","right"]].set_visible(False)

# vertical separator between In and P groups
ax3.axvline(2.5, color="#999", linewidth=1.0, linestyle=":")
ax3.text(0.97, 0.93, "In sublattice", transform=ax3.transAxes,
         ha="right", fontsize=9, color=C_IN, style="italic",
         bbox=dict(facecolor="white", edgecolor="none", alpha=0.7))
ax3.text(1.03, 0.93, "P sublattice", transform=ax3.transAxes,
         ha="left", fontsize=9, color=C_P, style="italic",
         bbox=dict(facecolor="white", edgecolor="none", alpha=0.7))

# source note
ax3.text(0.01, 0.04,
    "Exp. min = direction-specific minimum (along [111], Beserman & Bernstein, PRB 1986)\n"
    "NIEL eff. = orientation-averaged effective Ed used in displacement damage calculations",
    transform=ax3.transAxes, fontsize=7.5, color="#555",
    va="bottom")

# ── suptitle ─────────────────────────────────────────────────────────────────
fig.suptitle(
    "InP (JVASP-1183)  —  Displacement Threshold Energy  Ed\n"
    "DFT-PBE · Quantum ESPRESSO · gamma-only k-points",
    fontsize=13, fontweight="bold", y=1.01
)

out = args.out or os.path.join(BASE, "InP_Ed_results.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved: {out}")
