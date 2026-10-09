#!/usr/bin/env python3
"""PSS32 static checks locally; native and AArch64 object compilation in CI only."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def stripped(path):
    return "\n".join(line for line in path.read_text().splitlines()
                     if not line.startswith("#include")) + "\n"


def static_checks():
    source = (HERE / "mt6878_md_pss32.c").read_text()
    assert 'crypto_alloc_akcipher("rsa-generic", 0, CRYPTO_ALG_ASYNC)' in source
    assert 'crypto_alloc_shash("sha256-lib", 0, 0)' in source
    assert "crypto_akcipher_encrypt(ctx->request)" in source
    assert "length != 270" in source and "signature_size != MD_RSA_BYTES" in source
    assert "tbs_size > 16384" in source and "size > 64U * 1024 * 1024" in source
    assert "ctx->request->dst_len != MD_RSA_BYTES" in source
    assert "crypto_memneq(h, prime, MD_HASH_BYTES)" in source
    assert "ret = mt6878_md_pss32_sha256(ctx, seed" in source
    assert "ret = mt6878_md_pss32_sha256(ctx, prime_input" in source
    for forbidden in ("arm_smccc", "ioremap", "readl", "writel", "device_lock", "mutex_lock",
                      "request_firmware", "crypto_akcipher_decrypt", "crypto_wait_req"):
        assert forbidden not in source
    fixture = (HERE / "test_pss32_native.c").read_text()
    assert fixture.count("/* PRODUCTION_INSERT */") == 1
    assert fixture.count("/* VECTORS_INSERT */") == 1
    assert "BN_mod_exp" in fixture and "EVP_Digest" in fixture
    assert "fault <= 9" in fixture and "FAIL_REQUEST" in fixture
    # Lexical delimiter check only, not a C compile-success claim.
    for name in ("mt6878_md_pss32.c", "mt6878_md_pss32.h", "test_pss32_native.c"):
        text = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', "",
                      (HERE / name).read_text(), flags=re.S)
        stack = []
        for char in text:
            if char in "({[":
                stack.append(char)
            elif char in ")}]":
                assert stack and stack.pop() == {")": "(", "}": "{", "]": "["}[char], name
        assert not stack, name
    print("PSS32 source and fixture static checks PASS")


def ci_gate():
    if os.environ.get("CI") != "true":
        raise SystemExit("C builds/runs allowed only with CI=true in CI")


def vectors():
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tbs = b"Synthetic CI-only MT6878 TBS, not an authorized modem image"
    sig = key.sign(tbs, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                   hashes.SHA256())
    numbers = key.public_key().public_numbers()
    values = {
        "vector_key": key.public_key().public_bytes(serialization.Encoding.DER,
                                                    serialization.PublicFormat.PKCS1),
        "vector_tbs": tbs,
        "vector_signature": sig,
        "vector_salt64": key.sign(tbs, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=64),
                                   hashes.SHA256()),
        "vector_v15": key.sign(tbs, padding.PKCS1v15(), hashes.SHA256()),
        "vector_em": pow(int.from_bytes(sig, "big"), numbers.e, numbers.n).to_bytes(256, "big"),
    }
    assert len(values["vector_key"]) == 270
    return "\n".join(f"static const u8 {name}[] = {{" +
                     ",".join(f"0x{byte:02x}" for byte in data) + "};"
                     for name, data in values.items())


def native_ci():
    ci_gate()
    production = stripped(HERE / "mt6878_md_pss32.h") + stripped(HERE / "mt6878_md_pss32.c")
    fixture = (HERE / "test_pss32_native.c").read_text().replace(
        "/* PRODUCTION_INSERT */", production).replace("/* VECTORS_INSERT */", vectors())
    with tempfile.TemporaryDirectory(prefix="md-pss32-native-") as temp:
        path = Path(temp)
        (path / "test.c").write_text(fixture)
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        str(path / "test.c"), "-lcrypto", "-o", str(path / "test")], check=True)
        subprocess.run([str(path / "test")], check=True)


def aarch64_ci(kernel):
    ci_gate()
    kernel = kernel.resolve()
    for name in (".config", "include/generated/autoconf.h", "include/generated/utsrelease.h"):
        if not (kernel / name).is_file():
            raise SystemExit(f"Prepared AArch64 CI kernel required: missing {name}")
    config = (kernel / ".config").read_text()
    if "CONFIG_ARM64=y\n" not in config:
        raise SystemExit("Prepared CI kernel must be ARM64; no reconfiguration performed")
    # Generated external object only; no install, modpost, package or activation.
    with tempfile.TemporaryDirectory(prefix="md-pss32-arm64-") as temp:
        path = Path(temp)
        for name in ("mt6878_md_pss32.c", "mt6878_md_pss32.h"):
            (path / name).write_bytes((HERE / name).read_bytes())
        (path / "Makefile").write_text("obj-m := mt6878_md_pss32.o\n")
        subprocess.run(["make", "-C", str(kernel), f"M={path}", "ARCH=arm64",
                        f"CROSS_COMPILE={os.environ.get('CROSS_COMPILE', 'aarch64-linux-gnu-')}",
                        "W=1", "KCFLAGS=-Werror", "mt6878_md_pss32.o"], check=True)
        elf = (path / "mt6878_md_pss32.o").read_bytes()
        if elf[:4] != b"\x7fELF" or elf[4:6] != b"\x02\x01" or elf[18:20] != b"\xb7\x00":
            raise SystemExit("Object is not little-endian ELF64 AArch64")
        print("isolated AArch64 PSS32 object PASS (no link/runtime claim)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-ci", action="store_true")
    parser.add_argument("--aarch64-object-ci", type=Path, metavar="PREPARED_KERNEL")
    args = parser.parse_args()
    static_checks()
    if args.native_ci:
        native_ci()
    if args.aarch64_object_ci:
        aarch64_ci(args.aarch64_object_ci)


if __name__ == "__main__":
    main()
