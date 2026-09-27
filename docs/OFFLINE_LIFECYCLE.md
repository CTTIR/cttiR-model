# Metadata, evaluation and local release lifecycle

## Exact model metadata

`cttir-model models resolve --config configs/cpu.json` fetches **only** a fixed
allowlist of small public metadata files, each at most 512 KiB. It resolves the
Hub revision first and fetches metadata at that immutable SHA. There is no
weight-download code or remote Python execution. `--dry-run` performs no network
access. Metadata inspection is separate from approval or training compatibility.

The inspected revisions are recorded in `data/manifests/models.json` and configs:

| Role | Revision |
|---|---|
| Devstral Small 2 24B supervisor | `55c5b41e98c2dbd21b0c8afffc540dcfc9eb5128` |
| Ministral 3 8B specialist | `5b26027e7b19eeb4b7352e1fed3926375dd2cb4d` |

Both declare `Mistral3ForConditionalGeneration` and FP8 quantization. The
specialist metadata is approximately 56 KB and supervisor metadata 97 KB,
excluding the small API file lists. Source metadata hashes, upstream filenames
and sizes are recorded. Separate LICENSE files were absent in the inspected
allowlist; card license declarations do not close the legal gate. Actual
tokenizer loading, effective-base reconstruction, adapter targets, gradients,
conversion and serving compatibility remain unverified.

CPU training helpers validate supplied assistant-token masks, exclude source
and padding tokens, reject all-masked/overlength cases and compare eight resume
identity hashes. They do not implement a trainer or prove that the actual model
template supplies correct masks. `train` stays deferred for every profile.

## Offline evaluation

`benchmark freeze --config FILE --input FILE` consumes a version-1 object with
`benchmark_id`, `fixture_only`, and cases containing `case_id`, `group_id`,
`supported`, and a complete `request`. It pins the corpus and scoring policy
and writes a content-addressed local benchmark. This provides integrity, not
external access control for the sealed test set.

`evaluate --config FILE --candidate RUN_ID --benchmark FROZEN.json --records RUN.json`
scores saved model outputs. It never generates predictions. A run contains:
run_id, arm (A/B/C/D), fixture_only, benchmark_sha256, effective_base_fingerprint,
corpus_id, generation_config_sha256 and records. Each output row has case_id,
proposal (JSON object or raw JSON string), latency_ms and review (null or a
record-bound reviewer annotation). See `tests/test_evaluation.py` for a complete
small synthetic example of the data structures.

Review fields are reviewer, output_sha256, api_correct, scientific_pass,
task_pass and critical_violation. The output hash binds benchmark hash, case ID
and original proposal. Missing review is unknown and cannot earn task success.
Imported annotations are not authenticated human identities or proof that code
ran. Separate R execution evidence and scientific review remain necessary.

Metrics include raw schema validity, evidence constraints, supported-task/API
success, abstention precision/recall, review coverage, critical violations and
latency. Universal refusal earns zero supported-task success. Every case must
appear exactly once, including failures. Comparison with `--baseline REPORT.json`
requires identical corpus, effective base, benchmark and generation settings.
It uses 200 deterministic paired group bootstrap resamples, requires at least
20 groups for statistical gain support, and still leaves regression review and
release qualification pending. Small/fixture benchmarks never establish a model
improvement claim. A frozen scoring policy cannot be lowered retrospectively.

## Local release integrity and rollback

`release validate --config FILE --manifest PAYLOAD/release.json` checks the
original release contract, strict file allowlist, containment/symlinks, duplicates,
sizes/hashes, common credential/template markers, mandatory gate references and
matching base/adapter/evaluation provenance. The laptop limit is 64 MiB per
payload. This is an integrity check of trusted review artifacts; it does not
load tensors, authenticate reviewers, execute the consumer script or independently
reproduce G03–G13. Test payloads are temporary unit-test fixtures, never models.

`release prepare --config FILE --run RUN_ID` expects a real qualified manifest
and files in `artifacts/runs/RUN_ID/`, plus the exact configured HF destination
and visibility. It copies only allowlisted files into an atomic local payload,
then rechecks them. Missing targets or any unresolved mandatory gate blocks it.
No candidate exists here, so there is currently nothing that can legitimately
be prepared or published. `release publish` remains disabled.

`release activate --config FILE --manifest PREPARED/release.json` and
`release rollback --config FILE` preview a coherent local routing pointer.
Only `--apply` changes that pointer under an advisory single-writer lock. Both
revalidate payload hashes; rollback refuses corrupt prior artifacts and preserves
the active pointer on failure. No process starts, inference backend hot-load or
claim of live model readiness occurs. Real serving cutover needs a later loaded
candidate self-test and deployment adapter.

`update --target corpus --source FILE --dry-run` validates a prospective snapshot
without writing. Removing `--dry-run` stages it without activating or modifying
pinned configs. `update --target registry` refreshes only metadata at configured
immutable revisions; it never upgrades models, libraries, corpus pins or weights.
To inspect a new model revision, use a separate explicit config.

`audit` reads local corpus hashes, configured revisions, pinned parent contracts
and ledger integrity without network or mutation. Missing model/scientific gates
remain pending. Local records are evidence to inspect, not automatic approval.
