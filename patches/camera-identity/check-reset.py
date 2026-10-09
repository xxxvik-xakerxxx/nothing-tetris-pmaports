#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host-only regression test. No device access or kernel tree mutations."""
import os
import hashlib
from pathlib import Path
import shlex
import subprocess
import tempfile
import argparse

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PACKAGE = Path("pmaports/device/testing/linux-postmarketos-mediatek-mt6878")
BASE = PACKAGE / "0049-media-i2c-imx882-identity.patch"
FIXTURE = PACKAGE / "0055-arm64-dts-mediatek-tetris-imx882-disabled-fixture.patch"
DRIVER = "drivers/media/i2c/imx882-identity.c"
BASE_SHA256 = "855de12c6af5dd5f9abd8c4489ff15a91f98a7033b88a8cf90ecdb7979d45db1"
FIXTURE_SHA256 = "3495500adc10f1018ea000faecbfbabb7e558b2bae0435914026aa135b61d2fb"


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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true",
                        help="validate patch application without compiling C")
    args = parser.parse_args()
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
        target.write_text(original)
        run("git", "apply", str(REPO / PACKAGE / "0050-media-i2c-imx882-honor-active-low-reset.patch"), cwd=root)
        assert target.read_text() == source, "packaged reset fix differs from tested candidate"
        assert 'devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH)' in source
        assert source.count("gpiod_set_value_cansleep") == 3
        cleanup = HERE / "0002-imx882-identity-check-shutdown.patch"
        run("git", "apply", "--check", str(cleanup), cwd=root)
        run("git", "apply", str(cleanup), cwd=root)
        complete = target.read_text()
        assert (REPO / PACKAGE / "0106-media-i2c-imx882-check-shutdown.patch").read_bytes() == cleanup.read_bytes()
        assert "cleanup_ret = imx882_power_off" in complete
        assert "ret = cleanup_ret;" in complete
        run("git", "apply", str(REPO / PACKAGE / "0107-media-i2c-imx882-hold-clock-rate.patch"), cwd=root)
        clock_source = target.read_text()
        assert "clk_set_rate_exclusive" in clock_source
        assert "clk_get_rate(imx882->xclk) != IMX882_XCLK_RATE" in clock_source
        if args.check_only:
            print("PASS: reset + shutdown + clock patches apply; no local compilation")
            return
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
        power = power_source(complete)
        mutants = {
            "fixed": power,
            "ignore-shutdown": power.replace("return ret;\n}\n\nstatic int imx882_power_on",
                                               "return 0;\n}\n\nstatic int imx882_power_on"),
            "missing-dovdd-delay": power.replace(
                "*enabled_supplies |= BIT(IMX882_SUPPLY_DOVDD);\n\tusleep_range(1000, 1100);",
                "*enabled_supplies |= BIT(IMX882_SUPPLY_DOVDD);"),
        }
        for label, code in mutants.items():
            if label != "fixed":
                assert code != power, f"mutant not applied: {label}"
            (root / "identity-under-test.h").write_text(code)
            binary = root / ("cleanup-" + label)
            run(*compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-DTEST_CLEANUP", "-I", str(root), str(HERE / "reset-test.c"),
                "-o", str(binary))
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            if label == "fixed":
                assert result.returncode == 0, result.stderr
                print(result.stdout.strip())
            else:
                assert result.returncode != 0, f"mutant survived: {label}"
                assert "Assertion" in result.stderr or "assertion" in result.stderr
                print(f"PASS: rejected {label}")
        power = power_source(clock_source)
        for label, code in {
            "fixed": power,
            "missing-clock-put": power.replace("clk_rate_exclusive_put(imx882->xclk);", "(void)imx882->xclk;"),
            "ignore-clock-rounding": power.replace("clk_get_rate(imx882->xclk) != IMX882_XCLK_RATE", "clk_get_rate(imx882->xclk) == 0"),
        }.items():
            assert label == "fixed" or code != power
            (root / "identity-under-test.h").write_text(code)
            binary = root / ("clock-" + label)
            run(*compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-DTEST_CLEANUP", "-DTEST_CLOCK", "-I", str(root),
                str(HERE / "reset-test.c"), "-o", str(binary))
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            if label == "fixed":
                assert result.returncode == 0, result.stderr
                print(result.stdout.strip())
            else:
                assert result.returncode != 0, f"mutant survived: {label}"
                assert "Assertion" in result.stderr or "assertion" in result.stderr
                print(f"PASS: rejected {label}")


if __name__ == "__main__":
    main()
