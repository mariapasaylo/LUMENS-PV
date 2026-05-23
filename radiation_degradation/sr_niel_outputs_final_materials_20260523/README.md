# Final Materials SR-NIEL Outputs

Generated for the 62 final ML-selected materials using
`radiation_degradation/run_srniel_omere_pipeline.py`.

Validation counts:

- Materials: 62.
- Official SR-NIEL result links: 124 total, 62 electron and 62 proton.
- OMERE NIEL input files: 124 `.dat` files.
- Parsed raw SR-NIEL tables: 124 `.csv` files.
- Combined curve rows: 12046.
- Screening metrics: 62 rows with no missing values.

Important boundary: `srniel_screening_metrics.csv` ranks materials using
official SR-NIEL curves and a local QA spectrum integration, but it is not a
TRAD OMERE solar-cell EOL result.

Validated OMERE 5.8.1 SADC GUI outputs for the 62 materials are stored in
`../omere_sadc_outputs_final_materials_20260523`. Those outputs use
candidate-specific active-layer formula, density, and custom SR-NIEL curves,
but still use OMERE's sample/template GaAs-style degradation coefficients for
remaining-factor and Pmax calculations.
