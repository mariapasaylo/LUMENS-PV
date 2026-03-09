#!/usr/bin/env python3
"""Run a QE-based compound-specific Ed pipeline for one or more materials."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import spglib
from ase import Atoms
from ase.build import make_supercell
from ase.data import atomic_numbers, chemical_symbols
from ase.io import write
from ase.neighborlist import NeighborList, natural_cutoffs
from jarvis.core.atoms import Atoms as JarvisAtoms
from jarvis.db.figshare import data as jarvis_data


RY_TO_EV = 13.605693009

ED_DATABASE = {
    "C": 37.0,
    "Si": 20.5,
    "Ge": 14.5,
    "Sn": 12.0,
    "B": 22.0,
    "Al": 16.0,
    "Ga": 9.4,
    "In": 8.8,
    "Tl": 7.5,
    "N": 22.0,
    "P": 8.7,
    "As": 9.8,
    "Sb": 9.0,
    "Bi": 8.0,
    "Zn": 10.0,
    "Cd": 8.0,
    "Mg": 10.0,
    "Be": 15.0,
    "Ca": 8.0,
    "Sr": 7.0,
    "Ba": 6.5,
    "Hg": 6.0,
    "O": 28.0,
    "S": 7.6,
    "Se": 7.4,
    "Te": 5.5,
    "F": 15.0,
    "Cl": 12.0,
    "Br": 10.0,
    "I": 8.0,
    "Li": 12.0,
    "Na": 8.0,
    "K": 6.0,
    "Rb": 5.5,
    "Cs": 5.0,
    "Sc": 25.0,
    "Ti": 19.0,
    "V": 28.0,
    "Cr": 28.0,
    "Mn": 26.0,
    "Fe": 17.4,
    "Co": 22.0,
    "Ni": 23.0,
    "Cu": 19.0,
    "Y": 20.0,
    "Zr": 21.0,
    "Nb": 28.0,
    "Mo": 33.0,
    "Tc": 30.0,
    "Ru": 28.0,
    "Rh": 25.0,
    "Pd": 16.0,
    "Ag": 16.0,
    "Hf": 30.0,
    "Ta": 34.0,
    "W": 55.0,
    "Re": 40.0,
    "Os": 35.0,
    "Ir": 30.0,
    "Pt": 22.0,
    "Au": 15.0,
    "La": 9.0,
    "Ce": 9.0,
    "Pr": 9.0,
    "Nd": 9.0,
    "Pm": 9.0,
    "Sm": 9.0,
    "Eu": 9.0,
    "Gd": 9.0,
    "Tb": 9.0,
    "Dy": 9.0,
    "Ho": 9.0,
    "Er": 9.0,
    "Tm": 9.0,
    "Yb": 9.0,
    "Lu": 9.0,
    "Pb": 8.0,
    "Po": 7.0,
    "H": 5.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--formula", help="Single chemical formula to process.")
    inputs.add_argument(
        "--input-file",
        help="Batch input file. Supports CSV with a formula column, or plain text with one formula per line.",
    )
    parser.add_argument("--material-id", help="Optional JARVIS material id override for single-formula runs.")
    parser.add_argument(
        "--max-materials",
        type=int,
        help="Optional limit for batch runs. Useful for chunking long candidate lists.",
    )
    parser.add_argument(
        "--workspace",
        default=str(Path(__file__).resolve().parent),
        help="Base directory for calculations and candidate files.",
    )
    parser.add_argument(
        "--results-dir",
        default=str(Path(__file__).resolve().parent / "ed_outputs"),
        help="Directory for per-material summaries and aggregate batch outputs.",
    )
    parser.add_argument(
        "--skip-aggregate-outputs",
        action="store_true",
        help="Write per-material summary JSON files only. Recommended for Slurm array tasks that share a results directory.",
    )
    parser.add_argument(
        "--pseudo-dir",
        default="/usr/share/espresso/pseudo",
        help="Quantum ESPRESSO pseudopotential directory.",
    )
    parser.add_argument("--qe-executable", default=shutil.which("pw.x") or "pw.x")
    parser.add_argument(
        "--qe-scratch-root",
        default=os.environ.get("QE_SCRATCH_ROOT") or os.environ.get("SLURM_TMPDIR"),
        help="Optional root directory for QE scratch/outdir. Defaults to $QE_SCRATCH_ROOT or $SLURM_TMPDIR when set.",
    )
    parser.add_argument(
        "--keep-qe-scratch",
        action="store_true",
        help="Preserve QE scratch directories instead of deleting them after each run.",
    )
    parser.add_argument("--relax-timeout", type=int, default=21600)
    parser.add_argument("--ed-timeout", type=int, default=10800)
    parser.add_argument(
        "--direction-mode",
        choices=["fibonacci", "highsym"],
        default="fibonacci",
        help="Directional sampling mode for the Ed scan.",
    )
    parser.add_argument(
        "--ed-directions",
        type=int,
        default=26,
        help="Number of directions to sample. Use a small value only for quick tests.",
    )
    parser.add_argument("--ed-points", type=int, default=8, help="Coarse displacement points per direction.")
    parser.add_argument(
        "--refine-points",
        type=int,
        default=5,
        help="Additional local refinement points near the peak barrier. Use 0 to disable refinement.",
    )
    parser.add_argument(
        "--direction-index-start",
        type=int,
        default=0,
        help="Optional inclusive start index into the generated direction list. Useful for sharding.",
    )
    parser.add_argument(
        "--direction-index-stop",
        type=int,
        help="Optional exclusive stop index into the generated direction list. Useful for sharding.",
    )
    parser.add_argument(
        "--ed-mode",
        choices=["relax", "static"],
        default="relax",
        help="Use pinned-atom relaxes or cheaper displaced-structure single-point SCFs.",
    )
    parser.add_argument(
        "--skip-qe-relax",
        action="store_true",
        help="Use the JARVIS-relaxed structure directly instead of running a fresh QE vc-relax.",
    )
    parser.add_argument("--nprocs", type=int, default=1, help="Set >1 only if MPI is configured.")
    parser.add_argument(
        "--qe-launcher",
        choices=["auto", "srun", "mpirun", "mpiexec"],
        default="auto",
        help="How to launch QE when nprocs > 1. 'auto' prefers mpirun for Open MPI under Slurm.",
    )
    parser.add_argument(
        "--force-qe",
        action="store_true",
        help="Ignore cached QE outputs and recompute every step.",
    )
    parser.add_argument(
        "--relaxed-qe-xml",
        help="Optional cached QE XML file containing a final relaxed structure for single-formula runs.",
    )
    parser.add_argument(
        "--allow-ed-fallback",
        action="store_true",
        help="Allow elemental lookup estimates if the DFT Ed scan fails for any sublattice.",
    )
    parser.add_argument(
        "--reliability-floor-ev",
        type=float,
        default=0.3,
        help="Direction barriers at or below this threshold are ignored as unreliable.",
    )
    parser.add_argument(
        "--site-selection",
        choices=["inequivalent", "representative"],
        default="inequivalent",
        help="Sample one atom per symmetry-inequivalent site, or just one representative atom per element.",
    )
    parser.add_argument(
        "--site-label",
        action="append",
        dest="site_labels",
        help="Optional site label filter. Repeat to restrict the scan to specific sites.",
    )
    parser.add_argument(
        "--element-aggregation",
        choices=["weighted_mean", "min"],
        default="weighted_mean",
        help="How to collapse multiple inequivalent sites of the same element into one Ed value.",
    )
    parser.add_argument(
        "--supercell-min-length",
        type=float,
        default=12.0,
        help="Minimum target length in angstrom for each supercell lattice vector.",
    )
    parser.add_argument(
        "--kpoint-density",
        type=float,
        default=0.08,
        help="Reciprocal-space density target for the primitive-cell QE relax.",
    )
    parser.add_argument(
        "--ed-kpoint-mode",
        choices=["auto", "gamma"],
        default="auto",
        help="Use automatic k-points or Gamma-only for the Ed scan.",
    )
    parser.add_argument(
        "--idealize-relaxed-structure",
        action="store_true",
        help="Idealize the QE-relaxed structure with spglib before building the Ed supercell.",
    )
    parser.add_argument(
        "--ed-disable-symmetry",
        action="store_true",
        help="Disable QE symmetry operations for Ed supercell calculations.",
    )
    parser.add_argument(
        "--ed-kpoint-density",
        type=float,
        default=0.08,
        help="Reciprocal-space density target for Ed calculations when --ed-kpoint-mode auto is used.",
    )
    parser.add_argument(
        "--max-total-kpts",
        type=int,
        default=4096,
        help="Maximum total k-points for primitive-cell calculations.",
    )
    parser.add_argument(
        "--max-ed-kpts",
        type=int,
        default=2048,
        help="Maximum total k-points for supercell Ed calculations.",
    )
    parser.add_argument(
        "--ed-cutoff-scale",
        type=float,
        default=1.15,
        help="Scale factor applied to the recommended QE cutoffs for both relax and Ed calculations.",
    )
    parser.add_argument(
        "--occupations-mode",
        choices=["smearing", "fixed", "auto"],
        default="smearing",
        help="Electronic occupations treatment. 'auto' switches to fixed occupations for gapped materials.",
    )
    parser.add_argument(
        "--fixed-occupations-bandgap-ev",
        type=float,
        default=0.10,
        help="Band gap threshold used by --occupations-mode auto to choose fixed occupations.",
    )
    parser.add_argument(
        "--spin-mode",
        choices=["none", "auto", "collinear"],
        default="none",
        help="Spin treatment. 'auto' enables collinear spin when JARVIS reports a sizable total moment.",
    )
    parser.add_argument(
        "--spin-threshold-mub",
        type=float,
        default=0.5,
        help="Enable spin in auto mode when |magmom_oszicar| exceeds this value in Bohr magnetons.",
    )
    parser.add_argument(
        "--relax-force-conv-thr",
        type=float,
        default=1.0e-4,
        help="Primitive-cell vc-relax force convergence threshold in Ry/Bohr.",
    )
    parser.add_argument(
        "--relax-etot-conv-thr",
        type=float,
        default=1.0e-6,
        help="Primitive-cell vc-relax total-energy convergence threshold in Ry.",
    )
    parser.add_argument(
        "--relax-electron-conv-thr",
        type=float,
        default=1.0e-6,
        help="Primitive-cell vc-relax SCF convergence threshold.",
    )
    parser.add_argument(
        "--ed-force-conv-thr",
        type=float,
        default=1.0e-3,
        help="Pinned-atom Ed relax force convergence threshold in Ry/Bohr.",
    )
    parser.add_argument(
        "--ed-etot-conv-thr",
        type=float,
        default=1.0e-4,
        help="Pinned-atom Ed relax total-energy convergence threshold in Ry.",
    )
    parser.add_argument(
        "--ed-electron-conv-thr",
        type=float,
        default=1.0e-6,
        help="Ed SCF convergence threshold.",
    )
    parser.add_argument(
        "--relax-degauss",
        type=float,
        default=0.01,
        help="Smearing width in Ry for primitive-cell relaxes when smearing is used.",
    )
    parser.add_argument(
        "--ed-degauss",
        type=float,
        default=0.02,
        help="Smearing width in Ry for Ed calculations when smearing is used.",
    )
    parser.add_argument(
        "--mixing-beta",
        type=float,
        default=0.3,
        help="QE mixing_beta used for Ed SCF steps.",
    )
    parser.add_argument(
        "--vdw-corr",
        default="dft-d3",
        help="QE vdw_corr setting for primitive-cell vc-relax. Use 'none' to disable.",
    )
    parser.add_argument(
        "--symprec",
        type=float,
        default=1.0e-2,
        help="spglib symmetry tolerance in angstrom for inequivalent-site detection.",
    )
    parser.add_argument(
        "--angle-tolerance",
        type=float,
        default=-1.0,
        help="spglib angle tolerance. Use -1.0 for automatic handling.",
    )
    return parser.parse_args()


def load_material_requests(
    input_file: str | None,
    formula: str | None,
    material_id: str | None,
    max_materials: int | None,
) -> list[dict[str, str | None]]:
    requests: list[dict[str, str | None]] = []
    if formula:
        requests.append({"formula": formula, "material_id": material_id})
    else:
        path = Path(input_file or "")
        if not path.exists():
            raise SystemExit(f"Input file not found: {path}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            lines = handle.readlines()
        if not lines:
            raise SystemExit(f"Input file is empty: {path}")
        header = lines[0].strip().lower()
        if "formula" in header:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    item_formula = (row.get("formula") or "").strip()
                    if not item_formula:
                        continue
                    requests.append(
                        {
                            "formula": item_formula,
                            "material_id": (row.get("material_id") or "").strip() or None,
                        }
                    )
        else:
            for raw_line in lines:
                stripped = raw_line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                parts = [part.strip() for part in stripped.split(",")]
                item_formula = parts[0]
                item_material_id = parts[1] if len(parts) > 1 and parts[1] else None
                requests.append({"formula": item_formula, "material_id": item_material_id})

    deduped: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for request in requests:
        key = (str(request["formula"]), request["material_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(request)

    if max_materials is not None:
        deduped = deduped[:max_materials]
    if not deduped:
        raise SystemExit("No valid material requests were found.")
    return deduped


def parse_upf_header(upf_path: str) -> dict:
    info = {"z_valence": None, "l_max": None, "pseudo_type": None, "element": None}
    with open(upf_path, "r", encoding="utf-8", errors="ignore") as handle:
        content = handle.read()
    header_match = re.search(r"<PP_HEADER([^>]+)>", content, re.DOTALL)
    if not header_match:
        return info
    header = header_match.group(1)
    for key in ["z_valence", "l_max", "pseudo_type", "element"]:
        match = re.search(rf'{key}="([^"]+)"', header)
        if not match:
            continue
        value = match.group(1).strip()
        info[key] = float(value) if key in {"z_valence", "l_max"} else value
    return info


def parse_optional_float(value: object) -> float | None:
    if value in (None, "", "na", "NA", "NaN", "nan"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(parsed):
        return None
    return parsed


def get_material_bandgap(material: dict) -> float | None:
    for key in ["mbj_bandgap", "optb88vdw_bandgap", "bandgap", "gap pbe"]:
        bandgap = parse_optional_float(material.get(key))
        if bandgap is not None:
            return bandgap
    return None


def default_starting_magnetization(element: str) -> float:
    atomic_number = atomic_numbers.get(element, 0)
    if 21 <= atomic_number <= 30 or 39 <= atomic_number <= 48 or 72 <= atomic_number <= 80:
        return 0.5
    if 57 <= atomic_number <= 71 or 89 <= atomic_number <= 103:
        return 0.7
    if element in {"O", "N", "F", "S", "Cl", "Se", "Br", "Te", "I"}:
        return 0.1
    return 0.0


def has_correlated_elements(elements: list[str]) -> bool:
    correlated_candidates = {
        "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu",
        "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd",
        "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt",
    }
    for element in elements:
        atomic_number = atomic_numbers.get(element, 0)
        if element in correlated_candidates or 57 <= atomic_number <= 71 or 89 <= atomic_number <= 103:
            return True
    return False


def resolve_electronic_settings(material: dict, elements: list[str], args: argparse.Namespace, stage: str) -> dict:
    bandgap = get_material_bandgap(material)
    total_magmom = parse_optional_float(material.get("magmom_oszicar"))
    if total_magmom is None:
        total_magmom = parse_optional_float(material.get("magmom"))

    if args.spin_mode == "collinear":
        spin_polarized = True
    elif args.spin_mode == "auto":
        spin_polarized = total_magmom is not None and abs(total_magmom) >= args.spin_threshold_mub
    else:
        spin_polarized = False

    if args.occupations_mode == "fixed":
        occupations = "fixed"
    elif args.occupations_mode == "auto":
        occupations = "fixed" if bandgap is not None and bandgap >= args.fixed_occupations_bandgap_ev else "smearing"
    else:
        occupations = "smearing"

    if stage == "relax":
        degauss = args.relax_degauss
        electron_conv_thr = args.relax_electron_conv_thr
        force_conv_thr = args.relax_force_conv_thr
        etot_conv_thr = args.relax_etot_conv_thr
    else:
        degauss = args.ed_degauss
        electron_conv_thr = args.ed_electron_conv_thr
        force_conv_thr = args.ed_force_conv_thr
        etot_conv_thr = args.ed_etot_conv_thr

    starting_magnetization = {
        element: default_starting_magnetization(element) if spin_polarized else 0.0 for element in elements
    }

    return {
        "bandgap_ev": bandgap,
        "total_magmom_mub": total_magmom,
        "spin_polarized": spin_polarized,
        "occupations": occupations,
        "smearing": "cold",
        "degauss": degauss,
        "electron_conv_thr": electron_conv_thr,
        "force_conv_thr": force_conv_thr,
        "etot_conv_thr": etot_conv_thr,
        "mixing_beta": args.mixing_beta,
        "starting_magnetization": starting_magnetization,
    }


def get_recommended_cutoffs(element: str, z_valence: float | None, l_max: float | None, pseudo_type: str | None) -> tuple[float, float]:
    z_number = atomic_numbers.get(element, 30)
    row = 1 + (z_number > 2) + (z_number > 10) + (z_number > 18) + (z_number > 36) + (z_number > 54) + (z_number > 86)
    base_wfc = 30.0
    if l_max is not None:
        base_wfc += l_max * 8.0
    if z_valence is not None:
        base_wfc += z_valence * 1.5
    base_wfc += (row - 1) * 3.0
    rho_multiplier = 10.0 if pseudo_type == "PAW" else 4.0
    ecutwfc = max(40.0, round(base_wfc / 5.0) * 5.0)
    ecutrho = ecutwfc * rho_multiplier
    return ecutwfc, ecutrho


def rounded_cutoff(value: float) -> float:
    return float(round(value / 5.0) * 5.0)


def get_kpoints_from_cell(cell: np.ndarray, density: float, max_total_kpts: int) -> list[int]:
    recip = 2.0 * np.pi * np.linalg.inv(cell).T
    recip_lengths = np.linalg.norm(recip, axis=1)
    kpts = [max(1, int(np.ceil(length / density))) for length in recip_lengths]
    total = kpts[0] * kpts[1] * kpts[2]
    if total > max_total_kpts:
        scale = (max_total_kpts / total) ** (1.0 / 3.0)
        kpts = [max(1, int(np.floor(value * scale))) for value in kpts]
        kpts = [max(1, value) for value in kpts]
    return kpts


def resolve_executable(executable: str) -> str:
    resolved = shutil.which(executable)
    if resolved:
        return resolved
    candidate = Path(sys.executable).resolve().parent / executable
    if candidate.exists():
        return str(candidate)
    return executable


def prefer_mpirun_under_slurm(mpirun_executable: str | None) -> bool:
    loaded_modules = os.environ.get("LOADEDMODULES", "").lower()
    if "openmpi" in loaded_modules:
        return True
    return bool(mpirun_executable and "openmpi" in mpirun_executable.lower())


def build_qe_command(qe_executable: str, input_name: str, nprocs: int, qe_launcher: str) -> list[str]:
    if nprocs <= 1:
        return [qe_executable, "-in", input_name]

    srun_executable = shutil.which("srun")
    mpirun_executable = shutil.which("mpirun")
    mpiexec_executable = shutil.which("mpiexec")
    in_slurm = bool(os.environ.get("SLURM_JOB_ID"))

    if qe_launcher == "auto":
        if in_slurm and prefer_mpirun_under_slurm(mpirun_executable):
            qe_launcher = "mpirun"
        elif in_slurm and srun_executable:
            qe_launcher = "srun"
        elif mpirun_executable:
            qe_launcher = "mpirun"
        elif mpiexec_executable:
            qe_launcher = "mpiexec"
        else:
            raise RuntimeError("Requested nprocs > 1 but no Slurm srun or MPI launcher is available.")

    if qe_launcher == "srun":
        if not srun_executable:
            raise RuntimeError("Requested qe-launcher=srun but srun is not available.")
        return [srun_executable, "--ntasks", str(nprocs), "--cpu-bind=cores", qe_executable, "-in", input_name]

    if qe_launcher == "mpirun":
        if not mpirun_executable:
            raise RuntimeError("Requested qe-launcher=mpirun but mpirun is not available.")
        return [mpirun_executable, "-np", str(nprocs), qe_executable, "-in", input_name]

    if qe_launcher == "mpiexec":
        if not mpiexec_executable:
            raise RuntimeError("Requested qe-launcher=mpiexec but mpiexec is not available.")
        return [mpiexec_executable, "-np", str(nprocs), qe_executable, "-in", input_name]

    raise RuntimeError(f"Unsupported qe-launcher '{qe_launcher}'.")


def get_qe_scratch_dir(run_dir: Path, tag: str, qe_scratch_root: str | None) -> Path:
    if not qe_scratch_root:
        return run_dir / "tmp"

    scratch_root = Path(qe_scratch_root).expanduser()
    scratch_stub = sanitize_stub(f"{run_dir.parent.name}_{run_dir.name}_{tag}")
    return scratch_root / scratch_stub


def configure_qe_input_for_scratch(input_text: str, scratch_dir: Path) -> str:
    scratch_path = scratch_dir.as_posix()
    lines: list[str] = []
    found_outdir = False
    has_wfcdir = any(re.match(r"\s*wfcdir\s*=", line) for line in input_text.splitlines())

    for line in input_text.splitlines(keepends=True):
        if re.match(r"\s*outdir\s*=", line):
            indent = re.match(r"(\s*)", line).group(1) if re.match(r"(\s*)", line) else "  "
            lines.append(f"{indent}outdir='{scratch_path}'\n")
            if not has_wfcdir:
                lines.append(f"{indent}wfcdir='{scratch_path}'\n")
            found_outdir = True
            continue
        lines.append(line)

    if not found_outdir:
        return input_text
    return "".join(lines)


def run_qe(
    input_text: str,
    run_dir: Path,
    tag: str,
    qe_executable: str,
    timeout: int,
    nprocs: int,
    qe_launcher: str,
    force_qe: bool,
    qe_scratch_root: str | None = None,
    keep_qe_scratch: bool = False,
) -> str:
    run_dir.mkdir(parents=True, exist_ok=True)
    input_path = run_dir / f"{tag}.in"
    output_path = run_dir / f"{tag}.out"
    runtime_input_path = run_dir / f"{tag}.run.in"
    crash_path = run_dir / "CRASH"
    if not force_qe and input_path.exists() and output_path.exists():
        existing_input = input_path.read_text(encoding="utf-8")
        existing_output = output_path.read_text(encoding="utf-8")
        if existing_input == input_text and "JOB DONE" in existing_output and not crash_path.exists():
            return existing_output
    input_path.write_text(input_text, encoding="utf-8")
    if crash_path.exists():
        crash_path.unlink()

    scratch_dir = get_qe_scratch_dir(run_dir, tag, qe_scratch_root)
    if qe_scratch_root:
        scratch_dir.mkdir(parents=True, exist_ok=True)
        runtime_input_text = configure_qe_input_for_scratch(input_text, scratch_dir)
        runtime_input_path.write_text(runtime_input_text, encoding="utf-8")
        qe_input_name = runtime_input_path.name
    else:
        scratch_dir.mkdir(exist_ok=True)
        qe_input_name = input_path.name
    cmd = build_qe_command(qe_executable, qe_input_name, nprocs, qe_launcher)

    try:
        completed = subprocess.run(
            cmd,
            cwd=run_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        output_path.write_text(completed.stdout, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(f"QE failed for {tag} with code {completed.returncode}. See {output_path}.")
        if "JOB DONE" not in completed.stdout:
            raise RuntimeError(f"QE did not complete successfully for {tag}. See {output_path}.")
        return completed.stdout
    finally:
        if qe_scratch_root and not keep_qe_scratch:
            shutil.rmtree(scratch_dir, ignore_errors=True)


def parse_total_energy_ry(output_text: str, require_converged: bool = False) -> float:
    fallback_energy = None
    for line in reversed(output_text.splitlines()):
        if "!    total energy" in line:
            match = re.search(r"([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+Ry", line)
            if match:
                return float(match.group(1))
        if fallback_energy is None and "total energy" in line and "=" in line and "!" not in line:
            match = re.search(r"total energy\s*=\s*([+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s+Ry", line)
            if match:
                fallback_energy = float(match.group(1))
    if fallback_energy is not None and not require_converged:
        return fallback_energy
    if require_converged:
        raise ValueError("Could not find converged total energy in QE output.")
    raise ValueError("Could not find total energy in QE output.")


def parse_relaxed_structure(output_text: str, original_atoms: Atoms) -> Atoms:
    cell_blocks = list(
        re.finditer(
            r"CELL_PARAMETERS\s*\(?\s*angstrom\s*\)?\s*\n"
            r"\s*([\d\.\-\+eE]+\s+[\d\.\-\+eE]+\s+[\d\.\-\+eE]+)\s*\n"
            r"\s*([\d\.\-\+eE]+\s+[\d\.\-\+eE]+\s+[\d\.\-\+eE]+)\s*\n"
            r"\s*([\d\.\-\+eE]+\s+[\d\.\-\+eE]+\s+[\d\.\-\+eE]+)",
            output_text,
            re.IGNORECASE,
        )
    )
    pos_blocks = list(
        re.finditer(
            r"ATOMIC_POSITIONS\s*\(?\s*angstrom\s*\)?\s*\n"
            r"((?:\s*\w+\s+[\d\.\-\+eE]+\s+[\d\.\-\+eE]+\s+[\d\.\-\+eE]+(?:\s+\d+\s+\d+\s+\d+)?\s*\n?)+)",
            output_text,
            re.IGNORECASE,
        )
    )
    if not cell_blocks or not pos_blocks:
        return original_atoms
    cell_match = cell_blocks[-1]
    cell = np.array(
        [
            [float(value) for value in cell_match.group(1).split()],
            [float(value) for value in cell_match.group(2).split()],
            [float(value) for value in cell_match.group(3).split()],
        ]
    )
    symbols: list[str] = []
    positions: list[list[float]] = []
    for line in pos_blocks[-1].group(1).strip().splitlines():
        parts = line.split()
        if len(parts) >= 4:
            symbols.append(parts[0])
            positions.append([float(parts[1]), float(parts[2]), float(parts[3])])
    if len(symbols) != len(original_atoms):
        return original_atoms
    return Atoms(symbols=symbols, positions=np.asarray(positions), cell=cell, pbc=True)


def parse_relaxed_structure_from_qe_xml(xml_path: str) -> Atoms:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    output = next((child for child in root if child.tag.endswith("output")), None)
    if output is None:
        raise ValueError(f"Could not find output block in {xml_path}.")
    structure = next((child for child in output if child.tag.endswith("atomic_structure")), None)
    if structure is None:
        raise ValueError(f"Could not find final atomic_structure in {xml_path}.")

    cell_element = next((child for child in structure if child.tag.endswith("cell")), None)
    positions_element = next((child for child in structure if child.tag.endswith("atomic_positions")), None)
    if cell_element is None or positions_element is None:
        raise ValueError(f"Missing cell or atomic_positions in {xml_path}.")

    bohr_to_angstrom = 0.529177210903
    cell = []
    for axis in ["a1", "a2", "a3"]:
        vector = next((child for child in cell_element if child.tag.endswith(axis)), None)
        if vector is None or vector.text is None:
            raise ValueError(f"Missing {axis} in {xml_path}.")
        cell.append([float(value) * bohr_to_angstrom for value in vector.text.split()])

    symbols = []
    positions = []
    for atom in positions_element:
        if not atom.tag.endswith("atom"):
            continue
        symbols.append(atom.attrib["name"])
        positions.append([float(value) * bohr_to_angstrom for value in atom.text.split()])

    return Atoms(symbols=symbols, positions=np.asarray(positions), cell=np.asarray(cell), pbc=True)


def idealize_structure(atoms: Atoms, symprec: float, angle_tolerance: float) -> Atoms:
    cell_tuple = (
        atoms.cell.array,
        atoms.get_scaled_positions(),
        atoms.numbers,
    )
    standardized = spglib.standardize_cell(
        cell_tuple,
        to_primitive=True,
        no_idealize=False,
        symprec=symprec,
        angle_tolerance=angle_tolerance,
    )
    if standardized is None:
        return atoms
    lattice, scaled_positions, numbers = standardized
    return Atoms(
        symbols=[chemical_symbols[number] for number in numbers],
        scaled_positions=np.asarray(scaled_positions),
        cell=np.asarray(lattice),
        pbc=True,
    )


def nearest_neighbor_distance(atoms: Atoms, atom_index: int) -> float:
    cutoffs = natural_cutoffs(atoms, mult=1.8)
    neighbor_list = NeighborList(cutoffs, self_interaction=False, bothways=True)
    neighbor_list.update(atoms)
    neighbors, offsets = neighbor_list.get_neighbors(atom_index)
    if len(neighbors) == 0:
        return 2.5
    distances = []
    for offset, neighbor in zip(offsets, neighbors):
        position = atoms.positions[neighbor] + offset @ atoms.cell.array
        distances.append(float(np.linalg.norm(position - atoms.positions[atom_index])))
    return min(distances)


def overlaps_other_atom(atoms: Atoms, excluded_index: int, new_position: np.ndarray, min_distance: float = 1.0) -> bool:
    inv_cell = np.linalg.inv(atoms.cell.array)
    for atom_index, position in enumerate(atoms.positions):
        if atom_index == excluded_index:
            continue
        delta = position - new_position
        delta -= np.round(delta @ inv_cell) @ atoms.cell.array
        if np.linalg.norm(delta) < min_distance:
            return True
    return False


def build_vc_relax_input(
    atoms: Atoms,
    material_id: str,
    pseudo_dir: str,
    pseudos: dict[str, str],
    elements: list[str],
    ecutwfc: float,
    ecutrho: float,
    k_points: list[int],
    electronic_settings: dict,
    vdw_corr: str,
) -> str:
    lines = [
        "&CONTROL\n",
        "  calculation='vc-relax'\n",
        f"  prefix='{material_id}'\n",
        "  outdir='./tmp'\n",
        f"  pseudo_dir='{pseudo_dir}'\n",
        f"  forc_conv_thr={electronic_settings['force_conv_thr']:.1e}\n",
        f"  etot_conv_thr={electronic_settings['etot_conv_thr']:.1e}\n",
        "/\n",
        "&SYSTEM\n",
        "  ibrav=0\n",
        f"  nat={len(atoms)}\n",
        f"  ntyp={len(elements)}\n",
        f"  ecutwfc={ecutwfc:.1f}\n",
        f"  ecutrho={ecutrho:.1f}\n",
    ]
    if electronic_settings["occupations"] == "fixed":
        lines.append("  occupations='fixed'\n")
    else:
        lines.extend(
            [
                "  occupations='smearing'\n",
                f"  smearing='{electronic_settings['smearing']}'\n",
                f"  degauss={electronic_settings['degauss']:.4f}\n",
            ]
        )
    if electronic_settings["spin_polarized"]:
        lines.append("  nspin=2\n")
        for species_index, element in enumerate(elements, start=1):
            start_mag = electronic_settings["starting_magnetization"][element]
            if abs(start_mag) > 1.0e-12:
                lines.append(f"  starting_magnetization({species_index})={start_mag:.3f}\n")
    if vdw_corr != "none":
        lines.append(f"  vdw_corr='{vdw_corr}'\n")
    lines.extend(
        [
            "/\n",
            "&ELECTRONS\n",
            f"  conv_thr={electronic_settings['electron_conv_thr']:.1e}\n",
            "/\n",
        ]
    )
    lines.extend(
        [
            "&IONS\n",
            "  ion_dynamics='bfgs'\n",
            "/\n",
            "&CELL\n",
            "  cell_dynamics='bfgs'\n",
            "  press_conv_thr=0.1\n",
            "/\n",
            "ATOMIC_SPECIES\n",
        ]
    )
    for element in elements:
        mass = atoms.get_masses()[atoms.get_chemical_symbols().index(element)]
        lines.append(f"  {element}  {mass:.4f}  {pseudos[element]}\n")
    lines.append("\nCELL_PARAMETERS angstrom\n")
    for row in atoms.cell.array:
        lines.append(f"  {row[0]:16.10f} {row[1]:16.10f} {row[2]:16.10f}\n")
    lines.append("\nATOMIC_POSITIONS angstrom\n")
    for symbol, position in zip(atoms.get_chemical_symbols(), atoms.positions):
        lines.append(f"  {symbol:4s} {position[0]:16.10f} {position[1]:16.10f} {position[2]:16.10f}\n")
    lines.append(f"\nK_POINTS automatic\n  {k_points[0]} {k_points[1]} {k_points[2]}  0 0 0\n")
    return "".join(lines)


def build_ed_input(
    atoms: Atoms,
    tag: str,
    pseudo_dir: str,
    pseudos: dict[str, str],
    ecutwfc: float,
    ecutrho: float,
    calc_type: str,
    k_points: list[int],
    kpoint_mode: str,
    electronic_settings: dict,
    disable_symmetry: bool = False,
    fixed_index: int | None = None,
    displacement: np.ndarray | None = None,
) -> str:
    if calc_type == "static":
        calc_type = "scf"
    symbols = atoms.get_chemical_symbols()
    positions = atoms.positions.copy()
    if fixed_index is not None and displacement is not None:
        positions[fixed_index] = positions[fixed_index] + displacement
    unique_elements = list(dict.fromkeys(symbols))
    lines = [
        "&CONTROL\n",
        f"  calculation='{calc_type}'\n",
        f"  prefix='{tag}'\n",
        "  outdir='./tmp'\n",
        f"  pseudo_dir='{pseudo_dir}'\n",
    ]
    if calc_type == "relax":
        lines.extend(
            [
                f"  forc_conv_thr={electronic_settings['force_conv_thr']:.1e}\n",
                f"  etot_conv_thr={electronic_settings['etot_conv_thr']:.1e}\n",
            ]
        )
    lines.extend(
        [
            "/\n",
            "&SYSTEM\n",
            "  ibrav=0\n",
            f"  nat={len(atoms)}\n",
            f"  ntyp={len(unique_elements)}\n",
            f"  ecutwfc={ecutwfc:.1f}\n",
            f"  ecutrho={ecutrho:.1f}\n",
        ]
    )
    if disable_symmetry:
        lines.extend(
            [
                "  nosym=.true.\n",
                "  noinv=.true.\n",
            ]
        )
    if electronic_settings["occupations"] == "fixed":
        lines.append("  occupations='fixed'\n")
    else:
        lines.extend(
            [
                "  occupations='smearing'\n",
                f"  smearing='{electronic_settings['smearing']}'\n",
                f"  degauss={electronic_settings['degauss']:.4f}\n",
            ]
        )
    if electronic_settings["spin_polarized"]:
        lines.append("  nspin=2\n")
        for species_index, element in enumerate(unique_elements, start=1):
            start_mag = electronic_settings["starting_magnetization"].get(element, 0.0)
            if abs(start_mag) > 1.0e-12:
                lines.append(f"  starting_magnetization({species_index})={start_mag:.3f}\n")
    lines.extend(
        [
            "/\n",
            "&ELECTRONS\n",
            f"  conv_thr={electronic_settings['electron_conv_thr']:.1e}\n",
            f"  mixing_beta={electronic_settings['mixing_beta']:.3f}\n",
            "/\n",
        ]
    )
    if calc_type == "relax":
        lines.extend(["&IONS\n", "  ion_dynamics='bfgs'\n", "/\n"])
    lines.append("ATOMIC_SPECIES\n")
    for element in unique_elements:
        mass = atoms.get_masses()[symbols.index(element)]
        lines.append(f"  {element}  {mass:.4f}  {pseudos[element]}\n")
    lines.append("\nCELL_PARAMETERS angstrom\n")
    for row in atoms.cell.array:
        lines.append(f"  {row[0]:16.10f} {row[1]:16.10f} {row[2]:16.10f}\n")
    lines.append("\nATOMIC_POSITIONS angstrom\n")
    for atom_index, (symbol, position) in enumerate(zip(symbols, positions)):
        flags = "  0 0 0" if calc_type == "relax" and fixed_index is not None and atom_index == fixed_index else ""
        lines.append(f"  {symbol:4s} {position[0]:16.10f} {position[1]:16.10f} {position[2]:16.10f}{flags}\n")
    if kpoint_mode == "gamma" or all(value == 1 for value in k_points):
        lines.append("\nK_POINTS gamma\n")
    else:
        lines.append(f"\nK_POINTS automatic\n  {k_points[0]} {k_points[1]} {k_points[2]}  0 0 0\n")
    return "".join(lines)


def get_default_ed(element: str) -> float:
    if element in ED_DATABASE:
        return ED_DATABASE[element]
    atomic_number = atomic_numbers.get(element, 30)
    return max(5.0, 35.0 - 0.3 * atomic_number)


def _as_float_or_inf(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def select_material(dataset: list[dict], formula: str, material_id: str | None) -> tuple[dict, dict]:
    if material_id:
        material = next((item for item in dataset if item.get("jid") == material_id), None)
        if material is None:
            raise RuntimeError(f"Could not locate material id {material_id} in JARVIS dft_3d.")
        return material, {"selection_mode": "material_id", "candidate_count": 1}

    matches = [item for item in dataset if item.get("formula") == formula]
    if not matches:
        raise RuntimeError(f"Could not locate {formula} in JARVIS dft_3d.")
    if len(matches) == 1:
        return matches[0], {"selection_mode": "formula_unique", "candidate_count": 1}

    ranked_matches = sorted(
        matches,
        key=lambda item: (
            _as_float_or_inf(item.get("ehull")),
            _as_float_or_inf(item.get("formation_energy_peratom")),
            str(item.get("jid", "")),
        ),
    )
    selected = ranked_matches[0]
    return selected, {
        "selection_mode": "formula_lowest_ehull",
        "candidate_count": len(matches),
        "selected_ehull": selected.get("ehull"),
        "selected_formation_energy_peratom": selected.get("formation_energy_peratom"),
    }


def sanitize_stub(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text)


def build_supercell(atoms: Atoms, min_length: float) -> tuple[Atoms, tuple[int, int, int]]:
    lengths = atoms.cell.lengths()
    repeats = tuple(max(1, int(np.ceil(min_length / max(length, 1.0e-8)))) for length in lengths)
    transform = np.diag(repeats)
    return make_supercell(atoms, transform), repeats


def find_inequivalent_sites(atoms: Atoms, site_selection: str, symprec: float, angle_tolerance: float) -> list[dict]:
    symbols = atoms.get_chemical_symbols()
    if site_selection == "representative":
        groups: dict[str, list[int]] = {}
        for index, symbol in enumerate(symbols):
            groups.setdefault(symbol, []).append(index)
        return [
            {
                "element": symbol,
                "label": f"{symbol}_s0",
                "representative_index": indices[0],
                "base_indices": indices,
                "multiplicity": len(indices),
            }
            for symbol, indices in groups.items()
        ]

    cell_tuple = (
        atoms.cell.array,
        atoms.get_scaled_positions(),
        atoms.numbers,
    )
    dataset = spglib.get_symmetry_dataset(cell_tuple, symprec=symprec, angle_tolerance=angle_tolerance)
    if dataset is None:
        raise RuntimeError("spglib could not identify symmetry-equivalent sites for the relaxed structure.")
    equivalent_atoms = np.asarray(dataset["equivalent_atoms"], dtype=int)
    groups: dict[tuple[str, int], list[int]] = {}
    for index, representative in enumerate(equivalent_atoms):
        symbol = symbols[index]
        groups.setdefault((symbol, int(representative)), []).append(index)

    site_counts: dict[str, int] = {}
    site_groups: list[dict] = []
    for (symbol, _representative), indices in sorted(groups.items(), key=lambda item: (item[0][0], min(item[1]))):
        site_id = site_counts.get(symbol, 0)
        site_counts[symbol] = site_id + 1
        site_groups.append(
            {
                "element": symbol,
                "label": f"{symbol}_s{site_id}",
                "representative_index": min(indices),
                "base_indices": indices,
                "multiplicity": len(indices),
            }
        )
    return site_groups


def filter_site_groups(site_groups: list[dict], requested_labels: list[str] | None) -> list[dict]:
    if not requested_labels:
        return site_groups

    by_label = {group["label"]: group for group in site_groups}
    missing = [label for label in requested_labels if label not in by_label]
    if missing:
        available = ", ".join(group["label"] for group in site_groups)
        missing_text = ", ".join(missing)
        raise RuntimeError(
            f"Requested site label(s) not present in relaxed structure: {missing_text}. Available labels: {available}"
        )

    seen: set[str] = set()
    filtered: list[dict] = []
    for label in requested_labels:
        if label in seen:
            continue
        seen.add(label)
        filtered.append(by_label[label])
    return filtered


def map_base_site_to_supercell(base_atoms: Atoms, supercell: Atoms, repeats: tuple[int, int, int], base_index: int) -> int:
    target_symbol = base_atoms[base_index].symbol
    target_scaled = base_atoms.get_scaled_positions()[base_index] % 1.0
    super_scaled = supercell.get_scaled_positions() % 1.0
    super_symbols = np.array(supercell.get_chemical_symbols())
    center = 0.5 * np.sum(supercell.cell.array, axis=0)
    candidates: list[int] = []

    for i_repeat in range(repeats[0]):
        for j_repeat in range(repeats[1]):
            for k_repeat in range(repeats[2]):
                translation = np.array([i_repeat, j_repeat, k_repeat], dtype=float)
                target = (target_scaled + translation) / np.array(repeats, dtype=float)
                deltas = super_scaled - target
                deltas -= np.round(deltas)
                distances = np.linalg.norm(deltas, axis=1)
                matches = np.where((super_symbols == target_symbol) & (distances < 1.0e-6))[0]
                candidates.extend(int(match) for match in matches)

    if not candidates:
        raise RuntimeError(f"Could not map base atom {base_index} into the supercell.")
    unique_candidates = sorted(set(candidates))
    return min(unique_candidates, key=lambda index: float(np.linalg.norm(supercell.positions[index] - center)))


def generate_directions(mode: str, count: int) -> list[tuple[str, np.ndarray]]:
    if count <= 0:
        raise ValueError("ed-directions must be positive.")
    if mode == "highsym":
        base_directions = [
            ("[100]", np.array([1.0, 0.0, 0.0])),
            ("[010]", np.array([0.0, 1.0, 0.0])),
            ("[001]", np.array([0.0, 0.0, 1.0])),
            ("[110]", np.array([1.0, 1.0, 0.0])),
            ("[1-10]", np.array([1.0, -1.0, 0.0])),
            ("[101]", np.array([1.0, 0.0, 1.0])),
            ("[10-1]", np.array([1.0, 0.0, -1.0])),
            ("[011]", np.array([0.0, 1.0, 1.0])),
            ("[01-1]", np.array([0.0, 1.0, -1.0])),
            ("[111]", np.array([1.0, 1.0, 1.0])),
            ("[11-1]", np.array([1.0, 1.0, -1.0])),
            ("[1-11]", np.array([1.0, -1.0, 1.0])),
            ("[-111]", np.array([-1.0, 1.0, 1.0])),
        ]
        directions = base_directions[: min(count, len(base_directions))]
    else:
        directions = []
        golden_angle = np.pi * (3.0 - np.sqrt(5.0))
        for index in range(count):
            z_value = 1.0 - (2.0 * index + 1.0) / count
            radius = np.sqrt(max(0.0, 1.0 - z_value * z_value))
            phi = index * golden_angle
            vector = np.array([np.cos(phi) * radius, np.sin(phi) * radius, z_value], dtype=float)
            directions.append((f"d{index:03d}", vector))

    normalized = []
    for label, vector in directions:
        normalized.append((label, vector / np.linalg.norm(vector)))
    return normalized


def select_direction_subset(
    directions: list[tuple[str, np.ndarray]],
    start: int,
    stop: int | None,
) -> tuple[list[tuple[str, np.ndarray]], int, int, int]:
    total = len(directions)
    if start < 0:
        raise ValueError("direction-index-start must be >= 0.")
    resolved_stop = total if stop is None else stop
    if resolved_stop < 0:
        raise ValueError("direction-index-stop must be >= 0.")
    if start >= total:
        raise ValueError(f"direction-index-start {start} is outside the generated direction range [0, {total}).")
    if resolved_stop > total:
        raise ValueError(f"direction-index-stop {resolved_stop} exceeds the generated direction count {total}.")
    if start >= resolved_stop:
        raise ValueError("direction-index-start must be smaller than direction-index-stop.")
    return directions[start:resolved_stop], start, resolved_stop, total


def evaluate_displacement(
    supercell: Atoms,
    atom_index: int,
    distance: float,
    direction: np.ndarray,
    site_label: str,
    direction_label: str,
    material_id: str,
    args: argparse.Namespace,
    pseudos: dict[str, str],
    ed_dir: Path,
    ecutwfc: float,
    ecutrho: float,
    k_points: list[int],
    electronic_settings: dict,
) -> dict | None:
    displaced_position = supercell.positions[atom_index] + distance * direction
    if overlaps_other_atom(supercell, atom_index, displaced_position):
        return None
    distance_tag = f"{distance:.3f}".replace("-", "m").replace(".", "p")
    tag = f"{material_id}_{site_label}_{direction_label}_{distance_tag}"
    output_text = run_qe(
        build_ed_input(
            supercell,
            tag,
            args.pseudo_dir,
            pseudos,
            ecutwfc,
            ecutrho,
            args.ed_mode,
            k_points,
            args.ed_kpoint_mode,
            electronic_settings,
            disable_symmetry=args.ed_disable_symmetry,
            fixed_index=atom_index,
            displacement=distance * direction,
        ),
        ed_dir,
        tag,
        args.qe_executable,
        args.ed_timeout,
        args.nprocs,
        args.qe_launcher,
        args.force_qe,
        args.qe_scratch_root,
        args.keep_qe_scratch,
    )
    return {
        "distance_angstrom": float(distance),
        "tag": tag,
        "output_text": output_text,
    }


def refine_distance_grid(distances: np.ndarray, best_distance: float, refine_points: int) -> np.ndarray:
    if refine_points <= 0 or len(distances) < 2:
        return np.array([], dtype=float)
    sorted_distances = np.sort(np.unique(distances))
    peak_index = int(np.argmin(np.abs(sorted_distances - best_distance)))
    if peak_index == 0:
        left = sorted_distances[0]
        right = sorted_distances[1]
    elif peak_index == len(sorted_distances) - 1:
        left = sorted_distances[-2]
        right = sorted_distances[-1]
    else:
        left = sorted_distances[peak_index - 1]
        right = sorted_distances[peak_index + 1]
    refined = np.linspace(left, right, refine_points + 2)
    return refined[1:-1]


def site_failure(site_group: dict, message: str) -> dict:
    return {
        "element": site_group["element"],
        "site_label": site_group["label"],
        "multiplicity": site_group["multiplicity"],
        "representative_index": site_group["representative_index"],
        "status": "failed",
        "error": message,
    }


def scan_site_ed(
    supercell: Atoms,
    atom_index: int,
    site_group: dict,
    material_id: str,
    reference_energy: float,
    directions: list[tuple[str, np.ndarray]],
    args: argparse.Namespace,
    pseudos: dict[str, str],
    ed_dir: Path,
    ecutwfc: float,
    ecutrho: float,
    k_points: list[int],
    electronic_settings: dict,
) -> dict:
    nn_distance = nearest_neighbor_distance(supercell, atom_index)
    coarse_distances = np.linspace(0.3, 1.4 * nn_distance, args.ed_points)
    print(
        f"    {site_group['label']} ({site_group['element']}): atom {atom_index}, "
        f"multiplicity {site_group['multiplicity']}, nn = {nn_distance:.2f} A"
    )

    best_record = None
    direction_results: list[dict] = []
    for direction_label, direction in directions:
        sampled: dict[float, dict] = {}
        for distance in coarse_distances:
            result = evaluate_displacement(
                supercell,
                atom_index,
                float(distance),
                direction,
                site_group["label"],
                direction_label,
                material_id,
                args,
                pseudos,
                ed_dir,
                ecutwfc,
                ecutrho,
                k_points,
                electronic_settings,
            )
            if result is not None:
                sampled[round(float(distance), 8)] = result
        if not sampled:
            continue

        coarse_records = []
        for result in sampled.values():
            energy_ry = parse_total_energy_ry(result["output_text"])
            coarse_records.append(
                {
                    "distance_angstrom": result["distance_angstrom"],
                    "energy_ev": float((energy_ry - reference_energy) * RY_TO_EV),
                    "tag": result["tag"],
                    "output_text": result["output_text"],
                }
            )
        coarse_records.sort(key=lambda item: item["distance_angstrom"])
        peak_record = max(coarse_records, key=lambda item: item["energy_ev"])

        for distance in refine_distance_grid(
            np.array([record["distance_angstrom"] for record in coarse_records], dtype=float),
            peak_record["distance_angstrom"],
            args.refine_points,
        ):
            result = evaluate_displacement(
                supercell,
                atom_index,
                float(distance),
                direction,
                site_group["label"],
                direction_label,
                material_id,
                args,
                pseudos,
                ed_dir,
                ecutwfc,
                ecutrho,
                k_points,
                electronic_settings,
            )
            if result is not None:
                sampled[round(float(distance), 8)] = result

        scan_records = []
        for result in sampled.values():
            energy_ry = parse_total_energy_ry(result["output_text"])
            scan_records.append(
                {
                    "distance_angstrom": result["distance_angstrom"],
                    "energy_ev": float((energy_ry - reference_energy) * RY_TO_EV),
                    "tag": result["tag"],
                }
            )
        scan_records.sort(key=lambda item: item["distance_angstrom"])
        direction_best = max(scan_records, key=lambda item: item["energy_ev"])
        print(
            f"      {direction_label}: barrier {direction_best['energy_ev']:.3f} eV "
            f"at {direction_best['distance_angstrom']:.2f} A"
        )

        direction_result = {
            "direction": direction_label,
            "vector": [round(float(value), 8) for value in direction],
            "best_distance_angstrom": direction_best["distance_angstrom"],
            "best_energy_ev": direction_best["energy_ev"],
            "scan": scan_records,
            "status": "ignored" if direction_best["energy_ev"] <= args.reliability_floor_ev else "ok",
        }
        if direction_best["energy_ev"] <= args.reliability_floor_ev:
            print("        ignored: below reliability floor")
        else:
            if best_record is None or direction_best["energy_ev"] < best_record["energy_ev"]:
                best_record = {
                    "direction": direction_label,
                    "vector": [round(float(value), 8) for value in direction],
                    "distance_angstrom": direction_best["distance_angstrom"],
                    "energy_ev": direction_best["energy_ev"],
                    "tag": direction_best["tag"],
                    "scan": scan_records,
                }
        direction_results.append(direction_result)

    if best_record is None:
        raise RuntimeError("No reliable compound-specific DFT Ed found in scan.")

    return {
        "element": site_group["element"],
        "site_label": site_group["label"],
        "multiplicity": site_group["multiplicity"],
        "representative_index": site_group["representative_index"],
        "status": "ok",
        "ed_eV": round(float(best_record["energy_ev"]), 3),
        "best_direction": best_record["direction"],
        "best_direction_vector": best_record["vector"],
        "best_distance_angstrom": round(float(best_record["distance_angstrom"]), 6),
        "best_tag": best_record["tag"],
        "direction_results": direction_results,
    }


def aggregate_element_sites(site_results: list[dict], aggregation: str) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for result in site_results:
        grouped.setdefault(result["element"], []).append(result)

    aggregates: dict[str, dict] = {}
    for element, results in grouped.items():
        ed_values = np.array([float(result["ed_eV"]) for result in results], dtype=float)
        weights = np.array([int(result["multiplicity"]) for result in results], dtype=float)
        weighted_mean = float(np.average(ed_values, weights=weights))
        minimum = float(np.min(ed_values))
        maximum = float(np.max(ed_values))
        recommended = weighted_mean if aggregation == "weighted_mean" else minimum
        aggregates[element] = {
            "recommended_single_value_eV": round(recommended, 3),
            "aggregation_mode": aggregation,
            "weighted_mean_eV": round(weighted_mean, 3),
            "minimum_eV": round(minimum, 3),
            "maximum_eV": round(maximum, 3),
            "inequivalent_site_count": len(results),
            "site_labels": [result["site_label"] for result in results],
            "site_values_eV": {result["site_label"]: result["ed_eV"] for result in results},
            "site_multiplicities": {result["site_label"]: result["multiplicity"] for result in results},
        }
    return aggregates


def prepare_relaxed_structure(
    args: argparse.Namespace,
    material: dict,
    base_atoms: Atoms,
    elements: list[str],
    pseudos: dict[str, str],
    ecutwfc: float,
    ecutrho: float,
    k_points: list[int],
    material_id: str,
    pipeline_dir: Path,
) -> tuple[Atoms, str]:
    relax_dir = pipeline_dir / "relax"
    if args.relaxed_qe_xml:
        atoms_relaxed = parse_relaxed_structure_from_qe_xml(args.relaxed_qe_xml)
        relax_dir.mkdir(parents=True, exist_ok=True)
        write(relax_dir / f"{material_id}_relaxed.xyz", atoms_relaxed)
        return atoms_relaxed, "qe_xml_cache"
    if args.skip_qe_relax:
        return base_atoms, "jarvis_relaxed_input"

    print("  Running vc-relax...")
    relax_settings = resolve_electronic_settings(material, elements, args, stage="relax")
    relax_input = build_vc_relax_input(
        base_atoms,
        material_id,
        args.pseudo_dir,
        pseudos,
        elements,
        ecutwfc,
        ecutrho,
        k_points,
        relax_settings,
        args.vdw_corr,
    )
    relax_output = run_qe(
        relax_input,
        relax_dir,
        f"{material_id}_relax",
        args.qe_executable,
        args.relax_timeout,
        args.nprocs,
        args.qe_launcher,
        args.force_qe,
        args.qe_scratch_root,
        args.keep_qe_scratch,
    )
    atoms_relaxed = parse_relaxed_structure(relax_output, base_atoms)
    write(relax_dir / f"{material_id}_relaxed.xyz", atoms_relaxed)
    return atoms_relaxed, "qe_vc_relax"


def process_material(
    dataset: list[dict],
    request: dict[str, str | None],
    args: argparse.Namespace,
    workspace: Path,
) -> dict:
    formula = str(request["formula"])
    requested_material_id = request["material_id"]
    material, selection_info = select_material(dataset, formula, requested_material_id)
    material_id = material["jid"]
    jarvis_atoms = JarvisAtoms.from_dict(material["atoms"])
    base_atoms = Atoms(
        symbols=jarvis_atoms.elements,
        positions=jarvis_atoms.cart_coords,
        cell=jarvis_atoms.lattice_mat,
        pbc=True,
    )
    elements = list(dict.fromkeys(base_atoms.get_chemical_symbols()))
    material_bandgap = get_material_bandgap(material)
    material_magmom = parse_optional_float(material.get("magmom_oszicar"))
    if material_magmom is None:
        material_magmom = parse_optional_float(material.get("magmom"))
    primitive_settings = resolve_electronic_settings(material, elements, args, stage="relax")
    ed_settings = resolve_electronic_settings(material, elements, args, stage="ed")

    print(f"  Material: {formula} -> {material_id}")
    if selection_info["candidate_count"] > 1:
        print(f"  Selected lowest-ehull structure from {selection_info['candidate_count']} JARVIS matches.")
    print(f"  Unit cell atoms: {len(base_atoms)}")
    ehull = parse_optional_float(material.get("ehull"))
    if ehull is not None:
        print(f"  Ehull: {ehull:.4f} eV/atom")
        if ehull > 0.05:
            print("  Warning: selected polymorph is metastable above 0.05 eV/atom.")
    if material_bandgap is not None:
        print(f"  Reference band gap: {material_bandgap:.3f} eV")
    if material_magmom is not None:
        print(f"  Reference total moment: {material_magmom:.3f} mu_B")
    print(
        "  Electronic setup: "
        f"relax occupations={primitive_settings['occupations']}, "
        f"relax spin={'on' if primitive_settings['spin_polarized'] else 'off'}, "
        f"Ed occupations={ed_settings['occupations']}, "
        f"Ed spin={'on' if ed_settings['spin_polarized'] else 'off'}"
    )
    correlated_system = has_correlated_elements(elements)
    if correlated_system:
        print("  Warning: transition-metal or f-electron chemistry detected; highest fidelity may require DFT+U or hybrid validation.")

    pseudos: dict[str, str] = {}
    cutoffs_wfc: list[float] = []
    cutoffs_rho: list[float] = []
    for element in elements:
        candidates = sorted(
            file_name
            for file_name in os.listdir(args.pseudo_dir)
            if file_name.lower().endswith(".upf") and file_name.startswith(f"{element}.")
        )
        if not candidates:
            raise RuntimeError(f"Missing pseudopotential for {element} in {args.pseudo_dir}.")
        non_sp = [candidate for candidate in candidates if "_sp" not in candidate]
        pseudo_file = non_sp[0] if non_sp else candidates[0]
        pseudos[element] = pseudo_file
        info = parse_upf_header(str(Path(args.pseudo_dir) / pseudo_file))
        ecutwfc, ecutrho = get_recommended_cutoffs(element, info["z_valence"], info["l_max"], info["pseudo_type"])
        cutoffs_wfc.append(ecutwfc)
        cutoffs_rho.append(ecutrho)
        print(f"    {element}: {pseudo_file}, cutoff {ecutwfc:.0f}/{ecutrho:.0f} Ry")

    primitive_ecutwfc = rounded_cutoff(max(cutoffs_wfc) * args.ed_cutoff_scale)
    primitive_ecutrho = rounded_cutoff(max(cutoffs_rho) * args.ed_cutoff_scale)
    primitive_k_points = get_kpoints_from_cell(
        base_atoms.cell.array,
        density=args.kpoint_density,
        max_total_kpts=args.max_total_kpts,
    )
    print(f"  Primitive k-points: {primitive_k_points}")

    calculations_dir = workspace / "calculations"
    pipeline_dir = calculations_dir / f"pipeline_{material_id}"
    ed_dir = pipeline_dir / "ed"
    calculations_dir.mkdir(exist_ok=True)
    ed_dir.mkdir(parents=True, exist_ok=True)

    atoms_relaxed, structure_source = prepare_relaxed_structure(
        args,
        material,
        base_atoms,
        elements,
        pseudos,
        primitive_ecutwfc,
        primitive_ecutrho,
        primitive_k_points,
        material_id,
        pipeline_dir,
    )
    if args.idealize_relaxed_structure:
        atoms_relaxed = idealize_structure(
            atoms_relaxed,
            symprec=args.symprec,
            angle_tolerance=args.angle_tolerance,
        )
        write(pipeline_dir / f"{material_id}_idealized.xyz", atoms_relaxed)
        structure_source = f"{structure_source}+idealized"
    print(f"  Structure source: {structure_source}")

    site_groups = find_inequivalent_sites(
        atoms_relaxed,
        site_selection=args.site_selection,
        symprec=args.symprec,
        angle_tolerance=args.angle_tolerance,
    )
    site_groups = filter_site_groups(site_groups, args.site_labels)
    print(f"  Site sampling: {args.site_selection} ({len(site_groups)} site(s))")
    if args.site_labels:
        print(f"  Site filter: {', '.join(group['label'] for group in site_groups)}")

    supercell, repeats = build_supercell(atoms_relaxed, min_length=args.supercell_min_length)
    ed_ecutwfc = primitive_ecutwfc
    ed_ecutrho = primitive_ecutrho
    ed_k_points = [1, 1, 1]
    if args.ed_kpoint_mode == "auto":
        ed_k_points = get_kpoints_from_cell(
            supercell.cell.array,
            density=args.ed_kpoint_density,
            max_total_kpts=args.max_ed_kpts,
        )
    directions, direction_start, direction_stop, total_direction_count = select_direction_subset(
        generate_directions(args.direction_mode, args.ed_directions),
        args.direction_index_start,
        args.direction_index_stop,
    )

    print(f"  Supercell repeats: {repeats} -> {len(supercell)} atoms")
    print(f"  Ed k-points: {ed_k_points} ({args.ed_kpoint_mode})")
    if direction_start or direction_stop != total_direction_count:
        print(f"  Direction subset: [{direction_start}:{direction_stop}) of {total_direction_count}")
    print(f"  Direction count: {len(directions)} ({args.direction_mode})")
    print("  Running Ed scan...")

    reference_output = run_qe(
        build_ed_input(
            supercell,
            f"{material_id}_perf",
            args.pseudo_dir,
            pseudos,
            ed_ecutwfc,
            ed_ecutrho,
            "scf",
            ed_k_points,
            args.ed_kpoint_mode,
            ed_settings,
            disable_symmetry=args.ed_disable_symmetry,
        ),
        ed_dir,
        f"{material_id}_perf",
        args.qe_executable,
        args.ed_timeout,
        args.nprocs,
        args.qe_launcher,
        args.force_qe,
        args.qe_scratch_root,
        args.keep_qe_scratch,
    )
    reference_energy = parse_total_energy_ry(reference_output)

    site_results: list[dict] = []
    failures: list[str] = []
    print(f"  Ed mode: {args.ed_mode}")
    for site_group in site_groups:
        supercell_index = map_base_site_to_supercell(atoms_relaxed, supercell, repeats, site_group["representative_index"])
        try:
            site_result = scan_site_ed(
                supercell,
                supercell_index,
                site_group,
                material_id,
                reference_energy,
                directions,
                args,
                pseudos,
                ed_dir,
                ed_ecutwfc,
                ed_ecutrho,
                ed_k_points,
                ed_settings,
            )
            print(f"      -> Ed({site_group['label']}) = {site_result['ed_eV']:.3f} eV")
        except Exception as exc:
            message = str(exc)
            if args.allow_ed_fallback:
                fallback = get_default_ed(site_group["element"])
                site_result = {
                    "element": site_group["element"],
                    "site_label": site_group["label"],
                    "multiplicity": site_group["multiplicity"],
                    "representative_index": site_group["representative_index"],
                    "status": "fallback",
                    "ed_eV": round(float(fallback), 3),
                    "fallback": True,
                    "error": message,
                }
                print(f"      -> fallback Ed({site_group['label']}) = {fallback:.3f} eV")
            else:
                failures.append(f"{site_group['label']}: {message}")
                site_result = site_failure(site_group, message)
                print(f"      -> failed {site_group['label']}: {message}")
        site_results.append(site_result)

    failed_sites = [result for result in site_results if result["status"] == "failed"]
    if failed_sites:
        raise RuntimeError("; ".join(failures))

    element_aggregates = aggregate_element_sites(
        [result for result in site_results if result["status"] in {"ok", "fallback"}],
        aggregation=args.element_aggregation,
    )
    ed_values = {
        element: aggregate["recommended_single_value_eV"]
        for element, aggregate in element_aggregates.items()
    }

    return {
        "formula": formula,
        "material_id": material_id,
        "status": "ok",
        "material_selection": selection_info,
        "structure_source": structure_source,
        "material_ehull_ev_per_atom": ehull,
        "material_bandgap_ev": material_bandgap,
        "material_total_magmom_mub": material_magmom,
        "correlated_electron_caution": correlated_system,
        "qe_executable": args.qe_executable,
        "qe_relax_applied": not args.skip_qe_relax,
        "ed_mode": args.ed_mode,
        "direction_mode": args.direction_mode,
        "direction_count": len(directions),
        "direction_index_start": direction_start,
        "direction_index_stop": direction_stop,
        "total_direction_count": total_direction_count,
        "primitive_k_points": primitive_k_points,
        "ed_k_points": ed_k_points,
        "primitive_ecutwfc_ry": primitive_ecutwfc,
        "primitive_ecutrho_ry": primitive_ecutrho,
        "ed_scan_supercell_atoms": len(supercell),
        "primitive_electronic_settings": {
            "occupations": primitive_settings["occupations"],
            "spin_polarized": primitive_settings["spin_polarized"],
            "bandgap_ev": primitive_settings["bandgap_ev"],
            "total_magmom_mub": primitive_settings["total_magmom_mub"],
            "electron_conv_thr": primitive_settings["electron_conv_thr"],
            "force_conv_thr": primitive_settings["force_conv_thr"],
            "etot_conv_thr": primitive_settings["etot_conv_thr"],
            "degauss": primitive_settings["degauss"],
            "mixing_beta": primitive_settings["mixing_beta"],
        },
        "ed_electronic_settings": {
            "occupations": ed_settings["occupations"],
            "spin_polarized": ed_settings["spin_polarized"],
            "bandgap_ev": ed_settings["bandgap_ev"],
            "total_magmom_mub": ed_settings["total_magmom_mub"],
            "electron_conv_thr": ed_settings["electron_conv_thr"],
            "force_conv_thr": ed_settings["force_conv_thr"],
            "etot_conv_thr": ed_settings["etot_conv_thr"],
            "degauss": ed_settings["degauss"],
            "mixing_beta": ed_settings["mixing_beta"],
        },
        "ed_values_eV": ed_values,
        "element_aggregates_eV": element_aggregates,
        "site_results": site_results,
    }


def write_aggregate_outputs(results_dir: Path, summaries: list[dict]) -> None:
    element_csv_path = results_dir / "ed_results.csv"
    site_csv_path = results_dir / "ed_site_results.csv"
    json_path = results_dir / "ed_batch_summary.json"

    element_rows: list[dict[str, str | float | int | None]] = []
    site_rows: list[dict[str, str | float | int | None]] = []
    for summary in summaries:
        if summary.get("status") != "ok":
            element_rows.append(
                {
                    "formula": summary.get("formula", ""),
                    "material_id": summary.get("material_id", ""),
                    "element": "",
                    "recommended_ed_eV": "",
                    "aggregation_mode": "",
                    "weighted_mean_ed_eV": "",
                    "minimum_ed_eV": "",
                    "maximum_ed_eV": "",
                    "inequivalent_site_count": "",
                    "structure_source": summary.get("structure_source", ""),
                    "ed_mode": summary.get("ed_mode", ""),
                    "status": summary.get("status", "failed"),
                    "error": summary.get("error", ""),
                }
            )
            continue

        for element, aggregate in summary["element_aggregates_eV"].items():
            element_rows.append(
                {
                    "formula": summary["formula"],
                    "material_id": summary["material_id"],
                    "element": element,
                    "recommended_ed_eV": aggregate["recommended_single_value_eV"],
                    "aggregation_mode": aggregate["aggregation_mode"],
                    "weighted_mean_ed_eV": aggregate["weighted_mean_eV"],
                    "minimum_ed_eV": aggregate["minimum_eV"],
                    "maximum_ed_eV": aggregate["maximum_eV"],
                    "inequivalent_site_count": aggregate["inequivalent_site_count"],
                    "structure_source": summary["structure_source"],
                    "ed_mode": summary["ed_mode"],
                    "status": summary["status"],
                    "error": "",
                }
            )

        for site_result in summary["site_results"]:
            site_rows.append(
                {
                    "formula": summary["formula"],
                    "material_id": summary["material_id"],
                    "element": site_result["element"],
                    "site_label": site_result["site_label"],
                    "site_ed_eV": site_result.get("ed_eV", ""),
                    "multiplicity": site_result.get("multiplicity", ""),
                    "best_direction": site_result.get("best_direction", ""),
                    "best_distance_angstrom": site_result.get("best_distance_angstrom", ""),
                    "status": site_result["status"],
                    "error": site_result.get("error", ""),
                }
            )

    with element_csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "formula",
            "material_id",
            "element",
            "recommended_ed_eV",
            "aggregation_mode",
            "weighted_mean_ed_eV",
            "minimum_ed_eV",
            "maximum_ed_eV",
            "inequivalent_site_count",
            "structure_source",
            "ed_mode",
            "status",
            "error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(element_rows)

    with site_csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "formula",
            "material_id",
            "element",
            "site_label",
            "site_ed_eV",
            "multiplicity",
            "best_direction",
            "best_distance_angstrom",
            "status",
            "error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(site_rows)

    batch_summary = {
        "total_requests": len(summaries),
        "successful_materials": sum(1 for summary in summaries if summary.get("status") == "ok"),
        "failed_materials": sum(1 for summary in summaries if summary.get("status") != "ok"),
        "results_csv": str(element_csv_path),
        "site_results_csv": str(site_csv_path),
        "material_summaries": summaries,
    }
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(batch_summary, handle, indent=2)


def main() -> int:
    args = parse_args()
    args.qe_executable = resolve_executable(args.qe_executable)

    workspace = Path(args.workspace).resolve()
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)

    requests = load_material_requests(args.input_file, args.formula, args.material_id, args.max_materials)
    print(f"Loading JARVIS dataset for {len(requests)} material request(s)...")
    dataset = jarvis_data("dft_3d")

    summaries: list[dict] = []
    failures = 0
    for index, request in enumerate(requests, start=1):
        formula = str(request["formula"])
        print(f"\n[{index}/{len(requests)}] {formula}")
        try:
            summary = process_material(dataset, request, args, workspace)
        except Exception as exc:
            failures += 1
            summary = {
                "formula": formula,
                "material_id": request.get("material_id"),
                "status": "failed",
                "ed_mode": args.ed_mode,
                "error": str(exc),
            }
            print(f"  Failed: {exc}")
        summaries.append(summary)
        summary_stub = sanitize_stub(
            f"{summary.get('formula', formula)}_{summary.get('material_id') or 'auto'}"
        )
        summary_path = results_dir / f"{summary_stub}_summary.json"
        with summary_path.open("w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
        print(f"  Wrote {summary_path}")

    print(f"\nCompleted {len(summaries)} material(s) with {failures} failure(s).")
    if args.skip_aggregate_outputs:
        print("Skipped aggregate CSV generation (--skip-aggregate-outputs).")
    else:
        write_aggregate_outputs(results_dir, summaries)
        print(f"Aggregate CSV: {results_dir / 'ed_results.csv'}")
        print(f"Site CSV: {results_dir / 'ed_site_results.csv'}")
        print(f"Batch summary: {results_dir / 'ed_batch_summary.json'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
