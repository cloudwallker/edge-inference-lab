import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from .fixtures import small_config
from .test_simulation import one_node_config, burst
from edge_inference_lab.policies import Policy
from edge_inference_lab.simulation import simulate


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        from edge_inference_lab.metrics import summarize
        from edge_inference_lab.experiments import run_study, select_fixed_theta
        self.summarize, self.run_study, self.select = summarize, run_study, select_fixed_theta

    def test_ledger_reconstructs_profit_and_counts(self):
        run = simulate(one_node_config(True), burst(0), Policy("test"))
        summary = self.summarize(run.events)
        self.assertEqual(summary["requests"], 4)
        self.assertEqual(summary["accepted"], 4)
        self.assertEqual(summary["new_branch_requests"], 2)
        self.assertEqual(summary["created_extra"], 1)
        self.assertEqual(summary["released"], 1)
        self.assertAlmostEqual(summary["potential_payment"], 0.24)
        self.assertAlmostEqual(summary["revenue"], 0.24)
        self.assertAlmostEqual(summary["upload_cost"], 0.000016)
        self.assertAlmostEqual(summary["inference_cost"], 0.08)
        self.assertAlmostEqual(summary["profit"], 0.159984)
        corrupt = [dict(e) for e in run.events]
        next(e for e in corrupt if e["kind"] == "request")["profit"] = 999
        with self.assertRaisesRegex(ValueError, "ledger"):
            self.summarize(corrupt)

    def test_selection_uses_development_rows_only(self):
        rows = [{"phase": "development", "policy": "pd_theta_2", "profit": 1},
                {"phase": "development", "policy": "pd_theta_4", "profit": 2},
                {"phase": "test", "policy": "pd_theta_2", "profit": 1000}]
        self.assertEqual(self.select(rows), "pd_theta_4")

    def test_small_study_exports_real_results_and_repeats_core_values(self):
        raw = small_config()
        raw["workload"].update(slots=2, requests_per_slot=4, block_slots=1, switch_slot=1)
        raw["pricing"]["payments"]["toy"]["low"] = [0.2, 0.15]
        raw["pricing"]["payments"]["toy"]["high"] = [0.3, 0.25]
        raw["seeds"] = {"development": [1], "test": [101]}
        from edge_inference_lab.config import Config
        cfg = Config.from_dict(raw)
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "a", Path(temp) / "b"
            meta_a = self.run_study(cfg, a)
            meta_b = self.run_study(cfg, b)
            self.assertEqual(meta_a["trace_hashes"], meta_b["trace_hashes"])
            self.assertEqual(meta_a["selected_fixed_policy"], meta_b["selected_fixed_policy"])
            for name in ("aggregate.csv", "paired_differences.csv", "summary.md"):
                self.assertEqual((a / name).read_text(encoding="utf8"), (b / name).read_text(encoding="utf8"))
            self.assertTrue((a / "profit_matrix.svg").exists())
            self.assertTrue((a / "switch_timeseries.svg").exists())
            self.assertEqual(meta_a["status"], "complete")
            self.assertEqual(meta_a["test_seeds"], [101])
            self.assertTrue(meta_a["saved_ledgers"])
            from edge_inference_lab.experiments import verify_study
            verified = verify_study(a)
            self.assertEqual(verified["status"], "match")
            self.assertEqual(verified["checked_runs"], 64)
            self.assertEqual(verified["checked_rows"], 68)
            csv_path = a / "aggregate.csv"
            csv_path.write_text(csv_path.read_text(encoding="utf8") + "corrupt", encoding="utf8")
            with self.assertRaisesRegex(ValueError, "manifest"):
                verify_study(a)
            with self.assertRaises(FileExistsError):
                self.run_study(cfg, a)

    def test_cli_single_command_and_bad_config_exit(self):
        raw = small_config()
        raw["workload"].update(slots=2, requests_per_slot=4, block_slots=1, switch_slot=1)
        raw["pricing"]["payments"]["toy"]["low"] = [0.2, 0.15]
        raw["pricing"]["payments"]["toy"]["high"] = [0.3, 0.25]
        raw["seeds"] = {"development": [1], "test": [101]}
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.json"
            config.write_text(json.dumps(raw), encoding="utf8")
            output = Path(temp) / "report"
            result = subprocess.run([sys.executable, "-m", "edge_inference_lab", "--config", str(config), "--output", str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((output / "metadata.json").is_file())
            result = subprocess.run([sys.executable, "-m", "edge_inference_lab", "--config", str(config),
                                     "--policy", "pd_theta_4", "--output", str(Path(temp) / "wrong-policy")],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requests", result.stderr)
            config.write_text("{}", encoding="utf8")
            result = subprocess.run([sys.executable, "-m", "edge_inference_lab", "--config", str(config), "--output", str(output)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)

    def test_source_checkout_entry_runs_without_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "case"
            root = Path(__file__).resolve().parents[1]
            command = [sys.executable, str(root / "run_lab.py"), "--config", str(root / "configs/retention-case.json"),
                       "--requests", str(root / "data/examples/retention-case.csv"),
                       "--policy", "pd_theta_4", "--output", str(output)]
            result = subprocess.run(command, cwd=temp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((output / "summary.json").read_text(encoding="utf8"))
            self.assertEqual(summary["accepted"], 8)
            self.assertEqual(summary["created_extra"], 1)

    def test_csv_duplicate_headers_and_ragged_rows_are_rejected(self):
        from edge_inference_lab.experiments import load_requests
        header = "id,slot,source,model,min_accuracy,deadline_ms,data_mb\n"
        bodies = ["id,id,slot,source,model,min_accuracy,deadline_ms,data_mb\none,overwrite,0,a,toy,.5,200,1\n",
                  header + "one,0,a,toy,.5,200,1\ntwo,1,a,toy,.5,200,1,discarded\n",
                  header + "one,0,a,toy,.5,200\n"]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "requests.csv"
            for text in bodies:
                path.write_text(text, encoding="utf8")
                with self.assertRaisesRegex(ValueError, "CSV"):
                    load_requests(path)


if __name__ == "__main__":
    unittest.main()
