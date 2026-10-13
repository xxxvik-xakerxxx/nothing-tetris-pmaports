#!/usr/bin/env python3
"""Static locally; opt-in actual-source/controller native fixtures only in CI."""
import argparse
import os
from pathlib import Path
import resource
import shlex
import subprocess
import tempfile

import generate as g


def checked(argv, **kwargs):
    return subprocess.run(argv, check=True, timeout=60, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=g.MODULES)
    parser.add_argument("--libmnl", type=Path, default=Path(os.environ.get("TETRIS_B41_LIBMNL",
        "/private/tmp/tetris-b41-providers-ci38048111345/vendor/lib64/mt6878/libmnl.so")))
    parser.add_argument("--ci-native", action="store_true")
    args = parser.parse_args()
    if args.ci_native and not (os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true"):
        parser.error("native compilation is GitHub CI-only")
    env = dict(os.environ, TETRIS_MODULES_TREE=str(args.vendor.resolve()),
               TETRIS_B41_LIBMNL=str(args.libmnl.resolve()), PYTHONDONTWRITEBYTECODE="1")
    checked([os.sys.executable, "-B", str(g.HERE / "test_static.py")], env=env)
    if not args.ci_native:
        print("PASS: static only; no compilation/device access")
        return
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    compiler = shlex.split(os.environ.get("CC", "clang"))
    with tempfile.TemporaryDirectory(prefix="session-native-", dir=g.HERE) as directory:
        work = Path(directory)
        baseline = g.baseline(args.vendor)
        (work / "real_source.c").write_text(g.fixture(baseline))
        declarations = []
        for path, name in ((g.BASE + "plat/v051/inc/gps_dl_config.h", "gps_dl_link_id_enum"),
                           (g.FSM_H, "gps_dsp_state_t"),
                           (g.BASE + "inc/gps_each_link.h", "gps_each_link_state_enum")):
            declarations.append(g.write.read.declaration(g.write.source(path, args.vendor), "enum", name))
        (work / "real_types.h").write_text("\n".join(declarations))
        flags = ["-O1", "-g", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                 "-fno-omit-frame-pointer", "-I", str(work)]
        binary = work / "kernel-snapshot"
        checked([*compiler, "-std=gnu11", *flags, str(g.HERE / "native_harness.c"), "-o", str(binary)], env=env)
        checked([str(binary)], env=env)
        binary = work / "native-controller"
        wraps = ["-Wl,--wrap=" + name for name in ("clock_gettime", "fcntl", "fstat", "lstat", "ioctl", "write", "close")]
        checked([*compiler, "-std=c11", *flags, "-Wconversion", "-Wshadow", str(g.HERE / "session.c"),
                 str(g.HERE / "test_session.c"), *wraps, "-o", str(binary)], env=env)
        checked([str(binary)], env=env)
        binary = work / "session-help"
        checked([*compiler, "-std=c11", *flags, "-Wconversion", "-Wshadow", "-DSESSION_CLI_GUARD",
                 str(g.HERE / "session.c"), str(g.HERE / "session-tool.c"), str(g.HERE / "test_session.c"),
                 "-Wl,--wrap=ioctl", "-Wl,--wrap=write", "-o", str(binary)], env=env)
        checked([str(binary), "--help"], env=env)
        for argv in ([], ["--help", "1"], ["--unknown"], ["-1"], ["0", "--unknown"],
                     ["0", "--stop", "0"], ["0", "--wait-work", "30001"]):
            result = subprocess.run([str(binary), *argv], env=env, timeout=20, capture_output=True)
            if result.returncode != 2:
                raise SystemExit("argument fixture reached acquisition or failed unexpectedly")
    print("PASS: native fixtures only; not a full matching kernel/module build or hardware validation")


if __name__ == "__main__":
    main()
