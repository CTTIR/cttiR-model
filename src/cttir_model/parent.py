"""Read-only binding to the pinned parent contract; never applies a proposal."""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from importlib.resources import files

from jsonschema import FormatChecker
from jsonschema.validators import validator_for

from .corpus import Corpus
from .errors import ProjectError
from .protocol import validate_proposal, validate_request
from .provenance import canonical, fingerprint, read_json, decode_json

DEFAULT_MANIFEST = None


def parent_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    """Load the checked-in inspection snapshot, not an installed R package."""
    return read_json(Path(path)) if path is not None else decode_json(
        files('cttir_model').joinpath('schemas', 'cttir-parent.json').read_bytes())


def _fail(code: str, message: str) -> None:
    raise ProjectError(code, message)


def validate_parent_spec(spec: dict, manifest: dict | None = None) -> dict:
    manifest = parent_manifest() if manifest is None else manifest
    try:
        raw = canonical(spec)
    except (TypeError, ValueError, RecursionError):
        _fail('parent_spec', 'Parent specification must contain plain JSON values.')
    if len(raw) > 1048576:
        _fail('parent_spec', 'Parent specification exceeds 1 MiB.')
    def depth(value, level=0):
        if level > 32:
            _fail('parent_spec', 'Parent specification exceeds 32 nesting levels.')
        if isinstance(value, dict):
            for child in value.values():
                depth(child, level + 1)
        elif isinstance(value, list):
            for child in value:
                depth(child, level + 1)
    depth(spec)
    schema = manifest['schema_contract']['project_spec_schema']
    if next(validator_for(schema)(schema, format_checker=FormatChecker()).iter_errors(spec), None):
        _fail('parent_spec', 'Parent specification does not match the pinned schema.')
    for collection, key in [('publications', 'id'), ('data_sources', 'id'), ('packages', 'name')]:
        ids = [row[key].lower() for row in spec[collection]]
        if len(ids) != len(set(ids)):
            _fail('parent_spec', 'Parent identities must be unique.')
    slugs = [spec['project']['slug']] + [row['slug'] for row in spec['publications']]
    for slug in slugs:
        if len(slug) > 80 or re.fullmatch(r'(con|prn|aux|nul|com[0-9]|lpt[0-9])', slug):
            _fail('parent_spec', 'Parent slug is not portable.')
    if len(slugs[1:]) != len(set(slugs[1:])):
        _fail('parent_spec', 'Publication slugs must be unique.')
    analysis = spec.get('analysis', {})
    if analysis.get('approved') and (analysis.get('aim', 'unknown') == 'unknown' or
                                    analysis.get('unit_structure', 'unknown') == 'unknown'):
        _fail('parent_approval', 'Analysis approval requires known aim and unit structure.')
    return json.loads(raw)


@dataclass(frozen=True)
class ParentEnvelope:
    """Canonical immutable content; accessors return independent mutable copies."""
    payload_json: str

    @property
    def envelope_id(self) -> str:
        return 'sha256:' + fingerprint(self.as_dict())

    def as_dict(self) -> dict:
        return json.loads(self.payload_json)

    @property
    def request(self) -> dict:
        return self.as_dict()['request']


def bind_parent_request(spec: dict, request: dict, corpus: Corpus, *, parent_commit: str,
                        resource_pin: str, package_bindings: list[dict],
                        manifest_path: Path = DEFAULT_MANIFEST) -> ParentEnvelope:
    """Bind explicit v1 request and reviewed source/repository mappings to parent state.

    Each package binding has exactly name, source, revision, repository. Its source
    and revision must equal the parent package row; repository must equal v1 pin.
    Evidence revisions must equal the parent revision. No values are guessed.
    """
    manifest = parent_manifest(manifest_path)
    spec = validate_parent_spec(spec, manifest)
    if parent_commit != manifest['commit']:
        _fail('parent_commit', 'Parent commit differs from the inspected revision.')
    if resource_pin != manifest['resource_manifest']['content_id']:
        _fail('parent_resource_pin', 'Parent resource pin differs from the inspected snapshot.')
    evidence = validate_request(request, corpus)
    if request['language'] != spec['project']['language']:
        _fail('parent_language', 'Request language differs from the parent specification.')
    if not isinstance(package_bindings, list):
        _fail('parent_package', 'Explicit package source mappings must be a list.')
    mapped = {}
    for binding in package_bindings:
        if not isinstance(binding, dict) or set(binding) != {'name', 'source', 'revision', 'repository'} or not all(
                isinstance(v, str) and v.strip() for v in binding.values()):
            _fail('parent_package', 'Each package source mapping needs four explicit string fields.')
        if binding['name'] in mapped:
            _fail('parent_package', 'Package source mappings must be unique.')
        mapped[binding['name']] = binding
    if set(mapped) != {p['name'] for p in request['package_pins']}:
        _fail('parent_package', 'Source mappings must exactly cover requested package pins.')
    packages = {p['name']: p for p in spec['packages']}
    for pin in request['package_pins']:
        parent = packages.get(pin['name'])
        binding = mapped[pin['name']]
        if parent is None or not parent['version'] or parent['version'] != pin['version']:
            _fail('parent_package', 'Selected package needs an exact resolved parent version.')
        if binding['source'] != parent['source'] or binding['revision'] != parent['revision'] or binding['repository'] != pin['repository']:
            _fail('parent_package', 'Package source, repository or revision mapping differs from its pins.')
    for doc in evidence:
        if doc['source_revision'] != mapped[doc['package']['name']]['revision']:
            _fail('parent_revision', 'Evidence source revision differs from the parent package revision.')
    payload = {'envelope_version': 1, 'parent_package': manifest['package'],
               'parent_version': manifest['version'], 'parent_commit': parent_commit,
               'resource_pin': resource_pin, 'spec_sha256': fingerprint(spec), 'spec': spec,
               'request': request, 'package_bindings': package_bindings,
               'fixture_only': corpus.fixture_only, 'execution_authorized': False}
    return ParentEnvelope(canonical(payload).decode())


def fallback_plan(spec: dict, *, manifest_path: Path = DEFAULT_MANIFEST) -> dict:
    """Describe the offline baseline only; no inference, execution or file writes."""
    spec = validate_parent_spec(spec, parent_manifest(manifest_path))
    workflow = spec['workflow']
    supported = (workflow['profile'] == 'standard_reflowR' and workflow['project_backend'] == 'reflowR'
                 and workflow['pipeline'] == 'none' and workflow['environment'] == 'none'
                 and not workflow['git'] and not workflow['prepare_environment']
                 and workflow['reporting'] == 'generic' and workflow['table_backend'] == 'none'
                 and workflow['readiness'] == 'scaffold_ready' and not spec['packages'])
    return {'status': 'scaffold_pending' if supported else 'unsupported',
            'summary': 'Deterministic offline scaffold only; reflowR integration remains pending.' if supported
            else 'The current parent cannot apply this workflow or dependency selection.',
            'workflow': workflow, 'analysis': spec.get('analysis'), 'decisions': spec['decisions'],
            'spec_sha256': fingerprint(spec), 'execution_authorized': False,
            'model_ready': False, 'writes_performed': False}


def review_parent_proposal(envelope: ParentEnvelope, proposal: dict, corpus: Corpus, *,
                           expected_envelope_id: str, current_spec: dict,
                           current_parent_commit: str, current_resource_pin: str,
                           manifest_path: Path = DEFAULT_MANIFEST) -> dict:
    """Validate a response against unchanged context and return advice only."""
    if envelope.envelope_id != expected_envelope_id:
        _fail('parent_context', 'Response envelope binding is stale or differs.')
    bound = envelope.as_dict()
    rebuilt = bind_parent_request(current_spec, bound['request'], corpus,
        parent_commit=current_parent_commit, resource_pin=current_resource_pin,
        package_bindings=bound['package_bindings'], manifest_path=manifest_path)
    if rebuilt.envelope_id != envelope.envelope_id:
        _fail('parent_context', 'Parent context changed after request binding.')
    result = validate_proposal(proposal, bound['request'], corpus)
    return {**result, 'envelope_id': envelope.envelope_id, 'parent_version': bound['parent_version'],
            'spec_sha256': bound['spec_sha256'], 'resource_pin': bound['resource_pin'],
            'workflow': bound['spec']['workflow'], 'analysis': bound['spec'].get('analysis'),
            'decisions': bound['spec']['decisions'], 'application_authorized': False,
            'fixture_only': bound['fixture_only']}
