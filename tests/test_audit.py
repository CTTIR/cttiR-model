import copy
import tempfile
import unittest
from pathlib import Path

from cttir_model.audit import audit
from cttir_model.cli import pending_gates
from cttir_model.config import Config
from cttir_model.provenance import atomic_json, fingerprint, read_json, record_phase
from test_evidence import corpus_value

ROOT = Path(__file__).resolve().parents[1]


class AuditTests(unittest.TestCase):
    def test_missing_assets_pending_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(read_json(ROOT / 'configs/cpu.json'), Path(directory))
            result = audit(config, pending_gates())
            self.assertEqual(result['status'], 'pending')
            self.assertFalse(config.artifacts.exists())
            self.assertFalse(result['trained_candidate'])

    def test_corrupt_corpus_and_ledger_are_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = read_json(ROOT / 'configs/cpu.json')
            doc = corpus_value()
            atomic_json(root / 'corpus.json', doc)
            value['corpus'].update(path='corpus.json', snapshot_id='sha256:' + fingerprint(doc))
            config = Config(value, root)
            record_phase(config.artifacts, {'phase': 'test', 'exit_status': 0})
            initial = audit(config, pending_gates())
            self.assertTrue(all(row['status'] == 'pass' for row in initial['checks']))
            atomic_json(root/'corpus.json', {**doc, 'fixture_only': False})
            path = next(p for p in (config.artifacts/'implementation').glob('*.json') if len(p.stem) == 64)
            atomic_json(path, {'phase': 'tampered'})
            result = audit(config, pending_gates())
            self.assertEqual(result['status'], 'fail')
            failures = {row['check'] for row in result['checks'] if row['status'] == 'fail'}
            self.assertEqual(failures, {'corpus_integrity', 'ledger_integrity'})
