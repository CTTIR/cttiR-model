"""Bounded orchestration independent of any model family or GPU runtime."""

import copy
import threading
import time
from collections import OrderedDict
from typing import Protocol

from .config import validate
from .corpus import Corpus
from .errors import ProjectError
from .protocol import validate_proposal, validate_request
from .provenance import canonical, fingerprint


class Cancellation:
    def __init__(self, seconds: float):
        self.deadline = time.monotonic() + seconds
        self.event = threading.Event()

    def check(self) -> float:
        if self.event.is_set():
            raise ProjectError("cancelled", "Request was cancelled.")
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise ProjectError("timeout", "Request budget expired.")
        return left


class Endpoint(Protocol):
    identity: str
    fixture: bool

    def generate(self, request: dict, evidence: list[dict], cancellation: Cancellation,
                 repair: str | None = None) -> dict: ...

    def delegate(self, request: dict, cancellation: Cancellation) -> dict: ...


def abstention(request: dict, summary: str) -> dict:
    return {"protocol_version": 1, "request_id": request["request_id"],
            "status": "needs_input", "summary": summary, "r_code": None,
            "evidence_ids": [], "assumptions": [],
            "missing_inputs": ["Approved evidence for the requested task"],
            "limitations": ["No executable code or scientific conclusion is verified."]}


class FixtureEndpoint:
    """Deterministic integration double, never a model or quality benchmark."""

    identity = "fixture:no-model"
    fixture = True

    def generate(self, request, evidence, cancellation, repair=None):
        cancellation.check()
        response = abstention(request, "Synthetic integration fixture; no model was called.")
        if evidence:
            response.update(status="proposed", evidence_ids=[d["evidence_id"] for d in evidence],
                            missing_inputs=[], summary="Fixture evidence was received and pinned successfully.")
        return response

    def delegate(self, request, cancellation):
        cancellation.check()
        return {"tool": "consult_cttir_specialist", "task": request["task"],
                "evidence_ids": request["evidence_ids"]}


class Broker:
    def __init__(self, corpus: Corpus | None, specialist: Endpoint | None = None,
                 supervisor: Endpoint | None = None, cache_size: int = 128):
        self.corpus, self.specialist, self.supervisor = corpus, specialist, supervisor
        self._lock = threading.Lock()
        self._active: dict[str, Cancellation] = {}
        self._cache: OrderedDict = OrderedDict()
        self.cache_size = max(1, min(cache_size, 128))

    def health(self) -> dict:
        return {"protocol_version": 1, "service_ready": True, "model_ready": False,
                "mode": "fixture" if self.specialist and self.specialist.fixture else "unavailable",
                "specialist_id": self.specialist.identity if self.specialist else None,
                "supervisor_id": self.supervisor.identity if self.supervisor else None,
                "effective_base_fingerprint": None, "adapter_id": None,
                "corpus_id": self.corpus.snapshot_id if self.corpus else None,
                "fixture_only": self.corpus.fixture_only if self.corpus else False}

    def cancel(self, identity: str) -> bool:
        with self._lock:
            token = self._active.get(identity)
            if token:
                token.event.set()
            return token is not None

    def run(self, request: dict, consult: bool = False) -> dict:
        validate(request, "request")
        if len(canonical(request)) > 65536:
            raise ProjectError("input_limit", "Request is too large.")
        identity = request["request_id"]
        digest = fingerprint({"request": request, "consult": consult})
        with self._lock:
            if identity in self._cache:
                old_digest, result = self._cache[identity]
                if old_digest != digest:
                    raise ProjectError("duplicate_request", "Request ID already belongs to different content.")
                return copy.deepcopy(result)
            if identity in self._active:
                raise ProjectError("duplicate_request", "Request ID is already running.")
            if self._active:
                raise ProjectError("busy", "One request is already running; retry later.")
            token = Cancellation(min(request["budget"]["timeout_seconds"], 60))
            self._active[identity] = token
        start = time.monotonic()
        try:
            result = self._run(copy.deepcopy(request), consult, token)
            token.check()
            result["runtime"] = {"latency_ms": round((time.monotonic() - start) * 1000, 3),
                                 "specialist_id": self.specialist.identity if self.specialist else None,
                                 "supervisor_id": self.supervisor.identity if consult and self.supervisor else None,
                                 "fixture_only": bool(self.specialist and self.specialist.fixture)}
            with self._lock:
                self._cache[identity] = (digest, copy.deepcopy(result))
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            return result
        finally:
            with self._lock:
                self._active.pop(identity, None)

    def _run(self, request, consult, token):
        if self.corpus is None:
            raise ProjectError("missing_corpus", "No approved corpus is configured.")
        evidence = validate_request(request, self.corpus)
        if not evidence:
            response = abstention(request, "Supply approved version-pinned evidence before model consultation.")
            result = validate_proposal(response, request, self.corpus)
            result["routing"] = {"mode": "deterministic_abstention", "specialist_calls": 0, "repair_count": 0}
            return result
        if self.specialist is None:
            raise ProjectError("model_unavailable", "Model execution is disabled on this laptop.")
        if consult:
            if self.supervisor is None:
                raise ProjectError("model_unavailable", "Supervisor is unavailable.")
            decision = self.supervisor.delegate(copy.deepcopy(request), token)
            expected = {"tool": "consult_cttir_specialist", "task": request["task"],
                        "evidence_ids": request["evidence_ids"]}
            if decision != expected:
                raise ProjectError("invalid_delegation", "Supervisor requested an unapproved tool or changed scope.")
        repair = None
        for attempt in range(2):
            token.check()
            proposal = self.specialist.generate(copy.deepcopy(request), copy.deepcopy(evidence), token, repair)
            token.check()
            if len(canonical(proposal)) > 65536:
                raise ProjectError("output_limit", "Endpoint response exceeds the broker limit.")
            try:
                result = validate_proposal(proposal, request, self.corpus)
            except ProjectError as exc:
                if exc.code != "schema_invalid" or attempt == 1:
                    raise
                repair = exc.code
                continue
            result["routing"] = {"mode": "consult" if consult else "specialist",
                                 "specialist_calls": attempt + 1, "repair_count": attempt}
            return result
        raise ProjectError("invalid_response", "Endpoint did not produce an accepted response.")
