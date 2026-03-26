#!/usr/bin/env python3
"""
InP Ed convergence plot — direction and point sweep.
Run: /home/vm/miniconda3/envs/DSI/bin/python plot_convergence.py
"""
import json, glob, os, re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches

# ── data ─────────────────────────────────────────────────────────────────────
# (dirs, pts, Ed_In_eV, Ed_P_eV)
HARDCODED = [
    (4,  7,  9.408, 7.829),
    (6,  7,  7.540, 4.521),
    (8,  7,  6.585, 6.328),
    (10, 5,  7.129, 6.454),
    (10, 7,  7.095, 6.454),
    (10, 9,  6.943, 6.454),
    (10, 12, 6.803, 6.454),
    (14, 7, 15.754, 0.231),   # Ed(P)=0.231: periodic-image artifact (0.85 Å, 16-atom supercell)
    (18, 7, 16.080, 0.205),   # Ed(P)=0.205: same artifact, Ed(In)=16.080 same issue
]

# Flag clearly unphysical data points (artifact threshold)
ARTIFACT_FLOOR_EV = 0.5   # anything below this for Ed is clearly an artifact
ARTIFACT_CEIL_EV  = 14.0  # anything above this for In in InP is also clearly off

def is_artifact(element, ev):
    if ev < ARTIFACT_FLOOR_EV:
        return True
    if element == "In" and ev > ARTIFACT_CEIL_EV:
        return True
    return False

def load_extra_local():
    rows = list(HARDCODED)
    seen = {(r[0], r[1]) for r in rows}
    pattern = re.compile(r"d(\d+)_p(\d+)")
    base = os.path.dirname(__file__)
    for f in glob.glob(os.path.join(base, "calculating_energy_threshold_displacement",
                                    "conv_results_*", "InP_JVASP-1183_summary.json")):
        m = pattern.search(f)
        if not m:
            continue
        nd, pts = int(m.group(1)), int(m.group(2))
        if (nd, pts) in seen:
            continue
        try:
            d = json.load(open(f))
            ein = d["ed_values_eV"]["In"]
            ep  = d["ed_values_eV"]["P"]
            rows.append((nd, pts, ein, ep))
            seen.add((nd, pts))
        except Exception:
            pass
    return sorted(rows)

data = load_extra_local()

REF = {"In": 8.088, "P": 7.66}

dir_sweep = sorted([(nd, ein, ep) for nd, pts, ein, ep in data if pts == 7], key=lambda x: x[0])
pts_sweep = sorted([(pts, ein, ep) for nd, pts, ein, ep in data if nd == 10], key=lambda x: x[0])

# ── style ─────────────────────────────────────────────────────────────────────
C_IN    = "#1565c0"
C_P     = "#b71c1c"
C_ART   = "#888888"
MS = 8

fig = plt.figure(figsize=(15, 6.5))
fig.patch.set_facecolor("#f8f9fa")
gs = gridspec.GridSpec(1, 2, wspace=0.38)

def style_ax(ax, title, xlabel):
    ax.set_facecolor("#ffffff")
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.set_ylabel("Displacement threshold  Ed  (eV)", fontsize=11)
    ax.axhline(REF["In"], color=C_IN, linestyle="--", linewidth=1.4, alpha=0.6,
               label=f"Ed(In) lit. = {REF['In']} eV")
    ax.axhline(REF["P"],  color=C_P,  linestyle="--", linewidth=1.4, alpha=0.6,
               label=f"Ed(P)  lit. = {REF['P']} eV")
    ax.set_ylim(-0.3, 18)
    ax.grid(True, linestyle="--", alpha=0.35, color="#cccccc")
    ax.spines[["top","right"]].set_visible(False)

def plot_series(ax, xs, ys, color, marker, label):
    # Split into clean and artifact points
    clean_x, clean_y = [], []
    art_x, art_y = [], []
    elem = "In" if "In" in label else "P"
    for x, y in zip(xs, ys):
        if is_artifact(elem, y):
            art_x.append(x)
            art_y.append(y)
        else:
            clean_x.append(x)
            clean_y.append(y)

    # Plot clean points connected
    if clean_x:
        ax.plot(clean_x, clean_y, color=color, marker=marker, markersize=MS,
                linewidth=2.0, label=label, zorder=3)
        for x, y in zip(clean_x, clean_y):
            ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points",
                        xytext=(5, 6), fontsize=8.5, color=color, fontweight="bold")

    # Plot artifact points differently (X marker, greyed)
    for x, y in zip(art_x, art_y):
        ax.scatter([x], [min(y, 17.5)], color=C_ART, marker="x", s=80,
                   linewidths=2.5, zorder=4)
        label_text = f"{y:.2f} ⚠" if y >= ARTIFACT_FLOOR_EV else f"≈0 ⚠"
        ax.annotate(label_text, (x, min(y, 17.5)), textcoords="offset points",
                    xytext=(5, -14), fontsize=8, color=C_ART, style="italic")

# ── panel 1: direction sweep ──────────────────────────────────────────────────
ax1 = fig.add_subplot(gs[0])
if dir_sweep:
    xs  = [r[0] for r in dir_sweep]
    ins = [r[1] for r in dir_sweep]
    ps  = [r[2] for r in dir_sweep]
    plot_series(ax1, xs, ins, C_IN, "o", "Ed(In)  DFT")
    plot_series(ax1, xs, ps,  C_P,  "s", "Ed(P)   DFT")
    ax1.set_xticks(xs)

style_ax(ax1,
         "Direction convergence\n(scan points = 7, no refinement)",
         "Number of Fibonacci directions")

ax1.text(0.03, 0.97,
         "⚠ = artifact (grey ✕)\n"
         "Fibonacci sampling does not\n"
         "guarantee hitting crystallographic\n"
         "soft channels — values non-monotonic.\n"
         "Small supercell (16 atoms) causes\n"
         "periodic-image artifacts at large N.",
         transform=ax1.transAxes, fontsize=8, va="top",
         bbox=dict(boxstyle="round,pad=0.45", facecolor="#fff9c4",
                   edgecolor="#f9a825", alpha=0.92))

handles, labels = ax1.get_legend_handles_labels()
art_patch = mpatches.Patch(facecolor="none", edgecolor=C_ART,
                            label="Artifact / unreliable")
ax1.legend(handles=handles + [art_patch], fontsize=9, loc="lower right")

# ── panel 2: point sweep ──────────────────────────────────────────────────────
ax2 = fig.add_subplot(gs[1])
if pts_sweep:
    xs  = [r[0] for r in pts_sweep]
    ins = [r[1] for r in pts_sweep]
    ps  = [r[2] for r in pts_sweep]
    plot_series(ax2, xs, ins, C_IN, "o", "Ed(In)  DFT")
    plot_series(ax2, xs, ps,  C_P,  "s", "Ed(P)   DFT")
    ax2.set_xticks(sorted(set(xs)))
    if len(xs) < 4:
        ax2.text(0.97, 0.50, "more data\nstill running…",
                 transform=ax2.transAxes, fontsize=9, va="center", ha="right",
                 color="#777", style="italic")

style_ax(ax2,
         "Scan-point convergence\n(directions = 10, no refinement)",
         "Number of coarse scan points")
ax2.legend(fontsize=9, loc="lower right")

# ── suptitle ──────────────────────────────────────────────────────────────────
fig.suptitle(
    "InP (JVASP-1183)  —  Displacement Threshold  Ed  Convergence Study\n"
    "DFT-PBE · static mode · gamma-only k-points · 2×2×2 supercell (16 atoms)",
    fontsize=12, fontweight="bold", y=1.03
)

out = os.path.join(os.path.dirname(__file__), "InP_Ed_convergence.png")
fig.savefig(out, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved: {out}")

print("\n=== Direction sweep (pts=7) ===")
print(f"{'dirs':>6}  {'Ed(In)':>8}  {'Ed(P)':>8}  {'Ref In':>8}  {'Ref P':>8}  {'Note'}")
for nd, ein, ep in dir_sweep:
    note = []
    if is_artifact("In", ein): note.append("In=artifact")
    if is_artifact("P", ep):   note.append("P=artifact")
    print(f"{nd:6d}  {ein:8.3f}  {ep:8.3f}  {REF['In']:8.3f}  {REF['P']:8.3f}  {', '.join(note)}")

print("\n=== Point sweep (dirs=10) ===")
print(f"{'pts':>6}  {'Ed(In)':>8}  {'Ed(P)':>8}")
for pts, ein, ep in pts_sweep:
    print(f"{pts:6d}  {ein:8.3f}  {ep:8.3f}")
