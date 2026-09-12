#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host-only regression test. No device access or kernel tree mutations."""
import os
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PACKAGE = Path("pmaports/device/testing/linux-postmarketos-mediatek-mt6878")
BASE = PACKAGE / "0049-media-i2c-imx882-identity.patch"
FIXTURE = PACKAGE / "0055-arm64-dts-mediatek-tetris-imx882-disabled-fixture.patch"
DRIVER = "drivers/media/i2c/imx882-identity.c"
BASE_SHA256 = "855de12c6af5dd5f9abd8c4489ff15a91f98a7033b88a8cf90ecdb7979d45db1"
FIXTURE_SHA256 = "1e8ef39635510e2164eceaf107308bb6d53066af9f3789d06e43fa4b5f2e759e"


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def added_file(patch, path):
    section = patch.split(f"+++ b/{path}\n", 1)[1].split("\ndiff --git ", 1)[0]
    return "".join(line[1:] + "\n" for line in section.splitlines() if line.startswith("+"))


def require_sha256(path, expected):
    actual = hashlib.sha256((REPO / path).read_bytes()).hexdigest()
    assert actual == expected, f"baseline drift: {path}"


def power_source(source):
    # Keep actual declarations and power functions; omit the unrelated I2C helper.
    declarations = source.split("#define IMX882_REG_CHIP_ID_HIGH", 1)[1].split(
        "static int imx882_read_reg", 1)[0]
    functions = source.split("static int imx882_enable_supply", 1)[1].split(
        "static int imx882_identity_probe", 1)[0]
    return ("#define IMX882_REG_CHIP_ID_HIGH" + declarations
            + "static int imx882_enable_supply" + functions)


def main():
    require_sha256(BASE, BASE_SHA256)
    require_sha256(FIXTURE, FIXTURE_SHA256)
    fixture = (REPO / FIXTURE).read_text()
    assert "reset-gpios = <&pio 25 GPIO_ACTIVE_LOW>;" in fixture
    original = added_file((REPO / BASE).read_text(), DRIVER)
    with tempfile.TemporaryDirectory(prefix="imx882-reset-") as tmp:
        root = Path(tmp)
        target = root / DRIVER
        target.parent.mkdir(parents=True)
        target.write_text(original)
        candidate = HERE / "0001-imx882-identity-honor-active-low-reset.patch"
        run("git", "apply", "--check", str(candidate), cwd=root)
        run("git", "apply", str(candidate), cwd=root)
        source = target.read_text()
        assert 'devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH)' in source
        assert source.count("gpiod_set_value_cansleep") == 3
        compiler = shlex.split(os.environ.get("CC", "cc"))
        for label, code in (("fixed", source), ("baseline", original)):
            (root / "identity-under-test.h").write_text(power_source(code))
            binary = root / label
            run(*compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I", str(root), str(HERE / "reset-test.c"), "-o", str(binary))
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            if label == "fixed":
                assert result.returncode == 0, result.stderr
                print(result.stdout.strip())
            else:
                assert result.returncode != 0, "test failed to reject inverted baseline"
                assert "Assertion" in result.stderr or "assertion" in result.stderr
                print("PASS: unmodified baseline rejected by the same host test")


if __name__ == "__main__":
    main()
