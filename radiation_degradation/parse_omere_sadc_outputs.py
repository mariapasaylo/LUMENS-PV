#!/usr/bin/env python3
"""Parse TRAD OMERE/SADC text outputs into EOL ranking tables.

This script does not calculate solar-cell degradation. It extracts the layer
provenance and remaining-factor values already computed by OMERE/SADC.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from pathlib import Path


PARAM_RE = re.compile(r"^\s*(Isc|Voc|Pmax|Ipm|Vpm)\s+(.+?)\s*$")
LAYER_RE = re.compile(
    r'#\s+"(?P<layer_name>[^"]+)" \(layer #(?P<layer_number>\d+)\).*?'
    r"#\s+Type\s+:\s+(?P<layer_type>\w+).*?"
    r"#\s+Thickness\s+:\s+(?P<thickness_um>[-+0-9.eE]+)\s+um.*?"
    r"#\s+Density\s+:\s+(?P<density_g_cm3>[-+0-9.eE]+).*?"
    r"#\s+Composition\s+:\s+(?P<formula>\S+)"
    r"(?P<body>.*?)(?=\n#\s+\"|\n# Result)",
    re.DOTALL,
)
NIEL_E_RE = re.compile(r"#\s+e NIEL file\s+:\s+(?P<path>.+)")
NIEL_P_RE = re.compile(r"#\s+p NIEL file\s+:\s+(?P<path>.+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--status-csv", type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    return parser.parse_args()


def read_manifest(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return {(row["formula"], row["material_id"]): row for row in rows}


def read_status(path: Path | None) -> dict[tuple[str, str], dict[str, str]]:
    if path is None or not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    return {(row["formula"], row["material_id"]): row for row in rows}


def parse_name(path: Path) -> tuple[int, str, str]:
    match = re.match(r"(?P<rank>\d+)_(?P<formula>.+)_(?P<material_id>JVASP-\d+)\.dat$", path.name)
    if not match:
        raise ValueError(f"unexpected OMERE output filename: {path.name}")
    return int(match.group("rank")), match.group("formula"), match.group("material_id")


def parse_float(value: str) -> float | None:
    try:
        parsed = float(value)
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def niel_path_matches(path: str, formula: str, material_id: str, particle_marker: str) -> bool:
    basename = Path(path.replace("\\", "/")).name
    return basename == f"NIEL_{particle_marker}_{formula}_{material_id}.dat"


def density_matches(output_density: str, manifest_density: str, *, tolerance: float = 5e-3) -> bool:
    output_value = parse_float(output_density)
    manifest_value = parse_float(manifest_density)
    if output_value is None or manifest_value is None:
        return False
    return abs(output_value - manifest_value) <= tolerance


def parse_layers(text: str) -> list[dict[str, str]]:
    layers: list[dict[str, str]] = []
    for match in LAYER_RE.finditer(text):
        layer = match.groupdict()
        body = layer.pop("body")
        e_match = NIEL_E_RE.search(body)
        p_match = NIEL_P_RE.search(body)
        layer["electron_niel_file"] = e_match.group("path").strip() if e_match else ""
        layer["proton_niel_file"] = p_match.group("path").strip() if p_match else ""
        layers.append(layer)
    return layers


def parse_params(text: str) -> list[dict[str, float | str | None]]:
    params: list[dict[str, float | str | None]] = []
    for line in text.splitlines():
        match = PARAM_RE.match(line)
        if not match:
            continue
        values = [parse_float(token) for token in match.group(2).split()]
        row: dict[str, float | str | None] = {
            "parameter": match.group(1),
            "ddde_mev_per_g": values[0] if len(values) > 0 else None,
            "ddde_to_p_mev_per_g": values[1] if len(values) > 1 else None,
            "dddp_mev_per_g": values[2] if len(values) > 2 else None,
            "rf_min_pct": values[3] if len(values) > 3 else None,
            "rf_mid_pct": values[4] if len(values) > 4 else None,
            "rf_max_pct": values[5] if len(values) > 5 else None,
            "grf_min_pct": values[6] if len(values) > 6 else None,
            "grf_mid_pct": values[7] if len(values) > 7 else None,
            "grf_max_pct": values[8] if len(values) > 8 else None,
        }
        params.append(row)
    return params


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    manifest = read_manifest(args.manifest)
    status_rows = read_status(args.status_csv)

    metric_rows: list[dict[str, object]] = []
    ranking_rows: list[dict[str, object]] = []
    for output_path in sorted(args.output_dir.glob("*.dat")):
        rank, formula, material_id = parse_name(output_path)
        text = output_path.read_text(encoding="latin-1")
        layers = parse_layers(text)
        active_layer = next(
            (
                layer
                for layer in layers
                if layer["layer_type"] == "active" and layer.get("formula") == formula
            ),
            next((layer for layer in layers if layer["layer_type"] == "active"), {}),
        )
        params = parse_params(text)
        manifest_row = manifest.get((formula, material_id), {})
        status_row = status_rows.get((formula, material_id), {})
        pmax = next((param for param in params if param["parameter"] == "Pmax"), {})
        density_match = density_matches(
            active_layer.get("density_g_cm3", ""),
            manifest_row.get("density_g_cm3", ""),
        )
        electron_niel_matches = niel_path_matches(
            active_layer.get("electron_niel_file", ""),
            formula,
            material_id,
            "e",
        )
        proton_niel_matches = niel_path_matches(
            active_layer.get("proton_niel_file", ""),
            formula,
            material_id,
            "p",
        )
        validated = (
            active_layer.get("formula") == formula
            and density_match
            and electron_niel_matches
            and proton_niel_matches
            and status_row.get("status") == "completed_validated"
            and isinstance(pmax.get("rf_mid_pct"), float)
        )

        common = {
            "srniel_damage_rank": rank,
            "formula": formula,
            "material_id": material_id,
            "has_fallback_ed": manifest_row.get("has_fallback_ed", ""),
            "density_g_cm3": active_layer.get("density_g_cm3", ""),
            "manifest_density_g_cm3": manifest_row.get("density_g_cm3", ""),
            "density_matches_manifest": density_match,
            "active_layer_name": active_layer.get("layer_name", ""),
            "active_layer_formula": active_layer.get("formula", ""),
            "electron_niel_file": active_layer.get("electron_niel_file", ""),
            "proton_niel_file": active_layer.get("proton_niel_file", ""),
            "electron_niel_matches_candidate": electron_niel_matches,
            "proton_niel_matches_candidate": proton_niel_matches,
            "omere_status": status_row.get("status", ""),
            "validated_candidate_layer": validated,
            "source_file": str(output_path),
        }

        for param in params:
            metric_rows.append({**common, **param})

        ranking_metric = pmax.get("grf_mid_pct")
        ranking_metric_source = "Pmax GRF mid"
        if ranking_metric is None:
            ranking_metric = pmax.get("rf_mid_pct")
            ranking_metric_source = "Pmax RF mid"
        ranking_rows.append(
            {
                **common,
                "pmax_ddde_mev_per_g": pmax.get("ddde_mev_per_g"),
                "pmax_ddde_to_p_mev_per_g": pmax.get("ddde_to_p_mev_per_g"),
                "pmax_dddp_mev_per_g": pmax.get("dddp_mev_per_g"),
                "pmax_rf_mid_pct": pmax.get("rf_mid_pct"),
                "pmax_grf_mid_pct": pmax.get("grf_mid_pct"),
                "ranking_metric_pct": ranking_metric,
                "ranking_metric_source": ranking_metric_source,
            }
        )

    ranking_rows.sort(
        key=lambda row: (
            row["validated_candidate_layer"] is True,
            row["ranking_metric_pct"] if isinstance(row["ranking_metric_pct"], float) else -1.0,
        ),
        reverse=True,
    )
    for index, row in enumerate(ranking_rows, start=1):
        row["omere_eol_rank"] = index

    metric_fields = [
        "srniel_damage_rank",
        "formula",
        "material_id",
        "parameter",
        "ddde_mev_per_g",
        "ddde_to_p_mev_per_g",
        "dddp_mev_per_g",
        "rf_min_pct",
        "rf_mid_pct",
        "rf_max_pct",
        "grf_min_pct",
        "grf_mid_pct",
        "grf_max_pct",
        "has_fallback_ed",
        "density_g_cm3",
        "manifest_density_g_cm3",
        "density_matches_manifest",
        "active_layer_name",
        "active_layer_formula",
        "electron_niel_file",
        "proton_niel_file",
        "electron_niel_matches_candidate",
        "proton_niel_matches_candidate",
        "omere_status",
        "validated_candidate_layer",
        "source_file",
    ]
    ranking_fields = [
        "omere_eol_rank",
        "srniel_damage_rank",
        "formula",
        "material_id",
        "ranking_metric_pct",
        "ranking_metric_source",
        "pmax_rf_mid_pct",
        "pmax_grf_mid_pct",
        "pmax_ddde_mev_per_g",
        "pmax_ddde_to_p_mev_per_g",
        "pmax_dddp_mev_per_g",
        "has_fallback_ed",
        "density_g_cm3",
        "manifest_density_g_cm3",
        "density_matches_manifest",
        "active_layer_name",
        "active_layer_formula",
        "electron_niel_file",
        "proton_niel_file",
        "electron_niel_matches_candidate",
        "proton_niel_matches_candidate",
        "omere_status",
        "validated_candidate_layer",
        "source_file",
    ]
    write_csv(args.out_dir / "omere_sadc_eol_metrics_by_param.csv", metric_rows, metric_fields)
    write_csv(args.out_dir / "omere_sadc_eol_ranking.csv", ranking_rows, ranking_fields)
    print(f"parsed_outputs={len(ranking_rows)}")
    validated_count = sum(row["validated_candidate_layer"] is True for row in ranking_rows)
    print(f"validated_outputs={validated_count}")
    if len(ranking_rows) != len(manifest) or validated_count != len(manifest):
        print(
            f"ERROR: expected {len(manifest)} parsed and validated OMERE outputs",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
