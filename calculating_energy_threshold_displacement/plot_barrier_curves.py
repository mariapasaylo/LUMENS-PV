#!/usr/bin/env python3
"""
Figure 2: Direction-resolved Ed barrier curves + comparison to experiment.

Panel A (top-left):  In barrier curves from highsym run (13 crystallographic directions).
Panel B (top-right): P barrier curves from highsym run (with artifact annotation).
Panel C (bottom):    Ed comparison — DFT values vs experimental references.

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
    for pattern in [
        "best_run_results/InP_JVASP-1183_summary.json",
        "conv_results_d10_p09/InP_JVASP-1183_summary.json",
        "conv_results_d10_p07/InP_JVASP-1183_summary.json",
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

n_dirs = data.get("direction_count", "?")
n_atoms = data.get("ed_scan_supercell_atoms", "?")
ed_mode = data.get("ed_mode", "?")

# ── literature / reference values ────────────────────────────────────────────
LIT_IN = {"value": 3.5, "range": (3.0, 4.0), "label": "Exp. min\n(Beserman 1986)"}
LIT_P  = {"value": 8.7, "range": (6.7, 8.7), "label": "Exp.\n(Beserman 1986)"}
NIEL_EFF = {"In": 8.5, "P": 8.5}

# Fibonacci converged value for P (from convergence study, dirs=10, pts=7..12)
FIBO_ED_P = 6.454

# ── colours ──────────────────────────────────────────────────────────────────
C_SOFT   = "#d32f2f"
C_ART    = "#cccccc"
C_IN     = "#1565c0"
C_P      = "#b71c1c"
C_LIT    = "#2e7d32"
C_NIEL   = "#e65100"
C_FIBO   = "#7b1fa2"

fig = plt.figure(figsize=(15, 12))
fig.patch.set_facecolor("#f8f9fa")
gs = gridspec.GridSpec(2, 2, hspace=0.42, wspace=0.32,
                       height_ratios=[1.15, 1])

# ─────────────────────────────────────────────────────────────────────────────
# Panels A & B — barrier curves per element
# ─────────────────────────────────────────────────────────────────────────────
def plot_barrier_panel(ax, site_result, title, artifact_note=None):
    directions = site_result["direction_results"]
    if not directions:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes)
        return

    best_ev  = site_result["ed_eV"]
    best_dir = site_result["best_direction"]

    # Separate [100]-family, [111]-family, [110]-family for colour coding
    family_100 = {"[100]", "[010]", "[001]"}
    family_111 = {"[111]", "[11-1]", "[1-11]", "[-111]"}
    family_110 = {"[110]", "[1-10]", "[101]", "[10-1]", "[011]", "[01-1]"}

    # Compute sensible y-limits: ignore extreme [110] barriers
    reasonable_energies = []
    for dr in directions:
        if dr["direction"] not in family_110:
            for pt in dr["scan"]:
                reasonable_energies.append(pt["energy_ev"])
    if reasonable_energies:
        y_max = min(max(reasonable_energies) * 1.2, 15)
        y_min = min(min(reasonable_energies) * 1.1, -2)
    else:
        y_max, y_min = 15, -2

    for dr in sorted(directions, key=lambda d: d["best_energy_ev"], reverse=True):
        pts  = sorted(dr["scan"], key=lambda p: p["distance_angstrom"])
        xs   = [p["distance_angstrom"] for p in pts]
        ys   = [p["energy_ev"]         for p in pts]
        dname = dr["direction"]
        is_best = (dname == best_dir)

        # Skip [110] family entirely (barriers > 40 eV, off-scale)
        if dname in family_110:
            continue

        has_negative = any(e < -0.1 for e in ys)
        is_art = (dr["status"] == "ignored" or dr["best_energy_ev"] < 0.4)

        if is_art or (has_negative and dr["best_energy_ev"] < 1.0):
            color, lw, zo, alpha, ls = "#cccccc", 1.5, 1, 0.6, "--"
        elif is_best:
            color, lw, zo, alpha, ls = C_SOFT, 2.5, 4, 1.0, "-"
        elif dname in family_100:
            color, lw, zo, alpha, ls = "#1976d2", 2.0, 3, 0.85, "-"
        elif dname in family_111:
            color, lw, zo, alpha, ls = "#e65100", 1.5, 2, 0.75, "-"
        else:
            frac = min(dr["best_energy_ev"] / (y_max + 1e-9), 1.0)
            color = plt.cm.Blues(0.35 + 0.55 * frac)
            lw, zo, alpha, ls = 1.2, 2, 0.65, "-"

        ax.plot(xs, ys, color=color, linewidth=lw, alpha=alpha,
                zorder=zo, linestyle=ls, label=dname if is_best else None)

        if is_best:
            ax.scatter([dr["best_distance_angstrom"]], [dr["best_energy_ev"]],
                       color=C_SOFT, s=70, zorder=5, edgecolors="white", linewidths=0.5)
            ax.annotate(
                f"Ed = {best_ev:.2f} eV\n({best_dir})",
                xy=(dr["best_distance_angstrom"], dr["best_energy_ev"]),
                fontsize=9, color=C_SOFT, fontweight="bold",
                xytext=(8, 6), textcoords="offset points",
                bbox=dict(facecolor="white", edgecolor=C_SOFT, alpha=0.85,
                          boxstyle="round,pad=0.3"),
            )

    ax.axhline(0, color="#999", linewidth=0.8, linestyle="--", zorder=0)
    ax.set_xlim(left=0)
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel("Displacement distance  (A)", fontsize=10)
    ax.set_ylabel("dE  (eV)", fontsize=10)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.set_facecolor("#ffffff")
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)

    # Legend
    legend_handles = [
        Line2D([0], [0], color=C_SOFT, lw=2.5, label=f"Softest: Ed = {best_ev:.2f} eV"),
        Line2D([0], [0], color="#1976d2", lw=2.0, label="[100] family"),
        Line2D([0], [0], color="#e65100", lw=1.5, label="[111] family"),
        Line2D([0], [0], color="#cccccc", lw=1.5, ls="--", label="Artifact (dE < 0)"),
    ]
    ax.legend(handles=legend_handles, fontsize=7.5, loc="upper left",
              framealpha=0.9)

    if artifact_note:
        ax.text(0.97, 0.03, artifact_note,
                transform=ax.transAxes, fontsize=7.5, color="#555",
                ha="right", va="bottom",
                bbox=dict(facecolor="#fff9c4", edgecolor="#f9a825",
                          alpha=0.9, boxstyle="round,pad=0.4"))

# Plot panels A & B
for site in data["site_results"]:
    elem = site["element"]
    if elem == "In":
        ax = fig.add_subplot(gs[0, 0])
        plot_barrier_panel(ax, site,
            f"In  --  barrier curves  ({n_dirs} highsym dirs, {ed_mode}, {n_atoms} atoms)")
    elif elem == "P":
        ax = fig.add_subplot(gs[0, 1])
        note = (
            "[111] barrier = 0.34 eV is a static-mode artifact:\n"
            "frozen lattice allows P to slip into interstitial\n"
            "(dE goes negative). Relax mode would fix this."
        )
        plot_barrier_panel(ax, site,
            f"P  --  barrier curves  ({n_dirs} highsym dirs, {ed_mode}, {n_atoms} atoms)",
            artifact_note=note)

# ─────────────────────────────────────────────────────────────────────────────
# Panel C — Ed comparison bar chart
# ─────────────────────────────────────────────────────────────────────────────
ax3 = fig.add_subplot(gs[1, :])

# Use highsym In value, fibonacci converged P value
dft_in_highsym = data["ed_values_eV"]["In"]

# Find P [100] value from highsym data
p_100_ev = None
for site in data["site_results"]:
    if site["element"] == "P":
        for dr in site["direction_results"]:
            if dr["direction"] == "[100]":
                p_100_ev = dr["best_energy_ev"]
                break

categories = [
    "Ed(In)\nhighsym [001]\n(this work)",
    "Ed(In)\nExp. min\n(Beserman 1986)",
    "Ed(In)\nNIEL eff.",
    "",
    "Ed(P)\nfibonacci\n(this work)",
    "Ed(P)\nhighsym [100]\n(this work)",
    "Ed(P)\nExp.\n(Beserman 1986)",
    "Ed(P)\nNIEL eff.",
]
values = [
    dft_in_highsym,
    LIT_IN["value"],
    NIEL_EFF["In"],
    0,
    FIBO_ED_P,
    p_100_ev or 0,
    LIT_P["value"],
    NIEL_EFF["P"],
]
colors = [
    C_IN, C_LIT, C_NIEL,
    "#ffffff",
    C_FIBO, C_P, C_LIT, C_NIEL,
]
alphas = [
    1.0, 0.75, 0.6,
    0.0,
    0.85, 0.85, 0.75, 0.6,
]

x = np.arange(len(categories))
bars = ax3.bar(x, values, color=colors,
               alpha=1.0, width=0.6, zorder=3,
               edgecolor="white", linewidth=1.2)
for bar, alpha in zip(bars, alphas):
    bar.set_alpha(alpha)

# Experimental range error bars
ax3.errorbar([1], [LIT_IN["value"]],
             yerr=[[LIT_IN["value"] - LIT_IN["range"][0]],
                   [LIT_IN["range"][1] - LIT_IN["value"]]],
             fmt="none", color="#1b5e20", capsize=6, linewidth=2, zorder=5)
ax3.errorbar([6], [LIT_P["value"]],
             yerr=[[LIT_P["value"] - LIT_P["range"][0]],
                   [LIT_P["range"][1] - LIT_P["value"]]],
             fmt="none", color="#1b5e20", capsize=6, linewidth=2, zorder=5)

# Value labels
for i, (bar, val) in enumerate(zip(bars, values)):
    if val > 0:
        ax3.text(bar.get_x() + bar.get_width() / 2, val + 0.15,
                 f"{val:.2f}", ha="center", va="bottom",
                 fontsize=9, fontweight="bold")

ax3.set_xticks(x)
ax3.set_xticklabels(categories, fontsize=8)
ax3.set_ylabel("Displacement threshold  Ed  (eV)", fontsize=11)
ax3.set_title("Ed summary  --  InP (JVASP-1183)  vs  literature",
              fontsize=12, fontweight="bold")
ax3.set_ylim(0, max(v for v in values if v > 0) * 1.3)
ax3.set_facecolor("#ffffff")
ax3.grid(True, axis="y", linestyle="--", alpha=0.35)
ax3.spines[["top", "right"]].set_visible(False)

# Vertical separator
ax3.axvline(3, color="#999", linewidth=1.0, linestyle=":")
ax3.text(1.0, 0.95, "In sublattice", transform=ax3.transAxes,
         ha="right", fontsize=9, color=C_IN, style="italic",
         bbox=dict(facecolor="white", edgecolor="none", alpha=0.7))

# Annotation explaining DFT values
ax3.text(0.01, 0.04,
    "In: highsym [001] = softest crystallographic direction (DFT-PBE, static, gamma-only)\n"
    "P: fibonacci = 10-direction average (static mode artifact in [111] excluded)\n"
    "Exp: Beserman & Bernstein, Phys. Rev. B 33, 7281 (1986)",
    transform=ax3.transAxes, fontsize=7.5, color="#555", va="bottom")

# ── suptitle ─────────────────────────────────────────────────────────────────
fig.suptitle(
    "InP (JVASP-1183)  --  Displacement Threshold Energy  Ed\n"
    "DFT-PBE  |  Quantum ESPRESSO  |  gamma-only k-points  |  2x2x2 supercell (16 atoms)",
    fontsize=13, fontweight="bold", y=1.01
)

out = args.out or os.path.join(BASE, "InP_Ed_results.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved: {out}")

# Print summary
print(f"\n=== Ed Summary ===")
print(f"Ed(In) = {dft_in_highsym:.2f} eV  [highsym {data['site_results'][0].get('best_direction','')}]")
print(f"  Exp:  3.0 - 4.0 eV  (Beserman 1986)")
if p_100_ev:
    print(f"Ed(P)  = {p_100_ev:.2f} eV  [highsym [100]]  (artifact in [111]: {data['ed_values_eV']['P']:.2f} eV)")
print(f"Ed(P)  = {FIBO_ED_P:.2f} eV  [fibonacci converged, dirs=10]")
print(f"  Exp:  6.7 - 8.7 eV  (Beserman 1986)")
