# OMERE/SADC Outputs for Final Materials

This directory contains TRAD OMERE 5.8.1 SADC GUI outputs for the 62 final
ML-selected LUMENS-PV materials. The run used the official SR-NIEL curves
prepared in `../sr_niel_outputs_final_materials_20260523` as custom electron
and proton NIEL inputs.

## Contents

- `outputs/*.dat`: raw OMERE/SADC text outputs, one per material.
- `sadc_gui_batch_status.csv`: GUI automation status for each material.
- `sadc_gui_batch.log`: rank-level GUI batch log.
- `omere_sadc_eol_metrics_by_param.csv`: parsed OMERE electrical-parameter
  rows for `Isc`, `Voc`, `Pmax`, `Ipm`, and `Vpm`.
- `omere_sadc_eol_ranking.csv`: one row per material, ranked by `Pmax GRF mid`
  when available and `Pmax RF mid` otherwise.
- `automation_scripts/`: PowerShell scripts used to drive OMERE's SADC GUI.

## Official Software Sources

- TRAD OMERE software: <https://www.trad.fr/spatial/logiciel-omere/>
- TRAD downloads: <https://www.trad.fr/telechargements/>
- SR-NIEL electron calculator:
  <https://www.sr-niel.org/index.php/sr-niel-web-calculators/niel-calculator-for-electrons-protons-and-ions/electrons-niel-calculator>
- SR-NIEL proton/ion calculator:
  <https://www.sr-niel.org/index.php/sr-niel-web-calculators/niel-calculator-for-electrons-protons-and-ions/protons-ions-niel-calculator>

## OMERE/SADC Setup

OMERE version: `OMERE 5.8.1.35459 - SADC`, as reported in each raw output.

The local OMERE install did not expose a working standalone `SADC.exe`; the
batch was therefore run by GUI automation against OMERE's Solar Cell Degradation
dialog. Each material was accepted only when the raw output layer list verified:

- candidate active-layer formula,
- candidate active-layer density from `sadc_run_manifest.csv`,
- custom electron NIEL file named `NIEL_e_<formula>_<JVASP>.dat`,
- custom proton NIEL file named `NIEL_p_<formula>_<JVASP>.dat`,
- finite parsed `Pmax` remaining-factor values.

Validation summary:

- OMERE output files: 62.
- GUI status rows: 62 `completed_validated`.
- Parser validation rows: 62 `validated_candidate_layer=True`.
- Parsed electrical metric rows: 310.
- Candidate rows with fallback Stage A Ed values in SR-NIEL inputs: 15.

## Mission and Cell Model

Mission parameters from the OMERE output headers:

- Start mission: 2026.
- Lifetime: 10 years.
- Solar activity duration: 7 years.
- Orbit: `Orbit LEO1 POL`, circular 800 km perigee and apogee, 98 degree
  inclination.
- Orbit sampling: 100 orbits, 100 points per orbit.
- Trapped electrons: AE8 Max.
- Trapped protons: AP8 Min.
- Solar protons: ESP, 90 percent confidence.
- Geomagnetic model: Jensen-Cain.
- Cutoff model: Stormer, vertical magnetospheric cutoff.
- Weather: quiet.
- Earth shadow: yes.

Layer stack from the OMERE SADC GUI template:

- Coverglass: `SiO2`, optical, 100 um, density 2.610 g/cm3.
- Front adhesive: `SiOC2H6`, optical, 20 um, density 1.030 g/cm3.
- InP optical layer: `InP`, optical, 1 um, density 4.810 g/cm3.
- Candidate active layer: formula and density varied per material, 2 um.
- Ge shielding layer: `Ge`, 140 um, density 5.350 g/cm3.
- Back contact: `Ag`, 5 um, density 10.500 g/cm3.
- Back adhesive: `SiOC2H6`, 80 um, density 1.030 g/cm3.
- Aluminium back plate: `Al2`, 2000 um, density 2.700 g/cm3.

## Interpretation Boundary

These are real OMERE/SADC GUI outputs with candidate-specific active-layer
formula, density, and custom SR-NIEL electron/proton curves. They are suitable
for comparative screening under a single OMERE SADC template.

They are not fully publishable material-specific EOL predictions by themselves.
The remaining-factor and Pmax degradation calculations still use OMERE's
sample/template GaAs-style electrical degradation coefficients for every
candidate. Publishable EOL for novel PV materials requires measured or
calibrated material/cell remaining-factor-vs-DDD coefficients, or another
defensible calibrated degradation model.

Rows with `has_fallback_ed=True` should be treated as lower-confidence because
their SR-NIEL curves used fallback displacement-threshold energy inputs.

## Reproduction

The parser can be rerun from the repository root:

```bash
python radiation_degradation/parse_omere_sadc_outputs.py \
  --output-dir radiation_degradation/omere_sadc_outputs_final_materials_20260523/outputs \
  --manifest radiation_degradation/sr_niel_outputs_final_materials_20260523/sadc_input_bundles/sadc_run_manifest.csv \
  --status-csv radiation_degradation/omere_sadc_outputs_final_materials_20260523/sadc_gui_batch_status.csv \
  --out-dir radiation_degradation/omere_sadc_outputs_final_materials_20260523
```

The command must print `parsed_outputs=62` and `validated_outputs=62`.
