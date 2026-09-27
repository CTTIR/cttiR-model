import copy
import unittest
from pathlib import Path
from dataclasses import FrozenInstanceError

from cttir_model.errors import ProjectError
from cttir_model.parent import (bind_parent_request, fallback_plan, parent_manifest,
                                review_parent_proposal, validate_parent_spec)
from test_evidence import corpus, corpus_value, request
from cttir_model.provenance import read_json


def spec_fixture():
    return {'schema_version': 1,
        'project': {'id': 'synthetic-project', 'name': 'Example Study', 'slug': 'example_study',
                    'type': 'primary_research', 'goal': 'Describe longitudinal measurements',
                    'language': 'en', 'created_at': '2026-09-27T00:00:00Z'},
        'research': {'design': None, 'domain': None, 'data_types': [], 'ethics_status': 'unknown',
                     'analysis_role': 'unknown', 'data_origin': 'unknown', 'notes': ''},
        'publications': [], 'data_sources': [], 'packages': [], 'decisions': [],
        'workflow': {'pipeline': 'none', 'environment': 'none', 'git': False,
                     'prepare_environment': False, 'network': 'offline', 'reporting': 'generic',
                     'readiness': 'scaffold_ready', 'profile': 'standard_reflowR',
                     'project_backend': 'reflowR', 'table_backend': 'none'},
        'provenance': {'catalog_id': 'unavailable', 'template_version': '0.1.0',
                       'prompt_version': 'none', 'planner_mode': 'deterministic',
                       'model_id': None, 'model_digest': None},
        'analysis': {'aim': 'unknown', 'unit_structure': 'unknown', 'outcome_family': 'unknown',
                     'engine': None, 'approved': False}}


class ParentTests(unittest.TestCase):
    def test_packaged_manifest_matches_reviewed_snapshot(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(parent_manifest(), read_json(root / 'data/manifests/cttir-parent.json'))

    def setUp(self):
        self.manifest = parent_manifest()
        self.spec = spec_fixture()
        self.corpus = corpus()
        self.request = request(self.corpus)
        self.spec['packages'] = [{'name': 'fixtureR', 'version': '1.0', 'revision': 'fixture-v1',
                                 'source': 'synthetic-source', 'evidence_ids': [], 'required': False}]
        self.bindings = [{'name': 'fixtureR', 'source': 'synthetic-source',
                          'revision': 'fixture-v1', 'repository': 'synthetic'}]

    def bind(self, **kwargs):
        args = dict(parent_commit=self.manifest['commit'],
                    resource_pin=self.manifest['resource_manifest']['content_id'],
                    package_bindings=self.bindings)
        args.update(kwargs)
        return bind_parent_request(self.spec, self.request, self.corpus, **args)

    def proposal(self):
        return {'protocol_version': 1, 'request_id': self.request['request_id'], 'status': 'proposed',
                'summary': 'Synthetic advice only', 'r_code': None, 'evidence_ids': ['evidence-v1'],
                'assumptions': [], 'missing_inputs': [], 'limitations': []}

    def review(self, envelope, **kwargs):
        args = dict(expected_envelope_id=envelope.envelope_id, current_spec=self.spec,
                    current_parent_commit=self.manifest['commit'],
                    current_resource_pin=self.manifest['resource_manifest']['content_id'])
        args.update(kwargs)
        return review_parent_proposal(envelope, self.proposal(), self.corpus, **args)

    def test_offline_fallback_is_only_scaffold_and_preserves_unknowns(self):
        plan = fallback_plan(spec_fixture())
        self.assertEqual(plan['status'], 'scaffold_pending')
        self.assertFalse(plan['execution_authorized'])
        self.assertFalse(plan['analysis']['approved'])
        self.assertEqual(fallback_plan(self.spec)['status'], 'unsupported')

    def test_binding_immutable_and_response_preserves_approvals(self):
        envelope = self.bind()
        original = envelope.envelope_id
        self.request['instruction'] = 'later mutation'
        self.assertEqual(original, envelope.envelope_id)
        with self.assertRaises(FrozenInstanceError):
            envelope.payload_json = '{}'
        result = self.review(envelope)
        self.assertEqual(result['workflow'], self.spec['workflow'])
        self.assertEqual(result['analysis'], self.spec['analysis'])
        self.assertFalse(result['application_authorized'])
        self.assertTrue(result['fixture_only'])
        result['analysis']['approved'] = True
        self.assertFalse(envelope.as_dict()['spec']['analysis']['approved'])

    def test_unresolved_and_mismatched_version_rejected(self):
        for version in [None, '9.9']:
            self.spec['packages'][0]['version'] = version
            with self.assertRaisesRegex(ProjectError, 'resolved parent version'):
                self.bind()

    def test_commit_resource_and_revision_mismatch(self):
        for changes in [dict(parent_commit='wrong'), dict(resource_pin='wrong')]:
            with self.assertRaises(ProjectError):
                self.bind(**changes)
        self.spec['packages'][0]['revision'] = 'wrong'
        with self.assertRaises(ProjectError):
            self.bind()
        self.bindings[0]['revision'] = 'wrong'
        with self.assertRaisesRegex(ProjectError, 'Evidence source revision'):
            self.bind()

    def test_candidate_evidence_cannot_be_promoted(self):
        value = corpus_value()
        value['documents'][0]['review_status'] = 'candidate'
        self.corpus = corpus(value)
        self.request['corpus_id'] = self.corpus.snapshot_id
        with self.assertRaisesRegex(ProjectError, 'not approved'):
            self.bind()

    def test_stale_context_and_response_are_rejected(self):
        envelope = self.bind()
        with self.assertRaisesRegex(ProjectError, 'binding is stale'):
            self.review(envelope, expected_envelope_id='sha256:wrong')
        changed = copy.deepcopy(self.spec)
        changed['project']['goal'] = 'Changed goal'
        with self.assertRaisesRegex(ProjectError, 'context changed'):
            self.review(envelope, current_spec=changed)
        self.request['request_id'] = 'different-response'
        with self.assertRaisesRegex(ProjectError, 'request ID'):
            self.review(envelope)

    def test_semantic_approval_and_schema_rules(self):
        self.spec['analysis']['approved'] = True
        with self.assertRaises(ProjectError):
            validate_parent_spec(self.spec)
        self.spec['analysis'].update(aim='descriptive', unit_structure='longitudinal')
        self.assertTrue(validate_parent_spec(self.spec)['analysis']['approved'])
        self.spec['provider'] = 'invented'
        with self.assertRaises(ProjectError):
            validate_parent_spec(self.spec)

    def test_no_evidence_and_empty_packages_can_bind_without_inventing_context(self):
        self.spec = spec_fixture()
        self.request.update(package_pins=[], evidence_ids=[])
        envelope = self.bind(package_bindings=[])
        self.assertEqual(envelope.request['evidence_ids'], [])
        self.assertEqual(envelope.request['instruction'], self.request['instruction'])
