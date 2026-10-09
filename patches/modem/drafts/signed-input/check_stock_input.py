#!/usr/bin/env python3
"""Draft caller static checks locally; real public-root stock authentication CI only."""
import argparse
import ast
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
MODEM = HERE.parents[1]
sys.path.insert(0, str(MODEM))
from check_pss32_backend import ci_gate, stripped
from check_mtk_cert import DEFAULT_KERNEL, PREFIX
import check_mtk_cert
UBOOT_PIN = "bffec9306e7c40a432d79deefb450230c2ee2360"
DEFAULT_UBOOT = MODEM.parents[2] / "u-boot-mt6878"
LOADER_FILES = {
    "tetris_modem_layout.c": "b36b605dec37442801d4f1280f35aec948fae8acc4a27c1b11e6d79e47d0af59",
    "tetris_modem_layout.h": "0888cf612d439ce5791b732c5523b054db59a27723ff64f738a3d9bb9999111f",
    "tetris_modem_bundle.h": "c227e3823ae6180f10c02a2fbfa273288dea44e5249339087f25ffaf2b3cfeb4",
}


def loader_sources(uboot):
    sources = {}
    for name, expected in LOADER_FILES.items():
        data = subprocess.run(["git", "-C", str(uboot), "show",
                               f"{UBOOT_PIN}:board/mediatek/mt6878/{name}"],
                              check=True, capture_output=True).stdout
        if hashlib.sha256(data).hexdigest() != expected:
            raise SystemExit(f"Changed pinned loader input: {name}")
        # Sole Linux header adaptation; layout/SMEM implementation is unchanged.
        if name == "tetris_modem_layout.h":
            data = data.replace(b"#include <stddef.h>", b"#include <linux/types.h>")
        sources[name] = data
    return sources


def static_checks():
    source = (HERE / "mt6878_md_fw_metadata.c").read_text()
    prepare = source.split("int mt6878_md_fw_prepare(", 1)[1].split("EXPORT_SYMBOL_GPL", 1)[0]
    assert prepare.index("memcpy(snapshot, source, size)") < prepare.index("md_fw_prepare_snapshot(")
    request = source.split("int mt6878_md_fw_request(", 1)[1].split("EXPORT_SYMBOL_GPL", 1)[0]
    assert "md_fw_prepare_snapshot(firmware->data" in request and "kvmalloc" not in request
    assert request.index("owner->firmware = firmware;") < request.index("*out = owner;")
    assert source.index("crypto_memneq(hash, signed_hashes.payload_sha256") < source.index(
        "ret = md_fw_layout(") < source.index("*out = owner;")
    assert "md_mtk_verify_pin" not in source
    assert source.index("owner->verified_source = snapshot;") < source.index("*out = owner;")
    assert "kvfree(owner->verified_source);" in source
    assert "owner->verified_source + member->payload_offset + offset" in source
    placement = source.split("int mt6878_md_fw_place_b41(", 1)[1]
    assert "tetris_modem_plan_smem_b41(" in placement
    for forbidden in ("md_fw_next(", "md_fw_hash(", "kvmalloc(", "request_firmware(",
                      "mt6878_md_mtk_verify_header(", "tetris_modem_plan_layout("):
        assert forbidden not in placement
    assert placement.index("if (ret)") < placement.index("memcpy(destination, rom")
    for forbidden in ("arm_smccc", "ioremap", "readl(", "writel(", "device_lock(",
                      "-ENOKEY", "-EOPNOTSUPP", "startup_scope_begin"):
        assert forbidden not in source, forbidden
    for name in ("mt6878_md_fw_metadata.c", "mt6878_md_fw_metadata.h",
                 "stock_fixture_api.c", "test_stock_input.c"):
        text = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', "",
                      (HERE / name).read_text(), flags=re.S)
        stack = []
        for char in text:
            if char in "({[":
                stack.append(char)
            elif char in ")}]":
                assert stack and stack.pop() == {')': '(', '}': '{', ']': '['}[char], name
        assert not stack, name
    ast.parse(Path(__file__).read_text())
    print("draft signed-input static checks PASS (not C compilation)")


def native_ci(kernel, stock, sources):
    ci_gate()
    # No factory private key or synthetic root substitution. Fail absent input.
    if not stock.is_file() or not 0 < stock.stat().st_size <= 256 * 1024 * 1024:
        raise SystemExit("Bounded authentic stock md1img container required")
    data = stock.read_bytes()
    import verify_modem_signed_ram as oracle
    payloads = {}
    for name, _, payload in oracle.members(data):
        if name in (b"md1rom", b"md1drdi", b"md1dsp"):
            payloads[name] = payload
        if len(payloads) == 3:
            break
    # Independent actual factory signature check before native test. These are
    # source bytes, NOT RAM snapshots; oracle result grants no execution rights.
    oracle.verify_signed_placement(data, payloads[b"md1rom"], payloads[b"md1dsp"], 0xffffffff)
    with tempfile.TemporaryDirectory(prefix="md-stock-input-") as temp:
        path = Path(temp)
        for name in ("mt6878_md_pss32.h", "mt6878_md_pss32.c",
                     "mt6878_md_mtk_cert.h", "mt6878_md_mtk_cert.c",
                     "test_pss32_native.c", f"{PREFIX}.asn1"):
            (path / name).write_bytes((MODEM / name).read_bytes())
        for name, loader_data in sources.items():
            (path / name).write_bytes(loader_data)
        text = stripped(HERE / "stock_fixture_api.c")
        for name in ("tetris_modem_layout.h", "tetris_modem_bundle.h", "tetris_modem_layout.c"):
            text += stripped(path / name)
        for name in ("mt6878_md_fw_metadata.h", "mt6878_md_fw_metadata.c",
                     "test_stock_input.c"):
            text += stripped(HERE / name)
        (path / "test_mtk_cert_native.c").write_text(text)
        # Snapshot input once for both oracle and C, eliminating file replacement
        # between checks. This is ordinary CI memory, not physical modem RAM.
        (path / "stock.bin").write_bytes(data)
        # Reuse main's actual split-TU compiler/linker implementation unchanged.
        # Redirect only fixture input files and omit unused synthetic vectors;
        # NEVER patch verifier functions, production source or manufacturer pin.
        with patch.object(check_mtk_cert, "HERE", path), \
             patch.object(check_mtk_cert, "fixture_vectors", return_value=""), \
             patch.dict(os.environ, {"MT6878_MD_STOCK_INPUT": str(path / "stock.bin")}):
            check_mtk_cert.native_ci(kernel)
    print("tested stock container SHA256=" + hashlib.sha256(data).hexdigest())


def aarch64_ci(kernel, sources):
    ci_gate()
    for name in (".config", "include/generated/autoconf.h", "include/generated/utsrelease.h",
                 "scripts/asn1_compiler"):
        if not (kernel / name).is_file():
            raise SystemExit(f"Prepared ARM64 CI kernel required: {name}")
    if "CONFIG_ARM64=y\n" not in (kernel / ".config").read_text():
        raise SystemExit("Prepared kernel must be ARM64; no reconfiguration")
    with tempfile.TemporaryDirectory(prefix="md-stock-input-arm64-") as temp:
        path = Path(temp)
        for root, names in ((MODEM, ("mt6878_md_pss32.c", "mt6878_md_pss32.h",
                                     "mt6878_md_mtk_cert.c", "mt6878_md_mtk_cert.h",
                                     f"{PREFIX}.asn1")),
                            (HERE, ("mt6878_md_fw_metadata.c", "mt6878_md_fw_metadata.h"))):
            for name in names:
                (path / name).write_bytes((root / name).read_bytes())
        for name, loader_data in sources.items():
            (path / name).write_bytes(loader_data)
        (path / "Makefile").write_text(
            "obj-m := mt6878_md_signed_input.o\n"
            "mt6878_md_signed_input-y := mt6878_md_pss32.o mt6878_md_mtk_cert.o "
            f"{PREFIX}.asn1.o tetris_modem_layout.o mt6878_md_fw_metadata.o\n"
            f"$(obj)/mt6878_md_mtk_cert.o: $(obj)/{PREFIX}.asn1.h\n"
            f"$(obj)/{PREFIX}.asn1.o: $(obj)/{PREFIX}.asn1.c $(obj)/{PREFIX}.asn1.h\n")
        subprocess.run(["make", "-C", str(kernel), f"M={path}", "ARCH=arm64",
                        f"CROSS_COMPILE={os.environ.get('CROSS_COMPILE', 'aarch64-linux-gnu-')}",
                        "W=1", "KCFLAGS=-Werror", "mt6878_md_signed_input.o"], check=True)
        elf = (path / "mt6878_md_signed_input.o").read_bytes()
        if elf[:6] != b"\x7fELF\x02\x01" or elf[18:20] != b"\xb7\x00":
            raise SystemExit("Not little-endian ELF64 AArch64")
        print("isolated production signed-input ARM64 object PASS; no runtime claim")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, default=DEFAULT_KERNEL)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--stock-container", type=Path)
    parser.add_argument("--aarch64-object-ci", type=Path)
    parser.add_argument("--uboot", type=Path, default=DEFAULT_UBOOT)
    args = parser.parse_args()
    static_checks()
    sources = loader_sources(args.uboot.resolve())
    print("pinned existing loader layout/SMEM source hashes PASS")
    if args.native_ci:
        if args.stock_container is None:
            parser.error("--native-ci requires --stock-container; no synthetic positive fallback")
        native_ci(args.kernel.resolve(), args.stock_container.resolve(), sources)
    if args.aarch64_object_ci:
        aarch64_ci(args.aarch64_object_ci.resolve(), sources)


if __name__ == "__main__":
    main()
