# Laptop implementation audit

The laptop-side tooling is implemented and smoke-tested. No trained candidate,
real-model benchmark, demonstrated model improvement or release-qualified adapter
exists. Training, weight acquisition, real inference and remote model publication
remain disabled. The GPU trainer itself still needs implementation against a
verified checkpoint/backend; the CPU checks are not a substitute.

## Delivered and verified

- Installable Python package, strict contracts, preflight, atomic artifacts and
  resumable phase ledger; all 77 installed-wheel tests passed in 4.20 seconds,
  including the local HTTP, R client and isolated R tiers, with no skipped tests.
- Loopback broker with bounded admission, cancellation, duplicate-ID handling,
  one repair retry and unchanged validated proposal returns. Real HTTP tests use
  explicit deterministic fixtures, never model inference.
- Thin R client tested against the live local fixture service. R 4.6.1, curl 7.1.0
  and jsonlite 2.0.0 were already installed; the generated R lock records them.
- Real R parser/AST checks and two fixed synthetic invariants inside bubblewrap.
  Isolation tests passed: no home directory, inherited canary credential or host
  network routes. Workers use one BLAS thread, five CPU seconds, eight wall
  seconds, 1 GiB address-space and bounded output. These are limits, not measured
  peak consumption. Supplied R code is parsed, never evaluated.
- Bounded archive/Rd ingestion into candidate-only source review; immutable
  local lexical retrieval; dataset rights/review hashes and split-leakage checks;
  train-only build output excludes held-out answers.
- cttiR fetched and pulled cleanly at 0.0.2 / `03ecc04bd86e3b6f03d3df2a5c42ab1265628f58`.
  Exact public schemas/APIs are pinned; adapter tests preserve unknowns, approvals,
  workflow readiness and exact package/resource/evidence revisions. Parent code
  was inspected, not modified. Its own test suite was not rerun.
- Actual supervisor/specialist revisions resolved through small public metadata
  fetches: about 153 KB of metadata files plus API manifests. Both declare FP8
  `Mistral3ForConditionalGeneration`. No weights were fetched or tensors loaded.
- CPU assistant-loss-mask and resume-identity checks; frozen benchmark manifests;
  offline saved-output scoring and paired group comparisons. Synthetic arithmetic
  cannot produce an improvement or release claim.
- Local release allowlist/hash/provenance checks, staged preparation and atomic
  routing-pointer rollback. Tests use temporary synthetic payloads only. No real
  payload exists; no consumer loader, serving cutover or publication was run.
- Read-only corpus/ledger/parent-pin audit and corpus/model-metadata update previews.
- Three user-supplied books copied and hash-verified into ignored `ressources/`.
  Bounded, low-priority text extraction indexed all 943 available pages into
  1,180 local chunks with PDF-page/source hashes. No OCR or embeddings ran.
  Book-grounded training intent is registered in a local preparation plan;
  the 13-page Moscarelli file contains only front matter/contents, not chapters.

The initial CPU Python dependency wheels were approximately 2 MB; subsequent work
added no model framework, GPU package or large corpus download. Tests are serial
apart from small local HTTP/cancellation threads. GitHub CPU CI uses hosted
runners; the Linux R sandbox tier is explicitly enabled and was run locally.

## Remaining gates and findings

| Gate/scope | State | Evidence or remaining dependency |
|---|---|---|
| G01 local preflight | Pass | Local inventory and CPU policy in ignored artifacts |
| G02 full implementation readiness | Pending | CPU tools pass; real training/inference backends remain deferred |
| G03 effective base | Pending | Exact source metadata pinned; real FP8 backward/save/reload unverified |
| G04 corpus coverage | Pending | cttiR has 229 candidates and zero verified function/workflow approvals; no approved production corpus |
| G05 training dataset | Pending | Review tooling works; no independently reviewed production examples |
| G06–G10 model/science evaluation | Pending | Scoring and small R fixtures work; genuine baseline/candidate/privacy/domain evidence absent |
| G11 real orchestration | Pending | Fixture broker works; real endpoints and token accounting untested |
| G12 supported runtime | Pending | Local R client/pointer rollback tested; model cold load/restart/cutover absent |
| G13 reconstruction/release | Pending | Integrity tooling implemented; no trained adapter, consumer load or completed rights review |
| G14 model publication | Pending | No concrete qualified payload or configured HF owner target; publishing disabled |

Blockers are the missing verified model backend/hardware, approved corpus,
independent data/scientific review and parent provider implementation. cttiR has
no existing provider or knowledge-export hook, and `standard_reflowR` is a
scaffold with execution integration pending. The adapter does not invent one.

Remaining implementation limits: R AST support is intentionally conservative;
S3/S4/S7 dispatch and Bioconductor/Seurat invariants need reviewed package adapters.
Rd candidates lack verified callable signatures. Human review registries and
release gate reports are trusted attestations, not authenticated identities or
independent reproductions. Lexical duplicate checks miss paraphrases. Local HTTP
is a development server, not a remote authenticated/TLS service. Effective-base
hash checks prove consistency of the supplied recipe, not that it can be loaded.

## Resume and evidence

```sh
.venv/bin/cttir-model audit --config configs/cpu.json
CTTIR_TEST_SANDBOX=1 .venv/bin/python scripts/check_cpu.py
.venv/bin/cttir-model serve --config configs/fixture.json --fixture
```

Full local test output and input hashes are in `artifacts/implementation/ledger.json`;
`gates.json` records the honest phase state. Preflight records the source commit
and dirty state at validation, so uncommitted validation is not misrepresented as
a different source revision. Admin instructions, detailed inventory and all run
artifacts remain ignored. Source milestones are committed/pushed directly to main.

Use the linked guides for exact input formats and commands:
[cttiR alignment](docs/CTTIR_ALIGNMENT.md), [R validation](docs/R_VALIDATION.md),
[local service](docs/LOCAL_SERVICE.md), [offline lifecycle](docs/OFFLINE_LIFECYCLE.md).
