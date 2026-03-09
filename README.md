# Identifying Solar Cell Materials for Space Applications

## Current Implementation

The repo is now reduced to a pure displacement-threshold pipeline at
`calculating_energy_threshold_displacement/run_ed_pipeline.py`.

The default workflow is accuracy-first:

1. load a crystal structure from JARVIS,
2. run a fresh QE `vc-relax` unless `--skip-qe-relax` is passed,
3. build a larger defect supercell,
4. sample symmetry-inequivalent sites per element,
5. scan many directions per site,
6. use pinned-atom relaxes by default,
7. write site-resolved and per-element `Ed` outputs.

Batch input can come from `calculating_energy_threshold_displacement/candidate_materials.csv`
or any CSV/text file with formulas.

## Batch Usage

Single material:

```bash
/home/vm/miniconda3/envs/DSI/bin/python \
  /home/vm/LUMENS-PV/calculating_energy_threshold_displacement/run_ed_pipeline.py \
  --formula InP
```

Batch file:

```bash
/home/vm/miniconda3/envs/DSI/bin/python \
  /home/vm/LUMENS-PV/calculating_energy_threshold_displacement/run_ed_pipeline.py \
  --input-file /home/vm/LUMENS-PV/calculating_energy_threshold_displacement/candidate_materials.csv \
  --max-materials 10
```

Outputs go to `calculating_energy_threshold_displacement/ed_outputs/`:

- one JSON summary per material
- `ed_results.csv` with one row per material-element pair
- `ed_site_results.csv` with site-resolved `Ed` values
- `ed_batch_summary.json` with overall batch status

## Recommended Profiles

For many-material throughput, start from the screening wrapper:

```bash
cd /path/to/LUMENS-PV/calculating_energy_threshold_displacement
chmod +x run_ed_pipeline_screen.slurm
sbatch --array=1-N run_ed_pipeline_screen.slurm /path/to/materials.csv
```

`run_ed_pipeline_screen.slurm` is the bounded `1-2` hour profile:

- `--ed-mode static`
- `--site-selection representative`
- `--ed-kpoint-mode gamma`
- about `10-12` directions
- about `6` coarse points plus `2` refine points
- `12 A` supercell target

Use that profile to rank dozens of materials, then re-run only the shortlist with stricter settings.

## Supercomputer

For real high-fidelity runs, use the Slurm array launcher:

```bash
cd /path/to/LUMENS-PV/calculating_energy_threshold_displacement
chmod +x run_ed_pipeline.slurm
sbatch --array=1-5 run_ed_pipeline.slurm /path/to/LUMENS-PV/calculating_energy_threshold_displacement/high_accuracy_materials.csv
```

Update the `#SBATCH` resources in `run_ed_pipeline.slurm` for your cluster. The array index should match the number of data rows in the CSV, excluding the header.

If you want a faster, lower-fidelity smoke test instead of the default high-accuracy workflow:

```bash
/home/vm/miniconda3/envs/DSI/bin/python \
  /home/vm/LUMENS-PV/calculating_energy_threshold_displacement/run_ed_pipeline.py \
  --formula GaSb \
  --material-id JVASP-1177 \
  --skip-qe-relax \
  --ed-mode static \
  --direction-mode highsym \
  --ed-directions 3 \
  --ed-points 4 \
  --refine-points 0 \
  --site-selection representative \
  --ed-kpoint-mode gamma
```

Detailed, measured profile notes live in
`calculating_energy_threshold_displacement/ED_RUN_PROFILES.md`.

## Accuracy And Compute-Time Controls

Material choice itself dominates absolute runtime, but the tunable controls below are the main levers that change numerical fidelity, directional/site coverage, memory use, and wall time.

- Structure source and pre-relax: `--skip-qe-relax`, `--relaxed-qe-xml`, `--idealize-relaxed-structure`, `--vdw-corr`, `--pseudo-dir`.
  Reusing a cached or JARVIS-relaxed structure is much cheaper than a fresh QE `vc-relax`, but it can shift the relaxed geometry used for the Ed scan. `--idealize-relaxed-structure` can restore exact symmetry before supercell construction. `--vdw-corr` and the pseudopotential set in `--pseudo-dir` affect the relaxed structure, recommended cutoffs, and total cost.

- Site coverage and symmetry handling: `--site-selection`, `--site-label`, `--element-aggregation`, `--symprec`, `--angle-tolerance`.
  `--site-selection representative` is the main throughput setting; `inequivalent` is more complete but scales with the number of inequivalent sites. `--site-label` can intentionally restrict the scan to selected sites. `--symprec` and `--angle-tolerance` affect how aggressively sites are grouped by symmetry. `--element-aggregation` changes the reported per-element Ed value, not the raw site calculations.

- Directional sampling and curve resolution: `--direction-mode`, `--ed-directions`, `--ed-points`, `--refine-points`, `--direction-index-start`, `--direction-index-stop`, `--reliability-floor-ev`.
  More directions improve angular coverage and usually scale cost close to linearly. More coarse and refine points improve barrier-shape resolution and also scale close to linearly. `--direction-index-start/stop` are sharding controls: they reduce per-job work but do not reduce total work if the full direction set is still evaluated. `--reliability-floor-ev` filters low barriers from the final recommendation, which can change the reported Ed even though it does not change QE cost much.

- Supercell and Ed relaxation model: `--supercell-min-length`, `--ed-mode`, `--ed-disable-symmetry`.
  `--supercell-min-length` is one of the strongest accuracy and cost levers because atom count grows with supercell volume. `--ed-mode static` is the main screening shortcut; `relax` is more physical but much more expensive. `--ed-disable-symmetry` can improve robustness for displaced supercells, at some extra cost.

- Brillouin-zone and basis controls: `--kpoint-density`, `--ed-kpoint-mode`, `--ed-kpoint-density`, `--max-total-kpts`, `--max-ed-kpts`, `--ed-cutoff-scale`.
  Smaller density values mean denser meshes and higher cost. `--ed-kpoint-mode gamma` is the main throughput choice for large supercells; `auto` is more accurate but can increase cost sharply. `--max-total-kpts` and `--max-ed-kpts` cap mesh growth. `--ed-cutoff-scale` raises both relax and Ed cutoffs above the pseudopotential recommendation and increases memory and runtime.

- Electronic-state model: `--occupations-mode`, `--fixed-occupations-bandgap-ev`, `--spin-mode`, `--spin-threshold-mub`, `--relax-degauss`, `--ed-degauss`.
  Occupation and spin choices change the SCF problem itself, so they affect both accuracy and convergence cost. `auto` modes are the safer default when mixing semiconductors and magnetic materials. The degauss values matter only when smearing is used.

- Convergence thresholds: `--relax-force-conv-thr`, `--relax-etot-conv-thr`, `--relax-electron-conv-thr`, `--ed-force-conv-thr`, `--ed-etot-conv-thr`, `--ed-electron-conv-thr`, `--mixing-beta`.
  Tighter force, energy, and SCF thresholds can improve stability and reproducibility, but they increase ionic and electronic iteration counts. `--mixing-beta` does not change the target solution directly, but it can materially change convergence speed and whether difficult Ed points finish cleanly.

- Failure handling and bounded runtime: `--allow-ed-fallback`, `--relax-timeout`, `--ed-timeout`.
  `--allow-ed-fallback` trades DFT completeness for robustness by allowing elemental lookup estimates when a site scan fails. The timeout flags do not improve accuracy; they cap worst-case runtime per relax or Ed point and are important for keeping screening jobs bounded.

- Compute-only throughput and storage controls: `--nprocs`, `--qe-launcher`, `--qe-executable`, `--force-qe`, `--max-materials`, `--workspace`, `--results-dir`, `--qe-scratch-root`, `--keep-qe-scratch`.
  These settings mainly affect wall time, I/O behavior, or rerun behavior rather than the physics. `--nprocs` and `--qe-launcher` affect parallel efficiency. `--force-qe` disables cache reuse. `--max-materials` is useful for chunking long batches. `--qe-scratch-root` is important on clusters because fast local scratch can be the difference between a stable run and a home-quota failure.

For many-material screening, the highest-impact accuracy/cost levers are usually, in order:

1. `--ed-mode`
2. `--supercell-min-length`
3. `--ed-kpoint-mode` and `--ed-kpoint-density`
4. `--site-selection`
5. `--ed-directions`
6. `--ed-points` and `--refine-points`
7. `--ed-cutoff-scale` and the convergence thresholds
