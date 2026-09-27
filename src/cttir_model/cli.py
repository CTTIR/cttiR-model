"""One bounded JSON result per invocation; no model libraries imported."""

import argparse
import json
import sys
from pathlib import Path

from .config import load_config
from .corpus import Corpus, ingest
from .datasets import training_subset, validate_dataset
from .errors import ProjectError
from .preflight import inventory
from .provenance import atomic_json, fingerprint, now, read_json, record_phase


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cttir-model")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("preflight", "audit", "evaluate", "train", "serve", "update"):
        sub = commands.add_parser(name)
        sub.add_argument("--config", required=True, type=Path)
        if name == "train":
            sub.add_argument("--profile", choices=("smoke", "pilot", "full"), required=True)
        if name == "serve":
            sub.add_argument("--fixture", action="store_true", help="Use deterministic synthetic endpoints, never a model")
        if name == "evaluate":
            sub.add_argument("--candidate", required=True)
        if name == "update":
            sub.add_argument("--target", choices=("corpus", "registry"), required=True)
            sub.add_argument("--dry-run", action="store_true")
    for name, actions in {"models": ("resolve",), "corpus": ("ingest", "search", "extract"),
                          "data": ("validate", "build", "review"), "release": ("prepare", "publish"),
                          "r": ("parse", "fixtures", "isolation"), "parent": ("preview", "bind")}.items():
        parent = commands.add_parser(name)
        children = parent.add_subparsers(dest="action", required=True)
        for action in actions:
            sub = children.add_parser(action)
            sub.add_argument("--config", required=True, type=Path)
            if name == "parent":
                sub.add_argument("--input", type=Path, required=True)
            if name == "r" and action == "parse":
                sub.add_argument("--input", type=Path, required=True)
                sub.add_argument("--catalog", type=Path)
            if name == "corpus" and action == "extract":
                sub.add_argument("--source", type=Path, required=True)
                sub.add_argument("--repository", required=True)
                sub.add_argument("--max-topics", type=int, default=20)
            if name == "corpus" and action == "ingest":
                sub.add_argument("--source", type=Path)
            if name == "corpus" and action == "search":
                sub.add_argument("--query", required=True)
                sub.add_argument("--package", required=True)
                sub.add_argument("--version", required=True)
                sub.add_argument("--repository", required=True)
            if name == "data":
                sub.add_argument("--input", type=Path, required=True)
                if action != "review":
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
    if args.command == "serve":
        from .serving import serve
        return serve(config, args.fixture)
    if args.command == "parent":
        from .parent import bind_parent_request, fallback_plan
        value = read_json(args.input, config.limit)
        if args.action == "preview":
            return fallback_plan(value)
        required = {"spec", "request", "parent_commit", "resource_pin", "package_bindings"}
        if not isinstance(value, dict) or set(value) != required:
            raise ProjectError("parent_input", "Binding input needs spec, request, parent_commit, resource_pin and package_bindings.")
        envelope = bind_parent_request(value["spec"], value["request"], Corpus.from_config(config),
                                       parent_commit=value["parent_commit"], resource_pin=value["resource_pin"],
                                       package_bindings=value["package_bindings"])
        path = config.artifacts / "parent" / (fingerprint(envelope.as_dict()) + ".json")
        atomic_json(path, envelope.as_dict())
        return {"status": "bound", "envelope_id": envelope.envelope_id, "path": str(path),
                "execution_authorized": False}
    if args.command == "preflight":
        report = inventory(config)
        atomic_json(config.artifacts / "preflight.json", report)
        entry = {"timestamp": now(), "command": "preflight", "exit_status": 0,
                 "input_sha256": fingerprint(config.values), "output_sha256": fingerprint(report),
                 "outputs": ["preflight.json"], "next_action": "Run CPU contract tests; keep GPU work deferred."}
        # Append-only individual entries avoid rewriting previous phase evidence.
        record_phase(config.artifacts, entry)
        return {"status": "implemented", "report": str(config.artifacts / "preflight.json"),
                "training_ready": False, "execution_mode": config.values["execution"]["mode"]}
    if args.command == "audit":
        return {"status": "pending", "gates": pending_gates(), "trained_candidate": False,
                "release_qualified": False, "mutations": False}
    if args.command == "corpus":
        if args.action == "extract":
            from .sources import extract_candidates
            result = extract_candidates(args.source, args.repository, args.max_topics)
            root = config.artifacts / "source-review" / result["source"]["archive_sha256"]
            atomic_json(root / "candidates.json", result["corpus"])
            atomic_json(root / "source.json", result["source"])
            return {"status": "review_required", "path": str(root), "source": result["source"]}
        if args.action == "ingest":
            source = args.source
            if source is None and config.values["corpus"]["path"]:
                source = config.path(config.values["corpus"]["path"])
            if source is None:
                raise ProjectError("missing_source", "Supply --source or configure corpus.path.")
            return ingest(config, source)
        corpus = Corpus.from_config(config)
        documents = corpus.search(args.query, {"name": args.package, "version": args.version,
                                               "repository": args.repository})
        return {"status": "retrieved", "corpus_id": corpus.snapshot_id,
                "fixture_only": corpus.fixture_only, "documents": documents}
    if args.command == "data":
        records = read_json(args.input, config.limit)
        if args.action == "review":
            from .review import review_queue
            return review_queue(records)
        registry = read_json(args.registry, config.limit)
        corpus = Corpus.from_config(config)
        report = validate_dataset(records, corpus, registry)
        if args.action == "build":
            payload = {"manifest": report, "train": training_subset(records)}
            if not payload["train"]:
                raise ProjectError("empty_training", "The reviewed dataset has no training split.")
            path = config.artifacts / "datasets" / (fingerprint(payload) + ".json")
            atomic_json(path, payload)
            report = {**report, "output": str(path), "training_records": len(payload["train"])}
        return report
    if args.command == "r":
        from .r_validation import parse_r, run_worker
        if args.action == "parse":
            with args.input.open("rb") as stream:
                raw = stream.read(60001)
            if len(raw) > 60000:
                raise ProjectError("r_input", "R source exceeds 60 KiB.")
            report = parse_r(raw.decode("utf-8"), read_json(args.catalog) if args.catalog else None)
            if not report["parsed"] or not report["static_subset_supported"] or report["api_errors"]:
                raise ProjectError("r_rejected", "R source is syntactically invalid or outside the checked API subset.")
            return report
        output = run_worker("fixture" if args.action == "fixtures" else "isolation")
        return {"status": "smoke_tested", "mode": args.action, "output": output,
                "scientifically_reviewed": False}
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
