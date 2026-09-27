"""Model-family-neutral validation; model proposals never grant execution."""

from .config import validate
from .corpus import Corpus
from .errors import ProjectError


def validate_request(request: dict, corpus: Corpus) -> list[dict]:
    validate(request, "request")
    if request["corpus_id"] != corpus.snapshot_id:
        raise ProjectError("corpus_pin", "Request corpus ID does not match the server snapshot.")
    return corpus.evidence(request["evidence_ids"], request["package_pins"])


def validate_proposal(proposal: dict, request: dict, corpus: Corpus) -> dict:
    validate_request(request, corpus)
    validate(proposal, "response")
    if proposal["request_id"] != request["request_id"]:
        raise ProjectError("request_id", "Response request ID does not match.")
    if not set(proposal["evidence_ids"]).issubset(request["evidence_ids"]):
        raise ProjectError("invented_evidence", "Response cites evidence not supplied to the model.")
    if proposal["status"] == "proposed" and not proposal["evidence_ids"]:
        raise ProjectError("ungrounded_proposal", "A proposal requires approved evidence.")
    # Code validation is a later milestone: even schema-valid code is not accepted
    # as an executable result. A real R parser, API check and sandbox are required.
    if proposal["r_code"]:
        raise ProjectError("r_validation_pending", "Executable R proposals require the pending deterministic validator.")
    return {"proposal": proposal, "verification": {"schema_valid": True,
            "evidence_pins_valid": True, "r_execution_authorized": False,
            "scientifically_reviewed": False}, "corpus_id": corpus.snapshot_id}
