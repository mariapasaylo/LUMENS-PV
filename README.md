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
