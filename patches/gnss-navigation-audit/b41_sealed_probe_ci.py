#!/usr/bin/env python3
"""Actual CI control/load invocations, with a dedicated bounded child cgroup."""
import argparse
import json
import os
import platform
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from b41_sealed_probe_cli import trusted_ancestors, trusted_parent


def require_ci():
    if os.environ.get("CI") != "true" or os.geteuid():
        raise RuntimeError("dedicated Linux root CI required")
    if platform.system() != "Linux" or platform.machine() not in ("aarch64", "arm64"):
        raise RuntimeError("actual ARM64 Linux required for the pinned Bionic executable")
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise RuntimeError("single-thread CI runner required")


def delegated_parent(path):
    path = Path(path)
    if not path.is_relative_to("/sys/fs/cgroup") or path == Path("/sys/fs/cgroup"):
        raise ValueError("explicit delegated cgroup-v2 child required, not the hierarchy root")
    path = trusted_ancestors(path)
    # No controller enablement or limit changes on an existing/global cgroup.
    if "memory" not in (path / "cgroup.subtree_control").read_text().split():
        raise RuntimeError("parent must already delegate the memory controller")
    if not (path / "cgroup.controllers").is_file():
        raise RuntimeError("cgroup-v2 delegation required")
    return path


def enter(group, arguments):
    require_ci()
    # Parent-created fresh kernel cgroup; the actual native adapter independently
    # verifies /proc/self/cgroup and memory.max before any vendor child fork.
    group = trusted_ancestors(group)
    if not group.is_relative_to("/sys/fs/cgroup"):
        raise ValueError("kernel cgroup path required")
    if (group / "memory.max").read_text().strip() != str(128 * 1024 * 1024):
        raise RuntimeError("fresh cgroup must have an actual128 MiB limit")
    (group / "cgroup.procs").write_text(str(os.getpid()))
    script = Path(__file__).with_name("b41_sealed_probe_cli.py")
    os.execve(sys.executable, [sys.executable, str(script), *arguments], dict(os.environ))


def verify_result(mode, text, returncode):
    if mode not in ("control", "load", "xml-control", "xml-load"):
        raise ValueError("fixed load-only mode required")
    if returncode != 0:
        raise RuntimeError(f"{mode} parent exited {returncode}; retain logs")
    if "QUARANTINE:" in text or len(re.findall(r"^TERMINAL: status=0 first=0$", text, re.M)) != 1:
        raise RuntimeError("missing unique successful terminal reap acknowledgement")
    expected = ("CONTROL: eight network/device/namespace/privilege denials, failures=0"
                if mode in ("control", "xml-control") else
                "LOAD_OK: no vendor API called; no dlclose or destructors")
    if text.splitlines().count(expected) != 1 or "LOAD_FAILED:" in text:
        raise RuntimeError(f"missing actual {mode} output")
    xml_output = "XML_ROOT_OK: fixed config readable; data absent; writes denied"
    if text.splitlines().count(xml_output) != (1 if mode == "xml-control" else 0):
        raise RuntimeError("unexpected or missing XML root control acknowledgement")


def run_one(mode, args, group_parent, results):
    group = Path(tempfile.mkdtemp(prefix=f"b41-{mode}-", dir=group_parent))
    log = results / f"{mode}.log"
    report = {"mode": mode, "cgroup": str(group), "log": str(log), "status": "admitting"}
    failure = None
    try:
        (group / "memory.max").write_text(str(128 * 1024 * 1024))
        command = [sys.executable, str(Path(__file__).resolve()), "enter", str(group),
            "--selected-stock", str(args.selected_stock), "--probe-artifact", str(args.probe_artifact),
            "--parent", str(args.parent), "--log", str(log), "--mnl-layout", args.mnl_layout,
            "--mode", mode]
        admission_log = results / f"{mode}-admission.log"
        with open(os.devnull, "rb") as input_stream, admission_log.open("xb") as output_stream:
            child = subprocess.Popen(command, stdin=input_stream, stdout=output_stream,
                stderr=output_stream, close_fds=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        report["parent_pid"] = child.pid
        try:
            returncode = child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            # Do not kill the sole reaper, delete containment, or describe forced
            # group termination as terminal vendor reap. Parent keeps its lease.
            report["status"] = "quarantined-parent-running"
            raise RuntimeError(f"parent {child.pid} exceeded observation budget; containment retained")
        report["parent_returncode"] = returncode
        if (group / "cgroup.procs").read_text().strip():
            raise RuntimeError("parent exited but containment still populated; retained")
        if not log.exists() or log.stat().st_size > 1024 * 1024:
            raise RuntimeError("missing or oversized dedicated CLI log")
        verify_result(mode, log.read_text(), returncode)
        report["status"] = "passed-terminal-reap"
        group.rmdir()
        return report
    except BaseException as error:
        failure = error
        report["error"] = str(error)
        report.setdefault("status", "failed")
        if report["status"] == "admitting":
            report["status"] = "failed-retained-containment"
        raise
    finally:
        try:
            (results / f"{mode}-result.json").write_text(json.dumps(report, indent=2) + "\n")
        except BaseException as error:
            if failure is None:
                raise
            failure.add_note(f"result recording also failed: {error}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "enter":
        if len(sys.argv) < 4:
            raise ValueError("internal enter requires group and admission arguments")
        enter(Path(sys.argv[2]), sys.argv[3:])
        raise RuntimeError("FD admission exec unexpectedly returned")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-stock", required=True, type=Path)
    parser.add_argument("--probe-artifact", required=True, type=Path)
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--cgroup-parent", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--mnl-layout", required=True,
        choices=("vendor/lib64/libmnl.so", "vendor/lib64/mt6878/libmnl.so"))
    parser.add_argument("--xml-snapshot", action="store_true")
    args = parser.parse_args()
    require_ci()
    for name in ("selected_stock", "probe_artifact", "parent", "cgroup_parent", "results"):
        if not getattr(args, name).is_absolute():
            raise ValueError(f"absolute {name} input required")
    fd = trusted_parent(args.parent)
    os.close(fd)
    delegation = delegated_parent(args.cgroup_parent)
    results = trusted_ancestors(args.results)
    results.mkdir(mode=0o700, exist_ok=False)
    rows = []
    xml_snapshot = getattr(args, "xml_snapshot", False)
    for mode in (("xml-control", "xml-load") if xml_snapshot else ("control", "load")):
        rows.append(run_one(mode, args, delegation, results))
    (results / "RESULT.json").write_text(json.dumps({"status": "load-only-passed",
        "xml_snapshot": xml_snapshot, "engine_init_called": False,
        "hardware_readiness": False, "runs": rows}, indent=2) + "\n")
    print(f"Actual sealed control/load and terminal reap passed; logs: {results}")


if __name__ == "__main__":
    main()
