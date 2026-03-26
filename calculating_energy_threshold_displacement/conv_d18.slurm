#!/usr/bin/env bash
#SBATCH --job-name=ed-conv-d18
#SBATCH --partition=hpg-default
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --mem=192G
#SBATCH --time=14:00:00
#SBATCH --output=logs/ed_conv_d18_%j.out

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-$HOME/local/dsi3/miniforge/envs/dsi3_full/bin/python3}"
RUNNER="$HOME/LUMENS-PV/calculating_energy_threshold_displacement/run_ed_pipeline.py"
PSEUDO_DIR="$HOME/LUMENS-PV/pseudopotentials_psl_pbe_full"
RESULTS_DIR="$HOME/LUMENS-PV/calculating_energy_threshold_displacement/conv_results_d18_p07"

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
  --direction-mode fibonacci \
  --ed-directions 18 \
  --ed-points 7 \
  --refine-points 0 \
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

echo "Finished: dirs=18 pts=7"
