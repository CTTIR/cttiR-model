import copy
import unittest

from cttir_model.broker import FixtureEndpoint, Cancellation
from cttir_model.errors import ProjectError
from cttir_model.evaluation import compare_reports, freeze_benchmark, score_outputs
from cttir_model.provenance import fingerprint
from test_evidence import corpus, request


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.c = corpus()
        self.req = request(self.c)
        self.frozen = freeze_benchmark({'schema_version': 1, 'benchmark_id': 'synthetic-only',
                                       'fixture_only': True, 'cases': [
                                           {'case_id': 'one', 'group_id': 'family', 'supported': True, 'request': self.req}]}, self.c)
        proposal = FixtureEndpoint().generate(self.req, self.c.evidence(self.req['evidence_ids'], self.req['package_pins']), Cancellation(1))
        self.run = {'run_id': 'fixture-a', 'arm': 'A', 'fixture_only': True,
                    'benchmark_sha256': self.frozen['benchmark_sha256'], 'corpus_id': self.c.snapshot_id,
                    'effective_base_fingerprint': 'a' * 64, 'generation_config_sha256': 'b' * 64,
                    'records': [{'case_id': 'one', 'proposal': proposal, 'latency_ms': 1, 'review': None}]}

    def review(self):
        row = self.run['records'][0]
        row['review'] = {'reviewer': 'test-only', 'output_sha256': fingerprint({
            'benchmark_sha256': self.frozen['benchmark_sha256'], 'case_id': row['case_id'], 'proposal': row['proposal']}),
            'api_correct': True, 'scientific_pass': True, 'task_pass': True, 'critical_violation': False}

    def test_missing_review_not_counted_as_success(self):
        result = score_outputs(self.frozen, self.run, self.c)
        self.assertEqual(result['metrics']['raw_schema_valid'], 1)
        self.assertEqual(result['metrics']['supported_success'], 0)
        self.assertEqual(result['metrics']['review_coverage'], 0)

    def test_fixture_cannot_become_improvement_claim(self):
        baseline = score_outputs(self.frozen, self.run, self.c)
        self.review()
        self.run['arm'] = 'B'
        candidate = score_outputs(self.frozen, self.run, self.c)
        result = compare_reports(baseline, candidate)
        self.assertEqual(result['observed_gain'], 1)
        self.assertFalse(result['gain_supported'])
        self.assertFalse(result['release_qualified'])

    def test_refusal_is_not_success_on_supported_task(self):
        self.run['records'][0]['proposal']['status'] = 'unsupported'
        self.review()
        result = score_outputs(self.frozen, self.run, self.c)
        self.assertEqual(result['metrics']['supported_success'], 0)
        self.assertEqual(result['metrics']['abstention_precision'], 0)

    def test_policy_tampering_and_missing_outputs_fail(self):
        modified = copy.deepcopy(self.frozen)
        modified['scoring_policy']['supported_success_min'] = 0.01
        with self.assertRaises(ProjectError):
            score_outputs(modified, self.run, self.c)
        self.run['records'] = []
        with self.assertRaises(ProjectError):
            score_outputs(self.frozen, self.run, self.c)

    def test_stale_review_and_unfair_comparison_fail(self):
        self.review()
        self.run['records'][0]['proposal']['summary'] = 'Changed after review'
        with self.assertRaises(ProjectError):
            score_outputs(self.frozen, self.run, self.c)
        self.review()
        left = score_outputs(self.frozen, self.run, self.c)
        right = copy.deepcopy(left)
        right.update(arm='B', corpus_id='wrong')
        with self.assertRaises(ProjectError):
            compare_reports(left, right)
