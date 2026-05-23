# Final materials Stage A GPU L4 displacement-barrier screen

Run root on HiPerGator:
`/blue/uf-dsi/e.kolberg/lumens_pv_runs/20260522_final_materials_stageA_gpu_l4_guaranteed_niel`

Input list: `candidate_materials_from_ml.csv`, copied from `origin/ml:ml_classifiers/final_materials.csv` and normalized to `formula,material_id`.

Primary Slurm array: `33067311`, GPU L4 profile, `--array=1-62%16`, `--time=01:30:00`.

Retry Slurm job: `33075849`, single-material retry for `ScMo3O8 / JVASP-12703`, `--time=04:00:00`, completed after the primary array timed out that one row.

Pipeline settings:
- Quantum ESPRESSO GPU executable from `nvhpc/26.3 openmpi/5.0.7 espresso/7.5.0_l4`.
- `--skip-qe-relax`, using JARVIS-relaxed structures with spglib idealization.
- Static displaced-supercell scan, Gamma-point Ed scan.
- `--site-selection representative`, one representative site per element.
- `--direction-mode highsym`, 3 directions, 3 distance points, no refinement.
- `--supercell-min-length 6.0`, `--ed-cutoff-scale 1.0`.
- `--allow-ed-fallback` for sublattices whose QE scan failed.

Important interpretation:
These are Stage A DFT displacement-barrier proxy values for screening and SR-NIEL input preparation. They are not final dynamic threshold displacement energies and are not DFT+eDMFT results. Rows or sites marked `fallback` use elemental lookup estimates rather than material-specific converged DFT barriers.

Aggregated outputs:
- `results/ed_results.csv`: per-material/per-element recommended Ed proxy table.
- `results/ed_site_results.csv`: per-site status and barrier table.
- `results/niel_ed_inputs.csv`: SR-NIEL-oriented input table with interpretation notes.
- `results/ed_batch_summary.json`: batch-level JSON with all material summaries embedded.
