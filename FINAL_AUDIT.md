# Initial CPU milestone audit

This is a review of the initial software milestones, not the final model audit
requested by the full prompt stack. No trained candidate, baseline score,
improvement result, executable R validation or release-qualified model exists.

Implemented: strict configuration and original protocol schemas, lightweight
preflight, atomic artifacts and phase ledger, bounded immutable corpus import,
exact-version local retrieval, evidence-bound proposal checks, reviewed dataset
validation, split leakage checks and train-only dataset builds. All model-facing
lifecycle operations remain explicit deferred errors. There is no inference
server, GPU trainer or remote model upload implementation yet.

The CPU policy rejects enabling training/downloads, cloud fallback and non-local
endpoints. No heavy framework is installed by this project. All tests use small
synthetic fixtures; no model weights, private datasets or R documentation were
downloaded. Python dependencies total approximately 2 MB of wheel downloads
for the initial isolated environment, excluding existing Python/pip tooling.

Focused checks cover wrong corpus/package pins, altered content, unapproved
sources, invented evidence, client/model verification fields, unvalidated R code,
draft records, stale review hashes, family/near-duplicate leakage, corrupted
snapshots, atomic-write failure and accidental execution of deferred commands.
The installed-wheel test suite contains 35 passing tests, completing in about
one second on the laptop. Dependency consistency and package installation also
passed. GitHub CI status is recorded by the repository's CPU workflow.
These tests do not establish scientific validity or prompt-injection resistance
of a future model service. Corpus text is treated as data and never executed.

Remaining findings:

| Severity | Finding | Next action |
|---|---|---|
| Blocker for training | Exact effective base and FP8 compatibility unverified; GPU work intentionally deferred | Resolve checkpoint metadata, then run real backward/save/reload on suitable hardware |
| Blocker for training | No approved production corpus or reviewed dataset supplied | Implement native/parent corpus adapter and obtain documented review |
| Blocker for serving | Broker, R sandbox/client and real endpoints pending | Implement bounded local service and isolated R validators |
| Blocker for release | No trained/evaluated adapter, consumer reconstruction or owned HF target | Complete G03–G13 before any model publication |
| Major limitation | Review registry uses local attestations, not authenticated reviewer identities | Add review workflow and attach independently inspected execution/science artifacts |
| Major limitation | Lexical duplication checks can miss paraphrased leakage | Seal held-out families and perform independent review |
| Minor limitation | JSON corpus is a bounded initial adapter, without native R extraction or SQLite coverage catalog | Extend ingestion while preserving hashes and version filtering |

Run `.venv/bin/python scripts/check_cpu.py` for actual current test output and
`artifacts/implementation/gates.json`. The ledger retains source/config hashes,
commands and results. It is intended for one local writer. Detailed local paths
and raw runtime inventory stay ignored. The `audit` CLI reports the conservative
project-wide pending state; the check script records completed local evidence.

GitHub software milestones are authorized for direct pushes to main. This does
not publish model artifacts. Model-release payload generation is deferred
because no adapter or qualifying evidence exists; there is no valid publish
command to run yet. See [milestones](docs/MILESTONES.md) and
[local evidence/data commands](docs/CORPUS_AND_DATA.md) to resume development.
