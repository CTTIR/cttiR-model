import importlib.metadata
import os
import platform
import shutil
import subprocess
from pathlib import Path

from .config import Config
from .provenance import fingerprint, now


def probe(args: list[str], cwd: Path | None = None) -> dict:
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                timeout=5, check=False)
        return {"status": "observed" if result.returncode == 0 else "unavailable",
                "exit_status": result.returncode, "output": result.stdout[:4096].strip()}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unavailable", "exit_status": None, "output": ""}


def inventory(config: Config) -> dict:
    packages = {}
    for name in ("jsonschema", "attrs", "jsonschema-specifications", "referencing", "rpds-py", "setuptools"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    ram = None
    try:
        ram = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        pass
    disk_path = config.artifacts
    while not disk_path.exists():
        disk_path = disk_path.parent
    return {
        "schema_version": 1, "created_at": now(), "implementation_root": str(config.root),
        "artifact_root": str(config.artifacts), "config_sha256": fingerprint(config.values),
        "software_commit": probe(["git", "rev-parse", "HEAD"], config.root),
        "git_state": probe(["git", "status", "--porcelain"], config.root),
        "os": platform.system(), "architecture": platform.machine(),
        "python": platform.python_version(), "logical_cpus": os.cpu_count(),
        "memory_bytes": ram, "disk_free_bytes": shutil.disk_usage(disk_path).free,
        "gpu": probe(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"]),
        "gpu_probe_scope": "NVIDIA metadata only; unavailable is not proof of no GPU",
        "R": probe(["Rscript", "--version"]), "packages": packages,
        "execution_policy": config.values["execution"],
        "endpoints": {role: model["endpoint"] for role, model in config.values["models"].items()},
        "training_ready": False,
        "deferred": ["model acquisition", "model execution", "compatibility smoke", "baseline", "training", "evaluation"],
    }
