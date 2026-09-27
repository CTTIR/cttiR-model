"""One bounded JSON result per invocation; no model libraries imported."""

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .errors import ProjectError
from .preflight import inventory
from .provenance import atomic_json, fingerprint, now


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cttir-model")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("preflight", "audit", "evaluate", "train", "serve", "update"):
        sub = commands.add_parser(name)
        sub.add_argument("--config", required=True, type=Path)
        if name == "train":
            sub.add_argument("--profile", choices=("smoke", "pilot", "full"), required=True)
        if name == "evaluate":
            sub.add_argument("--candidate", required=True)
        if name == "update":
            sub.add_argument("--target", choices=("corpus", "registry"), required=True)
            sub.add_argument("--dry-run", action="store_true")
    for name, actions in {"models": ("resolve",), "corpus": ("ingest", "search"),
                          "data": ("validate", "build"), "release": ("prepare", "publish")}.items():
        parent = commands.add_parser(name)
        children = parent.add_subparsers(dest="action", required=True)
        for action in actions:
            sub = children.add_parser(action)
            sub.add_argument("--config", required=True, type=Path)
            if name == "corpus" and action == "ingest":
                sub.add_argument("--source", type=Path)
            if name == "corpus" and action == "search":
                sub.add_argument("--query", required=True)
                sub.add_argument("--package", required=True)
                sub.add_argument("--version", required=True)
                sub.add_argument("--repository", required=True)
            if name == "data":
                sub.add_argument("--input", type=Path, required=True)
                sub.add_argument("--registry", type=Path, required=True)
            if name == "release" and action == "prepare":
                sub.add_argument("--run", required=True)
            if name == "release" and action == "publish":
                sub.add_argument("--manifest", type=Path, required=True)
                sub.add_argument("--visibility", choices=("private", "public"), required=True)
    return root


def pending_gates() -> list[dict]:
    reasons = [
        "Run preflight to record local inventory.",
        "CPU contracts require recorded test evidence.",
        "Exact base, FP8 compatibility and real GPU smoke deferred.",
        "Production corpus and approved coverage not supplied.",
        "Reviewed dataset and frozen splits not supplied.",
        "Real same-base baseline deferred.",
        "Training disabled on this laptop; no candidate exists.",
        "Held-out domain evaluation deferred.",
        "Execution/privacy evaluation on actual model pending.",
        "Baseline/candidate comparison deferred.",
        "Real broker/endpoint orchestration not implemented.",
        "R client, serving and rollback integration pending.",
        "No trained, reconstructible release candidate.",
        "Model publication remains a later explicit action.",
    ]
    return [{"gate": f"G{i:02}", "status": "pending", "reason": reason}
            for i, reason in enumerate(reasons, 1)]


def dispatch(args: argparse.Namespace) -> dict:
    config = load_config(args.config)
    if args.command == "preflight":
        report = inventory(config)
        atomic_json(config.artifacts / "preflight.json", report)
        entry = {"timestamp": now(), "command": "preflight", "exit_status": 0,
                 "input_sha256": fingerprint(config.values), "output_sha256": fingerprint(report),
                 "outputs": ["preflight.json"], "next_action": "Run CPU contract tests; keep GPU work deferred."}
        # Append-only individual entries avoid rewriting previous phase evidence.
        atomic_json(config.artifacts / "implementation" / (fingerprint(entry) + ".json"), entry)
        return {"status": "implemented", "report": str(config.artifacts / "preflight.json"),
                "training_ready": False, "execution_mode": config.values["execution"]["mode"]}
    if args.command == "audit":
        return {"status": "pending", "gates": pending_gates(), "trained_candidate": False,
                "release_qualified": False, "mutations": False}
    if args.command == "update" and args.dry_run:
        return {"status": "pending", "target": args.target, "mutations": False,
                "reason": "Refresh adapters are not implemented; no source or model was changed."}
    raise ProjectError("deferred", "This operation is not implemented in the CPU foundation. "
                       "No weights were downloaded, loaded, trained or published.", exit_code=3)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        code = 0
    except ProjectError as exc:
        result = {"status": "deferred" if exc.exit_code == 3 else "failed",
                  "error": {"code": exc.code, "message": str(exc)}}
        code = exc.exit_code
    except OSError:
        result = {"status": "failed", "error": {"code": "io_error",
                  "message": "Local I/O failed; check file access and available disk space."}}
        code = 2
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
