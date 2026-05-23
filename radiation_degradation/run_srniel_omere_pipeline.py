#!/usr/bin/env python3
"""Generate SR-NIEL curves, OMERE inputs, and damage-ranking tables.

This script intentionally separates three levels of output:

1. SR-NIEL results downloaded from the public SR-NIEL web calculator.
2. OMERE-ready NIEL curve files written as two-column ``.dat`` files.
3. Screening damage metrics computed from the SR-NIEL curves.

It does not fabricate OMERE solar-cell EOL values. True OMERE EOL requires
running OMERE/TRAD with a mission, shielding, solar-cell model, and degradation
method/coefficients.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup


ELECTRON_URL = (
    "https://www.sr-niel.org/index.php/sr-niel-web-calculators/"
    "niel-calculator-for-electrons-protons-and-ions/electrons-niel-calculator"
)
PROTON_URL = (
    "https://www.sr-niel.org/index.php/sr-niel-web-calculators/"
    "niel-calculator-for-electrons-protons-and-ions/protons-ions-niel-calculator"
)

DEFAULT_LEO_OMERE_DIFFERENTIAL_SPECTRA = {
    # Extracted from the repository's OMERE 5.9 sample .fle output for a
    # 10-year 800 km, 98 deg LEO case using AE8 Max, AP8 Min, ESP 90%.
    # Units are differential fluence per MeV-cm2.
    "electron": [
        (4.00e-02, 1.27e15),
        (1.00e-01, 8.54e14),
        (2.50e-01, 2.42e14),
        (5.00e-01, 2.76e13),
        (7.50e-01, 7.43e12),
        (1.00e00, 3.32e12),
        (1.50e00, 1.26e12),
        (2.00e00, 5.30e11),
        (2.50e00, 2.59e11),
        (3.00e00, 1.06e11),
        (3.50e00, 4.20e10),
        (4.00e00, 1.57e10),
        (4.50e00, 5.06e09),
        (5.00e00, 1.47e09),
        (5.50e00, 3.39e08),
        (6.00e00, 5.47e07),
        (6.50e00, 8.45e06),
        (7.00e00, 6.44e05),
    ],
    "proton": [
        (1.00e-01, 1.62e13),
        (2.50e-01, 4.60e12),
        (5.00e-01, 1.09e12),
        (7.50e-01, 4.07e11),
        (1.00e00, 1.83e11),
        (1.00e00, 2.83e11),
        (2.00e00, 8.52e10),
        (3.00e00, 4.72e10),
        (4.00e00, 2.70e10),
        (5.00e00, 1.78e10),
        (6.00e00, 1.28e10),
        (7.00e00, 9.69e09),
        (8.00e00, 7.70e09),
        (1.00e01, 5.13e09),
        (1.20e01, 3.71e09),
        (1.50e01, 2.57e09),
        (1.70e01, 2.05e09),
        (2.00e01, 1.52e09),
        (2.50e01, 1.02e09),
        (3.00e01, 7.71e08),
        (3.50e01, 6.12e08),
        (4.00e01, 5.17e08),
        (4.50e01, 4.48e08),
        (5.00e01, 4.00e08),
        (5.50e01, 3.64e08),
        (6.00e01, 3.37e08),
        (7.00e01, 2.90e08),
        (8.00e01, 2.55e08),
        (9.00e01, 2.26e08),
        (1.00e02, 2.03e08),
        (1.25e02, 1.53e08),
        (1.50e02, 1.15e08),
        (1.75e02, 8.77e07),
        (2.00e02, 6.73e07),
        (2.25e02, 5.00e07),
        (2.50e02, 3.85e07),
        (2.75e02, 3.05e07),
        (3.00e02, 2.47e07),
    ],
}

ATOMIC_NUMBERS = {
    "H": 1,
    "He": 2,
    "Li": 3,
    "Be": 4,
    "B": 5,
    "C": 6,
    "N": 7,
    "O": 8,
    "F": 9,
    "Ne": 10,
    "Na": 11,
    "Mg": 12,
    "Al": 13,
    "Si": 14,
    "P": 15,
    "S": 16,
    "Cl": 17,
    "Ar": 18,
    "K": 19,
    "Ca": 20,
    "Sc": 21,
    "Ti": 22,
    "V": 23,
    "Cr": 24,
    "Mn": 25,
    "Fe": 26,
    "Co": 27,
    "Ni": 28,
    "Cu": 29,
    "Zn": 30,
    "Ga": 31,
    "Ge": 32,
    "As": 33,
    "Se": 34,
    "Br": 35,
    "Kr": 36,
    "Rb": 37,
    "Sr": 38,
    "Y": 39,
    "Zr": 40,
    "Nb": 41,
    "Mo": 42,
    "Tc": 43,
    "Ru": 44,
    "Rh": 45,
    "Pd": 46,
    "Ag": 47,
    "Cd": 48,
    "In": 49,
    "Sn": 50,
    "Sb": 51,
    "Te": 52,
    "I": 53,
    "Xe": 54,
    "Cs": 55,
    "Ba": 56,
    "La": 57,
    "Ce": 58,
    "Pr": 59,
    "Nd": 60,
    "Pm": 61,
    "Sm": 62,
    "Eu": 63,
    "Gd": 64,
    "Tb": 65,
    "Dy": 66,
    "Ho": 67,
    "Er": 68,
    "Tm": 69,
    "Yb": 70,
    "Lu": 71,
    "Hf": 72,
    "Ta": 73,
    "W": 74,
    "Re": 75,
    "Os": 76,
    "Ir": 77,
    "Pt": 78,
    "Au": 79,
    "Hg": 80,
    "Tl": 81,
    "Pb": 82,
    "Bi": 83,
}


@dataclass(frozen=True)
class Material:
    formula: str
    material_id: str
    elements: tuple[str, ...]
    stoich: tuple[float, ...]
    ed_ev: tuple[float, ...]
    methods: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.formula}_{self.material_id}"

    @property
    def safe_key(self) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", self.key)

    @property
    def has_fallback_ed(self) -> bool:
        return any("fallback" in method for method in self.methods)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ed-input", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--max-materials", type=int, default=None)
    parser.add_argument("--delay-s", type=float, default=1.0)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--electron-emin", type=float, default=0.04)
    parser.add_argument("--electron-emax", type=float, default=100.0)
    parser.add_argument("--electron-form-factor", default="0")
    parser.add_argument("--proton-emin", type=float, default=1.0e-4)
    parser.add_argument("--proton-emax", type=float, default=1.0e4)
    parser.add_argument("--proton-ion-model", default="1")
    parser.add_argument("--proton-scale", default="0")
    parser.add_argument("--fluence", type=float, default=1.0)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def read_materials(path: Path, max_materials: int | None) -> list[Material]:
    rows = list(csv.DictReader(path.open("r", encoding="utf-8", newline="")))
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault((row["formula"], row["material_id"]), []).append(row)

    materials: list[Material] = []
    for (formula, material_id), group in grouped.items():
        materials.append(
            Material(
                formula=formula,
                material_id=material_id,
                elements=tuple(row["element"] for row in group),
                stoich=tuple(float(row["stoichiometric_index"]) for row in group),
                ed_ev=tuple(float(row["displacement_threshold_energy_eV"]) for row in group),
                methods=tuple(row["calculation_method"] for row in group),
                notes=tuple(row["notes"] for row in group),
            )
        )

    materials.sort(key=lambda item: (item.formula, item.material_id))
    if max_materials is not None:
        materials = materials[:max_materials]
    return materials


def srniel_payload(material: Material, particle: str, args: argparse.Namespace) -> dict[str, str]:
    if particle == "electron":
        payload = {
            "FF": str(args.electron_form_factor),
            "TARGET": "0",
            "NELEM": str(len(material.elements)),
            "Emin": f"{args.electron_emin:g}",
            "Emax": f"{args.electron_emax:g}",
            "AddEnergy": "",
            "Fluence": f"{args.fluence:g}",
            "formSubmit": "CALCULATE",
        }
    elif particle == "proton":
        payload = {
            "Zi": "1",
            "Ionmodel": str(args.proton_ion_model),
            "Scale": str(args.proton_scale),
            "TARGET": "0",
            "NELEM": str(len(material.elements)),
            "Emin": f"{args.proton_emin:g}",
            "Emax": f"{args.proton_emax:g}",
            "AddEnergy": "",
            "Fluence": f"{args.fluence:g}",
            "formSubmit": "CALCULATE",
        }
    else:
        raise ValueError(f"unknown particle: {particle}")

    for index, (element, stoich, ed_ev) in enumerate(
        zip(material.elements, material.stoich, material.ed_ev, strict=True),
        start=1,
    ):
        payload[f"Z{index}"] = str(ATOMIC_NUMBERS[element])
        payload[f"Stoich{index}"] = f"{stoich:g}"
        payload[f"Th{index}"] = f"{ed_ev:g}"
    return payload


def result_anchor(soup: BeautifulSoup) -> str | None:
    for anchor in soup.find_all("a", href=True):
        text = anchor.get_text(" ", strip=True)
        href = anchor["href"]
        if "RESULT" in text.upper() and "Simulation" in href:
            return href
    return None


def fetch_srniel(
    session: requests.Session,
    material: Material,
    particle: str,
    args: argparse.Namespace,
) -> tuple[str, pd.DataFrame, dict[str, str]]:
    url = ELECTRON_URL if particle == "electron" else PROTON_URL
    payload = srniel_payload(material, particle, args)
    response = session.post(url, data=payload, timeout=args.timeout_s)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    href = result_anchor(soup)
    if href is None:
        raise RuntimeError("SR-NIEL response did not contain a Simulation result link")
    result_url = href if href.startswith("http") else f"https://www.sr-niel.org/{href.lstrip('/')}"

    result_response = session.get(result_url, timeout=args.timeout_s)
    result_response.raise_for_status()
    tables = pd.read_html(io.StringIO(result_response.text))
    curve = None
    for table in tables:
        if table.shape[1] >= 2 and "Energy" in str(table.columns[0]) and "NIEL" in str(table.columns[1]):
            curve = table.iloc[:, :2].copy()
            break
    if curve is None:
        raise RuntimeError(f"could not parse NIEL table from {result_url}")

    curve.columns = ["energy_MeV", "niel_MeV_cm2_g"]
    curve["energy_MeV"] = pd.to_numeric(curve["energy_MeV"], errors="coerce")
    curve["niel_MeV_cm2_g"] = pd.to_numeric(curve["niel_MeV_cm2_g"], errors="coerce")
    curve = curve.dropna().sort_values("energy_MeV").reset_index(drop=True)
    if curve.empty:
        raise RuntimeError(f"parsed empty NIEL table from {result_url}")
    return result_url, curve, payload


def write_omere_dat(path: Path, curve: pd.DataFrame) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# Energy_MeV\tNIEL_MeV_cm2_g\n")
        curve[["energy_MeV", "niel_MeV_cm2_g"]].to_csv(
            handle,
            sep="\t",
            index=False,
            header=False,
            float_format="%.6e",
        )


def log_integral(curve: pd.DataFrame) -> float:
    energies = curve["energy_MeV"].to_numpy(dtype=float)
    niel = curve["niel_MeV_cm2_g"].to_numpy(dtype=float)
    total = 0.0
    for idx in range(len(energies) - 1):
        e0, e1 = energies[idx], energies[idx + 1]
        y0, y1 = niel[idx], niel[idx + 1]
        if e0 <= 0 or e1 <= 0:
            total += 0.5 * (y0 + y1) * (e1 - e0)
        else:
            total += 0.5 * (y0 + y1) * math.log(e1 / e0)
    return total


def interp(curve: pd.DataFrame, energy: float) -> float | None:
    energies = curve["energy_MeV"].to_numpy(dtype=float)
    niel = curve["niel_MeV_cm2_g"].to_numpy(dtype=float)
    if energy < energies.min() or energy > energies.max():
        return None
    return float(pd.Series(niel, index=energies).sort_index().reindex([energy]).interpolate(method="index").iloc[0])


def niel_at_energy(curve: pd.DataFrame, energy: float) -> float:
    energies = curve["energy_MeV"].to_numpy(dtype=float)
    niel = curve["niel_MeV_cm2_g"].to_numpy(dtype=float)
    if energy <= energies.min():
        return float(niel[0])
    if energy >= energies.max():
        return float(niel[-1])
    positive = (energies > 0) & (niel > 0)
    if energy > 0 and positive.sum() >= 2 and niel_at_bracket_positive(energies, niel, energy):
        log_series = pd.Series(niel[positive], index=energies[positive]).sort_index().apply(math.log)
        interp_index = log_series.index.union([energy])
        log_value = log_series.reindex(interp_index).sort_index().interpolate(method="index").loc[energy]
        return float(math.exp(log_value))
    linear_series = pd.Series(niel, index=energies).sort_index()
    interp_index = linear_series.index.union([energy])
    return float(linear_series.reindex(interp_index).sort_index().interpolate(method="index").loc[energy])


def niel_at_bracket_positive(energies: object, niel: object, energy: float) -> bool:
    e_series = pd.Series(niel, index=energies).sort_index()
    below = e_series[e_series.index <= energy]
    above = e_series[e_series.index >= energy]
    return bool(len(below) and len(above) and below.iloc[-1] > 0 and above.iloc[0] > 0)


def spectral_ddd(curve: pd.DataFrame, spectrum: list[tuple[float, float]]) -> float:
    """Integrate differential fluence times NIEL over particle energy."""
    if not spectrum:
        return 0.0
    points = sorted(spectrum)
    total = 0.0
    for idx in range(len(points) - 1):
        e0, f0 = points[idx]
        e1, f1 = points[idx + 1]
        y0 = f0 * niel_at_energy(curve, e0)
        y1 = f1 * niel_at_energy(curve, e1)
        total += 0.5 * (y0 + y1) * (e1 - e0)
    return total


def append_manifest_row(path: Path, row: dict[str, object]) -> None:
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def load_existing_links(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    rows = csv.DictReader(path.open("r", encoding="utf-8", newline=""))
    return {(row["formula"], row["material_id"], row["particle"]) for row in rows if row.get("status") == "ok"}


def read_curve(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, comment="#", sep=r"\s+", names=["energy_MeV", "niel_MeV_cm2_g"])


def build_metrics(materials: Iterable[Material], out_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for material in materials:
        paths = {
            "electron": out_dir / "omere_inputs" / f"{material.safe_key}_e_NIEL.dat",
            "proton": out_dir / "omere_inputs" / f"{material.safe_key}_p_NIEL.dat",
        }
        if not all(path.exists() for path in paths.values()):
            continue
        e_curve = read_curve(paths["electron"])
        p_curve = read_curve(paths["proton"])
        rows.append(
            {
                "formula": material.formula,
                "material_id": material.material_id,
                "has_fallback_ed": material.has_fallback_ed,
                "element_count": len(material.elements),
                "elements": ";".join(material.elements),
                "ed_eV_by_element": ";".join(f"{el}:{ed:.6g}" for el, ed in zip(material.elements, material.ed_ev, strict=True)),
                "electron_log_integral_0p04_100_MeV": log_integral(e_curve),
                "electron_niel_1MeV_MeV_cm2_g": interp(e_curve, 1.0),
                "electron_niel_10MeV_MeV_cm2_g": interp(e_curve, 10.0),
                "electron_niel_100MeV_MeV_cm2_g": interp(e_curve, 100.0),
                "proton_log_integral_1e-4_1e4_MeV": log_integral(p_curve),
                "proton_niel_1MeV_MeV_cm2_g": interp(p_curve, 1.0),
                "proton_niel_10MeV_MeV_cm2_g": interp(p_curve, 10.0),
                "proton_niel_100MeV_MeV_cm2_g": interp(p_curve, 100.0),
                "leo10yr_electron_ddd_MeV_g": spectral_ddd(e_curve, DEFAULT_LEO_OMERE_DIFFERENTIAL_SPECTRA["electron"]),
                "leo10yr_proton_ddd_MeV_g": spectral_ddd(p_curve, DEFAULT_LEO_OMERE_DIFFERENTIAL_SPECTRA["proton"]),
            }
        )
    metrics = pd.DataFrame(rows)
    if metrics.empty:
        return metrics

    # Lower NIEL integral is less displacement damage for a fixed spectral fluence.
    for column in ["electron_log_integral_0p04_100_MeV", "proton_log_integral_1e-4_1e4_MeV"]:
        baseline = metrics[column].median()
        metrics[f"{column}_relative_to_median"] = metrics[column] / baseline
    metrics["srniel_damage_screening_score"] = (
        metrics["electron_log_integral_0p04_100_MeV_relative_to_median"]
        * metrics["proton_log_integral_1e-4_1e4_MeV_relative_to_median"]
    ) ** 0.5
    metrics["leo10yr_total_ddd_MeV_g"] = metrics["leo10yr_electron_ddd_MeV_g"] + metrics["leo10yr_proton_ddd_MeV_g"]
    metrics["leo10yr_total_ddd_relative_to_median"] = (
        metrics["leo10yr_total_ddd_MeV_g"] / metrics["leo10yr_total_ddd_MeV_g"].median()
    )
    metrics = metrics.sort_values(
        ["has_fallback_ed", "leo10yr_total_ddd_MeV_g", "srniel_damage_screening_score", "formula", "material_id"],
        ascending=[True, True, True, True, True],
    ).reset_index(drop=True)
    metrics["srniel_damage_rank"] = range(1, len(metrics) + 1)
    return metrics


def write_run_manifest(out_dir: Path, args: argparse.Namespace, materials: list[Material]) -> None:
    manifest = {
        "ed_input": str(args.ed_input),
        "material_count": len(materials),
        "generated_at_note": "Timestamp intentionally omitted for deterministic diffs; use file mtimes or SR-NIEL URLs for run provenance.",
        "srniel": {
            "electron_url": ELECTRON_URL,
            "proton_url": PROTON_URL,
            "electron_parameters": {
                "FF": args.electron_form_factor,
                "TARGET": "0",
                "Emin": args.electron_emin,
                "Emax": args.electron_emax,
                "Fluence": args.fluence,
            },
            "proton_parameters": {
                "Zi": 1,
                "Ionmodel": args.proton_ion_model,
                "Scale": args.proton_scale,
                "TARGET": "0",
                "Emin": args.proton_emin,
                "Emax": args.proton_emax,
                "Fluence": args.fluence,
            },
            "default_leo_omere_spectrum": {
                "description": (
                    "Repository OMERE 5.9 sample spectrum for 10-year circular 800 km, "
                    "98 deg LEO, AE8 Max electrons, AP8 Min protons, ESP 90% solar protons."
                ),
                "differential_fluence_units": "per MeV-cm2",
                "electron": DEFAULT_LEO_OMERE_DIFFERENTIAL_SPECTRA["electron"],
                "proton": DEFAULT_LEO_OMERE_DIFFERENTIAL_SPECTRA["proton"],
            },
        },
        "outputs": {
            "srniel_result_links": "srniel_result_links.csv",
            "omere_inputs": "omere_inputs/*.dat",
            "omere_input_manifest": "omere_input_manifest.csv",
            "srniel_curves": "srniel_curves.csv",
            "srniel_screening_metrics": "srniel_screening_metrics.csv",
            "eol_damage_screening_inputs": "eol_damage_screening_inputs.csv",
        },
        "eol_boundary": (
            "These files provide SR-NIEL curves and OMERE-ready inputs. "
            "True OMERE solar-cell EOL requires running OMERE/TRAD with a mission, shielding, "
            "solar-cell degradation method, and material/cell degradation coefficients."
        ),
    }
    (out_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def build_combined_curves(raw_dir: Path, links_path: Path, curves_path: Path) -> None:
    existing_curves = []
    raw_metadata: dict[str, dict[str, str]] = {}
    if links_path.exists():
        for row in csv.DictReader(links_path.open("r", encoding="utf-8", newline="")):
            raw_name = Path(row.get("raw_curve_csv", "")).name
            if raw_name:
                raw_metadata[raw_name] = {
                    "formula": row.get("formula", ""),
                    "material_id": row.get("material_id", ""),
                    "particle": row.get("particle", ""),
                }
    for raw_path in sorted(raw_dir.glob("*_srniel.csv")):
        metadata = raw_metadata.get(raw_path.name)
        if metadata is None:
            raise RuntimeError(f"missing manifest metadata for {raw_path}")
        curve = pd.read_csv(raw_path)
        for column in ["particle", "material_id", "formula"]:
            curve.insert(0, column, metadata[column])
        curve["source_file"] = raw_path.name
        existing_curves.append(curve)
    if existing_curves:
        pd.concat(existing_curves, ignore_index=True).to_csv(curves_path, index=False)


def main() -> int:
    args = parse_args()
    materials = read_materials(args.ed_input, args.max_materials)
    if args.out_dir.exists() and not args.resume and any(args.out_dir.iterdir()):
        raise SystemExit(f"{args.out_dir} already exists and is not empty; use --resume or choose a new --out-dir")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    omere_dir = args.out_dir / "omere_inputs"
    raw_dir = args.out_dir / "raw_srniel_tables"
    omere_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    write_run_manifest(args.out_dir, args, materials)

    links_path = args.out_dir / "srniel_result_links.csv"
    omere_manifest_path = args.out_dir / "omere_input_manifest.csv"
    curves_path = args.out_dir / "srniel_curves.csv"
    processed = load_existing_links(links_path) if args.resume else set()

    session = requests.Session()
    session.headers.update({"User-Agent": "LUMENS-PV SR-NIEL research pipeline"})

    for index, material in enumerate(materials, start=1):
        for particle in ["electron", "proton"]:
            if (material.formula, material.material_id, particle) in processed:
                continue
            print(f"[{index}/{len(materials)}] {material.formula} {material.material_id} {particle}", flush=True)
            try:
                result_url, curve, payload = fetch_srniel(session, material, particle, args)
                suffix = "e" if particle == "electron" else "p"
                dat_path = omere_dir / f"{material.safe_key}_{suffix}_NIEL.dat"
                raw_path = raw_dir / f"{material.safe_key}_{suffix}_srniel.csv"
                write_omere_dat(dat_path, curve)
                curve.to_csv(raw_path, index=False)

                row = {
                    "formula": material.formula,
                    "material_id": material.material_id,
                    "particle": particle,
                    "status": "ok",
                    "result_url": result_url,
                    "omere_dat": str(dat_path.relative_to(args.out_dir)),
                    "raw_curve_csv": str(raw_path.relative_to(args.out_dir)),
                    "elements": ";".join(material.elements),
                    "stoichiometry": ";".join(f"{value:g}" for value in material.stoich),
                    "ed_eV": ";".join(f"{value:g}" for value in material.ed_ev),
                    "has_fallback_ed": material.has_fallback_ed,
                    "payload_json": json.dumps(payload, sort_keys=True),
                    "error": "",
                }
                append_manifest_row(links_path, row)
                append_manifest_row(
                    omere_manifest_path,
                    {
                        "formula": material.formula,
                        "material_id": material.material_id,
                        "particle": particle,
                        "omere_dat": str(dat_path.relative_to(args.out_dir)),
                        "elements": ";".join(material.elements),
                        "stoichiometry": ";".join(f"{value:g}" for value in material.stoich),
                        "ed_eV": ";".join(f"{value:g}" for value in material.ed_ev),
                        "has_fallback_ed": material.has_fallback_ed,
                    },
                )
            except Exception as exc:  # noqa: BLE001 - preserve per-material failure and continue.
                append_manifest_row(
                    links_path,
                    {
                        "formula": material.formula,
                        "material_id": material.material_id,
                        "particle": particle,
                        "status": "failed",
                        "result_url": "",
                        "omere_dat": "",
                        "raw_curve_csv": "",
                        "elements": ";".join(material.elements),
                        "stoichiometry": ";".join(f"{value:g}" for value in material.stoich),
                        "ed_eV": ";".join(f"{value:g}" for value in material.ed_ev),
                        "has_fallback_ed": material.has_fallback_ed,
                        "payload_json": json.dumps(srniel_payload(material, particle, args), sort_keys=True),
                        "error": repr(exc),
                    },
                )
                print(f"  failed: {exc}", file=sys.stderr, flush=True)
            time.sleep(args.delay_s)

    build_combined_curves(raw_dir, links_path, curves_path)

    metrics = build_metrics(materials, args.out_dir)
    if not metrics.empty:
        metrics.to_csv(args.out_dir / "srniel_screening_metrics.csv", index=False)
        eol_inputs = metrics.copy()
        eol_inputs["eol_status"] = "requires_omere_or_material_degradation_coefficients"
        eol_inputs["required_next_inputs"] = (
            "OMERE mission/shielding output plus solar-cell degradation model "
            "(JPL/NRL/SADC) or material-specific remaining-factor-vs-DDD coefficients"
        )
        eol_inputs.to_csv(args.out_dir / "eol_damage_screening_inputs.csv", index=False)

    with (args.out_dir / "electron_input_files.txt").open("w", encoding="utf-8") as handle:
        for path in sorted(omere_dir.glob("*_e_NIEL.dat")):
            handle.write(str(path.relative_to(args.out_dir)).replace("/", "\\") + "\n")
    with (args.out_dir / "proton_input_files.txt").open("w", encoding="utf-8") as handle:
        for path in sorted(omere_dir.glob("*_p_NIEL.dat")):
            handle.write(str(path.relative_to(args.out_dir)).replace("/", "\\") + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
