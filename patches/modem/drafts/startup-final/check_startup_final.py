#!/usr/bin/env python3
"""New draft static checks locally; strict native production checks CI-only."""
import argparse
import ast
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
BASE = "94ead1146c93fef603db5c85820f2fb04c559c10"
BOARD = "board/mediatek/mt6878/"


def apply_file(original, section):
    """Exact-context in-memory application; never modify the shared checkout."""
    result = original.splitlines()
    hunks = []
    for line in section.splitlines():
        if line.startswith("@@"):
            hunks.append([])
        elif hunks and line.startswith((" ", "+", "-")):
            hunks[-1].append(line)
    for hunk in hunks:
        before = [line[1:] for line in hunk if line.startswith((" ", "-"))]
        after = [line[1:] for line in hunk if line.startswith((" ", "+"))]
        matches = [i for i in range(len(result) - len(before) + 1) if result[i:i + len(before)] == before]
        assert len(matches) == 1, "non-unique or stale review overlay context"
        i = matches[0]
        result[i:i + len(before)] = after
    return "\n".join(result) + "\n"


def reviewed_sources(uboot):
    """Each owned unit must match baseline or exact integrated overlay, not drift."""
    sources = {}
    for name in ("unified-storage.patch", "owned-loader.patch", "board-brom-only.patch"):
        for section in (HERE / name).read_text().split("diff --git ")[1:]:
            path = section.splitlines()[0].split(" b/", 1)[1]
            base = subprocess.check_output(["git", "-C", str(uboot), "show", f"{BASE}:{path}"]).decode()
            expected = apply_file(base, section)
            actual = (uboot / path).read_text()
            if path == BOARD + "mt6878_tetris.c":
                # Main owns board/GPU ordering. Its manual insertion may differ
                # from this illustrative patch, but not bypass or repeat calls.
                if actual != base:
                    assert actual.count("tetris_modem_brom_only_board(images)") == 1
                    gate = re.search(r"if\s*\(IS_ENABLED\(CONFIG_TETRIS_MODEM_BROM_ONLY\)\)\s*\{([^}]+)\}", actual)
                    assert gate and "tetris_modem_brom_only_board(images)" in gate[1]
                    assert "fdt = images->ft_addr;" in gate[1]
                    assert '#include "tetris_modem_final.h"' in actual
                print(f"PASS: board baseline/review or explicit default-OFF main-owned insertion: {path}")
            else:
                assert actual in (base, expected), f"unreviewed production drift: {path}"
                state = "integrated exact" if actual == expected else "baseline + review overlay"
                print(f"PASS: {state}: {path}")
            sources[path] = expected
    for name in ("tetris_modem_final.c", "tetris_modem_final.h", "tetris_modem_brom_board.c"):
        expected = (HERE / name).read_text()
        path = uboot / BOARD / name
        if path.exists():
            assert path.read_text() == expected, f"unreviewed production drift: {path}"
        sources[BOARD + name] = expected
    kconfig = (uboot / "arch/arm/mach-mediatek/Kconfig").read_text()
    gate = re.search(r"^config TETRIS_MODEM_BROM_ONLY\n(.*?)(?=^config |^endmenu|\Z)", kconfig, re.M | re.S)
    if gate:
        assert re.search(r"^\s*default n\s*$", gate[1], re.M), "integrated BROM gate not default OFF"
        assert not re.search(r"^\s*default (?!n\s*$)", gate[1], re.M), "unexpected BROM default"
        for symbol in ("TARGET_MT6878", "LMB", "OF_LIBFDT", "TETRIS_SCP_SECURITY",
                       "!TETRIS_MODEM_LOAD_DIAGNOSTIC", "!TETRIS_MODEM_RESERVE_DIAGNOSTIC",
                       "!TETRIS_GPUEB_FLAT_RETENTION_DIAGNOSTIC", "!TETRIS_GPUEB_TRANSFORM_DIAGNOSTIC"):
            assert symbol in gate[1], f"missing integrated BROM dependency {symbol}"
    else:
        assert (uboot / BOARD / "mt6878_tetris.c").read_text() == subprocess.check_output([
            "git", "-C", str(uboot), "show", f"{BASE}:{BOARD}mt6878_tetris.c"]).decode(), "board activation without Kconfig gate"
    return sources


def patched_storage(uboot):
    source = reviewed_sources(uboot)[BOARD + "tetris_modem_storage.c"]
    source = source[source.index("static int load_slot_owned("):source.rindex("#endif")]
    assert source.count("tetris_modem_prepare_bundle_b41(") == 1
    assert source.count("release_staging(") == 1
    assert source.count("tetris_modem_sync_payloads(") == 1
    assert source.count("return load_slot_owned(") == 2
    return source + "\n"


def static_check(uboot):
    for path in HERE.glob("*.py"):
        ast.parse(path.read_text(), filename=str(path))
    for path in HERE.glob("*.patch"):
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            if not line.startswith("@@"):
                continue
            match = re.match(r"@@ -\d+,(\d+) \+\d+,(\d+) @@", line)
            assert match
            j = i + 1
            while j < len(lines) and not lines[j].startswith(("@@", "diff --git")):
                j += 1
            assert int(match[1]) == sum(x.startswith((" ", "-")) for x in lines[i + 1:j])
            assert int(match[2]) == sum(x.startswith((" ", "+")) for x in lines[i + 1:j])
    if uboot:
        patched_storage(uboot)
    publish = (HERE / "tetris_modem_final.c").read_text()
    ordering = [publish.index(token) for token in (
        "bytes = tetris_modem_loaded_encode_tags", "ret = no_map_reservation",
        'ret = fdt_setprop(final, node, "ccci,modem_info_v2"',
        "flush_dcache_range((unsigned long)tags", "flush_dcache_range((unsigned long)final",
        "images->ft_addr = final")]
    assert ordering == sorted(ordering)
    assert "TAG_CAPACITY 65536UL" in publish
    assert '"status"' not in publish and "writel" not in publish
    owner = (HERE / "owned-loader.patch").read_text()
    assert "owner.check_header" in owner and "&owner.report, buffer, size" in owner
    board = (HERE / "tetris_modem_brom_board.c").read_text()
    assert board.index("images->ft_addr = final") < board.index("tetris_modem_linux_b41_once(final")
    assert "tetris_modem_publish_final(" not in board
    assert "default n" in (HERE / "brom-only.Kconfig").read_text()
    print("PASS: patch/source order, private metadata, unified lifetime, default-OFF; NOT C execution")


def native_ci(uboot):
    if os.environ.get("CI") != "true":
        raise SystemExit("C compilation/execution is CI-only")
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location("storage_checker", HERE.parent / "boot-producers/check_storage_lifetime.py")
    checker = module_from_spec(spec)
    spec.loader.exec_module(checker)
    # Reuse exact strict 14-case fixture, substituting ONLY extracted shared
    # production helper + wrappers. No duplicate harness providers or AUTH.
    checker.extracted = lambda: patched_storage(uboot)
    checker.native_ci(uboot)
    with tempfile.TemporaryDirectory(prefix="tetris-final-dt-") as directory:
        root = Path(directory)
        for name in ("tetris_modem_final.c", "tetris_modem_final.h", "test_final.c"):
            (root / name).write_bytes((HERE / name).read_bytes())
        # Review inputs are actual integrated U-Boot headers, not invented ABI.
        for name in ("tetris_modem_ccci_tags.h", "tetris_modem_loaded_boot.h",
                     "tetris_modem_bootstrap.h", "tetris_modem_boot_secure.h",
                     "tetris_modem_bundle.h", "tetris_modem_layout.h",
                     "tetris_modem_emi.h", "tetris_modem_emi_rows.h", "tetris_modem_remap.h"):
            path = uboot / "board/mediatek/mt6878" / name
            if not path.exists() and name == "tetris_modem_ccci_tags.h":
                path = HERE.parent / "boot-producers" / name
            (root / name).write_bytes(path.read_bytes())
        headers = {
            "bootm.h": "struct bootm_headers { void *ft_addr; unsigned long ft_len; };\n",
            "cpu_func.h": "void flush_dcache_range(unsigned long, unsigned long);\n",
            "mapmem.h": "void *map_sysmem(unsigned long long, unsigned long);\nvoid unmap_sysmem(const void *);\n",
            "lmb.h": "typedef unsigned long long phys_addr_t;\n#define LMB_MEM_ALLOC_MAX 1\n"
                     "#define LMB_NOOVERWRITE 1\n#define LMB_NONOTIFY 2\n"
                     "int lmb_alloc_mem(int,unsigned long,phys_addr_t*,unsigned long,unsigned long);\n"
                     "int lmb_free(phys_addr_t,unsigned long,unsigned long);\n",
            "asm/cache.h": "#define ARCH_DMA_MINALIGN 64\n",
            "linux/errno.h": "#include <asm-generic/errno.h>\n",
            "linux/string.h": "#include <string.h>\n",
            "linux/libfdt.h": "#include <libfdt.h>\n",
        }
        for name, content in headers.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        binary = root / "test-final"
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-O1", "-g",
                        "-I", str(root), str(root / "tetris_modem_final.c"), str(root / "test_final.c"),
                        "-lfdt", "-o", str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1", UBSAN_OPTIONS="halt_on_error=1")
        for case in range(10):
            subprocess.run([str(binary), str(case)], check=True, env=env)
        print("PASS: 10 actual libfdt publisher transaction cases; mocked owner/cache/LMB, NOT hardware")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uboot", type=Path)
    parser.add_argument("--native-ci", action="store_true")
    args = parser.parse_args()
    static_check(args.uboot)
    if args.native_ci:
        if not args.uboot:
            parser.error("--native-ci requires --uboot")
        native_ci(args.uboot)


if __name__ == "__main__":
    main()
