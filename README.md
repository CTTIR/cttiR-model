# cttiR-model

CPU-first implementation of the CTTIR Mistral specialist project. The intended
architecture pairs a Devstral supervisor with a Ministral R-domain specialist
and approved, versioned documentation. **No trained model exists in this repo.**

The laptop profile disables model downloads, model execution and training.
There are no PyTorch, Transformers, CUDA or embedding dependencies in the CPU
environment. Commands do not provision cloud resources.

## Local setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-cpu.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/cttir-model preflight --config configs/cpu.json
.venv/bin/cttir-model audit --config configs/cpu.json
```

Run `.venv/bin/python scripts/check_cpu.py` to retain local test evidence,
preflight, a resumable implementation ledger and the full gate matrix under
ignored `artifacts/`. The test suite runs serially and requires no network.

`preflight` only reads lightweight system metadata and writes ignored local
evidence under `artifacts/`. It runs no workload benchmark. `audit` is read-only
and reports pending project gates. Schema shape validation is not scientific,
training or release approval.

Available laptop tooling:

- [Local broker and R client](docs/LOCAL_SERVICE.md), with explicit fixture mode.
- [Isolated R parsing and small source imports](docs/R_VALIDATION.md).
- [Evidence and dataset review](docs/CORPUS_AND_DATA.md), without automatic approval.
- [Pinned cttiR package alignment](docs/CTTIR_ALIGNMENT.md).
- [Local book knowledge and training preparation](docs/BOOK_KNOWLEDGE.md).
- [Metadata, saved-output evaluation, release integrity and rollback](docs/OFFLINE_LIFECYCLE.md).

Training, model inference and publication remain deferred. Unimplemented
operations return JSON with `status: deferred`
and exit code 3; invalid inputs return exit code 2. They never pretend that a
training or inference run succeeded. `update --dry-run` validates/stages no
persistent changes. Metadata resolution is an explicit small network operation;
offline tests and user requests do not fetch model files.

See [milestones](docs/MILESTONES.md) for current scope and next steps. The
original ZIP and extracted instructions stay in ignored `admin/`; schemas and
synthetic format examples are copied into the package and `data/fixtures/`.
These examples are **drafts, not reviewed training data**.

Software is MIT licensed. Model, corpus, training-data and derived-weight
licenses require their own recorded review. No upstream weights or manuals
are included.
