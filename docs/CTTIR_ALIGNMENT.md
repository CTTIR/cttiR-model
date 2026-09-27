# Alignment with cttiR

Inspected 2026-09-27: public package **cttiR 0.0.2**, commit
[`03ecc04bd86e3b6f03d3df2a5c42ab1265628f58`](https://github.com/CTTIR/cttiR/tree/03ecc04bd86e3b6f03d3df2a5c42ab1265628f58).
All configured remotes were fetched with pruning; the clean `main` checkout was
already current after `git pull --ff-only`. `origin/main` is the only remote
branch. No parent implementation was changed. The machine-readable contract and
source SHA-256 hashes are in [cttir-parent.json](../data/manifests/cttir-parent.json).

## Actual public surface

| API | Current behavior and integration boundary |
| --- | --- |
| `project(name, type, goal, path, config, options, dry_run)` | Deterministic offline scaffold. `path` is an existing parent directory; the builder chooses a child slug. Required arguments override config; options override config. Creation defaults to writing, so an integration preview must explicitly use `dry_run = TRUE`. |
| `validate_config(config)` | Named list or local YAML/JSON; rejects unknown fields, duplicate identities, executable YAML and malformed values. |
| `validate_spec(spec)` | Resolved schema plus unique IDs, portable slugs and conservative analysis approval prerequisites. |
| `resources(query, domain, repository, path, limit)` | Read-only candidate metadata query; a project path requires its exact resource pin. No dependency installation or API verification. |
| `sync(path, config, options, dry_run)` | Defaults to preview, preserves identity and user files, reports managed-file conflicts; application backs up files and rolls back caught failures. Workflow/dependency migration is unsupported. |
| `audit(path, scope, repair, output, strict, live)` | Local integrity report; missing managed-file repairs require matching baselines. Live inference probes are unimplemented and remain unverified. |
| `doctor(path)` | Brief read-only audit. |

There is **no model provider registration interface, inference API or knowledge
export function** at this revision. The separate `r/client.R` in this repository
is therefore a preparatory client, not an installed cttiR integration.

Source basis: `NAMESPACE`, `R/*.R`, generated `man/*.Rd`, `README.md`, schemas and
the public tests at the pinned revision. Parent test sources cover input
validation, offline/idempotent scaffolding, edited files, traversal/symlinks,
resource pinning, sync conflicts/rollback and baseline repairs. Its published
development state reports 131 local assertions and an R check with no errors or
warnings; those checks were not rerun for this inspection, and this report does
not independently certify them or hosted CI.

## Contracts to preserve

The parent uses draft-07 schema version 1 with closed objects. Project types are
`primary_research`, `secondary_research`, `methods`, `review`, `software`, `mixed`
and `other`; languages are `en` and `de`. Lists of publications/data sources merge
by ID; packages merge by name. Project IDs and timestamps are builder-owned.
Configuration is bounded to 1 MiB and 32 nesting levels. Model transport has a
smaller request bound and needs its own checked conversion.

The standard profile is `standard_reflowR` with `project_backend = reflowR`, but
the implementation only produces a scaffold and explicitly reports reflowR
integration pending. No workflow is executed. Pipeline/environment/table backend
are `none`, reporting is `generic`, environment preparation/Git initialization
are false, and readiness is `scaffold_ready`. Unsupported options fail with
`cttir_api_mismatch` rather than silently degrading.

Keep scientific unknowns unknown: analysis aim/unit structure, research role,
data origin and ethics status are not supplied by model confidence. The parent
requires known aim and unit structure for analysis approval, but that structural
check is not scientific validation. Proposals must never set approval, ethics or
readiness automatically. Preserve accessible figure policy (viridis/cividis,
RColorBrewer, redundant encoding, patchwork and colour-vision checks) and the
ecosystem requirement for role approval.

Parent errors inherit `cttir_error` and carry `code`, `field` and `remediation`.
The client currently has `cttir_model_error`; a future parent adapter must map
errors deliberately without swallowing integrity or schema failures.

## Knowledge and provenance

The bundled snapshot contains 229 candidates, 229 observations, 449 evidence
records, 6,630 dependency records, 33 relationships and 10 profiles. It has
**zero verified function records and zero workflow approvals**. Its 13 documents
and 13 chunks are original research summaries explicitly labeled as non-API
evidence, with no full source documents stored. Snapshot content ID:
`sha256:122877f9677cfa5a42b3722301dc0c1d8a534847ca3746078d7db9ef165b5381`.

Do not feed this catalog directly into the model's approved corpus: that schema
requires symbols, signatures, concrete package versions, source revision,
license and separate rights/review approvals. None of those missing guarantees
can be invented from metadata retrieval status. A future exporter must join
package/observation/document/function records, retain source hashes and rights,
and reject unresolved or unapproved entries. Public cttiR source and reference
docs can be curated separately at this exact commit under its MIT license;
that does not approve the external candidates' APIs.

`resource_snapshot` pins candidate metadata; `catalog_id` currently says
`unavailable`. Neither is automatically the model's normalized corpus ID. The
parent build lock has `model = NULL`; project provenance starts deterministic
with null model identity/digest. Preserve these values unless an actual, reviewed
model operation and explicit provenance mapping justify a change.

## Gaps and implementation order

| Gap | Required handling |
| --- | --- |
| No parent provider hook | Keep transport opt-in and separate; add a reviewed parent adapter later without changing the three required project arguments or making ordinary creation call the network. |
| Parent packages allow null version and carry `revision`/`source`; model pins require concrete `version`/`repository` | Reject incomplete pins; explicitly resolve repository semantics and retain the revision. Do not substitute a version or discard provenance silently. |
| Parent spec holds workflow, scientific constraints and figure policy; model input only has columns/classes/unit | Define a versioned context bridge. Until available, unsupported conversions must return missing-input/unsupported results rather than lose constraints. Data registry entries do not establish measured columns or R object classes. |
| `select_workflow` response has summary text but no structured profile/backend selection | Treat it as advice only. Before application, add a versioned structured proposal validated against parent enums, supported adapters and approvals; never parse a prose summary into an executable choice. |
| Corpus IDs and resource IDs differ | Record explicit immutable mappings with source hashes and reviewed evidence. Missing evidence remains `needs_input`. |
| Parent disallows workflow/dependency changes in `sync()` | A model response cannot bypass that restriction. Require a future supported migration API. |
| Offline scaffold and model availability are separate | Unavailable/unsupported inference leaves the deterministic scaffold and its pending blockers intact. Do not call this successful reflowR execution. |
| Different error hierarchies | Map transport failures to typed parent conditions at the adapter boundary, preserving diagnostics without exposing raw private request text. |

Laptop-safe next steps are drift checks against the committed snapshot, small
contract fixtures, schema conversion tests, explicit refusal tests for missing
versions/unapproved evidence, and offline fallback tests. Real model inference,
large documentation extraction, training and broad adapter execution remain
deferred. No package installs, R builds, model downloads or compute-heavy tests
were performed for this parent inspection.

## Adapter envelope and synthetic fixtures

Keep protocol v1 unchanged. A separate validated adapter envelope should carry
the parent commit/version, validated resolved specification, build-lock resource
pin and the caller's approved model context. This envelope is not a new parent
configuration key: closed parent schemas would reject arbitrary provider fields.

| Model field or adapter state | Source and conversion rule |
| --- | --- |
| Resolved specification | `project(..., dry_run = TRUE)$spec` for a preview, or `validate_spec("cttir-project.yml")` for an existing project. Neither call establishes full runtime readiness. |
| Parent resource pin | Read `cttir-lock.json` separately for an existing project; `resources(path = project_root)` verifies availability. `project()` returns no lock field. A dry-run preview has no project lock on disk. |
| `language` | Validated `spec$project$language`. |
| `instruction` and `task` | Explicit caller instruction and one of the model task enums. `spec$project$goal` can inform a reviewed instruction but cannot establish the requested operation by itself. |
| `package_pins` | Explicit reviewed concrete pins, checked against relevant `spec$packages` identities/revisions. `resources()` observations are candidates, not validated installed dependencies. Empty packages remain empty; null versions must not become an invented version string. |
| `corpus_id`, `evidence_ids` | Explicit selected approved corpus and evidence; no current parent public API supplies these. `spec$decisions$evidence_ids` are empty by default. |
| `input_contract` | Explicit reviewed metadata. `spec$data_sources` describes registry entries, not measured columns/classes. `analysis$unit_structure` describes dependence and is not itself an experimental-unit identifier. |
| `request_id`, `budget` | Adapter-generated unique request identity and bounded caller policy; neither is a parent project ID or workflow readiness claim. |
| Parent constraints | Retain workflow/analysis/research/figure/ecosystem constraints in the outer envelope; validate any future structured workflow choice against supported parent behavior before application. |

Derive small fixtures from public examples and schema defaults:

1. Offline baseline: `project("Example Study", "primary_research",
   "Describe longitudinal measurements", path = tempdir(), dry_run = TRUE)`.
   Assert `packages` and `data_sources` are empty, analysis approval is false,
   `standard_reflowR` is pending and no network/model call happens on creation.
   Replace dynamic UUID/timestamp/path with clearly synthetic values when storing
   a fixture; do not assert exact generated identities.
2. Language and explicit scientific context: the same preview with
   `options = list(project = list(language = "de"), analysis = list(aim =
   "descriptive", unit_structure = "longitudinal"))`. Assert language maps to
   `de`, approval remains false and an experimental-unit identifier is still
   required from the caller.
3. Unresolved package: copy the validated baseline spec and append a complete
   schema-valid package row with `version = NULL`, synthetic `revision`, `source`,
   empty `evidence_ids` and `required = FALSE`. Parent `validate_spec()` permits
   the structural null; the model adapter must reject conversion. Do not pass
   nonempty packages to `project()` and claim successful foundation support.
4. Candidate-only evidence: reference one seed research-note chunk without API
   verification. Assert it cannot be promoted to an approved function reference,
   and the request returns missing-input/unsupported rather than fabricated code.
5. Unavailable service and fixture service: assert that both preserve original
   parent readiness, approval, identity and pins; fixture responses must remain
   visibly synthetic and must not be recorded as real model provenance.
6. Unsupported workflow change: propose a specialist profile or dependency
   migration and assert that the adapter cannot apply it through current `sync()`.
   A valid JSON proposal alone must not authorize a project write or R execution.

## Implemented local adapter

`cttir_model.parent` validates the pinned parent schema and semantic ID/slug and
analysis-approval constraints without loading R. It exposes:

```python
validate_parent_spec(spec, manifest=None)
fallback_plan(spec, *, manifest_path=DEFAULT_MANIFEST)
bind_parent_request(spec, request, corpus, *, parent_commit, resource_pin,
                    package_bindings, manifest_path=DEFAULT_MANIFEST)
review_parent_proposal(envelope, proposal, corpus, *, expected_envelope_id,
                       current_spec, current_parent_commit, current_resource_pin,
                       manifest_path=DEFAULT_MANIFEST)
```

Binding returns a frozen `ParentEnvelope` with `envelope_id`, `request` and
`as_dict()` accessors. Its canonical serialized contents preserve the entire
parent specification, version, commit, resource pin and explicit v1 request;
accessors return copies. The hash binds context but is not a signature or proof
that a user approved it. Trusted callers must retain the expected envelope ID.

Each selected package requires an explicit four-field binding (`name`, `source`,
`revision`, `repository`). Source/revision must match the parent package row,
repository/version must match the request pin, and each cited evidence document's
revision must match. Missing versions and candidate evidence fail closed. This
explicit mapping does not assert that a dependency is installed or executable.

Response review rebuilds the binding from current parent state, rejects changed
context and mismatched request IDs, and returns advice with application disabled.
The original model protocol stays unchanged. Code-bearing proposals are rejected
by this conservative path; it does not execute R or apply workflow changes. Parent
approval/readiness values remain unchanged, including explicit existing approvals.
The adapter neither validates scientific appropriateness nor grants new approval.

`fallback_plan()` only describes supported offline scaffolding, or reports an
unsupported selection; it does not create a project or start reflowR. A missing
approved corpus can use this plan without constructing an inference request.
The default snapshot path is relative to the source checkout; callers outside a
checkout must supply a deployed, trusted `manifest_path` explicitly.
