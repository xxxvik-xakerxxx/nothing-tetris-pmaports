#!/usr/bin/env python3
"""Source checks by default; explicit CI-only actual-body ASan/UBSan fixture."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from pinned_helpers import HERE, oracle_c, sources


def native_ci(uboot):
    if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("native compilation/execution is GitHub CI-only; parent must schedule CI")
    src = sources(uboot)
    with tempfile.TemporaryDirectory(prefix="smem-boot-evidence-") as temporary:
        root = Path(temporary)
        oracle = root / "oracle.c"
        oracle.write_text(oracle_c(src))
        binary = root / "test-boot-evidence"
        subprocess.run([
            os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-O1", "-g",
            "-DTETRIS_SMEM_BOOT_HOST_TEST", "-I", str(HERE),
            "-I", str(HERE.parent / "runtime-metadata"),
            str(HERE / "boot_evidence.c"), str(HERE / "test_boot_evidence.c"), str(oracle),
            "-o", str(binary),
        ], check=True)
        roundtrip = root / "roundtrip"
        subprocess.run([
            os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=undefined",
            "-fno-omit-frame-pointer", "-O1", "-g", "-DTETRIS_SMEM_BOOT_HOST_TEST",
            "-DTETRIS_MODEM_LAYOUT_HOST_TEST", "-I", str(HERE), "-I", str(uboot),
            "-I", str(HERE.parent / "runtime-metadata"),
            str(HERE / "boot_evidence.c"), str(HERE / "test_roundtrip.c"), str(oracle),
            str(uboot / "board/mediatek/mt6878/tetris_modem_smem_evidence.c"),
            "-o", str(roundtrip),
        ], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1")
        subprocess.run([str(binary)], check=True, env=env)
        subprocess.run([str(roundtrip)], check=True, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uboot", type=Path, default=HERE.parents[4] / "u-boot-mt6878")
    parser.add_argument("--native-ci", action="store_true")
    args = parser.parse_args()
    if args.native_ci and (os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true"):
        parser.error("native compilation/execution is GitHub CI-only; parent must schedule CI")
    os.environ["TETRIS_BOOT_EVIDENCE_UBOOT"] = str(args.uboot.resolve())
    import test_source
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_source)
    if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
        raise SystemExit(1)
    print("PASS: source-only checks; no C compilation/execution")
    if args.native_ci:
        native_ci(args.uboot)


if __name__ == "__main__":
    main()
