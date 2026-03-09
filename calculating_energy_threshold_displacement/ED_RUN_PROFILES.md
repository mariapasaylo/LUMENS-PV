# ED Run Profiles

This note captures the parameter sets and hardware choices that have worked for
the Quantum ESPRESSO displacement-threshold (`Ed`) pipeline in
`calculating_energy_threshold_displacement/run_ed_pipeline.py`, plus the main
precision vs compute-cost tradeoffs.

## Working Environment

- Cluster: HiPerGator
- QE module stack that worked: `gcc/14.2.0 openmpi/5.0.7 espresso/7.3.1`
- Working QE launcher under Slurm: `mpirun`
- Launcher to avoid for this workflow: `srun`
  - Earlier smoke runs hit QE rank/symmetry/file issues under `srun`.
- Python used on HiPerGator: `/home/e.kolberg/local/dsi3/miniforge/envs/dsi3_full/bin/python3`
- Pseudopotentials used on HiPerGator: `~/LUMENS-PV/pseudopotentials`
- GPU status:
  - Current production path is CPU-only.
  - Loading NVHPC-based `espresso` modules still resolved to a CPU `pw.x` binary on this system.
  - No validated GPU QE path has been established for this pipeline yet.

## Key Runtime Controls

The most important knobs are:

- `--ed-mode`
  - `static` is much cheaper.
  - `relax` is much more expensive and should be reserved for refinement/finals.
- `--site-selection`
  - `representative` is cheaper.
  - `inequivalent` is more complete but scales with the number of inequivalent sites.
- `--ed-directions`
  - More directions improves directional coverage.
  - Cost scales close to linearly with direction count.
- `--ed-points` and `--refine-points`
  - More points improve the barrier curve resolution.
  - Cost scales close to linearly with total sampled displacements.
- `--supercell-min-length`
  - Larger supercells reduce finite-size effects.
  - Cost grows very fast because atom count grows roughly with supercell volume.
- `--ed-kpoint-mode`
  - `gamma` is the cheapest option for Ed scans.
  - `auto` is more accurate but can multiply cost heavily.
- `--kpoint-density` and `--ed-kpoint-density`
  - Smaller values mean denser meshes and higher cost.
- `--ed-cutoff-scale`
  - Higher values improve basis completeness.
  - Cost and memory both rise substantially.
- Convergence thresholds (`relax-*`, `ed-*`, `mixing-beta`)
  - Tighter thresholds can improve stability/accuracy.
  - They also increase SCF and ionic iteration counts.

## Working Profiles

### 1. Smoke Validation Profile

This is the small proof-of-life profile that completed cleanly.

- Job: `26694128` (`ed-smoke-mini-mpi`)
- Date: March 8, 2026
- State: `COMPLETED`
- Elapsed: `00:03:50`
- Partition: `hpg-default`
- Allocated CPUs: `8`
- Requested memory: `32G`
- Node: `c0700a-s4`
- Workspace/results:
  - `smoke_workspace_mini_mpi/`
  - `smoke_workspace_mini_mpi/ed_outputs/`
- Observed outputs:
  - `Ed(In_s0) = 0.390 eV`
  - `Ed(P_s0) = 0.309 eV`

Operational shape:

- fresh QE `vc-relax`
- `static` Ed
- `representative` sites
- gamma-only Ed k-points
- very small directional sampling

This profile is useful only for confirming that the code path, modules,
pseudopotentials, and parser behavior are working.

### 2. Current Bounded Screening Profile

This is the recommended starting point for many-material throughput.

- Slurm wrapper:
  - `calculating_energy_threshold_displacement/run_ed_pipeline_screen.slurm`
- Intended runtime target:
  - about `1-2 hours` per material
- Current pilot job:
  - Job: `26704925_1`
  - Name: `ed-screen`
  - State when checked on March 9, 2026: `RUNNING`
  - Start: `2026-03-08T21:42:06`
  - Partition: `hpg-default`
  - QoS: `uf-dsi`
  - CPUs: `32`
  - Memory: `192G`
  - Example node: `c0702a-s8`
  - Example node hardware:
    - `128` total CPUs
    - `1028000 MB` physical memory
    - AMD Rome class node on `hpg-default`

Pilot parameters used for the live screen run:

- `--qe-launcher mpirun`
- `--nprocs 32`
- `--direction-mode fibonacci`
- `--ed-directions 10`
- `--ed-points 6`
- `--refine-points 2`
- `--ed-mode static`
- `--site-selection representative`
- `--element-aggregation min`
- `--supercell-min-length 12.0`
- `--kpoint-density 0.08`
- `--ed-kpoint-mode gamma`
- `--ed-cutoff-scale 1.15`
- `--reliability-floor-ev 0.20`
- `--occupations-mode auto`
- `--spin-mode auto`
- `--relax-force-conv-thr 1.0e-4`
- `--relax-etot-conv-thr 1.0e-6`
- `--relax-electron-conv-thr 1.0e-6`
- `--ed-electron-conv-thr 1.0e-6`
- `--relax-degauss 0.01`
- `--ed-degauss 0.01`
- `--mixing-beta 0.30`
- `--vdw-corr dft-d3`
- `--idealize-relaxed-structure`
- `--relax-timeout 3600`
- `--ed-timeout 1200`

Observed setup from the active InP pilot:

- primitive k-points: `[16, 16, 16]`
- supercell repeats: `(3, 3, 3)` -> `54` atoms
- Ed k-points: gamma-only
- representative sites: `2`

This is the best current throughput-oriented profile in the repo.

### 3. High-Accuracy Wrapper Profile

This is the stricter CPU profile baked into
`calculating_energy_threshold_displacement/run_ed_pipeline.slurm`.

Requested hardware in that wrapper:

- Partition: `hpg-default`
- CPUs: `32`
- Memory: `650G`
- Walltime: `48:00:00`

Default accuracy parameters in that wrapper:

- `--direction-mode fibonacci`
- `--ed-directions 62`
- `--ed-points 12`
- `--refine-points 9`
- `--ed-mode relax`
- `--ed-kpoint-mode auto`
- `--site-selection inequivalent`
- `--element-aggregation min`
- `--supercell-min-length 16.0`
- `--kpoint-density 0.06`
- `--ed-kpoint-density 0.06`
- `--max-total-kpts 8192`
- `--max-ed-kpts 4096`
- `--ed-cutoff-scale 1.30`
- `--reliability-floor-ev 0.20`
- `--occupations-mode auto`
- `--spin-mode auto`
- `--relax-force-conv-thr 5.0e-5`
- `--relax-etot-conv-thr 1.0e-7`
- `--relax-electron-conv-thr 1.0e-8`
- `--ed-force-conv-thr 2.0e-4`
- `--ed-etot-conv-thr 1.0e-6`
- `--ed-electron-conv-thr 1.0e-8`
- `--relax-degauss 0.01`
- `--ed-degauss 0.01`
- `--mixing-beta 0.20`
- `--vdw-corr dft-d3`
- `--idealize-relaxed-structure`

Recommendation:

- good for a small shortlist
- not appropriate for large-scale screening across many materials

### 4. Abandoned "Maximum Accuracy" Attempt

This was useful for learning the limits, but it is not the recommended
production mode.

Representative aggressive settings that were tested:

- `96` CPUs
- `1450G` memory on `bigmem`
- `--ed-directions 122`
- `--ed-points 14`
- `--refine-points 11`
- `--ed-mode relax`
- `--site-selection inequivalent`
- `--supercell-min-length 20.0`
- `--kpoint-density 0.04`
- `--ed-kpoint-density 0.05`
- `--max-total-kpts 32768`
- `--max-ed-kpts 8192`
- `--ed-cutoff-scale 1.40`
- much tighter SCF/force thresholds

Result:

- far too expensive for many-material throughput
- useful only for a very small number of final validation targets

## Precision vs Cost Relationships

These are the main tradeoffs observed in practice.

| Control | Accuracy Effect | Cost Effect |
|---|---|---|
| `ed-mode: static -> relax` | better local relaxation around the displaced atom | biggest runtime jump; often the first reason jobs become impractical |
| `site-selection: representative -> inequivalent` | better site coverage | roughly multiplies cost by number of inequivalent sites |
| `ed-directions` | better directional coverage | near-linear runtime scaling |
| `ed-points` + `refine-points` | better barrier-shape resolution | near-linear runtime scaling |
| larger `supercell-min-length` | lower finite-size error | atom count grows fast; runtime/memory can jump dramatically |
| `ed-kpoint-mode: gamma -> auto` | better Brillouin-zone sampling | very large cost increase for Ed supercells |
| smaller `kpoint-density` / `ed-kpoint-density` | denser k-meshes | cost rises with total k-point count |
| larger `ed-cutoff-scale` | more complete basis | cost and memory both rise significantly |
| tighter SCF/ionic thresholds | potentially cleaner energies/forces | more SCF iterations, more ionic steps |

Practical ordering of impact:

1. `ed-mode`
2. `supercell-min-length`
3. Ed k-point choice (`gamma` vs `auto`)
4. direction count
5. number of sampled sites
6. number of displacement points
7. cutoff scale and convergence tightening

## Recommended Workflow for Many Materials

Use a funnel, not one profile for everything.

### Stage A: Screening

Use the bounded screen profile:

- `static`
- `representative`
- gamma-only Ed
- about `10-12` directions
- about `6` coarse points and `2` refine points
- `12 A` supercell target

Goal:

- rank many materials cheaply
- remove obvious non-starters

### Stage B: Refinement

For the shortlist only, increase:

- `ed-mode` to `relax`
- `site-selection` to `inequivalent`
- direction count to roughly `26-42`
- supercell target to roughly `14-16 A`

Goal:

- improve confidence on the top materials without paying final-tier cost for every candidate

### Stage C: Final Validation

Reserve the aggressive settings for only a few materials.

Goal:

- produce the best numbers only where the decision is already close

## Current Status

When checked on March 9, 2026:

- the bounded screening pilot was running:
  - Job `26704925_1`
  - InP / `JVASP-1183`
  - `32` CPUs, `192G`, `2:00:00` walltime
- the live log showed:
  - successful dataset load
  - successful QE `vc-relax`
  - Ed scan started on `In_s0`

To re-check current status later:

```bash
squeue -u e.kolberg
sacct -j 26704925 --format=JobID,JobName,State,Elapsed,Timelimit,Start,End
tail -n 120 ~/LUMENS-PV/calculating_energy_threshold_displacement/logs/ed_screen_26704925_1.out
```
