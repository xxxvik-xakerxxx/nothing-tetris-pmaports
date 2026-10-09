#!/usr/bin/env python3
"""Static locally; real kernel ASN.1 + production PSS/MTK native/object CI only."""
import argparse
import ast
import os
from pathlib import Path
import re
import subprocess
import tempfile
from check_pss32_backend import ci_gate, stripped

HERE = Path(__file__).resolve().parent
DEFAULT_KERNEL = HERE.parents[2] / "linux-d84b264a54a37611f2f46bc19363cb9b41606205"
PREFIX = "mt6878_md_mtk_fields"


def static_checks():
    source = (HERE / "mt6878_md_mtk_cert.c").read_text()
    pin = re.search(r"md_mtk_root_pin\[32\]\s*=\s*\{([^}]+)\}", source).group(1)
    assert bytes(int(n, 16) for n in re.findall(r"0x([a-f0-9]{2})", pin)).hex() == (
        "e1b5235d9411473a358c754f84843801b91f05b8fb9dc4863393e378e41a115e")
    assert f"asn1_ber_decoder(&{PREFIX}_decoder" in source
    assert "out->count == MD_FIELDS_MAX" in source and "MD_FIELDS_MAX 48" in source
    assert "MD_CERT_MAX 16384" in source and "count > 2" in source
    assert "field->data[field->header]" in source
    assert "md_field_equal(field, &work->leaf.spki)" in source
    assert "mt6878_md_pss32_verify(root" in source and "mt6878_md_pss32_verify(leaf" in source
    assert source.index("mt6878_md_pss32_verify(leaf") < source.index("*out = verified;")
    assert "out, md_mtk_root_pin" in source
    for text in ("arm_smccc", "ioremap", "readl", "writel", "device_lock", "request_firmware",
                 "x509_cert_parse", "public_key_verify_signature"):
        assert text not in source
    assert (HERE / f"{PREFIX}.asn1").read_text().strip() == (
        "Fields ::= SEQUENCE OF ANY ({ mt6878_md_mtk_note_field })")
    for name in ("mt6878_md_mtk_cert.c", "mt6878_md_mtk_cert.h", "test_mtk_cert_native.c"):
        text = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', "", (HERE / name).read_text(), flags=re.S)
        stack = []
        for char in text:
            if char in "({[":
                stack.append(char)
            elif char in ")}]":
                assert stack and stack.pop() == {")": "(", "}": "{", "]": "["}[char], name
        assert not stack, name
    ast.parse(Path(__file__).read_text())
    print("MTK bounded DER/delegation static checks PASS")


def fixture_vectors():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from test_signed_ram_ci import certificate, der
    import verify_modem_signed_ram as v
    root = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    def spki(key):
        return key.public_key().public_bytes(serialization.Encoding.DER,
                                            serialization.PublicFormat.SubjectPublicKeyInfo)
    root_spki, leaf_spki = spki(root), spki(leaf)
    header = b"Bounded synthetic signed member header".ljust(512, b"\0")
    payload_hash = v.digest(b"synthetic payload (no RAM read)")
    metadata = [(2, 4, der(3, b"\0" + v.digest(header))),
                (2, 1, der(3, b"\0" + payload_hash)),
                (2, 6, der(3, b"\0\0")), (2, 8, der(3, b"\0\0")), (4, 2, der(3, b"\0\0"))]
    a = certificate(root, root_spki, [(1, 2, leaf_spki)])
    b = certificate(leaf, leaf_spki, metadata)
    def explicit(cert):
        env = v.sequence(cert)
        pss = bytearray(v.PSS)
        pss[1] += 5
        pss[14] += 5
        pss += bytes.fromhex("a303020101")
        return der(0x30, env[0].raw + bytes(pss) + env[2].raw)
    bad_bits = [(g, i, der(3, b"\1" + payload_hash) if (g, i) == (2, 1) else val)
                for g, i, val in metadata]
    values = {
        "fixture_pin": v.digest(root_spki), "fixture_root": a, "fixture_leaf": b,
        "fixture_header": header, "fixture_header_hash": v.digest(header),
        "fixture_payload_hash": payload_hash,
        "fixture_wrong_delegation": certificate(root, root_spki, [(1, 2, root_spki)]),
        "fixture_transformed": certificate(leaf, leaf_spki, [metadata[0], metadata[1],
                                    (2, 6, der(3, b"\0\1")), *metadata[3:]]),
        "fixture_duplicate_oid": certificate(leaf, leaf_spki, metadata + [metadata[0]]),
        "fixture_missing_digest": certificate(leaf, leaf_spki, metadata[:1] + metadata[2:]),
        "fixture_bad_bits": certificate(leaf, leaf_spki, bad_bits),
        "fixture_explicit_root": explicit(a), "fixture_explicit_leaf": explicit(b),
        "fixture_salt64": certificate(leaf, leaf_spki, metadata, salt_length=64),
        "fixture_many_fields": certificate(leaf, leaf_spki, [(9, i, der(3, b"\0\0")) for i in range(22)]),
    }
    return "\n".join(f"static const u8 {name}[] = {{" +
                     ",".join(f"0x{byte:02x}" for byte in data) + "};"
                     for name, data in values.items())


def native_ci(kernel):
    ci_gate()
    with tempfile.TemporaryDirectory(prefix="md-mtk-native-") as temp:
        path = Path(temp)
        includes = path / "include/linux"
        includes.mkdir(parents=True)
        for name in ("asn1.h", "asn1_ber_bytecode.h"):
            (includes / name).write_bytes((kernel / "include/linux" / name).read_bytes())
        cc = os.environ.get("CC", "cc")
        # Match the pinned kernel's host-tool warning policy. Our production
        # decoder and fixture below still compile with -Wextra/-Werror.
        subprocess.run([cc, "-std=gnu11", "-O2", "-Wall", "-Wmissing-prototypes", "-Wstrict-prototypes",
                        f"-I{path / 'include'}", str(kernel / "scripts/asn1_compiler.c"),
                        "-o", str(path / "asn1_compiler")], check=True)
        generated_c, generated_h = path / f"{PREFIX}.asn1.c", path / f"{PREFIX}.asn1.h"
        subprocess.run([str(path / "asn1_compiler"), str(HERE / f"{PREFIX}.asn1"),
                        str(generated_c), str(generated_h)], check=True)
        text = (HERE / "test_pss32_native.c").read_text().split("/* PRODUCTION_INSERT */")[0]
        text += ('\n#include <stdbool.h>\n#define unlikely(x) (x)\n'
                 '#define fallthrough __attribute__((fallthrough))\n'
                 '#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))\n'
                 '#define pr_debug(...) do { if (0) fprintf(stderr, __VA_ARGS__); } while (0)\n'
                 '#define pr_err(...) do { if (0) fprintf(stderr, __VA_ARGS__); } while (0)\n'
                 '#define MODULE_DESCRIPTION(x)\n')
        for name in ("asn1.h", "asn1_decoder.h", "asn1_ber_bytecode.h"):
            text += stripped(kernel / "include/linux" / name)
        text += stripped(generated_h) + stripped(kernel / "lib/asn1_decoder.c") + stripped(generated_c)
        for name in ("mt6878_md_pss32.h", "mt6878_md_pss32.c", "mt6878_md_mtk_cert.h", "mt6878_md_mtk_cert.c"):
            text += stripped(HERE / name)
        text += fixture_vectors() + "\n" + (HERE / "test_mtk_cert_native.c").read_text()
        (path / "test.c").write_text(text)
        subprocess.run([cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        str(path / "test.c"), "-lcrypto", "-o", str(path / "test")], check=True)
        subprocess.run([str(path / "test")], check=True)


def aarch64_ci(kernel):
    ci_gate()
    kernel = kernel.resolve()
    for name in (".config", "include/generated/autoconf.h", "include/generated/utsrelease.h", "scripts/asn1_compiler"):
        if not (kernel / name).is_file():
            raise SystemExit(f"Prepared ARM64 CI kernel required: {name}")
    if "CONFIG_ARM64=y\n" not in (kernel / ".config").read_text():
        raise SystemExit("Prepared kernel must be ARM64; no reconfiguration")
    with tempfile.TemporaryDirectory(prefix="md-mtk-arm64-") as temp:
        path = Path(temp)
        for name in ("mt6878_md_pss32.c", "mt6878_md_pss32.h", "mt6878_md_mtk_cert.c",
                     "mt6878_md_mtk_cert.h", f"{PREFIX}.asn1"):
            (path / name).write_bytes((HERE / name).read_bytes())
        (path / "Makefile").write_text(
            "obj-m := mt6878_md_mtk_stack.o\n"
            f"mt6878_md_mtk_stack-y := mt6878_md_pss32.o mt6878_md_mtk_cert.o {PREFIX}.asn1.o\n"
            f"$(obj)/mt6878_md_mtk_cert.o: $(obj)/{PREFIX}.asn1.h\n"
            f"$(obj)/{PREFIX}.asn1.o: $(obj)/{PREFIX}.asn1.c $(obj)/{PREFIX}.asn1.h\n")
        subprocess.run(["make", "-C", str(kernel), f"M={path}", "ARCH=arm64",
                        f"CROSS_COMPILE={os.environ.get('CROSS_COMPILE', 'aarch64-linux-gnu-')}",
                        "W=1", "KCFLAGS=-Werror", "mt6878_md_mtk_stack.o"], check=True)
        elf = (path / "mt6878_md_mtk_stack.o").read_bytes()
        if elf[:6] != b"\x7fELF\x02\x01" or elf[18:20] != b"\xb7\x00":
            raise SystemExit("Not little-endian ELF64 AArch64")
        print("isolated MTK/PSS32/generated ASN.1 composite object PASS (no runtime claim)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, default=DEFAULT_KERNEL)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--aarch64-object-ci", type=Path)
    args = parser.parse_args()
    static_checks()
    if args.native_ci:
        native_ci(args.kernel.resolve())
    if args.aarch64_object_ci:
        aarch64_ci(args.aarch64_object_ci)


if __name__ == "__main__":
    main()
