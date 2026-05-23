#!/usr/bin/env bash
#SBATCH --job-name=ed-gpu-screen
#SBATCH --partition=hpg-turin
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gpus=1
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=logs/ed_gpu_screen_%A_%a.out

set -euo pipefail

INPUT_FILE="${1:?usage: sbatch --array=1-N run_ed_pipeline_screen_gpu_l4.slurm /abs/path/materials.csv}"
shift

CODE_ROOT="${CODE_ROOT:-$HOME/LUMENS-PV}"
PYTHON_BIN="${PYTHON_BIN:-$HOME/local/dsi3/miniforge/envs/dsi3_full/bin/python3}"
RUNNER="$CODE_ROOT/calculating_energy_threshold_displacement/run_ed_pipeline.py"
RESULTS_DIR="${RESULTS_DIR:-$CODE_ROOT/calculating_energy_threshold_displacement/gpu_screen_outputs}"
if [[ -n "${SLURM_TMPDIR:-}" ]]; then
  DEFAULT_JOB_LOCAL_SCRATCH="$SLURM_TMPDIR/lumens-ed-gpu-${SLURM_JOB_ID:-$$}"
elif [[ -d /scratch/local ]]; then
  DEFAULT_JOB_LOCAL_SCRATCH="/scratch/local/$USER/lumens-ed-gpu/${SLURM_JOB_ID:-$$}"
else
  DEFAULT_JOB_LOCAL_SCRATCH="${TMPDIR:-/tmp}/$USER/lumens-ed-gpu/${SLURM_JOB_ID:-$$}"
fi
JOB_LOCAL_SCRATCH="${JOB_LOCAL_SCRATCH:-$DEFAULT_JOB_LOCAL_SCRATCH}"
WORKSPACE="${WORKSPACE:-$JOB_LOCAL_SCRATCH/workspace}"
QE_SCRATCH_ROOT="${QE_SCRATCH_ROOT:-$JOB_LOCAL_SCRATCH/qe}"
PSEUDO_DIR="${PSEUDO_DIR:-$CODE_ROOT/pseudopotentials_psl_pbe_full}"
TASK_ID="${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}"

module purge
module load nvhpc/26.3 openmpi/5.0.7 espresso/7.5.0

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-${SLURM_CPUS_PER_TASK:-1}}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export PYTHONUNBUFFERED=1
export QE_SCRATCH_ROOT
trap 'rm -rf "$JOB_LOCAL_SCRATCH"' EXIT

mkdir -p logs "$RESULTS_DIR" "$WORKSPACE" "$QE_SCRATCH_ROOT"

mapfile -t MATERIAL_SPEC < <(
  "$PYTHON_BIN" - <<'PY' "$INPUT_FILE" "$TASK_ID"
import csv
import sys
from pathlib import Path

path = Path(sys.argv[1])
task_id = int(sys.argv[2])

with path.open("r", encoding="utf-8", newline="") as handle:
    first_line = handle.readline()

if "formula" in first_line.lower():
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = rows[task_id - 1]
    print((row.get("formula") or "").strip())
    print((row.get("material_id") or row.get("jid") or row.get("JID") or row.get("jarvis_id") or "").strip())
else:
    with path.open("r", encoding="utf-8") as handle:
        rows = [line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#")]
    parts = [part.strip() for part in rows[task_id - 1].split(",")]
    print(parts[0])
    print(parts[1] if len(parts) > 1 else "")
PY
)

FORMULA="${MATERIAL_SPEC[0]}"
MATERIAL_ID="${MATERIAL_SPEC[1]}"

echo "GPU job on $(hostname), CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-}"
echo "QE executable: $(command -v pw.x)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

CMD=(
  "$PYTHON_BIN" "$RUNNER"
  --formula "$FORMULA"
  --workspace "$WORKSPACE"
  --results-dir "$RESULTS_DIR"
  --skip-aggregate-outputs
  --pseudo-dir "$PSEUDO_DIR"
  --qe-executable pw.x
  --nprocs "${NPROCS:-${SLURM_NTASKS:-1}}"
  --qe-launcher mpirun
  --direction-mode fibonacci
  --ed-directions "${ED_DIRECTIONS:-12}"
  --ed-points "${ED_POINTS:-6}"
  --refine-points "${REFINE_POINTS:-2}"
  --ed-mode static
  --site-selection representative
  --element-aggregation min
  --supercell-min-length "${SUPERCELL_MIN_LENGTH:-12.0}"
  --kpoint-density "${KPOINT_DENSITY:-0.08}"
  --ed-kpoint-mode gamma
  --ed-cutoff-scale "${ED_CUTOFF_SCALE:-1.15}"
  --reliability-floor-ev "${RELIABILITY_FLOOR_EV:-0.20}"
  --occupations-mode auto
  --spin-mode auto
  --relax-force-conv-thr "${RELAX_FORCE_CONV_THR:-1.0e-4}"
  --relax-etot-conv-thr "${RELAX_ETOT_CONV_THR:-1.0e-6}"
  --relax-electron-conv-thr "${RELAX_ELECTRON_CONV_THR:-1.0e-6}"
  --ed-electron-conv-thr "${ED_ELECTRON_CONV_THR:-1.0e-6}"
  --relax-degauss "${RELAX_DEGAUSS:-0.01}"
  --ed-degauss "${ED_DEGAUSS:-0.01}"
  --mixing-beta "${MIXING_BETA:-0.30}"
  --vdw-corr dft-d3
  --idealize-relaxed-structure
  --relax-timeout "${RELAX_TIMEOUT:-3600}"
  --ed-timeout "${ED_TIMEOUT:-1200}"
)

if [[ -n "$MATERIAL_ID" ]]; then
  CMD+=(--material-id "$MATERIAL_ID")
fi

if (($#)); then
  CMD+=("$@")
fi

printf 'Running:'
printf ' %q' "${CMD[@]}"
printf '\n'
"${CMD[@]}"
