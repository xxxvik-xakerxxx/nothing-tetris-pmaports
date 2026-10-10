#!/usr/bin/env python3
"""CI-only exact production storage-caller extraction and boundary fault tests."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PIN = "a0f68555123ad441cccd61d89d7176e68142c434"
BOARD = "board/mediatek/mt6878/"


def extracted():
    patch = (HERE / "retained-handoff-storage.patch").read_text()
    additions = "\n".join(line[1:] for line in patch.split("tetris_modem_storage.c\n+++", 1)[1].splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
    start = additions.index("int tetris_modem_load_slot_handoff_b41(")
    caller = additions[start:]
    assert caller.count("tetris_modem_prepare_bundle_b41(") == 1
    assert caller.count("release_staging(") == 1
    assert caller.count("tetris_modem_sync_payloads(") == 1
    assert caller.rstrip().endswith("}")
    return caller + "\n"


def native_ci(uboot):
    if os.environ.get("CI") != "true":
        raise SystemExit("C compilation/execution is CI-only")
    with tempfile.TemporaryDirectory(prefix="tetris-storage-lifetime-") as directory:
        root = Path(directory)
        for name in ("tetris_modem_bundle.h", "tetris_modem_layout.h",
                     "tetris_modem_emi.h", "tetris_scp_security.h"):
            (root / name).write_bytes(subprocess.check_output([
                "git", "-C", str(uboot), "show", f"{PIN}:{BOARD}{name}"]))
        (root / "tetris_modem_emi_rows.h").write_bytes(
            (HERE.parent / "emi-rows/tetris_modem_emi_rows.h").read_bytes())
        (root / "extracted_storage.inc").write_text(extracted())
        (root / "test_storage_lifetime.c").write_bytes((HERE / "test_storage_lifetime.c").read_bytes())
        binary = root / "test-storage"
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-O1", "-g",
                        "-I", str(root), str(root / "test_storage_lifetime.c"), "-o", str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1")
        for case in range(14):
            subprocess.run([str(binary), str(case)], check=True, env=env)
        print("PASS: 14 exact storage-caller boundary faults; crypto/LMB/cache providers mocked")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--uboot", type=Path)
    args = parser.parse_args()
    extracted()
    print("PASS: exact caller extraction; NOT C/authentication execution")
    if args.native_ci:
        if not args.uboot:
            parser.error("--native-ci requires --uboot")
        native_ci(args.uboot)


if __name__ == "__main__":
    main()
