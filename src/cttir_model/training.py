"""CPU-testable training invariants; no model, optimizer or trainer imports."""

from .errors import ProjectError
from .provenance import fingerprint


def assistant_labels(input_ids: list[int], assistant_mask: list[int], attention_mask: list[int], max_length: int) -> list[int]:
    """Consume verified tokenizer generation spans; never infer them from text."""
    if not input_ids or len(input_ids) != len(assistant_mask) or len(input_ids) != len(attention_mask):
        raise ProjectError("loss_mask", "Token and mask lengths must agree and be nonempty.")
    if len(input_ids) > max_length:
        raise ProjectError("overlength", "Exclude or segment overlength cases; answers are never silently truncated.")
    if any(type(token) is not int or token < 0 for token in input_ids):
        raise ProjectError("loss_mask", "Token IDs must be nonnegative integers.")
    if any(type(mask) is not int or mask not in (0, 1) for mask in assistant_mask + attention_mask):
        raise ProjectError("loss_mask", "Masks must be binary integer arrays from a verified template.")
    labels = [token if assistant and attended else -100
              for token, assistant, attended in zip(input_ids, assistant_mask, attention_mask)]
    if all(value == -100 for value in labels[1:]):
        raise ProjectError("loss_mask", "No supervised next-token targets remain after masking.")
    return labels


RESUME_KEYS = {"effective_base_fingerprint", "tokenizer_sha256", "template_sha256", "dataset_sha256",
               "split_sha256", "optimizer_config_sha256", "runtime_sha256", "training_config_sha256"}


def resume_fingerprint(manifest: dict) -> str:
    import re
    if set(manifest) != RESUME_KEYS or any(not isinstance(v, str) or not re.fullmatch(r"[a-f0-9]{64}", v) for v in manifest.values()):
        raise ProjectError("resume_manifest", "Resume identity requires all eight immutable input hashes.")
    return fingerprint(manifest)


def check_resume(saved: dict, current: dict) -> None:
    if resume_fingerprint(saved) != resume_fingerprint(current):
        raise ProjectError("resume_mismatch", "Training inputs changed; start a distinct run instead of resuming.")
