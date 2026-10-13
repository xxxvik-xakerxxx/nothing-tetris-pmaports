#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compose the stream lifecycle delta atop exact packaged sources; no compile."""
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
DRIVER = "drivers/media/i2c/imx882-tetris-stream.c"
IDENTITY = "drivers/media/i2c/imx882-identity.c"
CORE = "drivers/media/i2c/imx882-stream-core.h"
TABLES = "drivers/media/i2c/imx882-tetris-tables.h"
BINDING = "Documentation/devicetree/bindings/media/i2c/nothing,tetris-imx882-stream.yaml"
KCONFIG = "drivers/media/i2c/Kconfig"
MAKEFILE = "drivers/media/i2c/Makefile"
TOP = "drivers/clk/mediatek/clk-mt6878-topckgen.c"
INPUTS = (DRIVER, IDENTITY, CORE, TABLES, BINDING, KCONFIG, MAKEFILE, TOP,
          "include/linux/clk.h", "include/linux/clk-provider.h", "drivers/clk/clk.c",
          "include/linux/gpio/consumer.h", "drivers/pinctrl/mediatek/pinctrl-paris.c")
TARGETS = (DRIVER, BINDING, KCONFIG)
SENSOR = "mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, stderr=subprocess.PIPE)


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("missing or ambiguous source anchor: " + old[:100])
    return text.replace(old, new, 1)


def function(text, marker):
    start = text.index(marker)
    brace = text.index("{", start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end] + "\n"


def block(text, marker):
    result = function(text, marker)
    return result[result.index("{") + 1:result.rindex("}")]


def package_file(name, apk):
    path = PACKAGE / name
    run(["git", "ls-files", "--error-unmatch", str(path.relative_to(ROOT))], ROOT)
    data = path.read_bytes()
    expected = re.findall(r"^([0-9a-f]{128})  " + re.escape(name) + r"$", apk, re.M)
    if expected != [hashlib.sha512(data).hexdigest()]:
        raise ValueError("packaged input checksum missing/changed: " + name)
    return data


def project(data, targets=INPUTS):
    sections = re.split(r"(?=^diff --git |^diff -ruN |^--- (?:a/|orig/|/dev/null))",
                        data.decode("latin1"), flags=re.M)
    return "".join(section.split("\n-- \n", 1)[0].rstrip("\n") + "\n"
                   for section in sections
                   if (match := re.search(r"^\+\+\+ b/([^\n\t]+)", section, re.M))
                   and match[1] in targets).encode("latin1")


def baseline(archive):
    apk = (PACKAGE / "APKBUILD").read_text()
    for variable, pin in (("_commit", KERNEL), ("_devmods_commit", DEVICE), ("_connmods_commit", MODULES)):
        if f'{variable}="{pin}"' not in apk:
            raise ValueError("packaged source pin changed: " + variable)
    expected = re.search(r"^([0-9a-f]{128})  linux-postmarketos-mediatek-mt6878-" + KERNEL + r"\.tar\.gz$", apk, re.M)
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha512").hexdigest()
    if not expected or expected[1] != actual:
        raise ValueError("Linux archive differs from exact packaged checksum")
    source = re.search(r'^source="\n(.*?)^"$', apk, re.M | re.S).group(1).split()
    names = [name for name in source if name.endswith(".patch")]
    if len(names) != len(set(names)):
        raise ValueError("duplicate packaged patch")
    files = {}
    prefix = "linux-" + KERNEL + "/"
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            path = member.name.removeprefix(prefix)
            if member.isfile() and path in INPUTS:
                files[path] = tar.extractfile(member).read()
    original = {p: sha(data) for p, data in files.items()}
    patches = {}
    with tempfile.TemporaryDirectory(prefix="stream-packaged-base-") as directory:
        tree = Path(directory)
        for path, data in files.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for name in names:
            projected = project((PACKAGE / name).read_bytes())
            if not projected:
                continue
            data = package_file(name, apk)
            candidate = tree / "packaged-input.patch"
            candidate.write_bytes(project(data))
            try:
                run(["git", "apply", "--check", str(candidate)], tree)
                run(["git", "apply", str(candidate)], tree)
            except subprocess.CalledProcessError as error:
                raise ValueError(name + ": " + error.stderr.decode(errors="replace")) from error
            patches[name] = sha(data)
        files = {path: (tree / path).read_text() for path in INPUTS}
    if "0112-media-i2c-imx882-v4l2-controls.patch" not in patches or "0121-media-i2c-imx882-acquire-mclk-source.patch" not in patches:
        raise ValueError("shipping stream/identity source prerequisite absent")
    config = package_file("config-postmarketos-mediatek-mt6878.aarch64", apk).decode()
    if re.search(r"^CONFIG_VIDEO_IMX882_TETRIS=", config, re.M):
        raise ValueError("streaming driver is active in shipping config")
    return files, {"kernel_archive_sha512": actual, "archive_source_sha256": original,
                   "packaged_patch_sha256": patches, "baseline_sha256": {p: sha(d.encode()) for p, d in files.items()},
                   "shipping_config_sha256": sha(config.encode())}


def vendor(device_repo, modules_repo):
    result, blobs = {}, {}
    specs = ((device_repo, DEVICE, ("arch/arm64/boot/dts/mediatek/k6878v1_64_tetris.dts",
                                    "arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi",
                                    "drivers/clk/mediatek/clk-mt6878.c")),
             (modules_repo, MODULES, ("mtkcam/imgsensor/src-v4l2/adaptor-hw.c", SENSOR,
               "mtkcam/imgsensor/src-v4l2/common/imx882txd_mipi_raw/imx882txdmipiraw_Sensor.c")))
    for repo, commit, paths in specs:
        if run(["git", "cat-file", "-t", commit], repo).strip() != b"commit":
            raise ValueError("NOS pin is not a commit")
        for path in paths:
            result[path] = run(["git", "show", commit + ":" + path], repo).decode()
            blobs[path] = run(["git", "rev-parse", commit + ":" + path], repo).decode().strip()
    dt = result["arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi"]
    sensor = block(dt, "sensor0: sensor0@1a")
    ids = re.findall(r"CLK_TOP_\w+", re.search(r"clocks = (.*?);", sensor, re.S)[1])
    names = re.findall(r'"([^"]+)"', re.search(r"clock-names = (.*?);", sensor, re.S)[1])
    if dict(zip(names, ids)).get("24") != "CLK_TOP_UVPLL192M_D8" or ids[-1] != "CLK_TOP_CAMTG2_SEL":
        raise ValueError("NOS MCLK route changed")
    hw = result["mtkcam/imgsensor/src-v4l2/adaptor-hw.c"]
    if "return ctx->clk[CLK_24M];" not in hw or "clk_set_parent(mclk, mclk_src)" not in hw:
        raise ValueError("NOS MCLK source operation changed")
    expected = [("MCLK", 24, 0), ("RST", 0, 0), ("AFVDD", 2800000, 1), ("AVDD", 2800000, 0),
                ("DVDD", 1200000, 1), ("DOVDD", 1800000, 1), ("MCLK_DRIVING_CURRENT", 4, 5), ("RST", 1, 1)]
    for path, data in result.items():
        if path.endswith("Sensor.c"):
            rows = [(name, int(value), int(delay)) for name, value, delay in
                    re.findall(r"\{HW_ID_(\w+), (\d+), (\d+)\}", block(data, "static struct subdrv_pw_seq_entry pw_seq[]"))]
            if rows != expected:
                raise ValueError("NOS power table changed: " + path)
    return result, blobs


def payload(base):
    code = replace_once(base[DRIVER], "#include <linux/clk.h>\n", "#include <linux/clk.h>\n#include <linux/clk-provider.h>\n#include <linux/property.h>\n#include <linux/slab.h>\n")
    code = replace_once(code, "\tstruct clk *xclk;", "\tstruct clk *xclk;\n\tstruct clk *xclk_source;")
    code = replace_once(code, "\tbool rate_exclusive;", "\tbool rate_exclusive;\n\tbool source_rate_exclusive;\n\tbool mclk_selected;\n\tint first_error;")
    mclk = "\n".join(function(base[IDENTITY], "static " + kind + " imx882_mclk_" + name)
                       for kind, name in (("void", "release"), ("int", "acquire")))
    code = replace_once(code, "static int imx882_read_reg", mclk + "\nstatic int imx882_read_reg")
    begin = code.index("static int imx882_enable_supply")
    last = function(code, "static int imx882_power_on")
    end = code.index("static int imx882_power_on") + len(last)
    code = code[:begin] + (HERE / "stream-power.c").read_text() + "\n" + code[end:]
    code = replace_once(code, "\tbool faulted;", "\tbool faulted;\n\tbool supplies_acquired;\n\tint first_error;")
    lifecycle = (HERE / "stream-lifecycle.c").read_text()
    stop = function(lifecycle, "static int imx882_stop")
    helpers = lifecycle[:lifecycle.index("static int imx882_stop")]
    code = replace_once(code, "static int imx882_apply_controls", helpers + (HERE / "probe-resources.c").read_text() + "\nstatic int imx882_apply_controls")
    code = replace_once(code, function(code, "static int imx882_stop"), stop)
    code = replace_once(code, "\tif (camera->faulted)\n\t\treturn -EIO;\n\tif (camera->streaming)\n\t\tret = imx882_apply_controls(camera);\n\tif (ret)\n\t\tcamera->faulted = true;",
                        "\tif (camera->faulted)\n\t\treturn camera->first_error;\n\tif (camera->streaming) {\n\t\tret = imx882_power_validate(&camera->power);\n\t\tif (!ret)\n\t\t\tret = imx882_apply_controls(camera);\n\t}\n\tif (ret)\n\t\treturn imx882_camera_fault(camera, ret);")
    code = replace_once(code, "ret = camera->streaming ? imx882_stop(camera) : 0;\n\t\tgoto unlock;", "ret = imx882_stop(camera);\n\t\tgoto unlock;")
    code = replace_once(code, "\t\tret = -EIO;\n\t\tgoto unlock;", "\t\tret = camera->first_error;\n\t\tgoto unlock;")
    code = replace_once(code, "\tif (camera->streaming) {\n\t\tret = 0;", "\tif (camera->streaming) {\n\t\tret = imx882_power_validate(&camera->power);\n\t\tif (ret)\n\t\t\tret = imx882_camera_fault(camera, ret);")
    code = replace_once(code, "failed:\n\t/* Reset/power-down contains even an ambiguous final stream-on write. */\n\tcleanup = imx882_stop(camera);\n\tif (cleanup)",
                        "failed:\n\timx882_camera_fault(camera, ret);\n\t/* Only a checked reset/power-down contains an ambiguous stream-on. */\n\tcleanup = imx882_stop(camera);\n\tif (cleanup && camera->power.first_error)")
    code = replace_once(code, '"camera cleanup failed: %d\\n", cleanup);',
                        '"camera cleanup failed: %d\\n", camera->power.first_error);')
    probe = function(code, "static int imx882_camera_probe")
    probe = replace_once(probe, "\tstruct imx882_identity *power;\n", "")
    probe = replace_once(probe, "\tint ret, i;\n", "\tint ret;\n")
    probe = replace_once(probe, "\tep = fwnode_graph_get_next_endpoint", "\tif (!i2c_check_functionality(client->adapter, I2C_FUNC_I2C))\n\t\treturn -EOPNOTSUPP;\n\tep = fwnode_graph_get_next_endpoint")
    probe = replace_once(probe, "camera = devm_kzalloc(dev, sizeof(*camera), GFP_KERNEL);", "camera = kzalloc(sizeof(*camera), GFP_KERNEL);")
    probe = replace_once(probe, "\tpower = &camera->power;", "\tget_device(dev);")
    start = probe.index("\tfor (i = 0;")
    end = probe.index("\tmutex_init(&camera->lock);")
    probe = probe[:start] + "\tret = imx882_resources_get(camera);\n\tif (ret)\n\t\tgoto release_resources;\n" + probe[end:]
    probe = replace_once(probe, "\tmutex_destroy(&camera->lock);\n\treturn ret;", "\tmutex_destroy(&camera->lock);\nrelease_resources:\n\timx882_resources_put(camera);\n\treturn ret;")
    code = replace_once(code, function(code, "static int imx882_camera_probe"), probe)
    remove = function(code, "static void imx882_camera_remove")
    remove = replace_once(remove, "ret = camera->streaming ? imx882_stop(camera) : 0;", "ret = imx882_stop(camera);")
    remove = replace_once(remove, "\tmutex_destroy(&camera->lock);", "\tmutex_destroy(&camera->lock);\n\tif (camera->power.first_error || imx882_power_active(camera)) {\n\t\t/* Built-in storage/device/resources survive uncertain shutdown. */\n\t\tdev_err(&client->dev, \"camera power owner retained until reboot\\n\");\n\t\treturn;\n\t}\n\timx882_resources_put(camera);")
    code = replace_once(code, function(code, "static void imx882_camera_remove"), remove)
    code = replace_once(code, "ret = camera->streaming || camera->faulted ? -EBUSY : 0;", "ret = camera->streaming || camera->faulted || imx882_power_active(camera) ? -EBUSY : 0;")
    code = replace_once(code, '\t\t.name = "tetris-imx882-stream",', '\t\t.name = "tetris-imx882-stream",\n\t\t.suppress_bind_attrs = true,')
    binding = replace_once(base[BINDING], "  clocks:\n    maxItems: 1\n  clock-names:\n    const: xclk",
                           "  clocks:\n    items:\n      - description: CAMTG2_SEL selector and gate\n      - description: UVPLL192M_D8 source, already at 24 MHz\n  clock-names:\n    items:\n      - const: xclk\n      - const: xclk-source")
    config = replace_once(base[KCONFIG], '\ttristate "Nothing Tetris IMX882 V4L2 streaming candidate"', '\tbool "Nothing Tetris IMX882 V4L2 streaming candidate"\n\tdefault n')
    return {DRIVER: code, BINDING: binding, KCONFIG: config}


def patch_text(base, output):
    return "".join("diff --git a/" + path + " b/" + path + "\n" + "".join(
        difflib.unified_diff(base[path].splitlines(True), output[path].splitlines(True),
                             fromfile="a/" + path, tofile="b/" + path)) for path in TARGETS)


def apply_check(base, patch, output):
    with tempfile.TemporaryDirectory(prefix="stream-owner-apply-") as directory:
        tree = Path(directory)
        for path in TARGETS:
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(base[path])
        candidate = tree / "stream-owner.patch"
        candidate.write_text(patch)
        run(["git", "apply", "--check", str(candidate)], tree)
        run(["git", "apply", str(candidate)], tree)
        for path in TARGETS:
            if (tree / path).read_text() != output[path]:
                raise ValueError("applied stream bytes differ: " + path)


def build(archive, device_repo, modules_repo):
    sources, blobs = vendor(device_repo, modules_repo)
    base, evidence = baseline(archive)
    output = payload(base)
    delta = patch_text(base, output)
    apply_check(base, delta, output)
    evidence.update(kernel_commit=KERNEL, device_modules_commit=DEVICE, modules_commit=MODULES,
                    vendor_blob_ids=blobs, vendor_sha256={p: sha(d.encode()) for p, d in sources.items()},
                    payload_sha256={p: sha(d.encode()) for p, d in output.items()},
                    template_sha256={p: sha((HERE / p).read_bytes()) for p in
                                     ("stream-power.c", "stream-lifecycle.c", "probe-resources.c")},
                    patch_sha256=sha(delta.encode()))
    return base, output, sources, delta, evidence


def arguments(parser, explicit=False):
    upstream = ROOT.parent
    parser.add_argument("--kernel-archive", type=Path, required=explicit,
                        default=None if explicit else upstream / ("linux-" + KERNEL + ".tar.gz"))
    parser.add_argument("--device-repo", type=Path, required=explicit,
                        default=None if explicit else upstream / "android_kernel_device_modules_6.1_nothing_mt6878")
    parser.add_argument("--modules-repo", type=Path, required=explicit,
                        default=None if explicit else upstream / "android_kernel_modules_nothing_mt6878")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    arguments(parser)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    _, _, _, delta, evidence = build(args.kernel_archive, args.device_repo, args.modules_repo)
    for name, data in {"stream-owner.patch": delta, "evidence.json": json.dumps(evidence, indent=2, sort_keys=True) + "\n"}.items():
        if args.write:
            (HERE / name).write_text(data)
        elif (HERE / name).read_text() != data:
            raise ValueError("stale stream output: " + name)
    print("PASS: exact sources and strict shipping-baseline stream delta application")
    print("NOT RUN: native compile, DT, emulation, hardware or capture")
