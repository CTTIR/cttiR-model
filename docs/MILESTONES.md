# Implementation milestones

## 1 — CPU foundation

Installable `cttir_model` package and `cttir-model` CLI; bundled Draft 2020-12
contracts; strict offline configuration; bounded JSON input; canonical hashes;
atomic artifact writes; lightweight preflight; explicit deferred lifecycle
commands; CPU unit tests. Configuration adds a mandatory `execution` policy
to the original config contract. Request/response/training/release wire schemas
remain unchanged.

The source bundle is identified in `bundle-source.json`. Local extraction passed
its structural and SHA-256 checker. Full instructions remain in ignored admin.

## 2 — Local evidence and dataset safeguards

Implemented immutable corpus snapshots, exact-version lexical retrieval,
server-owned evidence checks, and reviewed dataset/split validation using
small synthetic fixtures. Draft examples, stale reviews and overlapping splits
are rejected. Training build outputs omit test/development records. See
`CORPUS_AND_DATA.md` for commands and format boundaries. Production corpus
approval, full native R extraction and scientific validation remain pending.

## 3 — Local service and R client

Implemented loopback HTTP health/specialist/consult/cancellation endpoints,
one-operation admission, duplicate-ID handling, bounded schema repair, immutable
validated proposal returns and explicit fixture mode. Added the R HTTP client
and real local HTTP/R integration tests. No model is loaded or called.
See `LOCAL_SERVICE.md`. Real model orchestration still requires later GPU gates.

## 4 — Isolated R checks and candidate source review

Added real parse-only AST inspection, fixed synthetic R fixtures and isolation
checks in resource-limited bubblewrap workers. Added safe small R-source archive
ingestion with native Rd parsing, provenance and candidate-only review queues.
No arbitrary user R execution or automatic source approval is enabled.
See `R_VALIDATION.md` for limits and explicit sandbox tests.

## 5 — Parent package alignment

Fetched/pulled the clean cttiR checkout and inspected version 0.0.2 at commit
03ecc04. Its actual APIs and schemas are pinned in a public contract snapshot.
The read-only parent adapter preserves scientific unknowns and approvals,
requires exact source/package/resource pins, binds immutable context, and rejects
stale responses. It does not invent an existing provider hook or approve a
workflow. See `CTTIR_ALIGNMENT.md`; scaffold-only fallback remains explicit.

## 6 — Offline lifecycle tooling

Resolved actual immutable model revisions with small metadata downloads only.
Implemented CPU loss-mask/resume checks, frozen benchmark and saved-output
evaluation with grouped comparisons, read-only integrity audit, safe staged
updates, local release validation/preparation and atomic pointer rollback.
These tools require genuine reviewed artifacts before release and cannot
substitute for training or loaded-model tests. See `OFFLINE_LIFECYCLE.md`.

## 7 — Local book knowledge

Copied and hash-verified the three supplied PDFs into gitignored `ressources/`.
Indexed their 943 available pages into 1,180 local page-cited text chunks using
bounded serial extraction; added local search and a provenance-bound training
preparation plan. The Moscarelli file contains only 13 front-matter/contents
pages, so its substantive chapters remain unavailable. Actual model training
and approval of derived training examples are still deferred.

## Deferred work

Verify FP8 training compatibility and an effective base; provision a tested
GPU environment; obtain approved production R documentation and independently
reviewed examples; freeze a real benchmark; implement and execute genuine
baseline, adapter training and save/reload; connect real model endpoints and
consumer reconstruction. Extend R metadata/execution adapters only with reviewed
package-specific support. cttiR itself needs a separately implemented provider
extension before this client can integrate into its public workflow.

Do not run these workloads on this laptop. Training and download switches are
schema constants set to false, so a profile edit cannot accidentally start them.
The GPU trainer is not implemented yet: reserved commands are not runnable GPU
job specifications. No training-runtime version or compatibility is claimed.

Milestone 1 validation: 11 unit tests passed in the isolated Python 3.14.4 environment;
editable package installation and preflight succeeded. Dependencies are pinned
in `requirements-cpu.lock`. Preflight observed approximately 14.8 GiB RAM;
the NVIDIA probe was unavailable. This is not a hardware training qualification.

Milestone 2 adds unit and installed-CLI integration tests for evidence and data.
Run `python scripts/check_cpu.py` to regenerate the exact current results and
local gate JSON. G01 passes for local inventory/CPU policy only. G02 has partial
CPU evidence; full lifecycle readiness is pending. G03–G14 remain pending. Model
publication requires a later explicit action and a concrete qualified payload.
GitHub software milestones are pushed directly to main as requested.
