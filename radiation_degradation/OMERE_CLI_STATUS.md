# OMERE/SADC Command-Line Status

## Current Finding

The local OMERE 5.8.1 CrossOver install exposes OMERE's SADC input format, but
it does not include a standalone `SADC.exe` binary. Running OMERE through Wine is
therefore not a reliable non-GUI route in this environment.

OMERE/SADC results for the 62 final materials were completed through validated
GUI automation instead. See:

```text
radiation_degradation/omere_sadc_outputs_final_materials_20260523
```

## Probes Performed

- `Omere.exe` with an `.mms` batch file: process faulted under Wine/CrossOver
  before producing SADC output files.
- `Omere.exe` copied or renamed to `SADC.exe`: invalid workaround; it launches
  OMERE GUI code rather than SADC CLI behavior.
- Installed files and logs: no real `datac/SADC/SADC.exe` was installed.
- Installed help/samples: SADC input files are JSON (`Cell.json`,
  `Mission.json`) and the documented command shape is:

```bash
SADC.exe -v3 -s Mission.json Cell.json
```

## Prepared Non-GUI Handoff

`build_sadc_input_bundles.py` converts the 62-material SR-NIEL output set into
SADC-ready bundles:

```bash
python radiation_degradation/build_sadc_input_bundles.py \
  --srniel-dir radiation_degradation/sr_niel_outputs_final_materials_20260523 \
  --jarvis-json /path/to/jdft_3d-12-12-2022.unzipped.json
```

The generated directory is:

```text
radiation_degradation/sr_niel_outputs_final_materials_20260523/sadc_input_bundles
```

It contains 62 `Cell.json` files, 62 `Mission.json` files, 124 copied official
SR-NIEL curve files, and `sadc_run_manifest.csv`.

## GUI Execution Status

The GUI batch completed with 62 raw OMERE/SADC output files and 62
`completed_validated` status rows. The parser requires each output to contain
the candidate formula, manifest density, exact custom electron NIEL filename,
exact custom proton NIEL filename, and finite Pmax values before a row is marked
`validated_candidate_layer=True`.

## Publication Boundary

The current GUI outputs are candidate-specific for active-layer formula,
density, and SR-NIEL electron/proton curves. They are still comparative
screening outputs, not fully material-specific publishable EOL predictions,
because the remaining-factor model uses OMERE sample GaAs-template degradation
coefficients for every candidate.

Fully material-specific EOL still requires:

- a valid licensed SADC/OMERE command-line executable or the validated GUI route,
  and
- calibrated material/cell degradation coefficients instead of the included
  OMERE sample GaAs-template coefficients.
