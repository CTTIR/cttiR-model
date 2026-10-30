"""Bind local test evidence to package bytes, including packaged contracts."""

import hashlib
from importlib.resources import files
from pathlib import Path

from .errors import ProjectError
from .provenance import fingerprint


def package_files(root):
    result = {}
    def visit(folder, prefix=""):
        for path in sorted(folder.iterdir(), key=lambda item: item.name):
            name = prefix + path.name
            if path.name == "__pycache__":
                continue
            if path.is_dir():
                visit(path, name + "/")
            elif path.name.endswith((".py", ".R", ".json")):
                result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    visit(root)
    return result


def installed_fingerprint():
    return fingerprint(package_files(files("cttir_model")))


def verify_installed_source(root: Path):
    source = package_files(root / "src" / "cttir_model")
    installed = package_files(files("cttir_model"))
    if source != installed:
        raise ProjectError("stale_install", "Installed package differs from this checkout; reinstall before recording test evidence.")
    return fingerprint(installed)
