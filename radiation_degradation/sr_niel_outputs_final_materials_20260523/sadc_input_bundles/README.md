# SADC Input Bundles

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

- 1: SbIrS (JVASP-10264)
- 2: InN (JVASP-17841)
- 3: Hg3Cl2O2 (JVASP-12474)
- 4: PbS (JVASP-17941)
- 5: Ag2Te (JVASP-108812)

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
