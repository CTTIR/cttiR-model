"""Review queue summaries expose hashes and gaps, not automatic approval."""

from .config import validate
from .errors import ProjectError
from .provenance import fingerprint


def review_queue(records: list[dict]) -> dict:
    if not isinstance(records, list) or not 1 <= len(records) <= 1000:
        raise ProjectError("dataset_size", "Review queue accepts 1–1000 records.")
    rows = []
    for record in records:
        validate(record, "training-record")
        rows.append({"record_id": record["record_id"], "sha256": fingerprint(record),
                     "group_id": record["group_id"], "task": record["task"],
                     "review_status": record["review_status"], "rights_status": record["rights_status"],
                     "split": record["split"], "required": [name for name, missing in {
                         "human_and_scientific_review": record["review_status"] != "reviewed",
                         "source_rights_review": record["rights_status"] != "approved",
                         "family_split_assignment": record["split"] == "unassigned",
                     }.items() if missing]})
    return {"schema_version": 1, "records": rows, "auto_approved": 0}
