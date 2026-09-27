# Bounded R validation and source review

Linux workers use bubblewrap user/process/network namespaces, read-only system
runtime mounts, an isolated temporary directory, no home/project mount and a
cleared environment. They have 1 GiB address-space, five CPU seconds, eight wall
seconds, 128 KiB output, 256 file descriptors and 16 processes (inside the
namespace). BLAS/OpenMP use one thread. Missing sandbox support fails closed;
there is no unsandboxed fallback. Only system R packages are visible.

```sh
cttir-model r isolation --config configs/cpu.json
cttir-model r fixtures --config configs/cpu.json
cttir-model r parse --config configs/cpu.json --input artifacts/proposal.R
```

`parse` calls R's real parser and walks the unevaluated AST. It recognizes a
conservative syntax subset and literal `package::function` calls, extracting
argument names. It never executes supplied code. Optional `--catalog FILE`
checks exports/named arguments against explicitly supplied approved, versioned
entries (`package::symbol`: `{approved, version, arguments}`). The standalone
catalog is a review input, not an automatic proof of source authenticity. Dynamic
calls, internals and unsupported argument patterns fail closed. Parsing/API
checking does not establish statistical correctness or grant execution rights.

`fixtures` runs two fixed original synthetic checks: unique-key join invariants
and donor aggregation. These are smoke cases, not validation of arbitrary user
analyses or support for Bioconductor/Seurat. Broker code proposals remain rejected
until a parent-aligned reviewed execution adapter exists.

```sh
cttir-model corpus extract --config configs/cpu.json --source artifacts/package.tar.gz --repository CRAN --max-topics 20
cttir-model data review --config configs/cpu.json --input artifacts/draft-records.json
```

Source extraction is bounded to 8 MiB expanded data and 20 topics by default.
It rejects traversal, links, special files and decompression over budget. Rd
files use the native R parser in isolation; dynamic Sexpr/macros are rejected
and no examples, vignettes, installation hooks or Rd converters are executed.
Candidate content, archive hashes, license declarations, literal export hints,
vignette inventory, failures and deferred-topic counts are retained locally.
Topic names/signatures and export hints remain unverified; S3/S4/S7, reexports
and method ownership require further native metadata review. Every extracted
record stays `candidate` and rights `pending`. There is no automatic approval.

Run the explicit sandbox tier with:

```sh
CTTIR_TEST_SANDBOX=1 PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

In a restrictive development sandbox, namespace/socket permissions may require
running this test command outside that outer sandbox. The worker's inner
isolation and limits still apply. Hosted CI may skip this explicit Linux tier;
skips are not reported as successful R containment evidence.
