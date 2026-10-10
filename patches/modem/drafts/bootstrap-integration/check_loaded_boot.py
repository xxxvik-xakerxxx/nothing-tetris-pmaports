#!/usr/bin/env python3
"""Local source checks; load-owner boundary faults are CI-only, not AUTH tests."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
PIN = "a0f68555123ad441cccd61d89d7176e68142c434"
BOARD = "board/mediatek/mt6878/"


def static_check():
    source = (HERE / "tetris_modem_loaded_boot.c").read_text()
    ordered = ["tetris_scp_check_atf_profile(dev)", "ret = cold_off();",
               "tetris_modem_reserve_diagnostic_window(fdt",
               "tetris_modem_reserve_boot_bank(fdt, 0",
               "tetris_modem_reserve_boot_bank(fdt, 1",
               "firmware = map_sysmem", "tetris_modem_load_slot_rows_b41(dev",
               "tetris_modem_initialize_smem_b41(&loaded",
               "tetris_modem_bootstrap_once(dev, boot)"]
    positions = [source.index(item) for item in ordered]
    assert positions == sorted(positions)
    assert "owner.report.error ? owner.report.error : -EALREADY" in source
    assert "lmb_free" not in source and "writel" not in source
    assert "r->nc.capacity = 0x8000000ULL" in source
    assert "r->cache.capacity = 0x8000000ULL" in source
    patch = (HERE / "retained-source-storage.patch").read_text()
    ordered = ["read_snapshot(&storage", "tetris_modem_prepare_bundle_b41(buffer",
               "ret = tetris_modem_emi_rows_b41(", "memcpy(destination",
               "release_ret = release_staging", "tetris_modem_sync_payloads(destination",
               "*rows = produced"]
    positions = [patch.index(item) for item in ordered]
    assert positions == sorted(positions)
    assert patch.count("tetris_modem_prepare_bundle_b41(buffer") == 1
    assert "tetris_modem_place_bundle_b41(" not in patch
    print("PASS: static load/derive/release/coherency/one-shot order; NOT C or AUTH execution")


def native_ci(uboot):
    if os.environ.get("CI") != "true":
        raise SystemExit("C compilation/execution is CI-only")
    with tempfile.TemporaryDirectory(prefix="tetris-loaded-boot-") as directory:
        root = Path(directory)
        for name in ("tetris_modem_layout.c", "tetris_modem_layout.h", "tetris_modem_emi.h", "tetris_modem_emi.c",
                     "tetris_modem_remap.h", "tetris_modem_bundle.h",
                     "tetris_modem_storage.h", "tetris_modem_reserve.h", "tetris_scp_security.h"):
            (root / name).write_bytes(subprocess.check_output([
                "git", "-C", str(uboot), "show", f"{PIN}:{BOARD}{name}"]))
        for name in ("tetris_modem_loaded_boot.c", "tetris_modem_loaded_boot.h",
                     "tetris_modem_bootstrap.h", "tetris_modem_boot_secure.h", "test_loaded_boot.c"):
            (root / name).write_bytes((HERE / name).read_bytes())
        (root / "tetris_modem_emi_rows.h").write_bytes(
            (HERE.parent / "emi-rows" / "tetris_modem_emi_rows.h").read_bytes())
        # Only new declarations from reviewed patches; mocked callees are
        # explicitly test boundaries, not alternative production providers.
        for patch, header in (("retained-source-storage.patch", "tetris_modem_storage.h"),
                              ("aligned-service-reserve.patch", "tetris_modem_reserve.h")):
            first = (HERE / patch).read_text().split("diff --git")[1]
            additions = "\n".join(line[1:] for line in first.splitlines()
                                  if line.startswith("+") and not line.startswith("+++"))
            original = (root / header).read_text()
            offset = original.rindex("#endif")
            (root / header).write_text(original[:offset] + additions + "\n" + original[offset:])
        headers = {
            "linux/errno.h": "#include <asm-generic/errno.h>\n",
            "linux/string.h": "#include <string.h>\n",
            "asm/cache.h": "#define ARCH_DMA_MINALIGN 64\n",
            "asm/global_data.h": (
                "#ifndef TEST_GD_H\n#define TEST_GD_H\n"
                "struct bd_info { struct { unsigned long long start, size; } bi_dram[1]; };\n"
                "struct global_data { struct bd_info *bd; };\n"
                "extern struct global_data *gd;\n#define DECLARE_GLOBAL_DATA_PTR\n"
                "#define CONFIG_NR_DRAM_BANKS 1\n#endif\n"),
            "asm/u-boot.h": "#include <asm/global_data.h>\n",
            "asm/io.h": "unsigned int readl(const volatile void *);\n",
            "asm/system.h": "unsigned int current_el(void);\n",
            "cpu_func.h": "void flush_dcache_range(unsigned long, unsigned long);\n",
            "mapmem.h": "void *map_sysmem(unsigned long long, unsigned long);\n"
                        "void unmap_sysmem(const void *);\n",
        }
        for name, content in headers.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        binary = root / "test-loaded"
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-O1", "-g",
                        "-DTETRIS_MODEM_LAYOUT_HOST_TEST", "-I", str(root),
                        *(str(root / name) for name in ("tetris_modem_layout.c", "tetris_modem_emi.c",
                          "tetris_modem_loaded_boot.c", "test_loaded_boot.c")),
                        "-o", str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1",
                   UBSAN_OPTIONS="halt_on_error=1")
        for case in range(17):
            subprocess.run([str(binary), str(case)], check=True, env=env)
        print("PASS: 17 native load-owner boundary faults; AUTH/allocator/bootstrap are mocked")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--uboot", type=Path)
    args = parser.parse_args()
    static_check()
    if args.native_ci:
        if not args.uboot:
            parser.error("native CI requires --uboot")
        native_ci(args.uboot)


if __name__ == "__main__":
    main()
