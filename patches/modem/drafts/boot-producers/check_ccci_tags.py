#!/usr/bin/env python3
"""CI-only consumer-ABI tags using public stock metadata, not firmware AUTH."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PIN = "a0f68555123ad441cccd61d89d7176e68142c434"


def native_ci(uboot, stock):
    if os.environ.get("CI") != "true":
        raise SystemExit("C compilation/execution is CI-only")
    with tempfile.TemporaryDirectory(prefix="tetris-ccci-tags-") as directory:
        root = Path(directory)
        for name in ("tetris_modem_layout.c", "tetris_modem_layout.h", "tetris_modem_bundle.h",
                     "tetris_modem_emi.c", "tetris_modem_emi.h", "tetris_modem_remap.h"):
            (root / name).write_bytes(subprocess.check_output([
                "git", "-C", str(uboot), "show", f"{PIN}:board/mediatek/mt6878/{name}"]))
        for name in ("tetris_modem_ccci_tags.c", "tetris_modem_ccci_tags.h", "test_ccci_tags.c"):
            (root / name).write_bytes((HERE / name).read_bytes())
        for name in ("tetris_modem_loaded_boot.h", "tetris_modem_bootstrap.h", "tetris_modem_boot_secure.h"):
            (root / name).write_bytes((HERE.parent / "bootstrap-integration" / name).read_bytes())
        for name in ("tetris_modem_emi_rows.c", "tetris_modem_emi_rows.h"):
            (root / name).write_bytes((HERE.parent / "emi-rows" / name).read_bytes())
        linux = root / "linux"
        linux.mkdir()
        (linux / "errno.h").write_text("#include <asm-generic/errno.h>\n")
        (linux / "string.h").write_text("#include <string.h>\n")
        binary = root / "test-tags"
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-O1", "-g",
                        "-DTETRIS_MODEM_LAYOUT_HOST_TEST", "-I", str(root),
                        *(str(root / name) for name in ("tetris_modem_layout.c", "tetris_modem_emi.c",
                          "tetris_modem_emi_rows.c", "tetris_modem_ccci_tags.c", "test_ccci_tags.c")),
                        "-o", str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1")
        for case in range(9):
            subprocess.run([str(binary), str(stock), str(case)], check=True, env=env)
        print("PASS: 9 public-stock tag ABI/atomic fault cases; synthetic BROM report, NOT AUTH/readiness")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--uboot", type=Path)
    parser.add_argument("--stock-container", type=Path)
    args = parser.parse_args()
    source = (HERE / "tetris_modem_ccci_tags.c").read_text()
    assert '"md1_smem_cahce_offset"' in source
    assert "report->hardware.reply[2] != 0x100000001ULL" in source
    assert "report->hardware.reply[3] != 0x100000001ULL" in source
    for forbidden in ("readl", "writel", "arm_smccc", "fdt_setprop", "map_sysmem"):
        assert forbidden not in source
    assert source.count("\n\tTAG(") == 21
    print("PASS: static tag producer boundary; NOT C/authentication/BROM execution")
    if args.native_ci:
        if not args.uboot or not args.stock_container:
            parser.error("--native-ci requires --uboot and --stock-container")
        native_ci(args.uboot, args.stock_container)


if __name__ == "__main__":
    main()
