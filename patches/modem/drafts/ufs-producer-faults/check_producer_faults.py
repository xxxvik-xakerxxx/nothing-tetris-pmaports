#!/usr/bin/env python3
"""Source extraction locally; actual producer/owned-loader C is CI-only."""
import argparse
import ast
import hashlib
from importlib.util import spec_from_file_location, module_from_spec
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
BASE = "94ead1146c93fef603db5c85820f2fb04c559c10"
PL_SHA = "5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f"
BOARD = "board/mediatek/mt6878/"


def module(name, path):
    spec = spec_from_file_location(name, path)
    result = module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def function(source, name):
    start = re.search(r"^(?:static\s+)?(?:int|unsigned int)\s+" + re.escape(name) + r"\s*\(", source, re.M)
    assert start, f"missing production function {name}"
    brace = source.index("{", start.start())
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start.start():end] + "\n"


def sources(uboot):
    # Produce the canonical review overlay even on an old pre-integration tree.
    draft = HERE.parent / "boot-producers"
    expected_policy = (draft / "tetris_modem_linux_policy.c").read_text()
    policy_path = uboot / BOARD / "tetris_modem_linux_policy.c"
    policy = policy_path.read_text() if policy_path.exists() else expected_policy
    assert policy == expected_policy, "unreviewed measured policy producer drift"
    patch = (draft / "ufs-boot-identity.patch").read_text().split("diff --git")[2]
    added = "\n".join(line[1:] for line in patch.splitlines()
                      if line.startswith("+") and not line.startswith("+++"))
    expected_identity = function(added, "ufs_read_lun_boot_identity")
    base = subprocess.check_output(["git", "-C", str(uboot), "show",
                                    f"{BASE}:drivers/ufs/ufs-uclass.c"]).decode()
    current = (uboot / "drivers/ufs/ufs-uclass.c").read_text()
    if re.search(r"^int ufs_read_lun_boot_identity\(", current, re.M):
        assert function(current, "ufs_read_lun_boot_identity") == expected_identity
        identity = function(current, "ufs_read_lun_boot_identity")
    else:
        assert current == base, "UFS baseline missing producer but contains unreviewed drift"
        identity = expected_identity
    assert function(current, "ufshcd_map_desc_id_to_length") == function(base, "ufshcd_map_desc_id_to_length")
    header = (uboot / "drivers/ufs/ufs.h").read_text()
    pinned_header = subprocess.check_output(["git", "-C", str(uboot), "show", f"{BASE}:drivers/ufs/ufs.h"]).decode()
    assert header == pinned_header, "unreviewed UFS protocol header drift"
    protocol = []
    match = re.search(r"struct ufs_desc_size\s*\{.*?\};", header, re.S)
    assert match
    protocol.append(match[0])
    for name in ("query_opcode", "attr_idn", "desc_idn"):
        match = re.search(r"enum " + name + r"\s*\{.*?\};", header, re.S)
        assert match
        protocol.append(match[0])
    for name in ("UFS_MAX_LUNS", "QUERY_DESC_MAX_SIZE"):
        match = re.search(r"^#define\s+" + name + r"\s+[^\n]+", header, re.M)
        assert match
        protocol.append(match[0])
    return {
        "protocol.inc": "\n".join(protocol) + "\n",
        "ufs_identity.inc": function(current, "ufshcd_map_desc_id_to_length") + identity,
        "policy_identity.inc": "\n".join(function(policy, name) for name in
                                         ("word", "selected_boot", "preloader_digest")),
    }


def native_ci(uboot, preloader):
    if os.environ.get("CI") != "true":
        raise SystemExit("C compilation/execution is CI-only")
    with tempfile.TemporaryDirectory(prefix="tetris-ufs-producers-") as directory:
        root = Path(directory)
        for name, content in sources(uboot).items():
            (root / name).write_text(content)
        (root / "test_ufs_producers.c").write_bytes((HERE / "test_ufs_producers.c").read_bytes())
        binary = root / "test-ufs"
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-O1", "-g",
                        "-I", str(root), str(root / "test_ufs_producers.c"), "-lcrypto", "-o", str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1", UBSAN_OPTIONS="halt_on_error=1")
        for case in (*range(32), 33, 34, 35):
            subprocess.run([str(binary), str(case)], check=True, env=env)
        if preloader:
            raw = preloader.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == PL_SHA, "not the exact declared pinned GFH image"
            subprocess.run([str(binary), "32", str(preloader)], check=True, env=env)
        print("PASS: 35 UFS/selected-LUN/GFH/stream/hash fault cases with real SHA and mocked I/O")
        print("Pinned-positive measured-GFH case:", "PASS" if preloader else "NOT RUN; --preloader-image required")


def owned_ci(uboot):
    """Compile exact reviewed/integrated owner, not frozen pre-footer source."""
    if os.environ.get("CI") != "true":
        raise SystemExit("C compilation/execution is CI-only")
    check = module("startup_check", HERE.parent / "startup-final/check_startup_final.py")
    reviewed = check.reviewed_sources(uboot)
    source = reviewed[BOARD + "tetris_modem_loaded_boot.c"]
    assert "tetris_modem_load_slot_handoff_b41(" in source
    assert "owner.check_header" in source and "tetris_modem_loaded_encode_tags(" in source
    with tempfile.TemporaryDirectory(prefix="tetris-owned-loader-") as directory:
        root = Path(directory)
        (root / "tetris_modem_loaded_boot.c").write_text(source)
        (root / "test_owned_loader.c").write_bytes((HERE / "test_owned_loader.c").read_bytes())
        (root / "baseline_fixture.inc").write_bytes(
            (HERE.parent / "bootstrap-integration/test_loaded_boot.c").read_bytes())
        for name in ("tetris_modem_layout.c", "tetris_modem_layout.h", "tetris_modem_emi.c",
                     "tetris_modem_emi.h", "tetris_modem_remap.h", "tetris_modem_bundle.h",
                     "tetris_modem_reserve.h", "tetris_scp_security.h", "tetris_modem_loaded_boot.h",
                     "tetris_modem_bootstrap.h", "tetris_modem_boot_secure.h", "tetris_modem_emi_rows.h"):
            path = uboot / BOARD / name
            (root / name).write_bytes(path.read_bytes())
        (root / "tetris_modem_storage.h").write_text(reviewed[BOARD + "tetris_modem_storage.h"])
        (root / "tetris_modem_final.h").write_text(reviewed[BOARD + "tetris_modem_final.h"])
        tag_header = uboot / BOARD / "tetris_modem_ccci_tags.h"
        if not tag_header.exists():
            tag_header = HERE.parent / "boot-producers/tetris_modem_ccci_tags.h"
        (root / tag_header.name).write_bytes(tag_header.read_bytes())
        headers = {
            "linux/errno.h": "#include <asm-generic/errno.h>\n",
            "linux/string.h": "#include <string.h>\n",
            "asm/cache.h": "#define ARCH_DMA_MINALIGN 64\n",
            "asm/global_data.h": "#ifndef TEST_GD_H\n#define TEST_GD_H\n"
                "struct bd_info { struct { unsigned long long start,size; } bi_dram[1]; };\n"
                "struct global_data { struct bd_info *bd; };\nextern struct global_data *gd;\n"
                "#define DECLARE_GLOBAL_DATA_PTR\n#define CONFIG_NR_DRAM_BANKS 1\n#endif\n",
            "asm/u-boot.h": "#include <asm/global_data.h>\n",
            "asm/io.h": "unsigned int readl(const volatile void *);\n",
            "asm/system.h": "unsigned int current_el(void);\n",
            "cpu_func.h": "void flush_dcache_range(unsigned long,unsigned long);\n",
            "mapmem.h": "void *map_sysmem(unsigned long long,unsigned long);\nvoid unmap_sysmem(const void*);\n",
        }
        for name, content in headers.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        binary = root / "test-owned"
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-O1", "-g",
                        "-DTETRIS_MODEM_LAYOUT_HOST_TEST", "-I", str(root),
                        *(str(root / name) for name in ("tetris_modem_layout.c", "tetris_modem_emi.c",
                          "tetris_modem_loaded_boot.c", "test_owned_loader.c")), "-o", str(binary)], check=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:abort_on_error=1", UBSAN_OPTIONS="halt_on_error=1")
        for case in range(19):
            subprocess.run([str(binary), str(case)], check=True, env=env)
        print("PASS: actual owned-loader 17 inherited faults + report/encode faults; private footer retained")
        print("All firmware authentication/SMC/tag encoder boundaries mocked; NOT hardware/AUTH proof")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uboot", type=Path, required=True)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--owned-loader-ci", action="store_true")
    parser.add_argument("--preloader-image", type=Path)
    args = parser.parse_args()
    for path in HERE.glob("*.py"):
        ast.parse(path.read_text(), filename=str(path))
    sources(args.uboot)
    check = module("startup_check", HERE.parent / "startup-final/check_startup_final.py")
    check.reviewed_sources(args.uboot)
    print("PASS: exact reviewed/production functions/protocol extraction; NOT C execution")
    if args.native_ci:
        native_ci(args.uboot, args.preloader_image)
    if args.owned_loader_ci:
        owned_ci(args.uboot)


if __name__ == "__main__":
    main()
