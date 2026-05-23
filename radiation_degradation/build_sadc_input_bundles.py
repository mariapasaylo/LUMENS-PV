#!/usr/bin/env python3
"""Build OMERE/SADC input bundles from the SR-NIEL handoff outputs.

The repository already stores official SR-NIEL curves for each final material.
This script packages those curves into the JSON layout used by OMERE's SADC
component so a real SADC executable can be run without manual GUI import work.

Important boundary: the active-layer NIEL curves and densities are
material-specific, but the electrical degradation coefficients below are the
OMERE sample GaAs-style template coefficients. They make the files runnable for
handoff and QA only; publishable EOL for a novel PV material still requires
material-specific remaining-factor-vs-DDD coefficients or a defensible calibrated
cell model.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any


DEFAULT_SR_NIEL_DIR = Path("radiation_degradation/sr_niel_outputs_final_materials_20260523")
DEFAULT_OUT_NAME = "sadc_input_bundles"


GAAS_TEMPLATE_ELECTRICAL_PARAMS: list[dict[str, Any]] = [
    {
        "name": "Isc",
        "type": "ISC",
        "A": {"value": 1.0, "error%": 0.0},
        "Ne": {"value": 1.0, "error%": 0.0},
        "Np": {"value": 1.0, "error%": 0.0},
        "Ce": {"value": 0.948, "error%": 0.0},
        "Cp": {"value": 0.948, "error%": 0.0},
        "DxE": {"value": 135000000000.0, "error%": 0.0},
        "DxP": {"value": 135000000000.0, "error%": 0.0},
    },
    {
        "name": "Voc",
        "type": "VOC",
        "A": {"value": 1.0, "error%": 0.0},
        "Ne": {"value": 1.0, "error%": 0.0},
        "Np": {"value": 1.0, "error%": 0.0},
        "Ce": {"value": 0.058, "error%": 0.0},
        "Cp": {"value": 0.058, "error%": 0.0},
        "DxE": {"value": 444000000.0, "error%": 0.0},
        "DxP": {"value": 205000000.0, "error%": 0.0},
    },
    {
        "name": "Pmax",
        "type": "PMAX",
        "A": {"value": 1.0, "error%": 0.0},
        "Ne": {"value": 1.0, "error%": 0.0},
        "Np": {"value": 1.0, "error%": 0.0},
        "Ce": {"value": 0.306, "error%": 0.0},
        "Cp": {"value": 0.306, "error%": 0.0},
        "DxE": {"value": 6720000000.0, "error%": 0.0},
        "DxP": {"value": 3630000000.0, "error%": 0.0},
    },
    {
        "name": "Ipm",
        "type": "IPM",
        "A": {"value": 1.0, "error%": 0.0},
        "Ne": {"value": 1.0, "error%": 0.0},
        "Np": {"value": 1.0, "error%": 0.0},
        "Ce": {"value": 0.703, "error%": 0.0},
        "Cp": {"value": 0.703, "error%": 0.0},
        "DxE": {"value": 68400000000.0, "error%": 0.0},
        "DxP": {"value": 68400000000.0, "error%": 0.0},
    },
    {
        "name": "Vpm",
        "type": "VPM",
        "A": {"value": 1.0, "error%": 0.0},
        "Ne": {"value": 1.0, "error%": 0.0},
        "Np": {"value": 1.0, "error%": 0.0},
        "Ce": {"value": 0.062, "error%": 0.0},
        "Cp": {"value": 0.062, "error%": 0.0},
        "DxE": {"value": 623000000.0, "error%": 0.0},
        "DxP": {"value": 123000000.0, "error%": 0.0},
    },
]


MISSION_LEO_10YR: dict[str, Any] = {
    "segments": [
        {
            "name": "LEO 10yrs",
            "sources": [
                {
                    "particle": "electrons",
                    "path": "samples/Missions data/electrons/trappedElectrons_LEOPOL_AE8.flx",
                    "unit": "MeV-1.cm-2.s-1",
                    "error%": 5,
                    "transported": False,
                },
                {
                    "particle": "protons",
                    "path": "samples/Missions data/protons/trappedProtons_LEO.flx",
                    "unit": "MeV-1.cm-2.s-1",
                    "error%": 5,
                    "transported": False,
                },
            ],
            "duration": {"value": 10.0, "unit": "years"},
        }
    ],
    "start_date": 1735732800,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--srniel-dir", type=Path, default=DEFAULT_SR_NIEL_DIR)
    parser.add_argument("--jarvis-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--active-thickness-um", type=float, default=2.0)
    parser.add_argument("--coverglass-thickness-um", type=float, default=150.0)
    parser.add_argument("--adhesive-thickness-um", type=float, default=20.0)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def load_jarvis_densities(path: Path) -> dict[str, float]:
    with path.open() as handle:
        records = json.load(handle)

    densities: dict[str, float] = {}
    for record in records:
        jid = record.get("jid") or record.get("material_id")
        density = record.get("density")
        if jid is None or density in (None, "", "na", "NA"):
            continue
        try:
            densities[str(jid)] = float(density)
        except (TypeError, ValueError):
            continue
    return densities


def cell_payload(
    *,
    formula: str,
    density_g_cm3: float,
    active_thickness_um: float,
    coverglass_thickness_um: float,
    adhesive_thickness_um: float,
) -> dict[str, Any]:
    return {
        "layers": [
            {
                "name": "coverglass",
                "type": "optical",
                "family": "glass",
                "thickness": {"value": coverglass_thickness_um, "unit": "um"},
                "density": 2.61,
                "formula": "SiO2",
                "transmission": {
                    "path": "optical loss/Optical_loss_table - clear.dat",
                    "error%": 0.0,
                },
            },
            {
                "name": "Adhesive",
                "type": "optical",
                "family": "silicones",
                "thickness": {"value": adhesive_thickness_um, "unit": "um"},
                "density": 1.03,
                "formula": "SiOC2H6",
                "transmission": {
                    "path": "optical loss/Optical_loss_table - clear.dat",
                    "error%": 0.0,
                },
                "electronTID": {"path": "config/optical_loss/TID_Table_DC93-500.dat"},
            },
            {
                "name": formula,
                "type": "active",
                "family": "semiconductors",
                "thickness": {"value": active_thickness_um, "unit": "um"},
                "density": density_g_cm3,
                "lambdaFrom_nm": 750,
                "lambdaTo_nm": 900,
                "protonNiel": "niel/proton_NIEL.dat",
                "electronNiel": "niel/electron_NIEL.dat",
                "electricalParams": GAAS_TEMPLATE_ELECTRICAL_PARAMS,
                "formula": formula,
            },
            {
                "name": "Aluminium back side",
                "type": "none",
                "family": "lightMetals",
                "thickness": {"value": 6000.0, "unit": "um"},
                "density": 2.7,
                "formula": "Al2",
            },
        ]
    }


def build_manifest_row(
    row: dict[str, str],
    bundle_rel: str,
    density: float | None,
    missing_density: bool,
) -> dict[str, Any]:
    return {
        "srniel_damage_rank": row["srniel_damage_rank"],
        "formula": row["formula"],
        "material_id": row["material_id"],
        "has_fallback_ed": row["has_fallback_ed"],
        "density_g_cm3": "" if density is None else f"{density:.6g}",
        "density_source": "JARVIS-DFT density field" if not missing_density else "missing",
        "cell_json": f"{bundle_rel}/Cell.json",
        "mission_json": f"{bundle_rel}/Mission.json",
        "electron_niel": f"{bundle_rel}/niel/electron_NIEL.dat",
        "proton_niel": f"{bundle_rel}/niel/proton_NIEL.dat",
        "cell_template": "OMERE SADC Generic_GaAs_cell-like layer stack",
        "degradation_coefficients": "OMERE sample GaAs template; replace for publishable novel-material EOL",
        "sadc_status": "ready_for_real_sadc_executable",
    }


def write_readme(out_dir: Path, manifest_rows: list[dict[str, Any]]) -> None:
    top_five = manifest_rows[:5]
    top_lines = "\n".join(
        f"- {row['srniel_damage_rank']}: {row['formula']} ({row['material_id']})"
        for row in top_five
    )
    readme = f"""# SADC Input Bundles

This directory packages the 62 final-material SR-NIEL outputs into the JSON
layout used by OMERE's SADC solar-array degradation component.

## Contents

- `sadc_run_manifest.csv`: one row per material bundle.
- `<rank>_<formula>_<jid>/Cell.json`: OMERE/SADC cell definition.
- `<rank>_<formula>_<jid>/Mission.json`: 10-year LEO mission segment definition.
- `<rank>_<formula>_<jid>/niel/*_NIEL.dat`: official SR-NIEL curve files copied
  from `../omere_inputs`.

## Current Ranking Boundary

The first five SR-NIEL screening materials are:

{top_lines}

These ranks are displacement-damage screening ranks from official SR-NIEL
curves and the repository's Stage A Ed inputs. They are not OMERE EOL values.

## SADC Command Pattern

Once a real `SADC.exe` is available, run each bundle from the OMERE `datac/SADC`
directory or make the sample mission/config paths visible from the working
directory:

```bash
SADC.exe -v3 -s /absolute/path/to/bundle/Mission.json /absolute/path/to/bundle/Cell.json
```

The OMERE 5.8.1 installer available in the local CrossOver bottle did not
install a standalone `SADC.exe`; copying or renaming `Omere.exe` is not a valid
substitute.

## Publication Boundary

The active layer's formula, density, and NIEL curves are material-specific.
The electrical degradation coefficients are the OMERE sample GaAs template
coefficients. Replace those coefficients with measured/calibrated
remaining-factor-vs-DDD coefficients before claiming material-specific EOL for
novel PV candidates.
"""
    out_dir.joinpath("README.md").write_text(readme)


def main() -> int:
    args = parse_args()
    srniel_dir = args.srniel_dir
    out_dir = args.out_dir or srniel_dir / DEFAULT_OUT_NAME

    metrics_path = srniel_dir / "srniel_screening_metrics.csv"
    omere_manifest_path = srniel_dir / "omere_input_manifest.csv"
    if not metrics_path.exists():
        raise FileNotFoundError(metrics_path)
    if not omere_manifest_path.exists():
        raise FileNotFoundError(omere_manifest_path)

    metrics = sorted(
        read_csv(metrics_path),
        key=lambda row: int(row["srniel_damage_rank"]),
    )
    omere_rows = read_csv(omere_manifest_path)
    omere_by_key = {
        (row["formula"], row["material_id"], row["particle"]): row
        for row in omere_rows
    }
    densities = load_jarvis_densities(args.jarvis_json)

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []
    missing_densities: list[str] = []

    for row in metrics:
        formula = row["formula"]
        material_id = row["material_id"]
        rank = int(row["srniel_damage_rank"])
        bundle_name = safe_name(f"{rank:02d}_{formula}_{material_id}")
        bundle_dir = out_dir / bundle_name
        niel_dir = bundle_dir / "niel"
        niel_dir.mkdir(parents=True, exist_ok=True)

        density = densities.get(material_id)
        manifest_density = density
        missing_density = density is None
        if missing_density:
            missing_densities.append(f"{formula}_{material_id}")
            density = 1.0

        for particle, target_name in (("electron", "electron_NIEL.dat"), ("proton", "proton_NIEL.dat")):
            manifest_row = omere_by_key.get((formula, material_id, particle))
            if manifest_row is None:
                raise KeyError(f"missing OMERE input manifest row for {formula} {material_id} {particle}")
            src = srniel_dir / manifest_row["omere_dat"]
            if not src.exists():
                raise FileNotFoundError(src)
            shutil.copy2(src, niel_dir / target_name)

        write_json(
            bundle_dir / "Cell.json",
            cell_payload(
                formula=formula,
                density_g_cm3=float(density),
                active_thickness_um=args.active_thickness_um,
                coverglass_thickness_um=args.coverglass_thickness_um,
                adhesive_thickness_um=args.adhesive_thickness_um,
            ),
        )
        write_json(bundle_dir / "Mission.json", MISSION_LEO_10YR)
        rel_bundle = f"{DEFAULT_OUT_NAME}/{bundle_name}"
        manifest_rows.append(build_manifest_row(row, rel_bundle, manifest_density, missing_density))

    manifest_path = out_dir / "sadc_run_manifest.csv"
    with manifest_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)

    write_readme(out_dir, manifest_rows)

    print(f"wrote {len(manifest_rows)} SADC bundles under {out_dir}")
    print(f"wrote manifest: {manifest_path}")
    print(f"missing JARVIS densities: {len(missing_densities)}")
    if missing_densities:
        for key in missing_densities:
            print(f"missing density: {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
