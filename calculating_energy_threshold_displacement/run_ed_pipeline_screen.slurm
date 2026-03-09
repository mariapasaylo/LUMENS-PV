#!/usr/bin/env bash
#SBATCH --job-name=ed-screen
#SBATCH --partition=hpg-default
#SBATCH --nodes=1
#SBATCH --ntasks=32
#SBATCH --mem=192G
#SBATCH --time=02:00:00
#SBATCH --output=logs/ed_screen_%A_%a.out

set -euo pipefail

INPUT_FILE="${1:?usage: sbatch --array=1-N run_ed_pipeline_screen.slurm /abs/path/materials.csv}"
shift

CODE_ROOT="${CODE_ROOT:-$HOME/LUMENS-PV}"
PYTHON_BIN="${PYTHON_BIN:-$HOME/local/dsi3/miniforge/envs/dsi3_full/bin/python3}"
RUNNER="$CODE_ROOT/calculating_energy_threshold_displacement/run_ed_pipeline.py"
RESULTS_DIR="${RESULTS_DIR:-$CODE_ROOT/calculating_energy_threshold_displacement/screen_outputs}"
WORKSPACE="${WORKSPACE:-$CODE_ROOT/calculating_energy_threshold_displacement/screen_workspace}"
PSEUDO_DIR="${PSEUDO_DIR:-$CODE_ROOT/pseudopotentials}"
TASK_ID="${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}"

module purge
module load gcc/14.2.0 openmpi/5.0.7 espresso/7.3.1

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export PYTHONUNBUFFERED=1

mkdir -p logs "$RESULTS_DIR" "$WORKSPACE"

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
  --results-dir "$RESULTS_DIR"
  --pseudo-dir "$PSEUDO_DIR"
  --qe-executable pw.x
  --nprocs "${SLURM_NTASKS:-32}"
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
