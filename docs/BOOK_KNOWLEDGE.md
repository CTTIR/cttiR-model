# Local book knowledge and future training inputs

The configured `knowledge.book_library` is `ressources/`, which is gitignored.
Its manifest, PDFs, extracted text chunks and training preparation plan remain
local. Source copies were verified by SHA-256 against the supplied files.

| Supplied PDF | Available PDF pages | Indexed text chunks |
|---|---:|---:|
| An Introduction to Statistical Learning with Applications in R, second edition | 616 | 822 |
| R Programming: Statistical Data Analysis in Research | 314 | 340 |
| Biostatistics With R: A Guide for Medical Doctors | 13 | 18 |

The third file contains front matter and contents only. Its substantive chapters
are missing; the local training plan marks it `awaiting_body_chapters`.

```sh
cttir-model books ingest --config configs/cpu.json
cttir-model books search --config configs/cpu.json --query "cross validation" --limit 3
cttir-model books training-plan --config configs/cpu.json
```

Ingestion is serial, resumable and idempotent for unchanged source manifests.
It performs text extraction only, never OCR, embeddings or model inference.
Each low-priority Poppler process is capped at 512 MiB address-space, ten CPU
seconds, fifteen wall seconds and 16 MiB output. This machine successfully
indexed all 943 available pages into 1,180 page-bound chunks without a model.
Original PDFs remain unchanged. This is text extraction, not visual validation
of every page, formula, table or figure.

Every chunk records the original PDF hash, title, PDF page (not printed page
number), character offset, text hash and immutable chunk ID. Search is local
lexical retrieval. Chunks are unreviewed book knowledge, never verified package
function evidence. The package corpus and cttiR approval/version constraints
retain precedence for executable suggestions. The current broker protocol is
unchanged; books are available through the separate retrieval interface for
future model/training integration, not silently injected as approved R APIs.

The user requested these sources for training as well as a knowledge base.
`ressources/training-plan.json` registers that intent, all source/index hashes
and grouping lineage. The training recipe is to derive original supervised
tasks grounded in reviewed passages, attach PDF-page provenance through each
record's source-review manifest, validate R APIs against exact approved package
versions, and keep book/chapter/template families separated before test sealing.
This plan creates no examples automatically and reports `training_ready: false`.
Actual model training remains deferred on this laptop.

Book-derived prompts/datasets stay local by default; the source registry keeps
rights review and redistribution separate from the user's requested use. Neither
the public code license nor indexing marks books or derived model artifacts
approved for public redistribution. Release preparation's strict allowlist
cannot accidentally copy the library into a model payload.
