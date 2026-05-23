import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = REPO_ROOT / "calculating_energy_threshold_displacement" / "run_ed_pipeline.py"
SLURM_PATH = REPO_ROOT / "calculating_energy_threshold_displacement" / "run_ed_pipeline.slurm"
AGGREGATE_PATH = REPO_ROOT / "calculating_energy_threshold_displacement" / "aggregate_ed_results.py"
HIGH_ACCURACY_CSV = REPO_ROOT / "calculating_energy_threshold_displacement" / "high_accuracy_materials.csv"


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location("run_ed_pipeline", PIPELINE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_aggregate_module():
    spec = importlib.util.spec_from_file_location("aggregate_ed_results", AGGREGATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def strict_args():
    return SimpleNamespace(
        occupations_mode="auto",
        fixed_occupations_bandgap_ev=0.10,
        spin_mode="auto",
        spin_threshold_mub=0.50,
        relax_force_conv_thr=5.0e-5,
        relax_etot_conv_thr=1.0e-7,
        relax_electron_conv_thr=1.0e-8,
        ed_force_conv_thr=2.0e-4,
        ed_etot_conv_thr=1.0e-6,
        ed_electron_conv_thr=1.0e-8,
        relax_degauss=0.01,
        ed_degauss=0.01,
        mixing_beta=0.20,
    )


class TestElectronicSettings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = load_pipeline_module()

    def test_auto_settings_choose_fixed_for_gapped_nonmagnetic_material(self):
        material = {"mbj_bandgap": 1.387, "magmom_oszicar": 0.0}
        settings = self.pipeline.resolve_electronic_settings(material, ["In", "P"], strict_args(), stage="ed")

        self.assertEqual(settings["occupations"], "fixed")
        self.assertFalse(settings["spin_polarized"])
        self.assertEqual(settings["bandgap_ev"], 1.387)
        self.assertEqual(settings["degauss"], 0.01)
        self.assertEqual(settings["electron_conv_thr"], 1.0e-8)

    def test_auto_settings_choose_spin_and_smearing_for_magnetic_metal(self):
        material = {"optb88vdw_bandgap": 0.0, "magmom_oszicar": 8.0}
        settings = self.pipeline.resolve_electronic_settings(material, ["V", "O", "F"], strict_args(), stage="ed")

        self.assertEqual(settings["occupations"], "smearing")
        self.assertTrue(settings["spin_polarized"])
        self.assertGreater(settings["starting_magnetization"]["V"], 0.0)
        self.assertEqual(settings["total_magmom_mub"], 8.0)

    def test_correlated_element_detection(self):
        self.assertTrue(self.pipeline.has_correlated_elements(["V", "O", "F"]))
        self.assertTrue(self.pipeline.has_correlated_elements(["Ti", "Si", "Pt"]))
        self.assertFalse(self.pipeline.has_correlated_elements(["In", "P"]))


class TestQeInputBuilders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = load_pipeline_module()
        cls.atoms = cls.pipeline.Atoms(
            symbols=["In", "P"],
            positions=[[0.0, 0.0, 0.0], [1.5, 1.5, 1.5]],
            cell=[[3.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 3.0]],
            pbc=True,
        )

    def test_vc_relax_input_uses_fixed_occupations_when_requested(self):
        settings = {
            "occupations": "fixed",
            "spin_polarized": False,
            "smearing": "cold",
            "degauss": 0.01,
            "electron_conv_thr": 1.0e-8,
            "force_conv_thr": 5.0e-5,
            "etot_conv_thr": 1.0e-7,
            "starting_magnetization": {"In": 0.0, "P": 0.0},
        }
        text = self.pipeline.build_vc_relax_input(
            self.atoms,
            "JVASP-1183",
            "/pseudo",
            {"In": "In.UPF", "P": "P.UPF"},
            ["In", "P"],
            80.0,
            800.0,
            [6, 6, 6],
            settings,
            "dft-d3",
        )

        self.assertIn("occupations='fixed'", text)
        self.assertNotIn("smearing='cold'", text)
        self.assertIn("vdw_corr='dft-d3'", text)
        self.assertIn("conv_thr=1.0e-08", text)

    def test_ed_input_writes_spin_smearing_and_pinned_atom_flags(self):
        settings = {
            "occupations": "smearing",
            "spin_polarized": True,
            "smearing": "cold",
            "degauss": 0.01,
            "electron_conv_thr": 1.0e-8,
            "force_conv_thr": 2.0e-4,
            "etot_conv_thr": 1.0e-6,
            "mixing_beta": 0.2,
            "starting_magnetization": {"In": 0.5, "P": 0.1},
        }
        text = self.pipeline.build_ed_input(
            self.atoms,
            "JVASP-1183_test",
            "/pseudo",
            {"In": "In.UPF", "P": "P.UPF"},
            80.0,
            800.0,
            "relax",
            [1, 1, 1],
            "gamma",
            settings,
            disable_symmetry=True,
            fixed_index=0,
            displacement=self.pipeline.np.array([0.1, 0.0, 0.0]),
        )

        self.assertIn("occupations='smearing'", text)
        self.assertIn("nspin=2", text)
        self.assertIn("nosym=.true.", text)
        self.assertIn("noinv=.true.", text)
        self.assertIn("starting_magnetization(1)=0.500", text)
        self.assertIn("mixing_beta=0.200", text)
        self.assertIn("K_POINTS gamma", text)
        self.assertIn("0 0 0", text)


class TestPinnedMaterials(unittest.TestCase):
    def test_high_accuracy_materials_are_pinned_to_ids(self):
        with HIGH_ACCURACY_CSV.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["formula"].strip() for row in rows))
        self.assertTrue(all(row["material_id"].strip().startswith("JVASP-") for row in rows))
        self.assertEqual(len({(row["formula"], row["material_id"]) for row in rows}), len(rows))

    def test_material_loader_accepts_jid_alias(self):
        pipeline = load_pipeline_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "materials.csv"
            csv_path.write_text("formula,jid\nSi,JVASP-25415\n", encoding="utf-8")

            requests = pipeline.load_material_requests(str(csv_path), None, None, None)

        self.assertEqual(requests, [{"formula": "Si", "material_id": "JVASP-25415"}])

    def test_material_id_selection_rejects_formula_mismatch(self):
        pipeline = load_pipeline_module()
        dataset = [{"jid": "JVASP-1", "formula": "GaAs"}]

        with self.assertRaisesRegex(RuntimeError, "Refusing to run a mismatched structure"):
            pipeline.select_material(dataset, "Si", "JVASP-1")


class TestStructureIdealization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = load_pipeline_module()

    def test_idealize_structure_restores_exact_zincblende_symmetry(self):
        atoms = self.pipeline.Atoms(
            symbols=["In", "P"],
            scaled_positions=[[0.2499, 0.2501, 0.2500], [0.5000, 0.5000, 0.5000]],
            cell=[
                [0.0000, 2.9613, 2.9612],
                [2.9612, 0.0000, 2.9613],
                [2.9613, 2.9612, 0.0001],
            ],
            pbc=True,
        )

        idealized = self.pipeline.idealize_structure(atoms, symprec=1.0e-2, angle_tolerance=-1.0)

        self.assertEqual(idealized.get_chemical_formula(), "InP")
        lengths = idealized.cell.lengths()
        self.assertAlmostEqual(lengths[0], lengths[1], places=6)
        self.assertAlmostEqual(lengths[1], lengths[2], places=6)


class TestScanShardingHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = load_pipeline_module()

    def test_filter_site_groups_returns_requested_labels_in_order(self):
        site_groups = [
            {"label": "In_s0", "element": "In"},
            {"label": "P_s0", "element": "P"},
            {"label": "P_s1", "element": "P"},
        ]

        filtered = self.pipeline.filter_site_groups(site_groups, ["P_s1", "In_s0", "P_s1"])

        self.assertEqual([group["label"] for group in filtered], ["P_s1", "In_s0"])

    def test_filter_site_groups_rejects_unknown_labels(self):
        with self.assertRaisesRegex(RuntimeError, "Requested site label"):
            self.pipeline.filter_site_groups([{"label": "In_s0", "element": "In"}], ["P_s0"])

    def test_select_direction_subset_slices_generated_directions(self):
        directions = self.pipeline.generate_directions("fibonacci", 6)

        subset, start, stop, total = self.pipeline.select_direction_subset(directions, 2, 5)

        self.assertEqual((start, stop, total), (2, 5, 6))
        self.assertEqual([label for label, _vector in subset], [label for label, _vector in directions[2:5]])

    def test_select_direction_subset_validates_bounds(self):
        directions = self.pipeline.generate_directions("fibonacci", 4)

        with self.assertRaisesRegex(ValueError, "outside the generated direction range"):
            self.pipeline.select_direction_subset(directions, 4, None)

        with self.assertRaisesRegex(ValueError, "must be smaller"):
            self.pipeline.select_direction_subset(directions, 3, 3)


class TestQeLauncherSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = load_pipeline_module()

    def test_auto_prefers_mpirun_for_openmpi_under_slurm(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
            mock.patch.dict(
                self.pipeline.os.environ,
                {"SLURM_JOB_ID": "26662600", "LOADEDMODULES": "gcc/14.2.0:openmpi/5.0.7:espresso/7.3.1"},
                clear=False,
            ), \
            mock.patch.object(
                self.pipeline.shutil,
                "which",
                side_effect=lambda name: {
                    "srun": "/usr/bin/srun",
                    "mpirun": "/apps/gcc/14.2.0/openmpi/5.0.7/bin/mpirun",
                    "mpiexec": None,
                }.get(name),
            ), \
            mock.patch.object(self.pipeline.subprocess, "run") as run_mock:
            run_mock.return_value = SimpleNamespace(returncode=0, stdout="JOB DONE\n")
            self.pipeline.run_qe(
                "&CONTROL\n/\n",
                Path(tmpdir),
                "test",
                "pw.x",
                timeout=60,
                nprocs=32,
                qe_launcher="auto",
                force_qe=True,
            )

        self.assertEqual(
            run_mock.call_args.args[0],
            ["/apps/gcc/14.2.0/openmpi/5.0.7/bin/mpirun", "-np", "32", "pw.x", "-in", "test.in"],
        )

    def test_forced_srun_uses_slurm_launcher(self):
        with tempfile.TemporaryDirectory() as tmpdir, \
            mock.patch.dict(self.pipeline.os.environ, {"SLURM_JOB_ID": "26662600"}, clear=False), \
            mock.patch.object(
                self.pipeline.shutil,
                "which",
                side_effect=lambda name: {
                    "srun": "/usr/bin/srun",
                    "mpirun": "/usr/bin/mpirun",
                    "mpiexec": "/usr/bin/mpiexec",
                }.get(name),
            ), \
            mock.patch.object(self.pipeline.subprocess, "run") as run_mock:
            run_mock.return_value = SimpleNamespace(returncode=0, stdout="JOB DONE\n")
            self.pipeline.run_qe(
                "&CONTROL\n/\n",
                Path(tmpdir),
                "test",
                "pw.x",
                timeout=60,
                nprocs=8,
                qe_launcher="srun",
                force_qe=True,
            )

        self.assertEqual(
            run_mock.call_args.args[0],
            ["/usr/bin/srun", "--ntasks", "8", "--cpu-bind=cores", "pw.x", "-in", "test.in"],
        )

    def test_cached_output_is_ignored_when_crash_file_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            (run_dir / "tmp").mkdir()
            (run_dir / "test.in").write_text("&CONTROL\n/\n", encoding="utf-8")
            (run_dir / "test.out").write_text("... JOB DONE.\n", encoding="utf-8")
            (run_dir / "CRASH").write_text("stale crash marker\n", encoding="utf-8")

            with mock.patch.object(
                self.pipeline.shutil,
                "which",
                side_effect=lambda name: {"srun": None, "mpirun": None, "mpiexec": None}.get(name),
            ), mock.patch.object(self.pipeline.subprocess, "run") as run_mock:
                run_mock.return_value = SimpleNamespace(returncode=0, stdout="JOB DONE\n")
                output_text = self.pipeline.run_qe(
                    "&CONTROL\n/\n",
                    run_dir,
                    "test",
                    "pw.x",
                    timeout=60,
                    nprocs=1,
                    qe_launcher="auto",
                    force_qe=False,
                )

        self.assertEqual(output_text, "JOB DONE\n")
        self.assertEqual(run_mock.call_count, 1)
        self.assertFalse((run_dir / "CRASH").exists())

    def test_run_qe_redirects_and_cleans_external_scratch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "run"
            scratch_root = root / "scratch"
            input_text = "&CONTROL\n  outdir='./tmp'\n/\n"
            expected_scratch = self.pipeline.get_qe_scratch_dir(run_dir, "test", str(scratch_root))

            with mock.patch.object(
                self.pipeline.shutil,
                "which",
                side_effect=lambda name: {"srun": None, "mpirun": None, "mpiexec": None}.get(name),
            ), mock.patch.object(self.pipeline.subprocess, "run") as run_mock:
                run_mock.return_value = SimpleNamespace(returncode=0, stdout="JOB DONE\n")
                output_text = self.pipeline.run_qe(
                    input_text,
                    run_dir,
                    "test",
                    "pw.x",
                    timeout=60,
                    nprocs=1,
                    qe_launcher="auto",
                    force_qe=True,
                    qe_scratch_root=str(scratch_root),
                )

            rendered_input = (run_dir / "test.run.in").read_text(encoding="utf-8")
            self.assertEqual(output_text, "JOB DONE\n")
            self.assertEqual(run_mock.call_args.args[0], ["pw.x", "-in", "test.run.in"])
            self.assertIn(f"outdir='{expected_scratch.as_posix()}'", rendered_input)
            self.assertIn(f"wfcdir='{expected_scratch.as_posix()}'", rendered_input)
            self.assertEqual((run_dir / "test.in").read_text(encoding="utf-8"), input_text)
            self.assertFalse(expected_scratch.exists())


class TestQeEnergyParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = load_pipeline_module()

    def test_parse_total_energy_prefers_final_converged_marker(self):
        output_text = """
     total energy              =   -10.00000000 Ry
!    total energy              =   -10.50000000 Ry
"""

        energy_ry = self.pipeline.parse_total_energy_ry(output_text)

        self.assertEqual(energy_ry, -10.5)

    def test_parse_total_energy_falls_back_to_last_scf_iteration(self):
        output_text = """
     iteration # 99
     total energy              =   -3721.01392668 Ry
     iteration #100
     total energy              =   -3721.01385949 Ry

     End of self-consistent calculation

     convergence NOT achieved after 100 iterations: stopping

   JOB DONE.
"""

        energy_ry = self.pipeline.parse_total_energy_ry(output_text)

        self.assertEqual(energy_ry, -3721.01385949)

    def test_parse_total_energy_can_require_converged_marker(self):
        output_text = """
     total energy              =   -3721.01385949 Ry
     convergence NOT achieved after 100 iterations: stopping
   JOB DONE.
"""

        with self.assertRaisesRegex(ValueError, "converged total energy"):
            self.pipeline.parse_total_energy_ry(output_text, require_converged=True)


class TestNielExportHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = load_pipeline_module()

    def test_formula_stoichiometry_parses_compounds(self):
        self.assertEqual(
            self.pipeline.formula_stoichiometry("GaAgP2Se6"),
            {"Ga": 1.0, "Ag": 1.0, "P": 2.0, "Se": 6.0},
        )

    def test_aggregate_outputs_write_niel_ready_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir)
            self.pipeline.write_aggregate_outputs(
                results_dir,
                [
                    {
                        "formula": "ZnO",
                        "material_id": "JVASP-17188",
                        "status": "ok",
                        "structure_source": "qe_vc_relax",
                        "ed_mode": "static",
                        "calculation_method": "dft_displacement_barrier_proxy",
                        "tde_interpretation": "screening_proxy_not_dynamic_threshold_displacement_energy",
                        "element_aggregates_eV": {
                            "Zn": {
                                "recommended_single_value_eV": 12.3,
                                "aggregation_mode": "min",
                                "weighted_mean_eV": 12.3,
                                "minimum_eV": 12.3,
                                "maximum_eV": 12.3,
                                "inequivalent_site_count": 1,
                                "site_labels": ["Zn_s0"],
                                "site_values_eV": {"Zn_s0": 12.3},
                                "site_multiplicities": {"Zn_s0": 1},
                            },
                            "O": {
                                "recommended_single_value_eV": 28.0,
                                "aggregation_mode": "min",
                                "weighted_mean_eV": 28.0,
                                "minimum_eV": 28.0,
                                "maximum_eV": 28.0,
                                "inequivalent_site_count": 1,
                                "site_labels": ["O_s0"],
                                "site_values_eV": {"O_s0": 28.0},
                                "site_multiplicities": {"O_s0": 1},
                            },
                        },
                        "site_results": [],
                    }
                ],
            )
            with (results_dir / "niel_ed_inputs.csv").open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["formula"], "ZnO")
        self.assertEqual(rows[0]["stoichiometric_index"], "1.0")
        self.assertEqual(rows[0]["displacement_threshold_energy_eV"], "12.3")


class TestAggregateScript(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aggregate = load_aggregate_module()

    def test_load_summaries_ignores_batch_summary_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_dir = Path(tmpdir)
            (results_dir / "ZnO_JVASP-17188_summary.json").write_text(
                json.dumps({"formula": "ZnO", "material_id": "JVASP-17188", "status": "ok"}),
                encoding="utf-8",
            )
            (results_dir / "ed_batch_summary.json").write_text(
                json.dumps({"total_requests": 1, "material_summaries": []}),
                encoding="utf-8",
            )

            summaries = self.aggregate.load_summaries(results_dir)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0]["formula"], "ZnO")


class TestSlurmWrapper(unittest.TestCase):
    def test_wrapper_builds_strict_command_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            csv_path = tmpdir_path / "materials.csv"
            csv_path.write_text("formula,jid\nInP,JVASP-1183\nBSb,JVASP-133843\n", encoding="utf-8")

            env = os.environ.copy()
            env.update({
                "SLURM_ARRAY_TASK_ID": "2",
                "CODE_ROOT": str(REPO_ROOT),
                "PYTHON_BIN": sys.executable,
                "RESULTS_DIR": str(tmpdir_path / "results"),
                "QE_EXECUTABLE": "pw.x",
                "QE_LAUNCHER": "mpirun",
                "ED_KPOINT_MODE": "auto",
                "IDEALIZE_RELAXED_STRUCTURE": "1",
                "PSEUDO_DIR": "/usr/share/espresso/pseudo",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "SLURM_TMPDIR": str(tmpdir_path / "slurm_tmp"),
            })

            completed = subprocess.run(
                ["bash", str(SLURM_PATH), str(csv_path), "--help"],
                cwd=SLURM_PATH.parent,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stdout)
        self.assertIn("Running:", completed.stdout)
        self.assertIn("--formula BSb", completed.stdout)
        self.assertIn("--material-id JVASP-133843", completed.stdout)
        self.assertIn("--qe-launcher mpirun", completed.stdout)
        self.assertIn("--ed-kpoint-mode auto", completed.stdout)
        self.assertIn("--idealize-relaxed-structure", completed.stdout)
        self.assertIn("--ed-directions 62", completed.stdout)
        self.assertIn("--spin-mode auto", completed.stdout)
        self.assertIn("--occupations-mode auto", completed.stdout)
        self.assertIn("--supercell-min-length 16.0", completed.stdout)


if __name__ == "__main__":
    unittest.main()
