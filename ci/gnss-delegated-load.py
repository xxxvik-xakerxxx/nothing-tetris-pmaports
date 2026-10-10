#!/usr/bin/env python3
"""Enable memory delegation only inside this fresh, dedicated CI service."""
import os
from pathlib import Path
import re
import sys


def owned_group(text, unit, pid, filesystem=Path("/sys/fs/cgroup")):
    if not re.fullmatch(r"tetris-sealed-[0-9]+-[0-9]+\.service", unit):
        raise ValueError("dedicated CI service identity required")
    expected = f"/system.slice/{unit}"
    if text.splitlines() != [f"0::{expected}"]:
        raise ValueError("process is not in the expected dedicated service")
    group = filesystem / expected.lstrip("/")
    if (group / "cgroup.procs").read_text().split() != [str(pid)]:
        raise RuntimeError("fresh delegated service must contain only this observer")
    if "memory" not in (group / "cgroup.controllers").read_text().split():
        raise RuntimeError("systemd did not delegate the memory controller")
    if (group / "cgroup.subtree_control").read_text().strip():
        raise RuntimeError("expected fresh unused service delegation")
    return group


def main():
    if os.environ.get("CI") != "true" or os.geteuid() or len(sys.argv) != 2:
        raise RuntimeError("dedicated root CI invocation required")
    if len(list(Path("/proc/self/task").iterdir())) != 1:
        raise RuntimeError("single-thread observer required")
    group = owned_group(Path("/proc/self/cgroup").read_text(),
                        os.environ["TETRIS_UNIT"], os.getpid())
    observer = group / "observer"
    observer.mkdir(exist_ok=False)
    (observer / "cgroup.procs").write_text(str(os.getpid()))
    if (group / "cgroup.procs").read_text().strip():
        raise RuntimeError("service delegation is still populated; refusing controller change")
    # Systemd owns the service limits. Only its newly delegated subtree changes.
    (group / "cgroup.subtree_control").write_text("+memory")
    script = Path(sys.argv[1])
    if not script.is_absolute():
        raise ValueError("absolute aggregate CI script required")
    environment = {**os.environ, "TETRIS_CGROUP_PARENT": str(group)}
    os.execve("/bin/sh", ["sh", str(script)], environment)


if __name__ == "__main__":
    main()
