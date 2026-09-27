# Local broker and R client

```sh
cttir-model serve --config configs/fixture.json --fixture
```

This binds `127.0.0.1:8088`. It uses deterministic synthetic endpoints, not model
inference. `/health` always reports `model_ready: false`; fixture responses are
marked `fixture_only: true`. Without `--fixture`, the service reports unavailable
models and never connects to configured inference addresses. No user query
downloads anything. Production inference adapters remain deferred.

POST the request-v1 JSON contract to `/v1/specialist` or `/v1/consult`. Responses
wrap the original proposal in broker-owned verification, routing and runtime
metadata. Consult validates exactly one specialist tool delegation and returns
the validated proposal unchanged. There is no model synthesis step that can
silently edit code/evidence. One schema-repair retry is permitted; invented tools,
changed evidence scope and unvalidated R code are rejected. Missing evidence
returns a deterministic `needs_input`; absent models return HTTP 503.

HTTP status codes: malformed requests 400, invalid schema/evidence 422, corpus
or duplicate-ID conflicts 409, busy broker 429, unavailable 503, timeout 504.
DELETE `/v1/requests/{request_id}` cancels an active request. The endpoint interface
receives a cooperative deadline/cancellation token. Production adapters must
obey it; this interface is not a process sandbox for arbitrary Python code.

The broker allows one active operation, four HTTP handler threads, 64 KiB request
bodies, two specialist calls and at most 60 seconds. A bounded 128-entry in-memory
cache makes exact duplicate requests idempotent while retained; changed content
under the same ID is rejected. Cache entries are neither durable nor shared
between processes. Use new IDs after restart; no exactly-once guarantee is made.
Raw request text is not logged. Origin headers and nonliteral loopback Host
headers are rejected. The standard-library HTTP server is a local development
service, not a production TLS/authenticated deployment.

## R

Source `r/client.R`. The client uses declared `curl` and `jsonlite` dependencies,
recorded in the generated `r/renv.lock`; it does not install packages during a
request. Call `cttir_model_health()`, then `cttir_model_consult(task, context)`.
`context` holds request_id, language, instruction, corpus_id, package_pins,
evidence_ids and input_contract. See `tests/r/client.R` for a runnable example.
Timeouts and response sizes are bounded; redirects/proxies and remote hosts are
disabled. Errors inherit `cttir_model_error` and a code-specific class.

Parent integration should use an explicit provider extension: call health,
send the existing workflow's task through this client, and retain the parent's
deterministic `standard_reflowR` fallback on unavailable/unsupported results.
Do not execute returned code or silently alter the parent's three-input API.
This repository does not modify the parent R package.

The Python suite starts a temporary real HTTP server and runs the R client
against it when R and the two declared libraries are available. Missing R
dependencies are an explicit skip, not a passed R integration result.
