#!/usr/bin/env python3
"""
Poster figure: InP displacement threshold energy (Ed).

Two-panel figure:
  (a) Direction-resolved barrier curves for In and P
  (b) Ed comparison: DFT vs experiment

Usage:
    python3 plot_poster_figure.py
    python3 plot_poster_figure.py --summary-json path/to/InP_summary.json
"""
from __future__ import annotations
import argparse, json, glob, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch

# ── data loading ─────────────────────────────────────────────────────────────
def find_best_json(base):
    for pat in [
        "best_run_results/InP_JVASP-1183_summary.json",
        "conv_results_d10_p09/InP_JVASP-1183_summary.json",
    ]:
        p = os.path.join(base, pat)
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

# ── constants ────────────────────────────────────────────────────────────────
# Experimental references (Beserman & Bernstein, Phys. Rev. B 33, 7281, 1986)
EXP_IN = {"val": 3.5, "lo": 3.0, "hi": 4.0}
EXP_P  = {"val": 8.7, "lo": 6.7, "hi": 8.7}

# Fibonacci converged Ed(P) from convergence study (dirs=10, pts=7-12)
FIBO_P = 6.454

# Direction families for zinc-blende
FAM_100 = {"[100]", "[010]", "[001]"}
FAM_110 = {"[110]", "[1-10]", "[101]", "[10-1]", "[011]", "[01-1]"}
FAM_111 = {"[111]", "[11-1]", "[1-11]", "[-111]"}

# ── colour palette (accessible, professional) ────────────────────────────────
PAL = {
    "dft_in":  "#2166ac",   # steel blue
    "dft_p":   "#b2182b",   # brick red
    "exp":     "#4daf4a",   # green
    "100":     "#2166ac",   # blue family
    "111_soft":"#d6604d",   # muted red-orange
    "111_hard":"#f4a582",   # light salmon
    "art":     "#bdbdbd",   # light grey
    "bg":      "#ffffff",
}

# ── figure setup ─────────────────────────────────────────────────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5),
                                gridspec_kw={"width_ratios": [1.2, 1], "wspace": 0.35})
fig.patch.set_facecolor(PAL["bg"])

# ─────────────────────────────────────────────────────────────────────────────
# Panel (a): Barrier curves — In and P on same axes, key directions only
# ─────────────────────────────────────────────────────────────────────────────
ax1.set_facecolor(PAL["bg"])

for site in data["site_results"]:
    elem = site["element"]
    best_dir = site["best_direction"]

    for dr in site["direction_results"]:
        dname = dr["direction"]

        # Skip [110] family (off-scale, 18-50 eV) and most [111] hard dirs
        if dname in FAM_110:
            continue

        pts = sorted(dr["scan"], key=lambda p: p["distance_angstrom"])
        xs = [p["distance_angstrom"] for p in pts]
        ys = [p["energy_ev"] for p in pts]

        # Clip to reasonable range for readability
        clipped = [(x, y) for x, y in zip(xs, ys) if y <= 20]
        if not clipped:
            continue
        xs_c, ys_c = zip(*clipped)

        if elem == "In":
            if dname == best_dir:  # [-111]
                ax1.plot(xs_c, ys_c, color=PAL["dft_in"], lw=2.8, zorder=5, solid_capstyle="round")
                # Mark Ed point
                peak_y = dr["best_energy_ev"]
                peak_x = dr["best_distance_angstrom"]
                if peak_y <= 20:
                    ax1.scatter([peak_x], [peak_y], color=PAL["dft_in"], s=80,
                                zorder=6, edgecolors="white", linewidths=1.5)
            elif dname in FAM_100:
                # Only show [100] as representative
                if dname == "[100]":
                    ax1.plot(xs_c, ys_c, color=PAL["dft_in"], lw=1.2, alpha=0.35,
                             zorder=2, linestyle="--")
            elif dname in FAM_111 and dname != "[111]":
                # Other [-111] variants — thin lines
                ax1.plot(xs_c, ys_c, color=PAL["dft_in"], lw=1.0, alpha=0.3, zorder=2)

        elif elem == "P":
            if dname in FAM_100:
                if dname == "[100]":
                    ax1.plot(xs_c, ys_c, color=PAL["dft_p"], lw=2.2, zorder=4, solid_capstyle="round")
                    peak_y = dr["best_energy_ev"]
                    peak_x = dr["best_distance_angstrom"]
                    if peak_y <= 20:
                        ax1.scatter([peak_x], [peak_y], color=PAL["dft_p"], s=60,
                                    zorder=6, edgecolors="white", linewidths=1.5)
            elif dname == "[111]":
                # Artifact — show as dashed grey
                ax1.plot(xs_c, ys_c, color=PAL["art"], lw=1.5, zorder=1,
                         linestyle=":", alpha=0.7)

# Annotations
in_site = [s for s in data["site_results"] if s["element"] == "In"][0]
p_site  = [s for s in data["site_results"] if s["element"] == "P"][0]

in_ed = in_site["ed_eV"]
in_dir = in_site["best_direction"]
in_best_dr = [d for d in in_site["direction_results"] if d["direction"] == in_dir][0]

ax1.annotate(
    f"In: $E_d$ = {in_ed:.1f} eV\n({in_dir})",
    xy=(in_best_dr["best_distance_angstrom"], in_ed),
    xytext=(30, 12), textcoords="offset points",
    fontsize=11, fontweight="bold", color=PAL["dft_in"],
    arrowprops=dict(arrowstyle="-|>", color=PAL["dft_in"], lw=1.5),
    bbox=dict(facecolor="white", edgecolor=PAL["dft_in"], alpha=0.92,
              boxstyle="round,pad=0.4", linewidth=1.2),
)

# P [100] annotation
p_100 = [d for d in p_site["direction_results"] if d["direction"] == "[100]"][0]
p_100_ev = p_100["best_energy_ev"]
p_100_x = p_100["best_distance_angstrom"]
if p_100_ev <= 20:
    ax1.annotate(
        f"P: $E_d$ = {p_100_ev:.1f} eV\n([100])",
        xy=(p_100_x, p_100_ev),
        xytext=(-50, 20), textcoords="offset points",
        fontsize=11, fontweight="bold", color=PAL["dft_p"],
        arrowprops=dict(arrowstyle="-|>", color=PAL["dft_p"], lw=1.5),
        bbox=dict(facecolor="white", edgecolor=PAL["dft_p"], alpha=0.92,
                  boxstyle="round,pad=0.4", linewidth=1.2),
    )

ax1.axhline(0, color="#cccccc", lw=0.8, zorder=0)
ax1.set_xlim(0, 5.2)
ax1.set_ylim(-3, 18)
ax1.set_xlabel("Displacement distance  ($\\AA$)", fontsize=13, labelpad=8)
ax1.set_ylabel("$\\Delta E$  (eV)", fontsize=13, labelpad=8)
ax1.tick_params(labelsize=11)
ax1.spines[["top", "right"]].set_visible(False)
ax1.spines["bottom"].set_linewidth(1.2)
ax1.spines["left"].set_linewidth(1.2)

# Legend
leg_handles = [
    Line2D([0], [0], color=PAL["dft_in"], lw=2.8, label="In (softest: $[\\overline{1}11]$)"),
    Line2D([0], [0], color=PAL["dft_p"], lw=2.2, label="P (softest: $[100]$)"),
    Line2D([0], [0], color=PAL["art"], lw=1.5, ls=":", label="P $[111]$ artifact"),
    Line2D([0], [0], color=PAL["dft_in"], lw=1.0, alpha=0.35, ls="--", label="Other directions"),
]
ax1.legend(handles=leg_handles, fontsize=10, loc="upper left", framealpha=0.95,
           edgecolor="#cccccc", fancybox=True)

ax1.text(0.02, 0.98, "(a)", transform=ax1.transAxes, fontsize=15,
         fontweight="bold", va="top", ha="left")

# ─────────────────────────────────────────────────────────────────────────────
# Panel (b): Grouped bar chart — DFT vs Experiment
# ─────────────────────────────────────────────────────────────────────────────
ax2.set_facecolor(PAL["bg"])

group_labels = ["$E_d$(In)", "$E_d$(P)"]
dft_vals  = [in_ed, FIBO_P]
exp_vals  = [EXP_IN["val"], EXP_P["val"]]
exp_lo    = [EXP_IN["lo"], EXP_P["lo"]]
exp_hi    = [EXP_IN["hi"], EXP_P["hi"]]

x_pos = np.array([0, 1.2])
bar_w = 0.35

# DFT bars
bars_dft = ax2.bar(x_pos - bar_w/2 - 0.02, dft_vals, bar_w,
                    color=[PAL["dft_in"], PAL["dft_p"]], zorder=3,
                    edgecolor="white", linewidth=1.5, label="DFT-PBE (this work)")

# Experiment bars
bars_exp = ax2.bar(x_pos + bar_w/2 + 0.02, exp_vals, bar_w,
                    color=PAL["exp"], zorder=3, alpha=0.8,
                    edgecolor="white", linewidth=1.5, label="Experiment")

# Experimental error bars
for i, (xp, val, lo, hi) in enumerate(zip(x_pos, exp_vals, exp_lo, exp_hi)):
    ax2.errorbar(xp + bar_w/2 + 0.02, val,
                 yerr=[[val - lo], [hi - val]],
                 fmt="none", color="#2d7f2d", capsize=7, linewidth=2.2,
                 capthick=2.2, zorder=5)

# Value labels on bars
for bar, val in zip(bars_dft, dft_vals):
    ax2.text(bar.get_x() + bar.get_width()/2, val + 0.25,
             f"{val:.1f}", ha="center", va="bottom",
             fontsize=12, fontweight="bold", color="#333333")

for bar, val in zip(bars_exp, exp_vals):
    ax2.text(bar.get_x() + bar.get_width()/2, val + 0.25,
             f"{val:.1f}", ha="center", va="bottom",
             fontsize=12, fontweight="bold", color="#333333")

ax2.set_xticks(x_pos)
ax2.set_xticklabels(group_labels, fontsize=14, fontweight="bold")
ax2.set_ylabel("$E_d$  (eV)", fontsize=13, labelpad=8)
ax2.set_ylim(0, 12)
ax2.tick_params(labelsize=11, axis="y")
ax2.tick_params(axis="x", length=0)
ax2.spines[["top", "right"]].set_visible(False)
ax2.spines["bottom"].set_linewidth(1.2)
ax2.spines["left"].set_linewidth(1.2)
ax2.yaxis.grid(True, linestyle="--", alpha=0.3, color="#999999")
ax2.set_axisbelow(True)

ax2.legend(fontsize=11, loc="upper right", framealpha=0.95,
           edgecolor="#cccccc", fancybox=True)

# Method note
ax2.text(0.5, -0.18,
    "DFT-PBE  |  static mode  |  QE 7.3  |  $\\Gamma$-only  |  16-atom supercell\n"
    "Exp: Beserman & Bernstein, Phys. Rev. B 33, 7281 (1986)",
    transform=ax2.transAxes, fontsize=8.5, color="#666666",
    ha="center", va="top", linespacing=1.5)

ax2.text(0.02, 0.98, "(b)", transform=ax2.transAxes, fontsize=15,
         fontweight="bold", va="top", ha="left")

# ── save ─────────────────────────────────────────────────────────────────────
out = args.out or os.path.join(os.path.dirname(BASE), "InP_Ed_poster.png")
fig.savefig(out, dpi=300, bbox_inches="tight", facecolor=PAL["bg"],
            pad_inches=0.3)
print(f"Saved: {out}")

# Also save PDF for poster
pdf_out = out.replace(".png", ".pdf")
fig.savefig(pdf_out, bbox_inches="tight", facecolor=PAL["bg"], pad_inches=0.3)
print(f"Saved: {pdf_out}")
