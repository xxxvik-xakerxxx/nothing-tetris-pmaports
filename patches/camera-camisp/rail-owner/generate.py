#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read exact NOS objects and pinned Linux archive; generate scoped deltas."""
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
DRIVER = "drivers/regulator/tetris-camera-gpio-regulator.c"
BINDING = "Documentation/devicetree/bindings/regulator/nothing,tetris-camera-gpio-regulator.yaml"
DTS = "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris.dts"
FIXTURE = "0055-arm64-dts-mediatek-tetris-imx882-disabled-fixture.patch"
PIN_TABLE = "drivers/pinctrl/mediatek/pinctrl-mtk-mt6878.h"
PIN_TABLE_PATCH = "0006-pinctrl-mediatek-mt6878-eint.patch"
KCONFIG = "drivers/regulator/Kconfig"
MAKEFILE = "drivers/regulator/Makefile"
NATIVE = (KCONFIG, MAKEFILE, "drivers/regulator/fixed.c", "drivers/regulator/core.c",
          "drivers/regulator/of_regulator.c", "include/linux/regulator/driver.h",
          "include/linux/gpio/consumer.h", "include/linux/of.h", "include/linux/of_platform.h",
          "include/linux/gpio/driver.h",
          "drivers/gpio/gpiolib.c", "drivers/gpio/gpiolib-devres.c",
          "drivers/pinctrl/core.c", "drivers/pinctrl/pinmux.c",
          "drivers/pinctrl/mediatek/pinctrl-paris.c",
          "drivers/pinctrl/mediatek/pinctrl-mtk-common-v2.c",
          "drivers/pinctrl/mediatek/pinctrl-mtk-common-v2.h",
          "drivers/pinctrl/mediatek/pinctrl-paris.h", PIN_TABLE,
          "drivers/pinctrl/mediatek/pinctrl-mt6878.c")
RAILS = {"afvdd": (1, 2800000), "avdd": (22, 2800000),
         "dvdd": (21, 1200000), "dovdd": (23, 1800000)}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, stderr=subprocess.PIPE)


def block(text, marker):
    begin = text.index("{", text.index(marker))
    end, depth = begin + 1, 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[begin + 1:end - 1]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("missing or ambiguous source anchor: " + old[:100])
    return text.replace(old, new, 1)


def sources(upstream, device_repo=None, modules_repo=None):
    files, blobs = {}, {}
    specs = (
        ("android_kernel_device_modules_6.1_nothing_mt6878", DEVICE, (
            "arch/arm64/boot/dts/mediatek/k6878v1_64_tetris.dts",
            "arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi")),
        ("android_kernel_modules_nothing_mt6878", MODULES, (
            "mtkcam/imgsensor/src-v4l2/common/imx882_mipi_raw/imx882mipiraw_Sensor.c",
            "mtkcam/imgsensor/src-v4l2/common/imx882txd_mipi_raw/imx882txdmipiraw_Sensor.c")))
    repositories = (device_repo, modules_repo)
    for (repo, commit, paths), supplied in zip(specs, repositories):
        tree = supplied if supplied is not None else upstream / repo
        if run(["git", "cat-file", "-t", commit], tree).strip() != b"commit":
            raise ValueError("NOS pin is not a commit")
        for path in paths:
            files[path] = run(["git", "show", commit + ":" + path], tree)
            blobs[path] = run(["git", "rev-parse", commit + ":" + path], tree).decode().strip()
    return files, blobs


def verify_vendor(files):
    board = files["arch/arm64/boot/dts/mediatek/k6878v1_64_tetris.dts"].decode()
    if '#include "mediatek/cust_mt6878_camera_v4l2.dtsi"' not in board:
        raise ValueError("Tetris camera description changed")
    dt = files["arch/arm64/boot/dts/mediatek/cust_mt6878_camera_v4l2.dtsi"].decode()
    for role, label in (("afvdd", "camera_afvdd: camera-afvdd"),
                        ("dovdd", "camera_common_dovdd: camera-common-dovdd")):
        node = block(dt, label)
        pin, voltage = RAILS[role]
        if f"gpio = <&pio {pin} 0x0>;" not in node or "enable-active-high;" not in node:
            raise ValueError("stock GPIO regulator topology changed: " + role)
        if f"regulator-min-microvolt = <{voltage}>;" not in node or f"regulator-max-microvolt = <{voltage}>;" not in node:
            raise ValueError("stock GPIO regulator voltage changed: " + role)
    for role, position in (("avdd", 2), ("dvdd", 4)):
        pin, _ = RAILS[role]
        for suffix, index, state in (("0", position, "low"), ("1", position + 1, "high")):
            node = block(dt, f"camera_pins_cam0_{role}_{suffix}: cam0@{index}")
            if f"PINMUX_GPIO{pin}__FUNC_GPIO{pin}" not in node or f"output-{state};" not in node:
                raise ValueError("stock switched rail GPIO changed: " + role)
    for sensor, address in ((0, "1a"), (1, "10"), (2, "36")):
        node = block(dt, f"sensor{sensor}: sensor{sensor}@{address}")
        if "dovdd-supply = <&camera_common_dovdd>;" not in node:
            raise ValueError("common DOVDD consumer graph changed")
    main = block(dt, "sensor0: sensor0@1a")
    if "afvdd-supply = <&camera_afvdd>;" not in main:
        raise ValueError("main AFVDD consumer changed")
    for path, data in files.items():
        if path.endswith("Sensor.c"):
            sequence = block(data.decode(), "static struct subdrv_pw_seq_entry pw_seq[]")
            for role, (_, voltage) in RAILS.items():
                if not re.search(r"\{HW_ID_" + role.upper() + ", " + str(voltage) + r", \d+\}", sequence):
                    raise ValueError("sensor voltage source changed: " + path)


def baseline(upstream, archive=None):
    archive = archive or upstream / ("linux-" + KERNEL + ".tar.gz")
    apk = (PACKAGE / "APKBUILD").read_text()
    expected = re.search(r"^([0-9a-f]{128})  linux-postmarketos-mediatek-mt6878-" + KERNEL + r"\.tar\.gz$", apk, re.M).group(1)
    with archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha512").hexdigest()
    if actual != expected:
        raise ValueError("Linux archive differs from packaged pin/checksum")
    files = {}
    prefix = "linux-" + KERNEL + "/"
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            path = member.name.removeprefix(prefix)
            if member.isfile() and path in NATIVE:
                files[path] = tar.extractfile(member).read().decode()
    if set(files) != set(NATIVE):
        raise ValueError("pinned kernel source incomplete")
    fixture = PACKAGE / FIXTURE
    run(["git", "ls-files", "--error-unmatch", str(fixture.relative_to(ROOT))], ROOT)
    data = fixture.read_bytes()
    expected_fixture = re.search(r"^([0-9a-f]{128})  " + re.escape(FIXTURE) + r"$", apk, re.M).group(1)
    if hashlib.sha512(data).hexdigest() != expected_fixture:
        raise ValueError("tracked sensor fixture checksum mismatch")
    body = data.decode().split("+++ b/" + DTS + "\n", 1)[1]
    line_hint = None
    current_line = 0
    for line in body.splitlines():
        hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk:
            current_line = int(hunk.group(1))
        elif line.startswith(("+", " ")):
            if line[1:].strip() == "camera_main_afvdd: regulator-camera-main-afvdd {":
                line_hint = current_line
            current_line += 1
    if line_hint is None or line_hint <= 1:
        raise ValueError("missing packaged rail-node source position")
    added = "".join(line[1:] for line in body.splitlines(True)
                    if line.startswith(("+", " ")) and not line.startswith("+++"))
    nodes = []
    for role, (pin, voltage) in RAILS.items():
        label = f"camera_main_{role}: regulator-camera-main-{role}"
        node = block(added, label)
        if (f"gpio = <&pio {pin} GPIO_ACTIVE_HIGH>;" not in node or
                f"regulator-min-microvolt = <{voltage}>;" not in node or
                f"regulator-max-microvolt = <{voltage}>;" not in node or
                'status = "disabled";' not in node):
            raise ValueError("packaged rail fixture differs from NOS topology")
        nodes.append("\t" + label + " {" + node + "};\n")
    files[DTS] = "\n".join(nodes)
    return files, {"kernel_archive_sha512": actual, "fixture_sha256": sha(data),
                   "fixture_line_hint": line_hint,
                   "dt_scope": "four complete disabled rail nodes from tracked 0055; full board assembly is parent CI"}


def payload(base):
    config = """config REGULATOR_TETRIS_CAMERA_GPIO
	bool "Nothing Tetris observed-OFF camera GPIO rails"
	depends on OF && GPIOLIB && PINCTRL_MT6878
	default n
	help
	  Check the four Tetris sensor GPIO rails through their native pinctrl
	  owner before GPIO request. ASIS still invokes a mux-writing callback;
	  the check is not an atomic GPIO/mux ownership handoff. Keep board DT
	  disabled until that handoff is established. Do not adopt inherited ON.

"""
    kconfig = replace_once(base[KCONFIG], "config REGULATOR_GPIO\n", config + "config REGULATOR_GPIO\n")
    makefile = replace_once(base[MAKEFILE], "obj-$(CONFIG_REGULATOR_FIXED_VOLTAGE) += fixed.o\n",
                            "obj-$(CONFIG_REGULATOR_FIXED_VOLTAGE) += fixed.o\nobj-$(CONFIG_REGULATOR_TETRIS_CAMERA_GPIO) += tetris-camera-gpio-regulator.o\n")
    dt = base[DTS]
    for role, (pin, _) in RAILS.items():
        label = f"camera_main_{role}: regulator-camera-main-{role}"
        old = block(dt, label)
        new = replace_once(old, 'compatible = "regulator-fixed";',
                           'compatible = "nothing,tetris-camera-gpio-regulator";\n\t\tnothing,rail = "' + role + '";')
        new = replace_once(new, f"gpio = <&pio {pin} GPIO_ACTIVE_HIGH>;", f"enable-gpios = <&pio {pin} GPIO_ACTIVE_HIGH>;")
        new = replace_once(new, "\t\tenable-active-high;\n", "")
        dt = replace_once(dt, old, new)
    return {DRIVER: (HERE / Path(DRIVER).name).read_text(),
            BINDING: (HERE / Path(BINDING).name).read_text(), KCONFIG: kconfig,
            MAKEFILE: makefile, DTS: dt}


def prepared_pin_table(base):
    """Reconstruct the sole packaged SoC table change, never accept tree drift."""
    candidate = PACKAGE / PIN_TABLE_PATCH
    run(["git", "ls-files", "--error-unmatch", str(candidate.relative_to(ROOT))], ROOT)
    data = candidate.read_bytes()
    apk = (PACKAGE / "APKBUILD").read_text()
    expected = re.search(r"^([0-9a-f]{128})  " + re.escape(PIN_TABLE_PATCH) + r"$", apk, re.M)
    if not expected or hashlib.sha512(data).hexdigest() != expected[1]:
        raise ValueError("packaged pin table delta checksum changed")
    if re.findall(r"^\+\+\+ b/(.+)$", data.decode(), re.M) != [PIN_TABLE]:
        raise ValueError("packaged pin table delta changed scope")
    with tempfile.TemporaryDirectory(prefix="rail-owner-pin-table-") as directory:
        tree = Path(directory)
        target = tree / PIN_TABLE
        target.parent.mkdir(parents=True)
        target.write_text(base[PIN_TABLE])
        patch = tree / PIN_TABLE_PATCH
        patch.write_bytes(data)
        run(["git", "apply", "--check", str(patch)], tree)
        run(["git", "apply", str(patch)], tree)
        table = target.read_text()
    # EINT repair must not alter the GPIO pin/functional table used by preflight.
    marker = "static struct mtk_eint_pin eint_pins_mt6878[]"
    pins = base[PIN_TABLE].split(marker, 1)[0]
    pins = pins.replace("#include \"pinctrl-paris.h\"\n", "#include \"pinctrl-paris.h\"\n\n#define EINT_INVALID_BASE\t0xff\n", 1)
    if table.split(marker, 1)[0] != pins:
        raise ValueError("packaged EINT repair changed GPIO pin metadata")
    return table, {"patch": PIN_TABLE_PATCH, "patch_sha256": sha(data),
                   "prepared_sha256": sha(table.encode())}


def patch_text(base, output, targets, line_offset=0):
    result = ""
    for path in targets:
        before = base.get(path, "")
        result += "diff --git a/" + path + " b/" + path + "\n"
        if path not in base:
            result += "new file mode 100644\n"
        delta = "".join(difflib.unified_diff(before.splitlines(True), output[path].splitlines(True),
                                           fromfile="a/" + path if path in base else "/dev/null",
                                           tofile="b/" + path))
        if line_offset:
            delta = re.sub(r"^@@ -(\d+)(,\d+)? \+(\d+)(,\d+)? @@",
                           lambda m: "@@ -" + str(int(m[1]) + line_offset) + (m[2] or "") +
                           " +" + str(int(m[3]) + line_offset) + (m[4] or "") + " @@", delta, flags=re.M)
        result += delta
    return result


def apply_check(base, provider, dt, output):
    with tempfile.TemporaryDirectory(prefix="rail-owner-apply-") as directory:
        tree = Path(directory)
        for path in (KCONFIG, MAKEFILE, DTS):
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(base[path])
        for name, content in (("provider.patch", provider), ("disabled-description.patch", dt)):
            candidate = tree / name
            candidate.write_text(content)
            run(["git", "apply", "--check", str(candidate)], tree)
            run(["git", "apply", str(candidate)], tree)
        for path, data in output.items():
            if (tree / path).read_text() != data:
                raise ValueError("applied source differs: " + path)


def build(upstream, archive=None, device_repo=None, modules_repo=None):
    vendor, blobs = sources(upstream, device_repo, modules_repo)
    verify_vendor(vendor)
    base, evidence = baseline(upstream, archive)
    _, pin_table_identity = prepared_pin_table(base)
    output = payload(base)
    provider = patch_text(base, output, (DRIVER, BINDING, KCONFIG, MAKEFILE))
    dt = patch_text(base, output, (DTS,), evidence["fixture_line_hint"] - 1)
    apply_check(base, provider, dt, output)
    evidence.update(kernel_commit=KERNEL, device_modules_commit=DEVICE, modules_commit=MODULES,
                    packaged_pin_table=pin_table_identity,
                    vendor_blob_ids=blobs, vendor_sha256={p: sha(d) for p, d in vendor.items()},
                    native_sha256={p: sha(d.encode()) for p, d in base.items() if p != DTS},
                    fixture_fragment_sha256=sha(base[DTS].encode()),
                    payload_sha256={p: sha(d.encode()) for p, d in output.items()},
                    patch_sha256={"provider.patch": sha(provider.encode()),
                                  "disabled-description.patch": sha(dt.encode())})
    return base, output, vendor, provider, dt, evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=ROOT.parent)
    parser.add_argument("--kernel-archive", type=Path)
    parser.add_argument("--device-repo", type=Path)
    parser.add_argument("--modules-repo", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    _, _, _, provider, dt, evidence = build(args.upstream, args.kernel_archive, args.device_repo, args.modules_repo)
    files = {"provider.patch": provider, "disabled-description.patch": dt,
             "evidence.json": json.dumps(evidence, indent=2, sort_keys=True) + "\n"}
    for name, data in files.items():
        if args.write:
            (HERE / name).write_text(data)
        elif (HERE / name).read_text() != data:
            raise ValueError("stale rail-owner output: " + name)
    print("PASS: exact NOS/Linux sources and byte-identical scoped patch application")
    print("NOT RUN: native compilation, schema/DTB, GPIO transitions or capture")
