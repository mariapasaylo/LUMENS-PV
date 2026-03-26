#!/usr/bin/env bash
# Best-quality InP Ed run: static mode, 2x2x2 supercell (16 atoms), highsym directions
#
# Why highsym over fibonacci:
#   Fibonacci sampling is random w.r.t. crystallographic axes. For zinc-blende InP,
#   the soft channel is [100]; fibonacci may never sample it. highsym mode samples
#   exactly the [100], [110], [111] families (13 directions total) — guaranteed to
#   find the true minimum.
#
# Why static over relax:
#   Relax mode requires ionic relaxation after each displacement; a 54-atom cell
#   takes >60 min/calc (far too slow). Static mode (16 atoms, ~3 min/calc) fits
#   within 10h for 13 dirs x 7 pts x 2 sites = 182 calculations.
#   Static Ed values are ~10-30% higher than relax (systematic bias), but with
#   correct crystallographic directions this gives far more reliable Ed minima.
#
#SBATCH --job-name=ed-inp-best3
#SBATCH --partition=hpg-default
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --mem=64G
#SBATCH --time=10:00:00
#SBATCH --output=logs/ed_inp_best3_%j.out

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$HOME/local/dsi3/miniforge/envs/dsi3_full/bin/python3}"
RUNNER="$HOME/LUMENS-PV/calculating_energy_threshold_displacement/run_ed_pipeline.py"
PSEUDO_DIR="$HOME/LUMENS-PV/pseudopotentials_psl_pbe_full"
RESULTS_DIR="$HOME/LUMENS-PV/calculating_energy_threshold_displacement/best_run_results"

if [[ -n "${SLURM_TMPDIR:-}" ]]; then
  JOB_LOCAL_SCRATCH="$SLURM_TMPDIR/lumens-ed-${SLURM_JOB_ID:-$$}"
elif [[ -d /scratch/local ]]; then
  JOB_LOCAL_SCRATCH="/scratch/local/$USER/lumens-ed/${SLURM_JOB_ID:-$$}"
else
  JOB_LOCAL_SCRATCH="${TMPDIR:-/tmp}/$USER/lumens-ed/${SLURM_JOB_ID:-$$}"
fi
WORKSPACE="$JOB_LOCAL_SCRATCH/workspace"
QE_SCRATCH_ROOT="$JOB_LOCAL_SCRATCH/qe"

cleanup() { rm -rf "$JOB_LOCAL_SCRATCH"; }
trap cleanup EXIT

module purge
module load gcc/14.2.0 openmpi/5.0.7 espresso/7.3.1

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export PYTHONUNBUFFERED=1
export QE_SCRATCH_ROOT

mkdir -p logs "$RESULTS_DIR" "$WORKSPACE" "$QE_SCRATCH_ROOT"

"$PYTHON_BIN" "$RUNNER" \
  --formula InP \
  --material-id JVASP-1183 \
  --workspace "$WORKSPACE" \
  --results-dir "$RESULTS_DIR" \
  --skip-aggregate-outputs \
  --pseudo-dir "$PSEUDO_DIR" \
  --qe-executable pw.x \
  --nprocs 32 \
  --qe-launcher mpirun \
  --skip-qe-relax \
  --force-qe \
  --direction-mode highsym \
  --ed-directions 13 \
  --ed-points 7 \
  --refine-points 3 \
  --ed-mode static \
  --site-selection representative \
  --element-aggregation min \
  --supercell-min-length 8.0 \
  --kpoint-density 0.08 \
  --ed-kpoint-mode gamma \
  --ed-cutoff-scale 1.00 \
  --reliability-floor-ev 0.20 \
  --occupations-mode auto \
  --spin-mode auto \
  --relax-force-conv-thr 1.0e-4 \
  --relax-etot-conv-thr 1.0e-6 \
  --relax-electron-conv-thr 1.0e-6 \
  --ed-electron-conv-thr 1.0e-6 \
  --relax-degauss 0.01 \
  --ed-degauss 0.01 \
  --mixing-beta 0.30 \
  --vdw-corr dft-d3 \
  --idealize-relaxed-structure \
  --relax-timeout 3600 \
  --ed-timeout 900

echo "Finished best-quality InP run (highsym static) -> ${RESULTS_DIR}"
