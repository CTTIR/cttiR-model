import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from cttir_model.errors import ProjectError
from cttir_model.provenance import atomic_json, fingerprint, read_json
from cttir_model.releases import REQUIRED, ReleaseRegistry, validate_release


def payload(root, name='test-a'):
    root.mkdir(parents=True, exist_ok=True)
    # Integrity fixtures only. These are not real adapters or runtime evidence.
    for filename in REQUIRED:
        (root / filename).write_text('Synthetic unit-test payload\n')
    base = {'source_repo_id': 'owner/base', 'source_revision': 'a' * 40,
            'config_sha256': '1' * 64, 'tokenizer_sha256': '2' * 64,
            'template_sha256': '3' * 64, 'conversion_sha256': '4' * 64}
    effective = fingerprint(base)
    base['effective_base_fingerprint'] = effective
    atomic_json(root / 'base-provenance.json', base)
    atomic_json(root / 'adapter_config.json', {'base_model_name_or_path': 'owner/base', 'revision': 'a' * 40, 'target_modules': ['test']})
    atomic_json(root / 'evaluation.json', {'effective_base_fingerprint': effective, 'corpus_id': 'test-corpus',
                                          'dataset_manifest_sha256': 'd' * 64, 'benchmark_id': 'test-only', 'source_commit': 'c' * 40,
                                          'fixture_only': False, 'release_qualified': True})
    atomic_json(root / 'gate-report.json', {'gates': [
        {'gate': f'G{i:02}', 'status': 'pass', 'exit_status': 0, 'command': 'unit-test-only',
         'artifacts': ['TRAINING_REPORT.md']} for i in range(1, 14)]})
    manifest = {'schema_version': 1, 'release_id': name, 'model_name': 'unit test', 'artifact_kind': 'lora_adapter',
                'base_repo_id': 'owner/base', 'base_revision': 'a' * 40, 'effective_base_fingerprint': effective,
                'source_commit': 'c' * 40, 'corpus_id': 'test-corpus', 'dataset_manifest_sha256': 'd' * 64,
                'benchmark_id': 'test-only', 'gate_report_sha256': hashlib.sha256((root/'gate-report.json').read_bytes()).hexdigest(),
                'status': 'publication_prepared', 'files': [], 'hf_repo': 'owner/test', 'visibility': 'private', 'remote_commit': None}
    for filename in sorted(REQUIRED):
        raw = (root/filename).read_bytes()
        manifest['files'].append({'path': filename, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    atomic_json(root/'release.json', manifest)
    return manifest


class ReleaseTests(unittest.TestCase):
    def test_hash_and_symlink_and_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = payload(root)
            self.assertFalse(validate_release(manifest, root)['runtime_loaded'])
            bad = copy.deepcopy(manifest)
            bad['files'].append(bad['files'][0])
            with self.assertRaises(ProjectError): validate_release(bad, root)
            (root/'README.md').write_text('changed')
            with self.assertRaises(ProjectError): validate_release(manifest, root)
            (root/'README.md').unlink()
            (root/'README.md').symlink_to(root/'TRAINING_REPORT.md')
            with self.assertRaises(ProjectError): validate_release(manifest, root)

    def test_pending_gate_and_wrong_base_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = payload(root)
            for filename, value in [('gate-report.json', {'gates': []}), ('base-provenance.json', {})]:
                current = payload(root)
                atomic_json(root/filename, value)
                raw=(root/filename).read_bytes()
                for entry in current['files']:
                    if entry['path']==filename:
                        entry.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
                if filename=='gate-report.json': current['gate_report_sha256']=hashlib.sha256(raw).hexdigest()
                with self.assertRaises(ProjectError): validate_release(current,root)

    def test_paths_and_text_secret_scanning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = payload(root)
            for path in ['../secret', '/secret', 'optimizer.pt', 'subdir/../README.md']:
                bad=copy.deepcopy(manifest)
                bad['files'].append({'path':path,'sha256':'e'*64,'bytes':1})
                with self.assertRaises(ProjectError): validate_release(bad,root)
            raw=b'hf_'+b'X'*25
            (root/'README.md').write_bytes(raw)
            for item in manifest['files']:
                if item['path']=='README.md': item.update(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw))
            with self.assertRaisesRegex(ProjectError,'credential'): validate_release(manifest,root)

    def test_atomic_pointer_rollback_and_dry_run(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            a=root/'releases/a'; b=root/'releases/b'
            payload(a); payload(b,'test-b')
            registry=ReleaseRegistry(root)
            registry.switch(a/'release.json')
            self.assertFalse((root/'release-registry').exists())
            registry.switch(a/'release.json',dry_run=False)
            registry.switch(b/'release.json',dry_run=False)
            report=registry.switch(rollback=True,dry_run=False)
            self.assertEqual(report['pointer']['current']['release_id'],'test-a')
            self.assertFalse(report['runtime_loaded'])
            (b/'adapter_model.safetensors').write_bytes(b'corrupt')
            before=(root/'release-registry/active.json').read_bytes()
            with self.assertRaises(ProjectError): registry.switch(rollback=True,dry_run=False)
            self.assertEqual((root/'release-registry/active.json').read_bytes(),before)
