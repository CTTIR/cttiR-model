# Public readiness audit — 2026-10-30

Scope: the CPU contracts, provenance, local fixture broker, review and release
integrity toolkit at `4426180083dcb34ffae34b2f5cb7867419675595`.
There is no trained model. Private books, corpora, training and publication are
outside this audit. The original checkout is preserved in a separate worktree.

## Baseline and findings

Python 3.14.4 on macOS ARM64, installed wheel and locked CPU dependencies:
77 tests ran in 1.367 seconds, 72 passed and five explicitly Linux-only sandbox
tests skipped. The live fixture broker/R client integration passed. `pip check`
passed. These results do not verify Linux isolation or inference.

| Finding | Evidence and impact | Priority |
| --- | --- | --- |
| Corpus objects retain mutable caller data and return internal documents | `corpus.py`: changing source content after construction changes retrieved evidence while its snapshot ID stays fixed. | Release blocker |
| Comparison trusts incomplete/edited report summaries | `evaluation.py`: two dictionaries with no benchmark identity or cases produce `gain_supported: true` for 20 invented groups. | Release blocker |
| Book training preparation omits source revalidation | `books.py`: a changed PDF still yields a preparation plan; requested-use metadata is not respected in its use label. | Essential repair |
| Audit claims local test evidence without reading any | `audit.py`: a fresh empty artifact directory reports that CPU tools have local test evidence. | Essential repair |
| Historical compatibility/setup documentation is misleading | README uses unqualified `python3` (Apple 3.9.6 here); parent docs describe a relative manifest although it is packaged; corpus docs omit implemented tooling. | Everyday use |
| R client trusts incomplete verification | `r/client.R`: it previously accepted a proposed response without checking `schema_valid`/`evidence_pins_valid` or requiring cited evidence. Malformed structured inputs could fail outside its typed error hierarchy. | Essential repair |
| Malformed metadata escapes typed validation | Release gate IDs/artifact lists and upstream model metadata could produce Python type errors; corrupt registry pointers lacked structural validation. | Essential repair |
| Build dependency advisories | setuptools 78.1.1 was flagged by the dependency audit; its manifest exclusion behavior matters when packaging on macOS. | Essential repair |
| Incomplete distribution contents | The wheel omitted the notice for bundled cttiR schemas; default source archives omitted setup/fixture resources. Explicit license files and a source manifest now preserve them. | Essential repair |

## Strategy and acceptance criteria

1. Preserve validated evidence across library boundaries. Copy corpus input and
   returned documents; reject changed book inputs and malformed indexes before
   writing any new plan. Validate with mutation, stale-content and reuse tests.
2. Make comparison evidence reviewable. Require complete scored-report identity
   and case results, recompute summary metrics, match paired cases and groups,
   and retain fixture/review/regression gates. Reject malformed or inconsistent
   reports with typed errors. Imported attestations remain unauthenticated.
3. Make readiness reports truthful. Bind recorded checks to the installed source
   and distinguish absent evidence from successful tests and platform skips.
   Exercise invalid CLI inputs and release metadata without tracebacks or raw
   private input in error output.
4. Verify distribution and first use. Build/install a fresh wheel outside this
   checkout, check packaged schemas/workers, run the full suite and live R
   client, inspect dependencies and CI, and document exact Python prerequisites.

Each milestone updates implementation, regression tests and documentation
together. Preserve the pinned historical cttiR contract; updating that contract
requires its own reviewed compatibility migration. A current parent package is
not silently substituted for the inspected snapshot.

Deferred: genuine reviewed corpus/model qualification, GPU training, Linux
sandbox execution on this Mac, remote service hardening and publication. The
stdlib HTTP server remains a loopback development fixture, consistent with
[Python's server guidance](https://docs.python.org/3.14/library/http.server.html).
Managed interpreter setup follows the
[uv Python installation documentation](https://docs.astral.sh/uv/guides/install-python/).

## Verification and handover

The repairs are implemented in version 0.1.1. Corpus state and retrieval results
are isolated, comparison summaries are checked against complete paired cases,
book preparation rechecks source hashes and requested use, and CPU test evidence
is bound to installed package bytes. Release/model metadata, local HTTP headers
and the R client reject the newly tested malformed inputs. The pinned historical
parent contract and scientific approvals are unchanged.

setuptools is pinned to 84.1.0 in both build requirements and the CPU lock.
The original dependency scan returned three entries for two distinct advisories:
[macOS manifest exclusions](https://github.com/pypa/setuptools/security/advisories/GHSA-h35f-9h28-mq5c)
and [legacy Windows wheel paths](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w).
The updated lock scan found no known vulnerabilities. This is a dated advisory
check, not a guarantee that every dependency is free of defects.

Local qualification includes Python 3.14.4 and 3.11.18, a clean installed wheel,
tests from the extracted source archive, and the live loopback broker/R client.
Both final suites (Python 3.14.4 and 3.11.18) ran 92 tests: 87 passed and five
explicit Linux-only sandbox tests were skipped. The 3.14.4 run used the
extracted source distribution and installed package; the 3.11.18 run used
the final wheel. Both included live R client and pointer-preservation tests.
Forty-two malformed CLI inputs returned exit 2 and bounded JSON errors, with
no traceback or synthetic canary exposure. Packaged parent contracts work
outside a checkout. Corrupt routing metadata remained unchanged after failure.
`pip check`, workflow syntax and whitespace checks passed.

The source archive now includes configs, fixtures, R client, test scripts and
the CPU lock needed to reproduce its checks. Wheel and source contents were
inspected; private `admin/`, `ressources/` and `artifacts/` paths are absent.
Complete raw evidence is retained in the local public-audit evidence directory;
no private books were accessed and no weights were downloaded.

First use: follow the Python 3.14.4 setup commands in README, then run
`.venv/bin/python scripts/check_cpu.py` and
`.venv/bin/cttir-model audit --config configs/cpu.json`. For a synthetic user
journey, run `corpus search --config configs/fixture.json --query align
--package fixtureR --version 1.0 --repository synthetic` using that CLI.
For the fixture service, follow `docs/LOCAL_SERVICE.md`; it always reports
`model_ready: false` and does not authorize R execution.

Local CPU readiness does not qualify a model release. Next external actions:
review this branch, run the expanded hosted CI and the explicitly enabled Linux
sandbox tier, then obtain an independently reviewed corpus and model execution
environment before model evaluation/training gates can advance. PDF extraction
and Linux namespace isolation were not executed on macOS. No push, release,
training, private-source import or remote deployment has occurred.
