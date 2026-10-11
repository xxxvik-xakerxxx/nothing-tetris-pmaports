#!/usr/bin/env python3
"""Static checks locally; opt-in real-source native fixture in CI only."""
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
    parser.add_argument("--vendor", type=Path, default=g.MODULES,
                        help="pinned Git blobs from this tree; default TETRIS_MODULES_TREE")
    parser.add_argument("--ci-native", action="store_true",
                        help="compile/run real production C fixture in GitHub CI only")
    args = parser.parse_args()
    vendor = args.vendor.resolve()
    if args.ci_native and not (os.environ.get("CI") == "true" and
                              os.environ.get("GITHUB_ACTIONS") == "true"):
        parser.error("native compilation is CI-only; requires CI=true and GITHUB_ACTIONS=true")
    env = dict(os.environ, TETRIS_MODULES_TREE=str(vendor),
               READ_BOUNDARY_MODULES=str(vendor), PYTHONDONTWRITEBYTECODE="1")
    if args.ci_native:
        env["READ_BOUNDARY_REQUIRE_GNU_PATCH"] = "1"
    checked([os.sys.executable, str(g.HERE / "test_read_boundary.py")], env=env)
    if not args.ci_native:
        print("PASS: static-only run; no native compilation or device access")
        return

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    fixed = g.fixture(vendor)
    mutations = {
        "original": g.fixture(vendor, originals=True),
        "without-zero-read": fixed.replace("\tif (!count)\n\t\treturn 0;\n\n", "", 1),
        "without-bound": fixed.replace(
            "\tif (count > sizeof(dev->i_buf))\n\t\tcount = sizeof(dev->i_buf);\n", "", 1),
        "without-nonblock": fixed.replace("filp->f_flags & O_NONBLOCK", "0", 1),
        "without-zero-timeout": fixed.replace(
            "\t\t\tif (timeout_usec == 0)\n\t\t\t\treturn -EAGAIN;\n\n", "", 1),
        "without-rollback": fixed.replace(
            "\t\tgdl_dma_buf_set_data_entry(p_dma, NULL);\n", "", 1),
    }
    if any(text == fixed for text in mutations.values()):
        raise SystemExit("native mutation did not change the production fixture")
    with tempfile.TemporaryDirectory(prefix="native-", dir=g.HERE) as directory:
        work = Path(directory)
        (work / "real_types.h").write_text(g.fixture_types(vendor))
        flags = ["-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                 "-Wno-unused-function", "-Wno-unused-parameter",
                 "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-I", str(work)]
        compiler = shlex.split(os.environ.get("CC", "cc"))
        for no_irq in (0, 1):
            for name, text in {"fixed": fixed, **mutations}.items():
                (work / "real_source.c").write_text(text)
                binary = work / f"read-{no_irq}-{name}"
                checked([*compiler, *flags, f"-DGPS_DL_NO_USE_IRQ={no_irq}",
                         str(g.HERE / "native_harness.c"), "-o", str(binary)], env=env)
                result = subprocess.run([str(binary)], env=env, timeout=20,
                                        capture_output=True, text=True)
                if name == "fixed":
                    if result.returncode:
                        raise SystemExit(result.stdout + result.stderr)
                    print(f"PASS: real production fixture GPS_DL_NO_USE_IRQ={no_irq}")
                elif result.returncode == 0:
                    raise SystemExit(f"native regression escaped: {name}, NO_USE_IRQ={no_irq}")
                else:
                    if "Assertion" not in result.stderr and "Sanitizer" not in result.stderr:
                        raise SystemExit(f"negative control failed unexpectedly: {result.stderr}")
                    print(f"PASS: rejected {name}, GPS_DL_NO_USE_IRQ={no_irq}")


if __name__ == "__main__":
    main()
