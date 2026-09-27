"""Run the small offline suite and retain machine-readable local evidence."""

import subprocess
import sys
import os
from pathlib import Path

from cttir_model.cli import pending_gates
from cttir_model.config import load_config
from cttir_model.preflight import inventory
from cttir_model.provenance import atomic_json, fingerprint, now, record_phase

root = Path(__file__).resolve().parents[1]
config = load_config(root / "configs/cpu.json")
command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
result = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=30)
print(result.stderr, end="")
report = inventory(config)
atomic_json(config.artifacts / "preflight.json", report)
entry = {
    "timestamp": now(), "phase": "cpu_tests", "command":
    ("CTTIR_TEST_SANDBOX=1 " if os.environ.get("CTTIR_TEST_SANDBOX") == "1" else "") + "python -m unittest discover -s tests -v",
    "exit_status": result.returncode, "state": "smoke_tested" if result.returncode == 0 else "failed",
    "input_sha256": fingerprint({str(p.relative_to(root)): p.read_text()
                                 for folder in ("src", "tests", "configs")
                                 for p in sorted((root / folder).rglob("*"))
                                 if p.is_file() and p.suffix in {".py", ".json"}}),
    "outputs": ["preflight.json", "implementation/gates.json"],
    "test_output": result.stderr[-16000:],
    "next_action": "Continue deferred R/broker work and obtain reviewed corpus; do not train on this laptop.",
}
gates = pending_gates()
for gate in gates:
    gate.update(timestamp=now(), command=None, exit_status=None, artifacts=[])
gates[0].update(status="pass", reason="Lightweight local inventory and CPU-only resource policy recorded; no GPU authorization.",
                command="scripts/check_cpu.py", exit_status=0, artifacts=["preflight.json"])
gates[1].update(reason="CPU foundation tests passed; remaining lifecycle commands explicitly deferred."
               if result.returncode == 0 else "CPU tests failed.",
               status="pending" if result.returncode == 0 else "fail",
               command=entry["command"], exit_status=result.returncode,
               artifacts=["implementation/ledger.json"])
atomic_json(config.artifacts / "implementation/gates.json",
            {"schema_version": 1, "gates": gates, "trained_candidate": False})
record_phase(config.artifacts, entry)
raise SystemExit(result.returncode)
