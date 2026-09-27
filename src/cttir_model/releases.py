"""Local release integrity and atomic routing metadata; no remote publication."""

import fcntl
import hashlib
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .config import validate
from .errors import ProjectError
from .provenance import atomic_json, fingerprint, read_json


ALLOWLIST = {"adapter_model.safetensors", "adapter_config.json", "README.md", "LICENSE", "NOTICE",
             "base-provenance.json", "load_adapter.py", "generation_config.json", "evaluation.json",
             "DATA_STATEMENT.md", "TRAINING_REPORT.md", "gate-report.json", "tokenizer_config.json",
             "special_tokens_map.json", "chat_template.jinja", "processor_config.json", "tokenizer.json"}
REQUIRED = {"adapter_model.safetensors", "adapter_config.json", "README.md", "LICENSE",
            "base-provenance.json", "load_adapter.py", "evaluation.json", "DATA_STATEMENT.md",
            "TRAINING_REPORT.md", "gate-report.json"}
SECRET = re.compile(rb"(?:hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


def payload_path(root: Path, name: str) -> Path:
    path = PurePosixPath(name)
    if (path.is_absolute() or ".." in path.parts or "\\" in name or name not in ALLOWLIST
            or name != path.as_posix()):
        raise ProjectError("release_path", "Release payload contains an unapproved or unsafe path.")
    target = root / name
    if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
        raise ProjectError("release_path", "Payload files must be ordinary files within the release root.")
    return target


def validate_release(manifest: dict, root: Path, byte_limit: int = 64 * 1024 * 1024) -> dict:
    validate(manifest, "release")
    if manifest["artifact_kind"] != "lora_adapter" or manifest["remote_commit"] is not None:
        raise ProjectError("release_kind", "Local preparation supports unpublished LoRA adapters only.")
    if manifest["status"] == "published":
        raise ProjectError("release_state", "Local tooling cannot attest remote publication.")
    names = [item["path"] for item in manifest["files"]]
    if len(names) != len(set(names)) or not REQUIRED.issubset(names):
        raise ProjectError("release_files", "Required files are missing or file paths are duplicated.")
    if any(word in manifest["release_id"].lower() for word in ("placeholder", "fixture", "unresolved")):
        raise ProjectError("release_placeholder", "A real release identity is required.")
    if sum(item["bytes"] for item in manifest["files"]) > byte_limit:
        raise ProjectError("release_budget", "Payload exceeds the laptop inspection budget; defer to the release machine.")
    for item in manifest["files"]:
        path = payload_path(root, item["path"])
        if path.stat().st_size != item["bytes"]:
            raise ProjectError("release_hash", "Payload size differs from the reviewed manifest.")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(65536):
                digest.update(chunk)
        if digest.hexdigest() != item["sha256"]:
            raise ProjectError("release_hash", "Payload hash differs from the reviewed manifest.")
        if path.suffix in {".json", ".md", ".py", ".jinja"} or path.name in {"LICENSE", "NOTICE"}:
            if path.stat().st_size > 1024 * 1024:
                raise ProjectError("release_text", "Text payload exceeds the review budget.")
            raw = path.read_bytes()
            if SECRET.search(raw) or any(marker in raw for marker in (b"[fill]", b"TEMPLATE ONLY", b"<YOUR_")):
                raise ProjectError("release_secret", "Payload contains a possible credential or unresolved template marker.")
    gates = read_json(root / "gate-report.json")
    if hashlib.sha256((root / "gate-report.json").read_bytes()).hexdigest() != manifest["gate_report_sha256"]:
        raise ProjectError("release_gates", "Gate report differs from the release pin.")
    gate_rows = gates.get("gates", []) if isinstance(gates, dict) else []
    if not isinstance(gate_rows, list) or any(not isinstance(row, dict) for row in gate_rows):
        raise ProjectError("release_gates", "Malformed release gates.")
    by_id = {row.get("gate"): row for row in gate_rows}
    if len(by_id) != len(gate_rows):
        raise ProjectError("release_gates", "Duplicate release gates.")
    for number in range(1, 14):
        row = by_id.get(f"G{number:02}", {})
        if (row.get("status") != "pass" or type(row.get("exit_status")) is not int or row["exit_status"] != 0
                or not row.get("command") or not row.get("artifacts")
                or not isinstance(row["artifacts"], list) or not set(row["artifacts"]).issubset(names)):
            raise ProjectError("release_gates", "All mandatory pre-publication gates need successful, referenced evidence.")
    base = read_json(root / "base-provenance.json")
    adapter = read_json(root / "adapter_config.json")
    evaluation = read_json(root / "evaluation.json")
    if not all(isinstance(value, dict) for value in (base, adapter, evaluation)):
        raise ProjectError("release_provenance", "Release provenance files must be objects.")
    recipe_keys = {"source_repo_id", "source_revision", "config_sha256", "tokenizer_sha256", "template_sha256", "conversion_sha256"}
    if (not recipe_keys.issubset(base) or any(not isinstance(base[k], str) or not re.fullmatch(r"[a-f0-9]{64}", base[k])
                                           for k in recipe_keys if k.endswith("sha256"))
            or fingerprint({k: base[k] for k in recipe_keys}) != base.get("effective_base_fingerprint")):
        raise ProjectError("release_base", "Effective-base fingerprint must bind the reconstruction recipe hashes.")
    if (base.get("source_repo_id") != manifest["base_repo_id"] or base.get("source_revision") != manifest["base_revision"]
            or base.get("effective_base_fingerprint") != manifest["effective_base_fingerprint"]
            or adapter.get("base_model_name_or_path") != manifest["base_repo_id"]
            or adapter.get("revision") != manifest["base_revision"] or not adapter.get("target_modules")
            or evaluation.get("effective_base_fingerprint") != manifest["effective_base_fingerprint"]
            or evaluation.get("corpus_id") != manifest["corpus_id"] or evaluation.get("fixture_only") is not False
            or evaluation.get("dataset_manifest_sha256") != manifest["dataset_manifest_sha256"]
            or evaluation.get("benchmark_id") != manifest["benchmark_id"]
            or evaluation.get("source_commit") != manifest["source_commit"]
            or evaluation.get("release_qualified") is not True):
        raise ProjectError("release_provenance", "Effective base, adapter or qualified evaluation provenance does not match.")
    return {"status": "integrity_checked", "manifest_sha256": fingerprint(manifest),
            "files": len(names), "bytes": sum(item["bytes"] for item in manifest["files"]),
            "runtime_loaded": False, "published": False}


def prepare_release(config, run_id: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        raise ProjectError("run_id", "Run ID must be a simple local identifier.")
    source = config.artifacts / "runs" / run_id
    if source.is_symlink() or not source.resolve().is_relative_to((config.artifacts / "runs").resolve()):
        raise ProjectError("run_id", "Run folder must be inside the local run store.")
    manifest = read_json(source / "release.json")
    if not config.values["project"]["hf_repo"] or manifest.get("hf_repo") != config.values["project"]["hf_repo"]:
        raise ProjectError("release_target", "Configure the exact reviewed Hugging Face target before preparing a payload.")
    if manifest.get("visibility") != config.values["release"]["visibility"]:
        raise ProjectError("release_target", "Configured visibility differs from the reviewed release manifest.")
    validate_release(manifest, source)
    manifest = {**manifest, "status": "publication_prepared"}
    destination = config.artifacts / "releases" / fingerprint(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if read_json(destination / "release.json") != manifest:
            raise ProjectError("release_collision", "An existing release path contains different metadata.")
        validate_release(manifest, destination)
    else:
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".staging-") as temporary:
            stage = Path(temporary) / "payload"
            stage.mkdir()
            for item in manifest["files"]:
                shutil.copyfile(payload_path(source, item["path"]), stage / item["path"])
            atomic_json(stage / "release.json", manifest)
            validate_release(manifest, stage)
            stage.rename(destination)
    return {"status": "publication_prepared", "path": str(destination), "remote_mutations": False}


class ReleaseRegistry:
    """Atomic local release pointer only. No process starts or hot-loading."""

    def __init__(self, artifact_root: Path):
        self.root = artifact_root.resolve()
        self.state = self.root / "release-registry"

    @contextmanager
    def locked(self):
        self.state.mkdir(parents=True, exist_ok=True)
        with (self.state / ".lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def inspect(self, manifest_path: Path) -> dict:
        resolved = manifest_path.resolve()
        if manifest_path.is_symlink() or not resolved.is_relative_to(self.root / "releases"):
            raise ProjectError("registry_path", "Registry accepts only prepared local release payloads.")
        manifest = read_json(resolved)
        checked = validate_release(manifest, resolved.parent)
        return {"manifest": str(resolved.relative_to(self.root)), "sha256": checked["manifest_sha256"],
                "release_id": manifest["release_id"], "effective_base_fingerprint": manifest["effective_base_fingerprint"],
                "corpus_id": manifest["corpus_id"], "source_commit": manifest["source_commit"]}

    def switch(self, manifest_path: Path | None = None, rollback: bool = False, dry_run: bool = True) -> dict:
        def plan():
            previous = read_json(self.state / "active.json") if (self.state / "active.json").exists() else None
            if rollback:
                if not previous or not previous.get("previous"):
                    raise ProjectError("rollback_unavailable", "No prior coherent release pointer is retained.")
                candidate = self.inspect(self.root / previous["previous"]["manifest"])
                if candidate != previous["previous"]:
                    raise ProjectError("rollback_hash", "Retained release metadata changed.")
            else:
                if manifest_path is None:
                    raise ProjectError("registry_path", "Supply a prepared release manifest.")
                candidate = self.inspect(manifest_path)
            return {"current": candidate, "previous": previous["current"] if previous else None}
        if dry_run:
            return {"status": "planned", "pointer": plan(), "runtime_loaded": False, "mutations": False}
        with self.locked():
            value = plan()
            atomic_json(self.state / "active.json", value)
        return {"status": "pointer_updated", "pointer": value, "runtime_loaded": False, "mutations": True}
