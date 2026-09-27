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

## 2 — Local evidence and dataset safeguards (next)

Implement immutable corpus snapshots, exact-version lexical retrieval,
server-owned evidence checks, and reviewed dataset/split validation using
small synthetic fixtures. Production corpus approval remains a separate gate.

## Deferred work

Resolve exact model metadata and FP8 training compatibility; provision a tested
GPU environment; obtain approved versioned R documentation and independently
reviewed examples; freeze benchmarks; implement and execute genuine baseline,
adapter training and save/reload; implement model broker, sandboxed R validators,
R client, serving rollback and release reconstruction.

Do not run these workloads on this laptop. Training and download switches are
schema constants set to false, so a profile edit cannot accidentally start them.
The GPU trainer is not implemented yet: reserved commands are not runnable GPU
job specifications. No training-runtime version or compatibility is claimed.

Local validation: 11 unit tests passed in the isolated Python 3.14.4 environment;
editable package installation and preflight succeeded. Dependencies are pinned
in `requirements-cpu.lock`. Preflight observed approximately 14.8 GiB RAM;
the NVIDIA probe was unavailable. This is not a hardware training qualification.

G01/G02 have partial preflight/CPU evidence; full lifecycle readiness is pending.
G03–G14 remain pending. Model
publication requires a later explicit action and a concrete qualified payload.
GitHub software milestones are pushed directly to main as requested.
