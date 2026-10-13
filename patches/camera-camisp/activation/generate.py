#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a sensor integration delta from pinned objects; never compile."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
KERNEL = "d84b264a54a37611f2f46bc19363cb9b41606205"
DEVICE = "ee2be53cb75670b548948636a0db1d1ff112bf12"
MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
DRIVER = "drivers/media/i2c/imx882-identity.c"
BINDING = "Documentation/devicetree/bindings/media/i2c/nothing,tetris-imx882-identity.yaml"
DTS = "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris.dts"
TOP = "drivers/clk/mediatek/clk-mt6878-topckgen.c"
TARGETS = (DRIVER, BINDING, DTS)
INPUTS = (DRIVER, BINDING, TOP, "drivers/media/i2c/Kconfig", "drivers/media/i2c/Makefile",
          "include/linux/clk.h", "include/linux/clk-provider.h", "drivers/clk/clk.c",
          "drivers/i2c/busses/i2c-mt65xx.c")
OBSERVE = "arch/arm64/boot/dts/mediatek/mt6878.dtsi"
FIXTURE = "0055-arm64-dts-mediatek-tetris-imx882-disabled-fixture.patch"
PATCH = HERE / "sensor-mclk.patch"
PACKAGED_PATCH = "0121-media-i2c-imx882-acquire-mclk-source.patch"


def run(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True, errors="replace", stderr=subprocess.PIPE)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("absent or ambiguous source anchor: " + old[:100])
    return text.replace(old, new, 1)


def block(text, marker):
    start = text.index("{", text.index(marker))
    depth = 1
    end = start + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start + 1:end - 1]


def project_patch(data):
    # Some packaged patches contain unrelated legacy diffs Git cannot parse.
    # Validate only complete file sections belonging to this sensor baseline.
    sections = re.split(r"(?=^diff --git |^diff -ruN |^--- (?:a/|orig/|/dev/null))",
                        data.decode("latin1"), flags=re.M)
    selected = []
    for section in sections:
        target = re.search(r"^\+\+\+ b/([^\n\t]+)", section, re.M)
        if target and target.group(1) in INPUTS:
            selected.append(section.split("\n-- \n", 1)[0].rstrip("\n") + "\n")
    return "".join(selected).encode("latin1")


def vendor_inputs(upstream):
    sources = {}
    for repo, commit, paths in (
        ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE, (
            "arch/arm64/boot/dts/mediatek/k6878v1_64_tetris.dts",
            "arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi",
            "drivers/clk/mediatek/clk-mt6878.c")),
        ("android_kernel_modules_nothing_mt6878", MODULES, (
            "mtkcam/imgsensor/src-v4l2/adaptor-hw.c",
            "mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c",
            "mtkcam/imgsensor/src-v4l2/common/imx882txd_mipi_raw/imx882txdmipiraw_Sensor.c"))):
        if run(["git", "cat-file", "-t", commit], upstream / repo).strip() != "commit":
            raise ValueError("source pin is not a commit")
        for path in paths:
            data = run(["git", "show", commit + ":" + path], upstream / repo)
            sources[path] = data
    return sources


def verify_vendor(sources):
    board = sources["arch/arm64/boot/dts/mediatek/k6878v1_64_tetris.dts"]
    if '#include "mediatek/cust_mt6878_camera_v4l2.dtsi"' not in board:
        raise ValueError("Tetris camera include changed")
    dtsi = sources["arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi"]
    sensor = block(dtsi, "sensor0: sensor0@1a")
    clocks = re.search(r"clocks = (.*?);", sensor, re.S).group(1)
    names = re.search(r"clock-names = (.*?);", sensor, re.S).group(1)
    ids = re.findall(r"CLK_TOP_\w+", clocks)
    labels = re.findall(r'"([^"]+)"', names)
    if dict(zip(labels, ids)).get("24") != "CLK_TOP_UVPLL192M_D8" or ids[-1] != "CLK_TOP_CAMTG2_SEL":
        raise ValueError("B4.1 sensor clock route changed")
    if "power-domains" in sensor:
        raise ValueError("sensor gained a domain dependency")
    hw = sources["mtkcam/imgsensor/src-v4l2/adaptor-hw.c"]
    if "return ctx->clk[CLK_24M];" not in hw or "clk_set_parent(mclk, mclk_src)" not in hw:
        raise ValueError("B4.1 explicit MCLK parent operation changed")
    expected = [("MCLK", 24, 0), ("RST", 0, 0), ("AFVDD", 2800000, 1),
                ("AVDD", 2800000, 0), ("DVDD", 1200000, 1), ("DOVDD", 1800000, 1),
                ("MCLK_DRIVING_CURRENT", 4, 5), ("RST", 1, 1)]
    for path, data in sources.items():
        if path.endswith("Sensor.c"):
            seq = block(data, "static struct subdrv_pw_seq_entry pw_seq[]")
            rows = [(name, int(value), int(delay)) for name, value, delay in
                    re.findall(r"\{HW_ID_(\w+), (\d+), (\d+)\}", seq)]
            if rows != expected:
                raise ValueError("B4.1 sensor power sequence changed: " + path)
    clk = sources["drivers/clk/mediatek/clk-mt6878.c"]
    if '"top_uvpll192m_d8"' not in block(clk, "top_camtg2_parents[]"):
        raise ValueError("source is not a CAMTG2 parent")


def baseline(upstream, archive=None):
    archive = archive or upstream / ("linux-" + KERNEL + ".tar.gz")
    apk = (PACKAGE / "APKBUILD").read_text()
    expected = re.search(r"^([0-9a-f]{128})  linux-postmarketos-mediatek-mt6878-" +
                         KERNEL + r"\.tar\.gz$", apk, re.M).group(1)
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha512").hexdigest()
    if actual != expected:
        raise ValueError("pinned Linux archive checksum mismatch")
    files = {}
    prefix = "linux-" + KERNEL + "/"
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            path = member.name.removeprefix(prefix)
            if member.isfile() and path in (*INPUTS, OBSERVE):
                files[path] = tar.extractfile(member).read()
    patches = {}
    with tempfile.TemporaryDirectory(prefix="sensor-base-") as directory:
        tree = Path(directory)
        for path, data in files.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for name in re.findall(r"^\s+(\S+\.patch)$", apk, re.M):
            if name == PACKAGED_PATCH:
                # Construct the pre-delta baseline; verify this reviewed copy below.
                continue
            patch = PACKAGE / name
            touched = re.findall(r"^\+\+\+ b/(.+)$", patch.read_bytes().decode("latin1"), re.M)
            if not set(touched).intersection(INPUTS):
                continue
            run(["git", "ls-files", "--error-unmatch", str(patch.relative_to(ROOT))], ROOT)
            data = patch.read_bytes()
            package_sha = re.search(r"^([0-9a-f]{128})  " + re.escape(name) + r"$", apk, re.M)
            if not package_sha or hashlib.sha512(data).hexdigest() != package_sha.group(1):
                raise ValueError("packaged source checksum mismatch: " + name)
            projection = tree / "baseline-input.patch"
            projection.write_bytes(project_patch(data))
            args = ["git", "apply", str(projection)]
            try:
                run(args, tree)
            except subprocess.CalledProcessError as error:
                raise ValueError(name + ": " + (error.output + error.stderr)[:2000]) from error
            patches[name] = digest(data)
        files = {path: (tree / path).read_text() for path in INPUTS}
        files[OBSERVE] = (tree / OBSERVE).read_text()
    # The parent owns full board patch assembly. Test this delta on the complete
    # sensor subtree added by the packaged fixture, rather than a mutated DT tree.
    fixture = PACKAGE / FIXTURE
    run(["git", "ls-files", "--error-unmatch", str(fixture.relative_to(ROOT))], ROOT)
    fixture_data = fixture.read_bytes()
    fixture_sha = re.search(r"^([0-9a-f]{128})  " + re.escape(FIXTURE) + r"$", apk, re.M).group(1)
    if hashlib.sha512(fixture_data).hexdigest() != fixture_sha:
        raise ValueError("packaged sensor fixture checksum mismatch")
    added = "".join(line[1:] for line in fixture_data.decode().splitlines(True)
                    if line.startswith("+") and not line.startswith("+++"))
    files[DTS] = "&i2c8 {" + block(added, "&i2c8 {") + "};\n"
    patches[FIXTURE] = digest(fixture_data)
    return files, {"kernel_archive_sha512": actual, "packaged_patch_sha256": patches,
                   "dt_application_scope": "complete I2C8 sensor subtree from packaged 0055; full board assembly is parent CI"}


def payload(base):
    driver = replace_once(base[DRIVER], "#include <linux/clk.h>\n",
                          "#include <linux/clk.h>\n#include <linux/clk-provider.h>\n#include <linux/kernel.h>\n")
    driver = replace_once(driver, "\tstruct clk *xclk;", "\tstruct clk *xclk;\n\tstruct clk *xclk_source;")
    driver = replace_once(driver, "\tbool rate_exclusive;", "\tbool rate_exclusive;\n\tbool source_rate_exclusive;")
    driver = replace_once(driver, "static int imx882_read_reg", (HERE / "imx882-mclk.c").read_text() + "\nstatic int imx882_read_reg")
    driver = replace_once(driver, "\tif (imx882->rate_exclusive) {\n\t\tclk_rate_exclusive_put(imx882->xclk);\n\t\timx882->rate_exclusive = false;\n\t}\n\treturn ret;",
                          "\timx882_mclk_release(imx882);\n\treturn ret;")
    driver = replace_once(driver, "\tret = clk_set_rate_exclusive(imx882->xclk, IMX882_XCLK_RATE);\n\tif (ret)\n\t\treturn ret;\n\timx882->rate_exclusive = true;\n\tif (clk_get_rate(imx882->xclk) != IMX882_XCLK_RATE)\n\t\treturn -EINVAL;\n\n", "")
    driver = replace_once(driver, "\tint cleanup_ret;\n", "\tint cleanup_ret;\n\tu32 xclk_rate;\n")
    driver = replace_once(driver, "\timx882 = devm_kzalloc", "\tif (!i2c_check_functionality(client->adapter, I2C_FUNC_I2C))\n\t\treturn -EOPNOTSUPP;\n\tret = device_property_read_u32(dev, \"clock-frequency\", &xclk_rate);\n\tif (ret || xclk_rate != IMX882_XCLK_RATE)\n\t\treturn dev_err_probe(dev, -EINVAL, \"requires explicit 24 MHz MCLK\\n\");\n\n\timx882 = devm_kzalloc")
    driver = replace_once(driver, '#include <linux/pinctrl/consumer.h>', '#include <linux/pinctrl/consumer.h>\n#include <linux/property.h>')
    driver = replace_once(driver, "\tfor (i = 0; i < IMX882_NUM_SUPPLIES; i++)\n\t\timx882->supplies[i].supply = imx882_supply_names[i];",
                          "\tfor (i = 0; i < IMX882_NUM_SUPPLIES; i++) {\n\t\tchar property[32];\n\n\t\tsnprintf(property, sizeof(property), \"%s-supply\", imx882_supply_names[i]);\n\t\tif (!device_property_present(dev, property))\n\t\t\treturn dev_err_probe(dev, -EINVAL, \"missing sensor supply reference\\n\");\n\t\timx882->supplies[i].supply = imx882_supply_names[i];\n\t}")
    driver = replace_once(driver, '\timx882->reset = devm_gpiod_get(dev, "reset", GPIOD_OUT_HIGH);',
                          '\timx882->xclk_source = devm_clk_get(dev, "xclk-source");\n\tif (IS_ERR(imx882->xclk_source))\n\t\treturn dev_err_probe(dev, PTR_ERR(imx882->xclk_source),\n\t\t\t\t     "24 MHz MCLK source unavailable\\n");\n\n\timx882->reset = devm_gpiod_get(dev, "reset", GPIOD_ASIS);')
    anchor = "\tret = imx882_power_on(imx882, &enabled_supplies, &clock_enabled);"
    driver = replace_once(driver, anchor, """\tif (!gpiod_is_active_low(imx882->reset))
		return dev_err_probe(dev, -EINVAL, "reset must be active-low\\n");
	/* Normal references preserve shared DOVDD; reject an observed ON rail. */
	for (i = 0; i < IMX882_NUM_SUPPLIES; i++) {
		ret = regulator_is_enabled(imx882->supplies[i].consumer);
		if (ret < 0)
			return dev_err_probe(dev, ret, "sensor rail state unavailable\\n");
		if (ret)
			return dev_err_probe(dev, -EBUSY, "sensor rail already enabled\\n");
	}
	ret = imx882_mclk_acquire(imx882);
	if (ret)
		return dev_err_probe(dev, ret, "cannot acquire sensor MCLK\\n");
	ret = gpiod_direction_output(imx882->reset, 1);
	if (ret) {
		imx882_mclk_release(imx882);
		return ret;
	}

""" + anchor)
    binding = replace_once(base[BINDING], "  clocks:\n    maxItems: 1\n\n  clock-names:\n    const: xclk",
                           "  clocks:\n    items:\n      - description: CAMTG2 selector and gate\n      - description: UVPLL192M_D8 source, already at 24 MHz\n\n  clock-names:\n    items:\n      - const: xclk\n      - const: xclk-source\n\n  clock-frequency:\n    const: 24000000")
    binding = replace_once(binding, "  - clock-names\n", "  - clock-names\n  - clock-frequency\n")
    binding = replace_once(binding, "            clocks = <&camera_clk>;\n            clock-names = \"xclk\";",
                           "            clocks = <&camera_clk 0>, <&camera_clk 1>;\n            clock-names = \"xclk\", \"xclk-source\";\n            clock-frequency = <24000000>;")
    binding = replace_once(binding, "reset-gpios = <&gpio 25 0>;", "reset-gpios = <&gpio 25 1>;")
    dts = replace_once(base[DTS], '\t\tclocks = <&topckgen CLK_TOP_CAMTG2>;\n\t\tclock-names = "xclk";',
                       '\t\tclocks = <&topckgen CLK_TOP_CAMTG2_SEL>,\n\t\t\t <&topckgen CLK_TOP_UVPLL192M_D8>;\n\t\tclock-names = "xclk", "xclk-source";\n\t\tclock-frequency = <24000000>;')
    return {DRIVER: driver, BINDING: binding, DTS: dts}


def patch_text(base, output):
    return "".join("diff --git a/" + path + " b/" + path + "\n" + "".join(
        difflib.unified_diff(base[path].splitlines(True), output[path].splitlines(True),
                             fromfile="a/" + path, tofile="b/" + path)) for path in TARGETS)


def apply_check(base, patch, output):
    with tempfile.TemporaryDirectory(prefix="sensor-delta-") as directory:
        tree = Path(directory)
        for path in TARGETS:
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(base[path])
        candidate = tree / "delta.patch"
        candidate.write_text(patch)
        run(["git", "apply", "--check", str(candidate)], tree)
        run(["git", "apply", str(candidate)], tree)
        for path in TARGETS:
            if (tree / path).read_text() != output[path]:
                raise ValueError("applied bytes differ: " + path)


def package_contract(patch):
    apk = (PACKAGE / "APKBUILD").read_text()
    source = re.search(r'^source="\n(.*?)^"$', apk, re.M | re.S).group(1).split()
    names = [name for name in source if name.endswith(".patch")]
    if names.count(PACKAGED_PATCH) != 1:
        raise ValueError("identity MCLK patch must be packaged exactly once")
    for prerequisite in ("0049-media-i2c-imx882-identity.patch",
                         "0050-media-i2c-imx882-honor-active-low-reset.patch", FIXTURE,
                         "0106-media-i2c-imx882-check-shutdown.patch",
                         "0107-media-i2c-imx882-hold-clock-rate.patch"):
        if names.index(prerequisite) >= names.index(PACKAGED_PATCH):
            raise ValueError("identity MCLK package order changed")
    data = (PACKAGE / PACKAGED_PATCH).read_bytes()
    if data != patch.encode():
        raise ValueError("packaged identity MCLK patch differs from reviewed delta")
    sums = re.findall(r"^([0-9a-f]{128})  " + re.escape(PACKAGED_PATCH) + r"$", apk, re.M)
    actual = hashlib.sha512(data).hexdigest()
    if sums != [actual]:
        raise ValueError("identity MCLK package checksum missing, duplicated or stale")
    return {"name": PACKAGED_PATCH, "sha512": actual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT.parent)
    parser.add_argument("--kernel-archive", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    sources = vendor_inputs(args.upstream)
    verify_vendor(sources)
    base, evidence = baseline(args.upstream, args.kernel_archive)
    output = payload(base)
    patch = patch_text(base, output)
    apply_check(base, patch, output)
    packaged = package_contract(patch)
    evidence.update(kernel_commit=KERNEL, device_modules_commit=DEVICE, modules_commit=MODULES,
                    vendor_source_sha256={p: digest(d.encode()) for p, d in sources.items()},
                    baseline_sha256={p: digest(d.encode()) for p, d in base.items()},
                    output_sha256={p: digest(d.encode()) for p, d in output.items()},
                    patch_sha256=digest(patch.encode()), packaged_patch=packaged)
    serialized = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.write:
        PATCH.write_text(patch)
        (HERE / "evidence.json").write_text(serialized)
    elif PATCH.read_text() != patch or (HERE / "evidence.json").read_text() != serialized:
        raise ValueError("stale integration patch or source evidence")
    print("PASS: pinned source route and packaged sensor baseline; delta applies byte-for-byte")
    print("NOT RUN: native compilation, DT validation or hardware activation")


if __name__ == "__main__":
    main()
