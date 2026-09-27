# Local evidence and dataset interfaces

This milestone implements a small normalized JSON corpus adapter. It does not
yet extract Rd files, vignettes or S3/S4/S7 metadata from R packages, import the
parent resource database, or establish real source rights. G04 remains pending.
The size limit is 2 MiB by default, with at most 1,000 documents or data records.
No indexing command fetches source URLs or executes documentation.

## Try the synthetic fixture

```sh
cttir-model corpus ingest --config configs/cpu.json --source data/fixtures/corpus.json
cttir-model corpus search --config configs/fixture.json --query fixtureR::align --package fixtureR --version 1.0 --repository synthetic
```

`fixtureR` is invented test data. Its documents are marked approved **within
the fixture only**; `fixture_only: true` prevents this snapshot from qualifying
a dataset. The examples demonstrate incompatible versions, not actual R APIs.

For a reviewed real export, follow `src/cttir_model/schemas/corpus.schema.json`.
Each document contains full content and SHA-256, package/version/repository,
symbol/signature, source locator/revision, license and separate rights/review
states. The importer verifies shape and hashes and requires at least one
approved document. It cannot establish whether external review assertions
are truthful. Candidate or rights-pending documents remain excluded.

Ingestion writes a content-addressed immutable JSON snapshot under
`artifacts/corpus/`. The returned `snapshot_id` is `sha256:` plus the canonical
JSON digest. Set `corpus.path` and `corpus.snapshot_id` explicitly in a local
config to activate that snapshot. Ingestion never changes config or an active
pointer. Keep earlier snapshots for pinned projects. A failed import leaves
them untouched. A corrupt existing snapshot is refused, not overwritten.

Retrieval filters exact package/version/repository **before** ranking. Exact
symbols have priority over lexical term matches. It returns complete documents
within a character budget; oversized documents are omitted, not truncated.
Production ingestion will need section-level chunks to avoid omission of long
topics. Source timestamps should be recorded separately from immutable content.

`protocol.validate_request` binds evidence to server-owned records and rejects
wrong corpus/package pins. `validate_proposal` checks request identity, evidence
subsets and schema; it rejects executable code until a deterministic R validator
exists. These are library functions, not a deployed broker or inference service.

## Dataset checks

The input is a JSON array of original `training-record` contract records.
Review status must be `reviewed`, rights `approved`, split assigned, and data
synthetic. Corpus/evidence pins must resolve and the final assistant JSON must
match the expected response. Positive proposals need approved evidence.

Each record needs a separately maintained registry entry for its rights source
and validation result. Registry format:

```json
{
  "schema_version": 1,
  "sources": [
    {"id": "source-id", "rights_status": "approved", "license": "actual license",
     "reviewer": "reviewer identity", "record_sha256": "64-character canonical record hash"}
  ],
  "validations": [
    {"id": "validation-id", "status": "passed", "reviewer": "reviewer identity",
     "record_sha256": "64-character canonical record hash"}
  ]
}
```

This illustrative registry is not a valid approved artifact. Compute each hash
with `cttir_model.provenance.fingerprint(record)` after reviewing the final
record, including split assignment. A later record change invalidates review.
Review registries are local attestations, not cryptographically authenticated
identities or proof that the R/scientific validation actually happened.

```sh
cttir-model data validate --config artifacts/local-config.json --input artifacts/reviewed-records.json --registry artifacts/reviews.json
cttir-model data build --config artifacts/local-config.json --input artifacts/reviewed-records.json --registry artifacts/reviews.json
```

Both check the complete supplied dataset for family overlap, normalized duplicate
prompts and cross-split near duplicates. Near duplicates use a fixed 0.8 Jaccard
threshold on word trigrams. Paraphrases can evade this check; independent leakage
review and sealed benchmark storage remain necessary. `build` writes only train
records, plus an aggregate manifest. It never copies test/development answers into
the training payload. It does not generate examples or auto-assign review/splits.

Paths in a config resolve against its directory (or the parent repository when
stored under `configs/`). Keep private records, review identities and source
material in ignored `artifacts/` or an external private location. MIT software
licensing does not approve any corpus or training source.
