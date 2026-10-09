#!/usr/bin/env python3
"""Static checks locally; unmodified production-body fault harness in CI only."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def without_includes(text):
    return "\n".join(line for line in text.splitlines()
                     if not line.startswith("#include")) + "\n"


def composed_fixture():
    text = without_includes((HERE / "mt6878_md_startup_scope.h").read_text())
    text += without_includes((HERE / "mt6878_md_handoff_reservation.h").read_text())
    text += without_includes((HERE / "mt6878_md_handoff_reservation.c").read_text())
    return (HERE / "test_handoff_reservation.c").read_text().replace(
        "/* PRODUCTION_INSERT */", text)


def static_checks():
    source = (HERE / "mt6878_md_handoff_reservation.c").read_text()
    header = (HERE / "mt6878_md_handoff_reservation.h").read_text()
    harness = (HERE / "test_handoff_reservation.c").read_text()
    assert harness.count("/* PRODUCTION_INSERT */") == 1
    assert '#error "MD handoff reservation owner must be built-in"' in source
    assert "IS_ENABLED(CONFIG_OF_DYNAMIC)" in source
    assert "reserved->ops" in source and '"reusable"' in source
    assert "resource.start != reserved->base" in source
    assert "resource.end != end - 1" in source
    assert source.count("request_mem_region(") == 2
    assert source.count("release_mem_region(") == 1
    assert source.index("owner->smem_claim =") < source.index("*out = owner;")
    callbacks = source[source.index("static int md_reserved_snapshot"):]
    assert "return -ENOKEY;" in callbacks and "return -ESTALE;" in callbacks
    assert source.count("return 0;") == 3  # range, factory, snapshot only
    # Callback boundary deliberately has no supplier/scope lock or external
    # verifier callback. Only snapshot copy and exact scalar/digest comparison.
    calls = set(re.findall(r"\b([a-zA-Z_]\w*)\s*\(", callbacks))
    assert calls <= {"md_reserved_snapshot", "md_reserved_authenticate", "if",
                     "memcmp", "sizeof", "EXPORT_SYMBOL_GPL", "MODULE_LICENSE"}, calls
    for forbidden in ("arm_smccc", "ioremap", "readl", "writel", "device_lock",
                      "mutex_lock", "request_firmware", "memremap"):
        assert forbidden not in source
    assert "UNVERIFIED" in header and "no teardown" in header
    for field in ("rom_base", "rom_size", "smem_base", "smem_size", "rom_digest"):
        assert f"state->{field}" in callbacks
    # Lexical delimiter check is not a C compilation/syntax-success claim.
    fixture = re.sub(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"', "",
                     composed_fixture(), flags=re.S)
    stack = []
    for char in fixture:
        if char in "({[":
            stack.append(char)
        elif char in ")}]":
            assert stack and stack.pop() == {")": "(", "}": "{", "]": "["}[char]
    assert not stack
    assert "-Werror" in Path(__file__).read_text()
    print("handoff reservation static checks PASS")


def native_ci():
    if os.environ.get("CI") != "true":
        raise SystemExit("Native C compile/run allowed only with CI=true in CI")
    with tempfile.TemporaryDirectory(prefix="md-handoff-ci-") as temp:
        path = Path(temp)
        source = path / "test.c"
        source.write_text(composed_fixture())
        binary = path / "test"
        subprocess.run([os.environ.get("CC", "cc"), "-std=gnu11", "-Wall",
                        "-Wextra", "-Werror", "-fsanitize=address,undefined",
                        "-fno-omit-frame-pointer", str(source), "-o", str(binary)],
                       check=True)
        subprocess.run([str(binary)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-ci", action="store_true")
    args = parser.parse_args()
    static_checks()
    if args.native_ci:
        native_ci()


if __name__ == "__main__":
    main()
