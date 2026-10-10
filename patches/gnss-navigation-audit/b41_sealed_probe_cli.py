#!/usr/bin/env python3
"""Dedicated Linux root admission and exec handoff; never call a vendor API."""
import argparse
import errno
import os
from pathlib import Path
import stat
import time

from b41_mipc_probe_resources import ProbeResources, PROBE_SHA, MNL_SHA
from b41_mipc_provider_resources import LoaderResources, _close_preserving
from b41_mipc_sealed_stage import seal_provider


class SelectedProbeResources(ProbeResources):
    """Reuse ProbeResources ownership with independent selected/probe artifacts."""
    def __init__(self, selected, probe_artifact, mnl_layout):
        if mnl_layout not in ("vendor/lib64/libmnl.so", "vendor/lib64/mt6878/libmnl.so"):
            raise ValueError("explicit selected-artifact libmnl layout required")
        self.base = LoaderResources(selected, selected)
        self.extra = []
        try:
            for path, pin, mode in ((Path(probe_artifact) / "probe", PROBE_SHA, 0o555),
                                   (Path(selected) / mnl_layout, MNL_SHA, 0o444)):
                source = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    copy = seal_provider(source, pin)
                    self.extra.append(copy)
                    os.fchmod(copy, mode)
                except BaseException as error:
                    try:
                        os.close(source)
                    except BaseException as cleanup:
                        error.add_note(f"source cleanup also failed: {cleanup}")
                    raise
                else:
                    os.close(source)
        except BaseException as error:
            _close_preserving(self, error)
            raise


def trusted_ancestors(path):
    path = Path(path)
    if not path.is_absolute() or str(path) != os.path.normpath(str(path)):
        raise ValueError("absolute canonical trusted path required")
    for directory in path.parents:
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid or info.st_mode & 0o022:
            raise OSError(errno.EPERM, "untrusted path ancestor", str(directory))
    return path


def trusted_parent(path):
    """Open trusted native CI executable once; exec its FD, never reopen by path."""
    path = trusted_ancestors(path)
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid or info.st_mode & 0o022 or
                not info.st_mode & 0o111 or os.pread(fd, 4, 0) != b"\x7fELF"):
            raise OSError(errno.EPERM, "trusted native CI parent required")
        return fd
    except BaseException as error:
        try:
            os.close(fd)
        except BaseException as cleanup:
            error.add_note(f"parent cleanup also failed: {cleanup}")
        raise


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selected-stock", required=True, type=Path)
    parser.add_argument("--probe-artifact", required=True, type=Path)
    parser.add_argument("--parent", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--mnl-layout", required=True,
                        choices=("vendor/lib64/libmnl.so", "vendor/lib64/mt6878/libmnl.so"))
    parser.add_argument("--mode", required=True, choices=("control", "load"))
    return parser.parse_args()


def main():
    args = arguments()
    if (os.geteuid() or os.execve not in os.supports_fd or
            len(list(Path("/proc/self/task").iterdir())) != 1):
        raise OSError(errno.EPERM, "dedicated Linux root process and FD exec required")
    for fd in range(3):
        os.fstat(fd)  # Ensure subsequent owned opens cannot alias standard FDs.
    # Absolute budget includes admission/copying, not just the eventual dlopen.
    deadline = time.monotonic_ns() + 20_000_000_000
    parent = trusted_parent(args.parent)
    resources, moved = None, []
    try:
        resources = SelectedProbeResources(args.selected_stock, args.probe_artifact, args.mnl_layout)
        moved = resources.move()
        for fd in moved:
            os.set_inheritable(fd, True)
        # Avoid terminal/socket/pipe inheritance. Operator must choose an
        # exclusively controlled log directory; C validates the resulting FDs.
        log = os.open(trusted_ancestors(args.log), os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            null = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                os.dup2(null, 0)
                os.dup2(log, 1)
                os.dup2(log, 2)
            finally:
                os.close(null)
        finally:
            os.close(log)
        argv = ["b41-sealed-probe-parent", args.mode, str(deadline), str(deadline + 5_000_000_000),
                *map(str, moved)]
        # Same process: no Python wait thread, second reaper or duplicate lease.
        os.execve(parent, argv, {"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
    except BaseException as error:
        for fd in [*moved, parent]:
            try:
                os.close(fd)
            except BaseException as cleanup:
                error.add_note(f"handoff cleanup also failed: {cleanup}")
        if resources is not None:
            _close_preserving(resources, error)
        raise


if __name__ == "__main__":
    main()
