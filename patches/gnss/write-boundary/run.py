#!/usr/bin/env python3
"""Static locally; opt-in actual-source ASan/UBSan fixture in GitHub CI only."""
import argparse
import os
from pathlib import Path
import resource
import shlex
import subprocess
import tempfile

import generate as g


def checked(argv, **kwargs):
    subprocess.run(argv, check=True, timeout=60, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=g.MODULES)
    parser.add_argument("--ci-native", action="store_true")
    args = parser.parse_args()
    if args.ci_native and not (os.environ.get("CI") == "true" and
                              os.environ.get("GITHUB_ACTIONS") == "true"):
        parser.error("native compilation is CI-only; requires CI=true and GITHUB_ACTIONS=true")
    vendor = args.vendor.resolve()
    env = dict(os.environ, TETRIS_MODULES_TREE=str(vendor), PYTHONDONTWRITEBYTECODE="1")
    if args.ci_native:
        env["WRITE_BOUNDARY_REQUIRE_GNU_PATCH"] = "1"
    checked([os.sys.executable, "-B", str(g.HERE / "test_write_boundary.py")], env=env)
    if not args.ci_native:
        print("PASS: static only; no native compilation or device access")
        return
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    baseline = g.stacked(vendor)
    fixed = g.fixture(vendor, baseline=baseline)
    cases = {"fixed": fixed, "original": g.fixture(vendor, originals=True, baseline=baseline),
             **g.mutations(fixed)}
    with tempfile.TemporaryDirectory(prefix="native-", dir=g.HERE) as directory:
        work = Path(directory)
        (work / "real_types.h").write_text(g.fixture_types(vendor))
        flags = ["-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                 "-Wno-unused-function", "-Wno-unused-parameter",
                 "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I", str(work)]
        compiler = shlex.split(os.environ.get("CC", "cc"))
        for no_irq in (0, 1):
            for name, text in cases.items():
                if no_irq == 0 and name in ("without-completion-guard", "legacy-forced-completion"):
                    continue  # Completion waiting exists only in the polling build.
                (work / "real_source.c").write_text(text)
                binary = work / f"write-{no_irq}-{name}"
                checked([*compiler, *flags, f"-DGPS_DL_NO_USE_IRQ={no_irq}",
                         f"-DWRITE_BOUNDARY_ORIGINAL={int(name == 'original')}",
                         str(g.HERE / "native_harness.c"), "-o", str(binary)], env=env)
                result = subprocess.run([str(binary)], env=env, timeout=20,
                                        capture_output=True, text=True)
                if name == "fixed":
                    if result.returncode:
                        raise SystemExit(result.stdout + result.stderr)
                    print(f"PASS: actual TX production fixture NO_USE_IRQ={no_irq}")
                elif result.returncode == 0:
                    raise SystemExit(f"native regression escaped: {name}, NO_USE_IRQ={no_irq}")
                elif "Assertion" not in result.stderr and "Sanitizer" not in result.stderr:
                    raise SystemExit(f"negative control failed unexpectedly: {result.stderr}")
                else:
                    print(f"PASS: rejected {name}, NO_USE_IRQ={no_irq}")


if __name__ == "__main__":
    main()
