import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cttir_model.provenance import atomic_json, read_json
from test_evidence import corpus, corpus_value, registry, reviewed_record

ROOT = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        result = subprocess.run([sys.executable, "-m", "cttir_model", *args],
                                capture_output=True, text=True, timeout=5)
        return result, json.loads(result.stdout)

    def test_ingest_and_search_installed_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            config = read_json(ROOT / "configs/cpu.json")
            config_path = Path(directory) / "cpu.json"
            atomic_json(config_path, config)
            result, report = self.run_cli("corpus", "ingest", "--config", str(config_path),
                                          "--source", str(ROOT / "data/fixtures/corpus.json"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(report["coverage"]["fixture_only"])
            config["corpus"].update(path=report["path"], snapshot_id=report["snapshot_id"])
            atomic_json(config_path, config)
            result, report = self.run_cli("corpus", "search", "--config", str(config_path),
                                          "--query", "align", "--package", "fixtureR",
                                          "--version", "1.0", "--repository", "synthetic")
            self.assertEqual(result.returncode, 0)
            self.assertEqual([d["evidence_id"] for d in report["documents"]], ["evidence-v1"])

    def test_invalid_config_errors_do_not_echo_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            atomic_json(path, {"secret": "SYNTHETIC_CANARY_DO_NOT_ECHO"})
            result, report = self.run_cli("preflight", "--config", str(path))
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("SYNTHETIC_CANARY", result.stdout + result.stderr)
            self.assertEqual(report["status"], "failed")

    def test_dataset_build_keeps_test_answers_out_of_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = corpus_value(fixture_only=False)
            c = corpus(value)
            records = [reviewed_record(c), reviewed_record(c)]
            records[1].update(record_id="held-out", group_id="other-family", split="test",
                              source_manifest_id="other-source", validation_id="other-validation")
            records[1]["messages"][0]["content"] = "SYNTHETIC_SEALED_TEST_CANARY categorise unavailable colour maps"
            atomic_json(root / "corpus.json", value)
            atomic_json(root / "records.json", records)
            atomic_json(root / "reviews.json", registry(records))
            config = read_json(ROOT / "configs/cpu.json")
            config["corpus"].update(path="corpus.json", snapshot_id=c.snapshot_id)
            atomic_json(root / "config.json", config)
            result, report = self.run_cli("data", "build", "--config", str(root / "config.json"),
                                          "--input", str(root / "records.json"),
                                          "--registry", str(root / "reviews.json"))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = Path(report["output"]).read_text()
            self.assertNotIn("SYNTHETIC_SEALED_TEST_CANARY", payload)
            self.assertEqual(len(json.loads(payload)["train"]), 1)

    def test_deferred_commands_exit_nonzero_without_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            atomic_json(path, read_json(ROOT / "configs/cpu.json"))
            for command in [("train", "--profile", "pilot"), ("models", "resolve"),
                            ("evaluate", "--candidate", "baseline"), ("serve",),
                            ("release", "prepare", "--run", "absent")]:
                result, report = self.run_cli(*command, "--config", str(path))
                self.assertEqual(result.returncode, 3)
                self.assertEqual(report["status"], "deferred")
            self.assertFalse((path.parent / "artifacts").exists())
