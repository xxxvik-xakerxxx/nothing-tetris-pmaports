#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compose exact packaged/frozen owners into one disabled real Kbuild closure."""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
DIR = "drivers/media/platform/mediatek/tetris-cold/"
GRAPH = "drivers/media/platform/mediatek/seninf/mt6878-seninf-graph.c"
MEDIA_KCONFIG = "drivers/media/platform/mediatek/Kconfig"
MEDIA_MAKEFILE = "drivers/media/platform/mediatek/Makefile"
SENINF_MAKEFILE = "drivers/media/platform/mediatek/seninf/Makefile"
PD = "drivers/pmdomain/mediatek/"
SMI = "drivers/memory/mtk-smi.c"
IOMMU = "drivers/iommu/mtk_iommu.c"
CAM = "drivers/clk/mediatek/clk-mt6878-cam.c"
HEADER = "include/soc/mediatek/camera-vmm-consumer.h"
PRODUCTION = (
    "patches/camera-camsv/mt6878-camsv-vb2.c",
    "patches/camera-direct/mt6878-camsv-direct.c",
    "patches/camera-direct-platform/mt6878-camsv-platform.c",
    "patches/camera-direct-hardware/mt6878-camsv-hardware.c",
    "patches/camera-smi-owner/smi-backend.c",
    "patches/camera-seninf-route/mt6878-seninf-route.c",
    "patches/camera-seninf-controller/mt6878-seninf-controller.c",
    "patches/camera-native-capture/mt6878-seninf-pm.c",
    "patches/camera-native-capture/mt6878-native-capture.c",
    "patches/camera-native-video/mt6878-native-video.c",
    "patches/camera-joint-reset/cold-probe.c",
    "patches/camera-joint-reset/mt6878-camera-cold-reset.c",
    "patches/camera-joint-reset/mt6878-camera-joint-reset.c",
    "patches/camera-camisp/mt6878-camisp-dma.c",
)
FROZEN = {
    "stream-owner/stream-owner.patch": "ac387c580c232b7032489646c42e3f64885700bdcf457bfddb5e4e9498c91954",
    "stream-owner/evidence.json": "d262650646148680cc72b156ddf3be1ea579dea0ecdbb0440479dd59ffa90455",
    "rail-owner/provider.patch": "b1cc170aa712674d5d18ff68e407baa740b541424fdb2d966454baefaf2864b6",
    "rail-owner/evidence.json": "6de9f3b474ff06aedb9788534afc35aeb44908b6255bc04396f67df4eda0c90f",
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stream = load("frozen_stream_generator", HERE.parent / "stream-owner/generate.py")
rail = load("frozen_rail_generator", HERE.parent / "rail-owner/generate.py")
native = load("native_vmm_generator", HERE.parent / "native-integration/generate.py")
sha = stream.sha
replace_once = stream.replace_once
function = stream.function
block = stream.block
KERNEL, DEVICE, MODULES = stream.KERNEL, stream.DEVICE, stream.MODULES


def tracked(path, evidence):
    data = (ROOT / path).read_bytes()
    subprocess.check_output(["git", "ls-files", "--error-unmatch", path], cwd=ROOT, stderr=subprocess.PIPE)
    evidence[path] = sha(data)
    return data.decode()


def shipping_disabled(config):
    for symbol in ("VIDEO_MT6878_COLD_CAPTURE", "VIDEO_IMX882_TETRIS", "VIDEO_MT6878_SENINF_GRAPH",
                   "REGULATOR_TETRIS_CAMERA_GPIO", "MTK_MT6878_NATIVE_VMM"):
        if re.search(r"^CONFIG_" + symbol + r"=(y|m)$", config, re.M):
            raise ValueError("unvalidated camera owner enabled in shipping config: " + symbol)


def overlay(files, data, *, prefix="", evidence=None, name=None):
    # Rebase complete basename patch file sections onto this one production dir.
    if prefix:
        data = re.sub(r"^(---|\+\+\+) ([ab])/([^\n]+)$",
                      lambda m: m[1] + " " + m[2] + "/" + prefix + m[3], data, flags=re.M)
    targets = set(re.findall(r"^\+\+\+ b/(.+)$", data, re.M))
    with tempfile.TemporaryDirectory(prefix="cold-owner-overlay-") as directory:
        tree = Path(directory)
        for path in targets:
            if path in files:
                target = tree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(files[path])
        patch = tree / "overlay.patch"
        patch.write_text(data)
        for args in (["git", "apply", "--check", str(patch)], ["git", "apply", str(patch)]):
            stream.run(args, tree)
        for path in targets:
            files[path] = (tree / path).read_text()


def inputs(archive, device_repo, modules_repo):
    frozen = {}
    for path, digest in FROZEN.items():
        data = (HERE.parent / path).read_bytes()
        if sha(data) != digest:
            raise ValueError("frozen owner drift: " + path)
        frozen[path] = digest
    extra = (GRAPH, SENINF_MAKEFILE, "drivers/media/platform/mediatek/seninf/Kconfig",
             MEDIA_KCONFIG, MEDIA_MAKEFILE, SMI, IOMMU, CAM, "drivers/clk/mediatek/Makefile",
             PD + "mtk-pm-domains.c", PD + "mtk-pm-domains.h", PD + "Kconfig", PD + "Makefile",
             native.BINDING, rail.KCONFIG, rail.MAKEFILE, "include/linux/pm_domain.h",
             "drivers/pmdomain/core.c", "include/dt-bindings/power/mediatek,mt6878-power.h")
    extra = tuple(dict.fromkeys((*extra, *rail.NATIVE)))
    extra += ("drivers/media/v4l2-core/v4l2-subdev.c", "include/media/v4l2-subdev.h",
              "drivers/base/core.c", "drivers/pinctrl/mediatek/Makefile",
              "drivers/media/Kconfig", "drivers/media/v4l2-core/Kconfig",
              "drivers/media/platform/Kconfig")
    base, evidence = stream.baseline(archive)
    # Frozen generator's projection defaults intentionally cover only its scope.
    # Reconstruct additional files separately, without changing that generator.
    additional = {}
    with tarfile.open(archive, "r|gz") as source:
        for member in source:
            path = member.name.removeprefix("linux-" + KERNEL + "/")
            if member.isfile() and path in extra:
                additional[path] = source.extractfile(member).read()
    evidence["archive_source_sha256"].update({p: sha(data) for p, data in additional.items()})
    apk = (PACKAGE / "APKBUILD").read_text()
    shipping_disabled(stream.package_file("config-postmarketos-mediatek-mt6878.aarch64", apk).decode())
    smoke = load("cold_packaged_smoke", ROOT / "ci/kernel-object-smoke.py")
    evidence["packaged_preparation"] = {}
    names = re.search(r'^source="\n(.*?)^"$', apk, re.M | re.S)[1].split()
    with tempfile.TemporaryDirectory(prefix="cold-extra-base-") as directory:
        tree = Path(directory)
        for path, data in additional.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for name in names:
            if not name.endswith(".patch"):
                continue
            projected = stream.project((PACKAGE / name).read_bytes(), extra)
            if not projected:
                continue
            data = stream.package_file(name, apk)
            patch = tree / "extra.patch"
            patch.write_bytes(stream.project(data, extra))
            try:
                flags = ["--fuzz=0"] if name in smoke.STRICT_PATCHES else []
                # Match the existing package checker for legacy context changes.
                # The new candidate is always checked separately by git apply.
                stream.run(["patch", "--batch", *flags, "-p1", "-i", str(patch)], tree)
            except subprocess.CalledProcessError as error:
                raise ValueError(name + ": " + error.stderr.decode(errors="replace")) from error
            evidence["packaged_patch_sha256"][name] = sha(data)
            # Human patch messages vary between host versions. Identity is
            # established by input hashes and every resulting source hash.
            evidence["packaged_preparation"][name] = {"zero_fuzz": bool(flags)}
        for path in extra:
            base[path] = (tree / path).read_text()
    evidence["baseline_sha256"] = {p: sha(text.encode()) for p, text in base.items()}
    vendor, blobs = stream.vendor(device_repo, modules_repo)
    native_vendor = native.vendor_inputs(device_repo, modules_repo)
    native.verify_vendor_contract(native_vendor)
    evidence.update(frozen_sha256=frozen, kernel_commit=KERNEL, device_modules_commit=DEVICE,
                    modules_commit=MODULES, vendor_blob_ids=blobs,
                    vendor_sha256={p: sha(s.encode()) for p, s in vendor.items()},
                    vmm_vendor_sha256={p: sha(s) for p, s in native_vendor.items()})
    return base, vendor, native_vendor, evidence


def payload(base, native_vendor):
    files = dict(base)
    adopted = {}
    stream_output = stream.payload(base)
    if stream.patch_text(base, stream_output) != (HERE.parent / "stream-owner/stream-owner.patch").read_text():
        raise ValueError("frozen stream implementation differs from verified patch")
    files.update(stream_output)
    # Apply only the frozen regulator implementation, never its disabled DT delta.
    overlay(files, (HERE.parent / "rail-owner/provider.patch").read_text())
    native_input = {name: base[native.native_path(name)] for name in
                    ("mtk-pm-domains.c", "mtk-pm-domains.h", "Kconfig", "Makefile", native.BINDING)}
    vmm = native.payload(native_input, native_vendor)
    canonical = native.patch_text(native_input, vmm)
    if canonical != (HERE.parent / "native-integration/native-provider.patch").read_text():
        raise ValueError("native VMM composition no longer matches canonical baseline; require reviewed profile")
    files.update(vmm)
    admission = tracked("patches/camera-camisp/native-integration/supplier-admission.patch", adopted)
    overlay(files, admission)

    # Only tracked production sources/headers are eligible; no unfrozen CCD bus.
    paths = stream.run(["git", "ls-files", "patches"], ROOT).decode().splitlines()
    headers = {}
    for path in paths:
        if Path(path).suffix in (".h", ".inc") and path.startswith("patches/camera-"):
            headers.setdefault(Path(path).name, []).append(path)
    for source in PRODUCTION:
        files[DIR + Path(source).name] = tracked(source, adopted)
    files[DIR + "mt6878-seninf-cold-graph.c"] = base[GRAPH]
    queue = [p for p in files if p.startswith(DIR)]
    seen = set()
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for name in re.findall(r'^#include "([^"/]+)"', files[path], re.M):
            target = DIR + name
            if target not in files:
                choices = headers.get(name, [])
                if len(choices) != 1:
                    raise ValueError("missing/ambiguous tracked header: " + name)
                files[target] = tracked(choices[0], adopted)
                queue.append(target)
    # Compose the frozen concrete receiver/controller/reset overlays, no smoke TUs.
    graph_name = DIR + "mt6878-seninf-graph.c"
    files[graph_name] = files.pop(DIR + "mt6878-seninf-cold-graph.c")
    for name in ("patches/camera-seninf-controller/native-bind.patch",
                 "patches/camera-native-capture/native-pm.patch",
                 "patches/camera-joint-reset/video-cold.patch",
                 "patches/camera-camisp/consumer-pm.patch"):
        overlay(files, tracked(name, adopted), prefix=DIR)
    files[DIR + "mt6878-seninf-cold-graph.c"] = files.pop(graph_name)
    for name in ("patches/camera-cam-main-provider/provider.patch", "patches/camera-smi-owner/provider.patch",
                 "patches/camera-camisp/provider.patch", "patches/camera-camisp/resources/clock-providers.patch"):
        overlay(files, tracked(name, adopted))
    for source, target in (
        ("patches/camera-cam-main-provider/cam-main-lease.inc", "drivers/clk/mediatek/cam-main-lease.inc"),
        ("patches/camera-cam-main-provider/cam-main-lease-test.inc", "drivers/clk/mediatek/cam-main-lease-test.inc"),
        ("patches/camera-cam-main-provider/cam-main-lease.h", "include/soc/mediatek/cam-main-lease.h"),
        ("patches/camera-smi-owner/mt6878-smi-camera-reset.inc", "drivers/memory/mt6878-smi-camera-reset.inc"),
        ("patches/camera-smi-owner/smi-camera-reset.h", "include/soc/mediatek/smi-camera-reset.h"),
        ("patches/camera-camisp/camisp-dma.h", "include/soc/mediatek/camisp-dma.h"),
        ("patches/camera-camisp/mt6878-camisp-smi.inc", "drivers/memory/mt6878-camisp-smi.inc"),
        ("patches/camera-camisp/camisp-smi-test.inc", "drivers/memory/camisp-smi-test.inc"),
        ("patches/camera-camisp/mt6878-camisp-iommu.inc", "drivers/iommu/mt6878-camisp-iommu.inc")):
        files[target] = tracked(source, adopted)
    accessor = (HERE / "vmm-consumer.inc").read_text()
    inc = PD + "mt6878-native-vmm.inc"
    files[inc] = replace_once(files[inc], "static int scpsys_vmm_observe_off",
                             '#include <soc/mediatek/camera-vmm-consumer.h>\n' + accessor + "\nstatic int scpsys_vmm_observe_off")
    files[HEADER] = (HERE / "camera-vmm-consumer.h").read_text()
    # Actual leaf consumers check the existing supplier on every powered access.
    hw = DIR + "mt6878-camsv-hardware.c"
    files[hw] = replace_once(files[hw], "\treturn iommu_get_domain_for_dev(d->dma_owner) == d->resources.domain ? 0 : -ESTALE;",
                            "\tif (iommu_get_domain_for_dev(d->dma_owner) != d->resources.domain)\n\t\treturn -ESTALE;\n\treturn mt6878_camera_vmm_check(p->cam_main, MT6878_POWER_DOMAIN_CAM_MAIN);")
    files[hw] = replace_once(files[hw], '// SPDX-License-Identifier: GPL-2.0-only\n',
                            '// SPDX-License-Identifier: GPL-2.0-only\n#include <soc/mediatek/camera-vmm-consumer.h>\n')
    pm = DIR + "mt6878-seninf-pm.c"
    files[pm] = replace_once(files[pm], '// SPDX-License-Identifier: GPL-2.0-only\n',
                            '// SPDX-License-Identifier: GPL-2.0-only\n#include <soc/mediatek/camera-vmm-consumer.h>\n')
    files[pm] = replace_once(files[pm], "\tfor (i = 0; i < 3; i++) {\n\t\tret = enable_clock(p, i);",
                            "\tret = mt6878_camera_vmm_check(p->domains[0], MT6878_POWER_DOMAIN_CAM_MAIN);\n\tif (ret)\n\t\tgoto fail;\n\tfor (i = 0; i < 3; i++) {\n\t\tret = enable_clock(p, i);")
    files[pm] = replace_once(files[pm], "int ret, cleanup, voltage;", "int ret, voltage;")
    files[pm] = replace_once(files[pm], "\tcsi = 3 + p->port;",
        "\tret = mt6878_camera_vmm_validate_domain(p->domains[0], MT6878_POWER_DOMAIN_CAM_MAIN);\n"
        "\tif (ret)\n\t\tgoto out;\n\tcsi = 3 + p->port;")
    files[pm] = replace_once(files[pm], "\tcleanup = release(p);\n\tif (cleanup)\n\t\tdev_err(p->dev, \"SENINF PM cleanup failed: %d; first error: %d\\n\", cleanup, ret);",
                            "\t/* Retain actual clock/domain/vote references after the first failure. */")
    files[pm] = replace_once(files[pm], "\tret = release(p);", "\tret = p->first_error ? p->first_error : release(p);")
    platform = DIR + "mt6878-camsv-platform.c"
    files[platform] = replace_once(files[platform], '// SPDX-License-Identifier: GPL-2.0-only\n',
        '// SPDX-License-Identifier: GPL-2.0-only\n#include <soc/mediatek/camera-vmm-consumer.h>\n')
    files[platform] = replace_once(files[platform], '\tret = pm_runtime_resume_and_get(p->cam_main);',
        '\tret = mt6878_camera_vmm_validate_domain(p->cam_main, MT6878_POWER_DOMAIN_CAM_MAIN);\n'
        '\tif (ret)\n\t\tgoto out;\n\tret = pm_runtime_resume_and_get(p->cam_main);')
    route = DIR + "mt6878-seninf-route.c"
    files[route] = replace_once(files[route],
        "v4l2_subdev_call(r->sensor, pad, get_fmt, NULL, &fmt)",
        "v4l2_subdev_call_state_active(r->sensor, pad, get_fmt, &fmt)")
    sensor = files[stream.DRIVER]
    sensor = replace_once(sensor, "static int imx882_stream(struct v4l2_subdev *sd, int enable)", "static int imx882_stream_locked(struct v4l2_subdev *sd, int enable)")
    body = function(sensor, "static int imx882_stream_locked")
    locked = replace_once(body, "mutex_lock(&camera->lock);", "lockdep_assert_held(&camera->lock);")
    locked = replace_once(locked, "\tmutex_unlock(&camera->lock);\n", "")
    sensor = replace_once(sensor, body, locked)
    sensor = replace_once(sensor, "static const struct v4l2_subdev_video_ops imx882_video_ops", (HERE / "sensor-pad-streams.inc").read_text() + "\nstatic const struct v4l2_subdev_video_ops imx882_video_ops")
    sensor = replace_once(sensor, ".s_stream = imx882_stream,", ".s_stream = v4l2_subdev_s_stream_helper,")
    sensor = replace_once(sensor, "static const struct v4l2_subdev_pad_ops imx882_pad_ops = {", "static const struct v4l2_subdev_pad_ops imx882_pad_ops = {\n\t.enable_streams = imx882_enable_streams,\n\t.disable_streams = imx882_disable_streams,")
    sensor = replace_once(sensor, "static const struct v4l2_subdev_ops imx882_subdev_ops = {", "static const struct v4l2_subdev_ops imx882_subdev_ops = {\n\t.core = &imx882_core_ops,")
    sensor = replace_once(sensor, "format->which == V4L2_SUBDEV_FORMAT_ACTIVE && camera->streaming", "format->which == V4L2_SUBDEV_FORMAT_ACTIVE &&\n\t    (camera->streaming || media_entity_pipeline(&sd->entity))")
    files[stream.DRIVER] = sensor
    for name in ("cold-capture.c", "cold-capture.h"):
        files[DIR + name] = (HERE / name).read_text()
    video = DIR + "mt6878-native-video.c"
    files[video] = replace_once(files[video], '#include "mt6878-native-video.h"', '#include "mt6878-native-video.h"\n#include "cold-capture.h"')
    files[video] = replace_once(files[video], "\t*result = NULL;\n\tif (!s", "\t*result = NULL;\n\tret = mt6878_cold_suppliers_check(s);\n\tif (ret)\n\t\treturn ret;\n\tif (!s")
    files[video] += "\nEXPORT_SYMBOL_GPL(mt6878_native_video_unregister);\nEXPORT_SYMBOL_GPL(mt6878_native_video_wait_ready);\n"
    units = [Path(p).name.removesuffix(".c") + ".o" for p in files if p.startswith(DIR) and p.endswith(".c")]
    files[DIR + "Makefile"] = ("# SPDX-License-Identifier: GPL-2.0-only\nobj-y += mt6878-cold-capture.o\n"
                              "mt6878-cold-capture-y := " + " \\\n\t".join(units) + "\n")
    files[DIR + "Kconfig"] = '''# SPDX-License-Identifier: GPL-2.0-only
config VIDEO_MT6878_COLD_CAPTURE
	bool "MT6878 integrated cold capture owner (unvalidated)"
	default n
	depends on OF && PM && PM_GENERIC_DOMAINS && GPIOLIB && REGULATOR && NVMEM
	depends on VIDEO_DEV=y && MEDIA_CONTROLLER && I2C && PINCTRL_MT6878
	depends on MTK_SMI=y && MTK_IOMMU=y && MTK_SCPSYS_PM_DOMAINS=y
	depends on COMMON_CLK_MT6878_CAM=y && COMMON_CLK
	select VIDEO_IMX882_TETRIS
	select VIDEO_MT6878_SENINF_GRAPH
	select REGULATOR_TETRIS_CAMERA_GPIO
	select MTK_MT6878_NATIVE_VMM
	select VIDEOBUF2_DMA_CONTIG
	select VIDEOBUF2_V4L2
	select VIDEO_V4L2_SUBDEV_API
	help
	  Link the existing real capture/receiver/supplier owners in one closure.
	  No DT activation, fabricated firmware admission or default frame layout.
'''
    files[MEDIA_KCONFIG] += '\nsource "' + DIR + 'Kconfig"\n'
    files[MEDIA_MAKEFILE] += "\nobj-$(CONFIG_VIDEO_MT6878_COLD_CAPTURE) += tetris-cold/\n"
    files[SENINF_MAKEFILE] = "ifneq ($(CONFIG_VIDEO_MT6878_COLD_CAPTURE),y)\n" + files[SENINF_MAKEFILE] + "endif\n"
    files["drivers/clk/mediatek/Makefile"] += "\nobj-$(CONFIG_VIDEO_MT6878_COLD_CAPTURE) += clk-mt6878-camisp-resources.o\n"
    output = {p: text for p, text in files.items() if p not in base or text != base[p]}
    return output, adopted, units


def delta(base, output):
    result = ""
    for path, text in sorted(output.items()):
        result += "diff --git a/" + path + " b/" + path + "\n"
        if path not in base:
            result += "new file mode 100644\n"
        result += "".join(difflib.unified_diff(base.get(path, "").splitlines(True), text.splitlines(True),
                    fromfile="a/" + path if path in base else "/dev/null", tofile="b/" + path))
    return result


def build(archive, device_repo, modules_repo):
    base, vendor, native_vendor, evidence = inputs(archive, device_repo, modules_repo)
    output, adopted, units = payload(base, native_vendor)
    patch = delta(base, output)
    with tempfile.TemporaryDirectory(prefix="cold-integrated-apply-") as directory:
        tree = Path(directory)
        for path, text in base.items():
            target = tree / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        candidate = tree / "cold-integration.patch"
        candidate.write_text(patch)
        for args in (["git", "apply", "--check", str(candidate)], ["git", "apply", str(candidate)]):
            stream.run(args, tree)
        for path, text in output.items():
            if (tree / path).read_text() != text:
                raise ValueError("integrated application mismatch: " + path)
    evidence.update(adopted_tracked_sha256=adopted, production_units=units,
                    payload_sha256={p: sha(t.encode()) for p, t in output.items()}, patch_sha256=sha(patch.encode()),
                    template_sha256={p: sha((HERE / p).read_bytes()) for p in
                        ("vmm-consumer.inc", "camera-vmm-consumer.h", "sensor-pad-streams.inc", "cold-capture.c", "cold-capture.h")})
    return base, output, patch, evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    stream.arguments(parser)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    _, _, patch, evidence = build(args.kernel_archive, args.device_repo, args.modules_repo)
    for name, text in {"cold-integration.patch": patch, "evidence.json": json.dumps(evidence, indent=2, sort_keys=True) + "\n"}.items():
        if args.write:
            (HERE / name).write_text(text)
        elif (HERE / name).read_text() != text:
            raise ValueError("stale cold integration: " + name)
    print("PASS: exact source composition and strict integrated native patch application; no compilation")
