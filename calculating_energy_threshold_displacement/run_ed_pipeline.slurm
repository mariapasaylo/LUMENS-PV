#!/usr/bin/env bash
#SBATCH --job-name=ed-hifi
#SBATCH --partition=hpg-default
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --mem=650G
#SBATCH --time=48:00:00
#SBATCH --output=logs/ed_%A_%a.out

set -euo pipefail

INPUT_FILE="${1:?usage: sbatch --array=1-N run_ed_pipeline.slurm /abs/path/materials.csv}"
shift
CODE_ROOT="${CODE_ROOT:-$HOME/LUMENS-PV}"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
elif [[ -x "$HOME/miniconda3/envs/DSI/bin/python" ]]; then
  PYTHON_BIN="$HOME/miniconda3/envs/DSI/bin/python"
else
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Could not find a usable Python interpreter. Set PYTHON_BIN explicitly." >&2
  exit 1
fi
RUNNER="$CODE_ROOT/calculating_energy_threshold_displacement/run_ed_pipeline.py"
RESULTS_DIR="${RESULTS_DIR:-$CODE_ROOT/calculating_energy_threshold_displacement/ed_outputs}"
if [[ -n "${SLURM_TMPDIR:-}" ]]; then
  DEFAULT_JOB_LOCAL_SCRATCH="$SLURM_TMPDIR/lumens-ed-${SLURM_JOB_ID:-$$}"
elif [[ -d /scratch/local ]]; then
  DEFAULT_JOB_LOCAL_SCRATCH="/scratch/local/$USER/lumens-ed/${SLURM_JOB_ID:-$$}"
else
  DEFAULT_JOB_LOCAL_SCRATCH="${TMPDIR:-/tmp}/$USER/lumens-ed/${SLURM_JOB_ID:-$$}"
fi
JOB_LOCAL_SCRATCH="${JOB_LOCAL_SCRATCH:-$DEFAULT_JOB_LOCAL_SCRATCH}"
WORKSPACE="${WORKSPACE:-$JOB_LOCAL_SCRATCH/workspace}"
QE_SCRATCH_ROOT="${QE_SCRATCH_ROOT:-$JOB_LOCAL_SCRATCH/qe}"
QE_EXECUTABLE="${QE_EXECUTABLE:-pw.x}"
PSEUDO_DIR="${PSEUDO_DIR:-/usr/share/espresso/pseudo}"
TASK_ID="${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}"
NPROCS="${NPROCS:-${SLURM_NTASKS:-1}}"
QE_LAUNCHER="${QE_LAUNCHER:-auto}"
ED_KPOINT_MODE="${ED_KPOINT_MODE:-auto}"
IDEALIZE_RELAXED_STRUCTURE="${IDEALIZE_RELAXED_STRUCTURE:-1}"
ED_DISABLE_SYMMETRY="${ED_DISABLE_SYMMETRY:-0}"
EXTRA_ARGS=("$@")
DEFAULT_ARGS=(
  --qe-launcher "$QE_LAUNCHER"
  --direction-mode "${DIRECTION_MODE:-fibonacci}"
  --ed-directions "${ED_DIRECTIONS:-62}"
  --ed-points "${ED_POINTS:-12}"
  --refine-points "${REFINE_POINTS:-9}"
  --ed-mode "${ED_MODE:-relax}"
  --ed-kpoint-mode "$ED_KPOINT_MODE"
  --site-selection "${SITE_SELECTION:-inequivalent}"
  --element-aggregation "${ELEMENT_AGGREGATION:-min}"
  --supercell-min-length "${SUPERCELL_MIN_LENGTH:-16.0}"
  --kpoint-density "${KPOINT_DENSITY:-0.06}"
  --ed-kpoint-density "${ED_KPOINT_DENSITY:-0.06}"
  --max-total-kpts "${MAX_TOTAL_KPTS:-8192}"
  --max-ed-kpts "${MAX_ED_KPTS:-4096}"
  --ed-cutoff-scale "${ED_CUTOFF_SCALE:-1.30}"
  --reliability-floor-ev "${RELIABILITY_FLOOR_EV:-0.20}"
  --occupations-mode "${OCCUPATIONS_MODE:-auto}"
  --fixed-occupations-bandgap-ev "${FIXED_OCCUPATIONS_BANDGAP_EV:-0.10}"
  --spin-mode "${SPIN_MODE:-auto}"
  --spin-threshold-mub "${SPIN_THRESHOLD_MUB:-0.50}"
  --relax-force-conv-thr "${RELAX_FORCE_CONV_THR:-5.0e-5}"
  --relax-etot-conv-thr "${RELAX_ETOT_CONV_THR:-1.0e-7}"
  --relax-electron-conv-thr "${RELAX_ELECTRON_CONV_THR:-1.0e-8}"
  --ed-force-conv-thr "${ED_FORCE_CONV_THR:-2.0e-4}"
  --ed-etot-conv-thr "${ED_ETOT_CONV_THR:-1.0e-6}"
  --ed-electron-conv-thr "${ED_ELECTRON_CONV_THR:-1.0e-8}"
  --relax-degauss "${RELAX_DEGAUSS:-0.01}"
  --ed-degauss "${ED_DEGAUSS:-0.01}"
  --mixing-beta "${MIXING_BETA:-0.20}"
  --vdw-corr "${VDW_CORR:-dft-d3}"
)

case "${ED_DISABLE_SYMMETRY,,}" in
  1|true|yes|on)
    DEFAULT_ARGS+=(--ed-disable-symmetry)
    ;;
esac

case "${IDEALIZE_RELAXED_STRUCTURE,,}" in
  1|true|yes|on)
    DEFAULT_ARGS+=(--idealize-relaxed-structure)
    ;;
esac

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
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
    print((row.get("material_id") or "").strip())
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

CMD=(
  "$PYTHON_BIN" "$RUNNER"
  --formula "$FORMULA"
  --workspace "$WORKSPACE"
  --nprocs "$NPROCS"
  --results-dir "$RESULTS_DIR"
  --skip-aggregate-outputs
  --qe-executable "$QE_EXECUTABLE"
  --pseudo-dir "$PSEUDO_DIR"
  "${DEFAULT_ARGS[@]}"
)

if [[ -n "$MATERIAL_ID" ]]; then
  CMD+=(--material-id "$MATERIAL_ID")
fi

if ((${#EXTRA_ARGS[@]})); then
  CMD+=("${EXTRA_ARGS[@]}")
fi

printf 'Running:'
printf ' %q' "${CMD[@]}"
printf '\n'
"${CMD[@]}"
