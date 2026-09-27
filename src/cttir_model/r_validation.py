"""Linux bubblewrap workers: no host home, credentials, network or user eval."""

import os
import shutil
import signal
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path

from .errors import ProjectError


def run_worker(mode: str, content: str = "") -> str:
    if mode not in {"parse", "fixture", "isolation", "rd"} or len(content.encode()) > 60000:
        raise ProjectError("r_input", "Unsupported R worker mode or oversized input.")
    if not all(shutil.which(tool) for tool in ("bwrap", "prlimit", "Rscript")):
        raise ProjectError("sandbox_unavailable", "Linux bwrap, prlimit and Rscript are required; there is no unsandboxed fallback.")
    with tempfile.TemporaryDirectory(prefix="cttir-r-") as directory:
        root = Path(directory)
        (root / "worker.R").write_bytes(files("cttir_model").joinpath("r_worker.R").read_bytes())
        (root / ("source.Rd" if mode == "rd" else "code.R")).write_text(content)
        args = ["prlimit", "--as=1073741824", "--cpu=5", "--fsize=131072", "--nofile=256", "--",
                "bwrap", "--unshare-all", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
                "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
                "--ro-bind", "/etc/R", "/etc/R", "--ro-bind", "/etc/alternatives", "/etc/alternatives",
                "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache", "--proc", "/proc", "--dev", "/dev",
                "--tmpfs", "/tmp", "--dir", "/work", "--chdir", "/work",
                "--ro-bind", str(root), "/input", "--clearenv",
                "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/tmp",
                "--setenv", "R_LIBS_USER", "/nonexistent", "--setenv", "R_LIBS_SITE", "/nonexistent",
                "--setenv", "OMP_NUM_THREADS", "1", "--setenv", "OPENBLAS_NUM_THREADS", "1",
                "--setenv", "LANG", "C.UTF-8", "/usr/bin/prlimit", "--nproc=16", "--",
                "/usr/bin/Rscript", "--vanilla", "/input/worker.R", mode]
        # Bounded files avoid unbounded communicate() allocations from worker output.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            proc = subprocess.Popen(args, stdout=stdout, stderr=stderr, start_new_session=True,
                                    env={"PATH": "/usr/bin:/bin"})
            try:
                code = proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise ProjectError("r_timeout", "Isolated R worker exceeded its time budget.")
            stdout.seek(0)
            output = stdout.read(131073)
            if code or len(output) > 131072:
                raise ProjectError("sandbox_failed", "Isolated R worker failed; inspect platform support. No unsandboxed retry was made.")
            return output.decode("utf-8")


def parse_r(code: str, api_catalog: dict | None = None) -> dict:
    output = run_worker("parse", code)
    calls, status = [], None
    for line in output.splitlines():
        parts = line.split("\t")
        if parts[0] == "STATUS":
            status = parts[1]
        elif parts[0] == "CALL" and len(parts) == 4:
            calls.append({"package": parts[1], "symbol": parts[2],
                          "arguments": parts[3].split(",") if parts[3] else []})
    if status not in {"parsed", "unsupported", "syntax_error"}:
        raise ProjectError("r_worker_protocol", "R worker returned an unexpected result.")
    api_errors = []
    if api_catalog is not None and status == "parsed":
        for call in calls:
            item = api_catalog.get(call["package"] + "::" + call["symbol"])
            if not item or item.get("approved") is not True or not item.get("version"):
                api_errors.append("unknown_or_unapproved_api")
                continue
            # Reject positional and dots arguments until a reviewed adapter can resolve them.
            if any(arg not in item.get("arguments", []) or arg == "_positional" for arg in call["arguments"]):
                api_errors.append("unsupported_arguments")
    return {"parsed": status != "syntax_error", "static_subset_supported": status == "parsed",
            "calls": calls, "api_checked": bool(api_catalog is not None and status == "parsed" and not api_errors),
            "api_errors": api_errors, "executed": False, "scientifically_reviewed": False}
