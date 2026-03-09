#!/usr/bin/env python3
"""Rebuild aggregate Ed outputs from per-material summary JSON files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        required=True,
        help="Directory containing per-material *_summary.json files.",
    )
    return parser.parse_args()


def load_summaries(results_dir: Path) -> list[dict]:
    summary_paths = sorted(results_dir.glob("*_summary.json"))
    if not summary_paths:
        raise SystemExit(f"No per-material summary JSON files were found in {results_dir}")

    summaries: list[dict] = []
    for summary_path in summary_paths:
        with summary_path.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        if not isinstance(summary, dict):
            raise SystemExit(f"Summary file does not contain a JSON object: {summary_path}")
        summaries.append(summary)

    summaries.sort(
        key=lambda summary: (
            str(summary.get("formula") or ""),
            str(summary.get("material_id") or ""),
            str(summary.get("status") or ""),
        )
    )
    return summaries


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
    results_dir = Path(args.results_dir).resolve()
    results_dir.mkdir(parents=True, exist_ok=True)
    summaries = load_summaries(results_dir)
    write_aggregate_outputs(results_dir, summaries)
    print(f"Loaded {len(summaries)} material summaries from {results_dir}")
    print(f"Aggregate CSV: {results_dir / 'ed_results.csv'}")
    print(f"Site CSV: {results_dir / 'ed_site_results.csv'}")
    print(f"Batch summary: {results_dir / 'ed_batch_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
