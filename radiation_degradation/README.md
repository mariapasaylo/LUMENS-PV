# Radiation Degradation Handoff

This directory contains the SR-NIEL-to-OMERE handoff for the 62 final ML-selected
materials. The code here is orchestration and provenance only: SR-NIEL values
come from the official SR-NIEL web calculators, and final solar-cell EOL must be
computed in TRAD OMERE.

## Official Tools

- SR-NIEL electrons calculator:
  <https://www.sr-niel.org/index.php/sr-niel-web-calculators/niel-calculator-for-electrons-protons-and-ions/electrons-niel-calculator>
- SR-NIEL protons/ions calculator:
  <https://www.sr-niel.org/index.php/sr-niel-web-calculators/niel-calculator-for-electrons-protons-and-ions/protons-ions-niel-calculator>
- TRAD OMERE download page:
  <https://www.trad.fr/telechargements/>
- TRAD OMERE software page:
  <https://www.trad.fr/spatial/logiciel-omere/>

## Reproducing the SR-NIEL Handoff

Run from the repository root:

```bash
python radiation_degradation/run_srniel_omere_pipeline.py \
  --ed-input calculating_energy_threshold_displacement/screen_outputs_final_materials_stageA_gpu_l4_guaranteed_niel/results/niel_ed_inputs.csv \
  --out-dir radiation_degradation/sr_niel_outputs_final_materials_20260523 \
  --delay-s 0.1 \
  --resume
```

Remove `--resume` only when intentionally re-querying the SR-NIEL calculators.

The run uses these SR-NIEL parameters:

- Electrons: exponential nuclear form factor (`FF=0`), compound target
  (`TARGET=0`), energy range 0.04-100 MeV, fluence 1.
- Protons: proton incident particle (`Zi=1`), total NIEL model
  Hadronic + Coulomb (`Ionmodel=1`), no hadronic Ed scaling (`Scale=0`),
  compound target (`TARGET=0`), energy range 1e-4-10000 MeV, fluence 1.
- Target material: each material uses formula stoichiometry from
  `niel_ed_inputs.csv`; element-specific Ed values are supplied from the Stage A
  DFT displacement-barrier screen or marked as elemental fallback in that input.

## Output Meanings

- `srniel_result_links.csv`: one official SR-NIEL result URL per material and
  particle type; expected count is 124 rows for 62 materials.
- `raw_srniel_tables/*.csv`: parsed SR-NIEL result tables.
- `omere_inputs/*_NIEL.dat`: two-column `Energy_MeV NIEL_MeV_cm2_g` files for
  OMERE import.
- `electron_input_files.txt` and `proton_input_files.txt`: Windows-style
  relative paths for OMERE batch/GUI import.
- `srniel_screening_metrics.csv`: local QA/screening metrics computed from the
  official SR-NIEL curves. These are not OMERE EOL values.
- `eol_damage_screening_inputs.csv`: explicit queue of rows that still require
  OMERE or material-specific degradation coefficients.
- `sadc_input_bundles/`: one SADC-ready `Cell.json`/`Mission.json` bundle per
  material, plus copied official SR-NIEL curves and a run manifest.

## Building SADC Input Bundles

Run from the repository root after downloading the JARVIS-DFT 3D dataset JSON:

```bash
python radiation_degradation/build_sadc_input_bundles.py \
  --srniel-dir radiation_degradation/sr_niel_outputs_final_materials_20260523 \
  --jarvis-json /path/to/jdft_3d-12-12-2022.unzipped.json
```

This does not compute OMERE EOL by itself. It creates reproducible SADC inputs
so a real `SADC.exe` command-line binary can process the 62 materials without
manual GUI import.

## OMERE Boundary

OMERE is required for publishable solar-cell degradation/EOL results because it
combines mission environment, shielding/transport, displacement damage, and the
solar-cell degradation model or coefficients. The SR-NIEL files here are ready
inputs to that step, but the repository does not include the OMERE executable.

See `OMERE_CLI_STATUS.md` for the current non-GUI execution status.

The official TRAD download currently routes through a form and the TRAD license
does not permit redistribution. Do not replace OMERE with local LLM-generated
EOL formulas; run TRAD OMERE once the installer/link is available.
