"""Regressions for evidence mutation and false readiness claims."""

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

from cttir_model.audit import audit
from cttir_model.books import ingest_library, training_plan
from cttir_model.cli import pending_gates
from cttir_model.config import Config
from cttir_model.errors import ProjectError
from cttir_model.evaluation import compare_reports, freeze_benchmark, score_outputs
from cttir_model.provenance import atomic_json, fingerprint, read_json, record_phase
from cttir_model.releases import ReleaseRegistry, validate_release
from cttir_model.verification import installed_fingerprint, verify_installed_source
import test_books
import test_evaluation
from test_evidence import corpus, corpus_value, document, request
from test_releases import payload

ROOT = Path(__file__).resolve().parents[1]


class CorpusIsolationTests(unittest.TestCase):
    def test_mutating_input_and_all_public_views_cannot_change_pinned_evidence(self):
        value = corpus_value()
        c = corpus(value)
        expected = copy.deepcopy(value['documents'][0])
        pin = c.snapshot_id
        value['documents'][0]['content'] = 'changed after validation'
        for view in (c.documents['evidence-v1'],
                     c.evidence(['evidence-v1'], [document()['package']])[0],
                     c.search('align', document()['package'])[0]):
            view['content'] = 'caller mutation'
            view['package']['version'] = 'unreviewed'
            view['rights_status'] = 'rejected'
        self.assertEqual(c.evidence(['evidence-v1'], [document()['package']]), [expected])
        self.assertEqual(c.snapshot_id, pin)
        for attr in ('snapshot_id', 'fixture_only'):
            with self.assertRaises(AttributeError):
                setattr(c, attr, None)


class ComparisonIntegrityTests(unittest.TestCase):
    def setUp(self):
        fixture = test_evaluation.EvaluationTests()
        fixture.setUp()
        self.fixture = fixture
        self.left = score_outputs(fixture.frozen, fixture.run, fixture.c)
        fixture.review()
        fixture.run['arm'] = 'B'
        self.right = score_outputs(fixture.frozen, fixture.run, fixture.c)

    def test_identity_free_summary_cannot_support_gain(self):
        left = {'arm': 'A', 'fixture_only': False, 'group_scores': {str(i): 0 for i in range(20)},
                'metrics': {'review_coverage': 1}}
        right = {**left, 'arm': 'B', 'group_scores': {str(i): 1 for i in range(20)}}
        with self.assertRaises(ProjectError):
            compare_reports(left, right)

    def test_summary_and_case_tampering_are_rejected(self):
        mutations = [lambda r: r['group_scores'].update(family=0.5),
                     lambda r: r['metrics'].update(review_coverage=0),
                     lambda r: r['case_results'][0].update(case_id='other'),
                     lambda r: r['case_results'][0].update(reviewed=False),
                     lambda r: r['case_results'].append(r['case_results'][0]),
                     lambda r: r.pop('records_sha256')]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                right = copy.deepcopy(self.right)
                mutate(right)
                with self.assertRaises(ProjectError):
                    compare_reports(self.left, right)

    def test_malformed_run_values_raise_typed_errors(self):
        for change in ({'arm': []}, {'run_id': []}):
            with self.assertRaises(ProjectError):
                score_outputs(self.fixture.frozen, {**self.fixture.run, **change}, self.fixture.c)
        self.fixture.run['records'][0]['latency_ms'] = 10 ** 1000
        with self.assertRaises(ProjectError):
            score_outputs(self.fixture.frozen, self.fixture.run, self.fixture.c)

    def test_complete_paired_reviewed_cases_can_support_observed_gain(self):
        # Arithmetic fixture with production-shaped provenance, never a model claim.
        c = corpus(corpus_value(fixture_only=False))
        req = request(c)
        cases = [{'case_id': str(i), 'group_id': str(i), 'supported': True, 'request': req}
                 for i in range(20)]
        frozen = freeze_benchmark({'schema_version': 1, 'benchmark_id': 'unit-test-only',
                                   'fixture_only': False, 'cases': cases}, c)
        reports = []
        for arm in ('A', 'B'):
            run = copy.deepcopy(self.fixture.run)
            run.update(arm=arm, fixture_only=False, corpus_id=c.snapshot_id,
                       benchmark_sha256=frozen['benchmark_sha256'], records=[])
            for case in cases:
                proposal = copy.deepcopy(self.fixture.run['records'][0]['proposal'])
                proposal['status'] = 'unsupported' if arm == 'A' else 'proposed'
                review = {'reviewer': 'unit-test-only', 'api_correct': True, 'scientific_pass': True,
                          'task_pass': True, 'critical_violation': False,
                          'output_sha256': fingerprint({'benchmark_sha256': frozen['benchmark_sha256'],
                                                        'case_id': case['case_id'], 'proposal': proposal})}
                run['records'].append({'case_id': case['case_id'], 'proposal': proposal,
                                       'latency_ms': 1, 'review': review})
            reports.append(score_outputs(frozen, run, c))
        result = compare_reports(*reports)
        self.assertTrue(result['gain_supported'])
        self.assertEqual(result['observed_gain'], 1)
        self.assertFalse(result['release_qualified'])


class BookPreparationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_books.BookTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.ingest()

    def test_changed_source_does_not_replace_existing_plan(self):
        root = self.fixture.root
        training_plan(root)
        before = (root / 'training-plan.json').read_bytes()
        source = root / 'book.pdf'
        raw = source.read_bytes()
        source.write_bytes(b'X' + raw[1:])
        with self.assertRaises(ProjectError):
            training_plan(root)
        self.assertEqual((root / 'training-plan.json').read_bytes(), before)

    def test_unrequested_training_stays_unrequested(self):
        f = self.fixture
        f.source['training_requested_by_user'] = False
        atomic_json(f.root / 'manifest.json', {'schema_version': 1, 'visibility': 'local_only', 'sources': [f.source]})
        f.ingest()
        self.assertEqual(training_plan(f.root)['sources'][0]['training_use'], 'not_requested')

    def test_corrupt_index_or_snapshot_is_not_replaced(self):
        f = self.fixture
        for path in (next((f.root / 'snapshots').glob('*.json')), next((f.root / 'index').glob('*.json'))):
            before = path.read_bytes()
            atomic_json(path, [])
            with self.assertRaises(ProjectError):
                ingest_library(f.root)
            self.assertEqual(read_json(path), [])
            path.write_bytes(before)


class AuditEvidenceTests(unittest.TestCase):
    def test_absent_stale_and_matching_test_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Config(read_json(ROOT / 'configs/cpu.json'), Path(directory))
            def check():
                return next(row for row in audit(config, pending_gates())['checks'] if row['check'] == 'cpu_test_evidence')
            self.assertEqual(check()['status'], 'pending')
            record_phase(config.artifacts, {'phase': 'cpu_tests', 'exit_status': 0,
                                           'installed_package_sha256': '0' * 64, 'timestamp': '2026-01-01'})
            self.assertEqual(check()['status'], 'pending')
            record_phase(config.artifacts, {'phase': 'cpu_tests', 'exit_status': 0,
                                           'installed_package_sha256': installed_fingerprint(), 'timestamp': '2026-01-02'})
            self.assertEqual(check()['status'], 'pass')
            record_phase(config.artifacts, {'phase': 'cpu_tests', 'exit_status': 1,
                                           'installed_package_sha256': installed_fingerprint(), 'timestamp': '2026-01-03'})
            self.assertEqual(check()['status'], 'fail')
            atomic_json(config.artifacts / 'implementation/ledger.json', {'schema_version': 1, 'entries': []})
            self.assertEqual(audit(config, pending_gates())['status'], 'fail')

    def test_stale_installed_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src/cttir_model').mkdir(parents=True)
            (root / 'src/cttir_model/__init__.py').write_text('changed source')
            with self.assertRaisesRegex(ProjectError, 'reinstall'):
                verify_installed_source(root)


class ReleaseBoundaryTests(unittest.TestCase):
    def test_malformed_active_pointer_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'release-registry/active.json'
            atomic_json(path, [])
            before = path.read_bytes()
            with self.assertRaises(ProjectError):
                ReleaseRegistry(root).switch(rollback=True, dry_run=False)
            self.assertEqual(path.read_bytes(), before)

    def test_malformed_gates_and_adapter_return_typed_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, mutate in [('gate-report.json', lambda d: d['gates'][0].update(gate=[])),
                                     ('gate-report.json', lambda d: d['gates'][0].update(artifacts=[{}])),
                                     ('gate-report.json', lambda d: d['gates'][0].update(command=True)),
                                     ('adapter_config.json', lambda d: d.update(target_modules='unresolved'))]:
                manifest = payload(root)
                value = read_json(root / filename)
                mutate(value)
                atomic_json(root / filename, value)
                raw = (root / filename).read_bytes()
                digest = hashlib.sha256(raw).hexdigest()
                for row in manifest['files']:
                    if row['path'] == filename:
                        row.update(bytes=len(raw), sha256=digest)
                if filename == 'gate-report.json':
                    manifest['gate_report_sha256'] = digest
                with self.assertRaises(ProjectError):
                    validate_release(manifest, root)
