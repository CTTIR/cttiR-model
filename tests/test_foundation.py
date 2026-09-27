import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cttir_model.cli import main
from cttir_model.config import load_config, validate
from cttir_model.errors import ProjectError
from cttir_model.provenance import atomic_json, decode_json, fingerprint, read_json, record_phase

ROOT = Path(__file__).resolve().parents[1]


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.config = read_json(ROOT / "configs/cpu.json")

    def test_config_schema_and_defaults(self):
        loaded = load_config(ROOT / "configs/cpu.json")
        self.assertEqual(loaded.root, ROOT)
        self.assertFalse(loaded.values["execution"]["allow_training"])

    def test_expensive_and_cloud_flags_rejected(self):
        for section, key in [("execution", "allow_training"),
                             ("execution", "allow_model_downloads"),
                             ("serving", "allow_cloud_fallback")]:
            value = copy.deepcopy(self.config)
            value[section][key] = True
            with self.assertRaises(ProjectError):
                validate(value, "config")

    def test_mutable_revision_rejected(self):
        self.config["models"]["specialist"]["revision"] = "main"
        with self.assertRaises(ProjectError):
            validate(self.config, "config")

    def test_remote_and_credential_endpoints_rejected(self):
        for endpoint in ["https://example.org/v1", "http://secret@127.0.0.1/v1", "http://localhost/v1"]:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                self.config["models"]["specialist"]["endpoint"] = endpoint
                atomic_json(path, self.config)
                with self.assertRaises(ProjectError):
                    load_config(path)

    def test_response_cannot_grant_verification_or_execute_on_abstention(self):
        response = read_json(ROOT / "data/fixtures/response.json")
        validate(response, "response")
        for extra in [{"verified": True}, {"r_code": "base::system('bad')"}]:
            with self.assertRaises(ProjectError):
                validate({**response, **extra}, "response")

    def test_request_rejects_unknown_task_and_client_verification(self):
        request = read_json(ROOT / "data/fixtures/request.json")
        validate(request, "request")
        for extra in [{"task": "execute_shell"}, {"verified": True}, {"protocol_version": 2}]:
            with self.assertRaises(ProjectError):
                validate({**request, **extra}, "request")

    def test_json_is_strict_and_bounded(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}', b'\xff']:
            with self.assertRaises(ProjectError):
                decode_json(raw)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * 100)
            with self.assertRaises(ProjectError):
                read_json(path, limit=10)

    def test_atomic_replacement_preserves_old_file_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            atomic_json(path, {"old": True})
            with patch("cttir_model.provenance.os.replace", side_effect=OSError):
                with self.assertRaises(OSError):
                    atomic_json(path, {"new": True})
            self.assertEqual(read_json(path), {"old": True})
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_hash_ignores_object_key_order(self):
        self.assertEqual(fingerprint({"a": 1, "b": 2}), fingerprint({"b": 2, "a": 1}))

    def test_ledger_keeps_previous_phase_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_phase(root, {"phase": "one", "exit_status": 0})
            record_phase(root, {"phase": "two", "exit_status": 3})
            ledger = read_json(root / "implementation/ledger.json")
            self.assertEqual({item["phase"] for item in ledger["entries"]}, {"one", "two"})

    def test_training_defers_without_inventory_or_network(self):
        with patch("builtins.print"), patch("cttir_model.cli.inventory", side_effect=AssertionError):
            self.assertEqual(main(["train", "--config", str(ROOT / "configs/cpu.json"),
                                   "--profile", "smoke"]), 3)

    def test_audit_and_update_preview_do_not_write(self):
        with patch("builtins.print"), patch("cttir_model.cli.atomic_json", side_effect=AssertionError):
            self.assertEqual(main(["audit", "--config", str(ROOT / "configs/cpu.json")]), 0)
            self.assertEqual(main(["update", "--config", str(ROOT / "configs/cpu.json"),
                                   "--target", "corpus", "--dry-run"]), 0)


if __name__ == "__main__":
    unittest.main()
