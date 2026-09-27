"""Offline scoring of saved outputs; never invokes models or invents reviews."""

import math
import random
from collections import defaultdict

from .config import validate
from .corpus import Corpus
from .errors import ProjectError
from .protocol import validate_request
from .provenance import decode_json, fingerprint


SCORING_POLICY = {"version": 1, "raw_schema_min": 0.95, "api_correct_min": 0.9,
                  "supported_success_min": 0.8, "critical_violations_max": 0,
                  "primary_metric": "mean_group_supported_success", "minimum_gain": 0.05,
                  "bootstrap_resamples": 200, "bootstrap_seed": 1729}


def freeze_benchmark(value: dict, corpus: Corpus) -> dict:
    if not isinstance(value, dict) or set(value) != {"schema_version", "benchmark_id", "fixture_only", "cases"} or value["schema_version"] != 1:
        raise ProjectError("benchmark", "Expected benchmark-v1 identity, fixture marker and cases.")
    if not isinstance(value["benchmark_id"], str) or not value["benchmark_id"] or type(value["fixture_only"]) is not bool:
        raise ProjectError("benchmark", "Invalid benchmark identity or fixture marker.")
    if corpus.fixture_only and not value["fixture_only"]:
        raise ProjectError("fixture_benchmark", "Synthetic corpus cannot qualify a real benchmark.")
    cases = value["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 1000:
        raise ProjectError("benchmark_size", "Expected 1–1000 benchmark cases.")
    seen = set()
    for case in cases:
        if (not isinstance(case, dict) or set(case) != {"case_id", "group_id", "supported", "request"}
                or any(not isinstance(case[k], str) or not case[k] for k in ("case_id", "group_id"))
                or type(case["supported"]) is not bool or case["case_id"] in seen):
            raise ProjectError("benchmark", "Malformed or duplicate benchmark case.")
        seen.add(case["case_id"])
        validate_request(case["request"], corpus)
    return {"schema_version": 1, "benchmark": value, "corpus_id": corpus.snapshot_id,
            "scoring_policy": dict(SCORING_POLICY), "benchmark_sha256": fingerprint({"benchmark": value,
                    "corpus_id": corpus.snapshot_id, "scoring_policy": SCORING_POLICY})}


def score_outputs(frozen: dict, run: dict, corpus: Corpus) -> dict:
    try:
        rebuilt = freeze_benchmark(frozen["benchmark"], corpus)
    except (KeyError, TypeError) as exc:
        raise ProjectError("benchmark", "Frozen benchmark is malformed.") from exc
    if rebuilt != frozen:
        raise ProjectError("benchmark_hash", "Frozen benchmark or preregistered policy changed.")
    required = {"run_id", "arm", "fixture_only", "benchmark_sha256", "effective_base_fingerprint",
                "corpus_id", "generation_config_sha256", "records"}
    if not isinstance(run, dict) or set(run) != required:
        raise ProjectError("evaluation_run", "Expected saved-output run manifest with exact identity fields.")
    if (run["benchmark_sha256"] != frozen["benchmark_sha256"] or run["corpus_id"] != corpus.snapshot_id
            or run["arm"] not in {"A", "B", "C", "D"} or type(run["fixture_only"]) is not bool):
        raise ProjectError("evaluation_pin", "Evaluation benchmark, corpus or comparison arm is invalid.")
    import re
    if any(not isinstance(run[k], str) or not re.fullmatch(r"[a-f0-9]{64}", run[k])
           for k in ("effective_base_fingerprint", "generation_config_sha256")):
        raise ProjectError("evaluation_pin", "Evaluation needs exact base and generation configuration hashes.")
    if frozen["benchmark"]["fixture_only"] and not run["fixture_only"]:
        raise ProjectError("fixture_evaluation", "Fixture results must remain labelled synthetic.")
    if not isinstance(run["records"], list) or len(run["records"]) != len(frozen["benchmark"]["cases"]):
        raise ProjectError("evaluation_coverage", "Every benchmark case must have exactly one output, including failures.")
    outputs = {}
    for item in run["records"]:
        if (not isinstance(item, dict) or set(item) != {"case_id", "proposal", "latency_ms", "review"}
                or not isinstance(item["case_id"], str) or item["case_id"] in outputs
                or type(item["latency_ms"]) not in (float, int) or not math.isfinite(item["latency_ms"])
                or item["latency_ms"] < 0):
            raise ProjectError("evaluation_output", "Malformed or duplicate saved output.")
        outputs[item["case_id"]] = item
    cases = frozen["benchmark"]["cases"]
    if set(outputs) != {c["case_id"] for c in cases}:
        raise ProjectError("evaluation_coverage", "Saved output IDs differ from the sealed case list.")
    rows = []
    for case in cases:
        item = outputs[case["case_id"]]
        proposal = item["proposal"]
        schema_ok, evidence_ok = False, False
        try:
            if isinstance(proposal, str):
                proposal = decode_json(proposal.encode())
            validate(proposal, "response")
            schema_ok = True
            evidence_ok = (proposal["request_id"] == case["request"]["request_id"]
                           and set(proposal["evidence_ids"]).issubset(case["request"]["evidence_ids"])
                           and (proposal["status"] != "proposed" or bool(proposal["evidence_ids"])))
        except ProjectError:
            pass
        review = item["review"]
        if review is not None:
            expected_keys = {"reviewer", "output_sha256", "api_correct", "scientific_pass", "task_pass", "critical_violation"}
            if (not isinstance(review, dict) or set(review) != expected_keys
                    or not isinstance(review["reviewer"], str) or not review["reviewer"]
                    or any(type(review[k]) is not bool for k in ("api_correct", "scientific_pass", "task_pass", "critical_violation"))
                    or review["output_sha256"] != fingerprint({"benchmark_sha256": frozen["benchmark_sha256"],
                                                              "case_id": case["case_id"], "proposal": item["proposal"]})):
                raise ProjectError("evaluation_review", "Output review is malformed or no longer matches its evidence.")
        positive = schema_ok and proposal["status"] == "proposed"
        success = bool(schema_ok and evidence_ok and positive and review and review["api_correct"]
                       and review["scientific_pass"] and review["task_pass"] and not review["critical_violation"])
        rows.append({"case_id": case["case_id"], "group_id": case["group_id"], "supported": case["supported"],
                     "schema_valid": schema_ok, "evidence_valid": evidence_ok, "success": success,
                     "abstained": schema_ok and proposal["status"] in {"unsupported", "needs_input"},
                     "reviewed": review is not None, "api_correct": bool(review and review["api_correct"] and schema_ok and evidence_ok),
                     "critical_violation": bool(review and review["critical_violation"]), "latency_ms": item["latency_ms"]})
    supported = [r for r in rows if r["supported"]]
    unsupported = [r for r in rows if not r["supported"]]
    abstentions = [r for r in rows if r["abstained"]]
    groups = defaultdict(list)
    for row in supported:
        groups[row["group_id"]].append(int(row["success"]))
    group_scores = {g: sum(v) / len(v) for g, v in groups.items()}
    metrics = {"raw_schema_valid": sum(r["schema_valid"] for r in rows) / len(rows),
               "api_correct": sum(r["api_correct"] for r in supported) / len(supported) if supported else None,
               "supported_success": sum(r["success"] for r in supported) / len(supported) if supported else None,
               "mean_group_supported_success": sum(group_scores.values()) / len(group_scores) if groups else None,
               "abstention_precision": sum(not r["supported"] for r in abstentions) / len(abstentions) if abstentions else None,
               "abstention_recall": sum(r["abstained"] for r in unsupported) / len(unsupported) if unsupported else None,
               "review_coverage": sum(r["reviewed"] for r in rows) / len(rows),
               "critical_violations": sum(r["critical_violation"] for r in rows),
               "mean_latency_ms": sum(r["latency_ms"] for r in rows) / len(rows)}
    return {"status": "scored_saved_outputs", **{k: run[k] for k in required - {"records"}},
            "records_sha256": fingerprint(run["records"]), "metrics": metrics, "case_results": rows,
            "group_scores": group_scores, "release_qualified": False,
            "limitations": ["Review annotations are imported attestations; reviewer identity is not authenticated.",
                            "No model or R code was executed by this scorer."]}


def compare_reports(baseline: dict, candidate: dict) -> dict:
    for key in ("benchmark_sha256", "corpus_id", "effective_base_fingerprint", "generation_config_sha256"):
        if baseline.get(key) != candidate.get(key):
            raise ProjectError("unfair_comparison", "Comparison requires identical benchmark, evidence, base and generation budgets.")
    if baseline.get("arm") != "A" or candidate.get("arm") not in {"B", "D"}:
        raise ProjectError("comparison_arm", "Compare baseline A against candidate B or D explicitly.")
    left, right = baseline["group_scores"], candidate["group_scores"]
    if not left or set(left) != set(right):
        raise ProjectError("comparison_groups", "Comparison requires matching supported-task groups.")
    deltas = [right[group] - left[group] for group in sorted(left)]
    rng = random.Random(SCORING_POLICY["bootstrap_seed"])
    samples = sorted(sum(rng.choices(deltas, k=len(deltas))) / len(deltas)
                     for _ in range(SCORING_POLICY["bootstrap_resamples"]))
    low, high = samples[4], samples[194]
    gain = sum(deltas) / len(deltas)
    fixture = baseline["fixture_only"] or candidate["fixture_only"]
    review_complete = baseline["metrics"]["review_coverage"] == candidate["metrics"]["review_coverage"] == 1
    # A numerical gain alone cannot supply the remaining scientific/regression gates.
    return {"observed_gain": gain, "paired_group_interval_95": [low, high], "groups": len(deltas),
            "fixture_only": fixture, "review_complete": review_complete,
            "gain_supported": not fixture and review_complete and len(deltas) >= 20 and gain >= 0.05 and low > 0,
            "release_qualified": False, "regression_review": "pending",
            "interpretation": "Fixture-only arithmetic" if fixture else "Paired observed comparison; complete scientific and regression review before promotion."}
