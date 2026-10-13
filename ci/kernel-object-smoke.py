#!/usr/bin/env python3
"""Compile packaged candidates in CI, with opt-in GNSS module validation; never install."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request


PACKAGE = Path("pmaports/device/testing/linux-postmarketos-mediatek-mt6878")
CONFIG = "config-postmarketos-mediatek-mt6878.aarch64"
MODULES = (
    "VIDEO_IMX882_TETRIS", "VIDEO_MT6878_SENINF_GRAPH",
    "MTK_MT6878_CCCI_FIRST_START", "MTK_MT6878_GPUEB_POWER",
    "TETRIS_GPUEB_FLAT_ANALYSIS",
)
ENABLE = (
    "MEDIA_SUPPORT", "MEDIA_CAMERA_SUPPORT", "VIDEO_DEV",
    "MEDIA_PLATFORM_SUPPORT", "MEDIA_PLATFORM_DRIVERS",
    "MEDIA_CONTROLLER", "VIDEO_V4L2_SUBDEV_API", "V4L2_FWNODE",
)
OBJECTS = (
    "drivers/media/i2c/imx882-tetris-stream.o",
    "drivers/media/platform/mediatek/seninf/mt6878-seninf-graph.o",
    "drivers/media/platform/mediatek/seninf/mt6878-seninf-phy-smoke.o",
    "drivers/soc/mediatek/mt6878-ccci-start.o",
    "drivers/pmdomain/mediatek/mt6878-gpueb-power.o",
    "drivers/misc/gpueb-flat-analysis.o",
)
DTBS = tuple("mediatek/" + name + ".dtb" for name in (
    "mt6878-nothing-tetris-native", "mt6878-nothing-tetris-vgpu-observe",
    "mt6878-nothing-tetris-modem-preflight-off", "mt6878-nothing-tetris-modem-preflight",
))
HIF_DT_SOURCE = "patches/modem/drafts/runtime-hif-dt/mt6878-nothing-tetris-ccci-hif-resources.dts"
HIF_DTB = "mediatek/mt6878-nothing-tetris-ccci-hif-resources.dtb"
STRICT_PATCHES = frozenset((
    "0116-media-platform-mediatek-mt6878-seninf-phy-backend.patch",
    "0117-soc-mediatek-mt6878-ccci-first-start-backend.patch",
    "0118-pmdomain-mediatek-mt6878-gpueb-power-backend.patch",
    "0120-misc-tetris-gpueb-authenticated-ram-analysis.patch",
))
RESEARCH_DIR = "drivers/soc/mediatek/tetris-owner-smoke"
RESEARCH_SOURCES = {
    "patches/gpu/sram-owner/mt6878-gpueb-sram.c": f"{RESEARCH_DIR}/mt6878-gpueb-sram.c",
    "patches/gpu/sram-owner/mt6878-gpueb-sram.h": f"{RESEARCH_DIR}/mt6878-gpueb-sram.h",
    "patches/gpu/sram-owner/mt6878-gpueb-sram-core.c": f"{RESEARCH_DIR}/mt6878-gpueb-sram-core.c",
    "patches/gpu/sram-owner/mt6878-gpueb-sram-core.h": f"{RESEARCH_DIR}/mt6878-gpueb-sram-core.h",
    "patches/gpu/reset-owner-draft/mt6878-gpueb-reset.c": f"{RESEARCH_DIR}/mt6878-gpueb-reset.c",
    "patches/gpu/reset-owner-draft/mt6878-gpueb-reset.h": f"{RESEARCH_DIR}/mt6878-gpueb-reset.h",
    "patches/gpu/reset-provider-draft/mt6878-gpueb-reset-provider.c": f"{RESEARCH_DIR}/mt6878-gpueb-reset-provider.c",
    "patches/gpu/reset-provider-draft/mt6878-gpueb-reset-provider.h": f"{RESEARCH_DIR}/mt6878-gpueb-reset-provider.h",
    "patches/gpu/mfg0-supplier-draft/mt6878-gpueb-mfg0.c": f"{RESEARCH_DIR}/mt6878-gpueb-mfg0.c",
    "patches/gpu/mfg0-supplier-draft/mt6878-gpueb-mfg0.h": f"{RESEARCH_DIR}/mt6878-gpueb-mfg0.h",
    "patches/gpu/bound-parent-draft/mt6878-gpueb-control.c": f"{RESEARCH_DIR}/mt6878-gpueb-control.c",
    "patches/gpu/bound-parent-draft/mt6878-gpueb-control.h": f"{RESEARCH_DIR}/mt6878-gpueb-control.h",
    "patches/modem/mt6878_md_startup_scope.c": f"{RESEARCH_DIR}/mt6878_md_startup_scope.c",
    "patches/modem/mt6878_md_startup_scope.h": "include/linux/soc/mediatek/mt6878_md_startup_scope.h",
    "patches/modem/mt6878_md_handoff_reservation.c": f"{RESEARCH_DIR}/mt6878_md_handoff_reservation.c",
    "patches/modem/mt6878_md_handoff_reservation.h": f"{RESEARCH_DIR}/mt6878_md_handoff_reservation.h",
    "patches/modem/mt6878_md_pss32.c": f"{RESEARCH_DIR}/mt6878_md_pss32.c",
    "patches/modem/mt6878_md_pss32.h": f"{RESEARCH_DIR}/mt6878_md_pss32.h",
    "patches/camera-smi-owner/mt6878-smi-camera-reset.inc": "drivers/memory/mt6878-smi-camera-reset.inc",
    "patches/camera-smi-owner/smi-camera-reset.h": "include/soc/mediatek/smi-camera-reset.h",
}
PROVIDER_PATCH = "patches/camera-smi-owner/provider.patch"
# Use the existing provider Kbuild, never replace drivers/memory/Makefile.
PROVIDER_OBJECTS = ("drivers/memory/mtk-smi.o",)
INFRA_CLOCK_DIR = "drivers/clk/mediatek/tetris-infra-smoke"
RESEARCH_SOURCES["patches/modem/infra-clocks/clk-mt6878-infra-ao.c"] = \
    f"{INFRA_CLOCK_DIR}/clk-mt6878-infra-ao.c"
RESEARCH_OBJECTS = tuple(f"{RESEARCH_DIR}/{name}.o" for name in (
    "mt6878-gpueb-sram", "mt6878-gpueb-sram-core",
    "mt6878-gpueb-reset", "mt6878-gpueb-reset-provider",
    "mt6878-gpueb-mfg0", "mt6878-gpueb-control",
    "mt6878_md_startup_scope", "mt6878_md_handoff_reservation",
    "mt6878_md_pss32",
)) + (f"{INFRA_CLOCK_DIR}/clk-mt6878-infra-ao.o",)
CAMERA_MANIFEST = "patches/camera-pipeline-owner/STAGING.json"
CAMERA_GRAPH = "drivers/media/platform/mediatek/seninf/mt6878-seninf-graph.c"
CAMERA_REVIEW_PATCHES = (
    "patches/camera-seninf-controller/imx882-native-streams.patch",
    "patches/camera-seninf-controller/native-bind.patch",
    "patches/camera-native-capture/native-pm.patch",
    "patches/camera-joint-reset/video-cold.patch",
)


def camera_staging(root, manifest=CAMERA_MANIFEST):
    data = json.loads((root / manifest).read_text())
    destination = data["destination"]
    if destination != "drivers/media/platform/mediatek/tetris-camera-owner-smoke":
        raise ValueError("unexpected camera staging destination")
    sources = data["sources"]
    if not isinstance(sources, list) or not sources or len(set(sources)) != len(sources):
        raise ValueError("invalid camera source list")
    mapping = {}
    for source in sources:
        path = Path(source)
        if (not source.startswith("patches/camera-") or ".." in path.parts
                or path.suffix not in (".c", ".h", ".inc")):
            raise ValueError("unsafe camera source path")
        target = f"{destination}/{path.name}"
        if target in mapping.values():
            raise ValueError("camera basename collision")
        mapping[source] = target
    names = [*data["objects"]]
    if "fault_object" in data:
        names.append(data["fault_object"])
    if len(set(names)) != len(names):
        raise ValueError("duplicate camera object")
    for name in names:
        if Path(name).name != name or not name.endswith(".o"):
            raise ValueError("unsafe camera object path")
        if f"{destination}/{Path(name).with_suffix('.c')}" not in mapping.values():
            raise ValueError("camera object lacks production source")
    symbols = [*data.get("required_enabled", []), *data.get("fault_required_enabled", [])]
    if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", name) for name in symbols):
        raise ValueError("invalid camera config symbol")
    return mapping, tuple(f"{destination}/{name}" for name in names), tuple(symbols)


CAMERA_SOURCES, CAMERA_OBJECTS, CAMERA_ENABLE = camera_staging(Path(__file__).resolve().parents[1])
# Hidden vb2 helpers need an upstream selector in the isolated config. The
# virtual driver is neither compiled nor installed by this object-only harness.
CAMERA_SELECTORS = ("MEDIA_TEST_SUPPORT", "V4L_TEST_DRIVERS", "VIDEO_VIVID")
RESEARCH_SOURCES.update(CAMERA_SOURCES)
RESEARCH_OBJECTS += CAMERA_OBJECTS
CAMERA_JOINT_MANIFEST = "patches/camera-joint-reset/STAGING.json"
CAMERA_JOINT_SOURCES, CAMERA_JOINT_OBJECTS, _ = camera_staging(
    Path(__file__).resolve().parents[1], CAMERA_JOINT_MANIFEST)
if set(CAMERA_JOINT_SOURCES.values()) & set(RESEARCH_SOURCES.values()):
    raise ValueError("duplicate camera joint-reset staging destination")
RESEARCH_SOURCES.update(CAMERA_JOINT_SOURCES)
RESEARCH_OBJECTS += CAMERA_JOINT_OBJECTS
CAMERA_REPEAT_MANIFEST = "patches/camera-repeat-capture/STAGING.json"
CAMERA_REPEAT_CHECK = "patches/camera-repeat-capture/check.py"
CAMERA_REPEAT_SOURCES, CAMERA_REPEAT_OBJECTS, _ = camera_staging(
    Path(__file__).resolve().parents[1], CAMERA_REPEAT_MANIFEST)
if set(CAMERA_REPEAT_SOURCES.values()) & set(RESEARCH_SOURCES.values()):
    raise ValueError("duplicate repeat-capture staging destination")
RESEARCH_SOURCES.update(CAMERA_REPEAT_SOURCES)
RESEARCH_OBJECTS += CAMERA_REPEAT_OBJECTS
CAMERA_REPEAT_PATCHES = tuple("patches/camera-repeat-capture/" + name for name in (
    "epoch-owner.patch", "epoch-stop-lock.patch", "epoch-final-retire.patch", "epoch-video.patch"))
CAM_MAIN_MANIFEST = "patches/camera-cam-main-provider/STAGING.json"
CAM_MAIN_CHECK = "patches/camera-cam-main-provider/check-staging.py"
CAM_MAIN_PLAN = json.loads((Path(__file__).resolve().parents[1] / CAM_MAIN_MANIFEST).read_text())
if (set(CAM_MAIN_PLAN["sources"].values()) & set(RESEARCH_SOURCES.values()) or
        any(Path(name).is_absolute() or ".." in Path(name).parts
            for name in (*CAM_MAIN_PLAN["sources"], *CAM_MAIN_PLAN["sources"].values()))):
    raise ValueError("unsafe or duplicate CAM_MAIN staging input")
RESEARCH_SOURCES.update(CAM_MAIN_PLAN["sources"])
RESEARCH_OBJECTS += tuple(CAM_MAIN_PLAN["research_objects"])
PROVIDER_OBJECTS += tuple(CAM_MAIN_PLAN["provider_objects"])
CAM_MAIN_ENABLE = tuple(CAM_MAIN_PLAN["required_enabled"])
CAM_MAIN_REACHABLE = tuple(CAM_MAIN_PLAN["required_reachable"])
CAMISP_MANIFEST = "patches/camera-camisp/STAGING.json"
CAMISP_CHECK = "patches/camera-camisp/check.py"
CAMISP_PLAN = json.loads((Path(__file__).resolve().parents[1] / CAMISP_MANIFEST).read_text())
if (set(CAMISP_PLAN["sources"].values()) & set(RESEARCH_SOURCES.values()) or
        any(Path(name).is_absolute() or ".." in Path(name).parts
            for name in (*CAMISP_PLAN["sources"], *CAMISP_PLAN["sources"].values()))):
    raise ValueError("unsafe or duplicate CAMISP staging input")
RESEARCH_SOURCES.update(CAMISP_PLAN["sources"])
CAMISP_OBJECTS = tuple(CAMISP_PLAN["research_objects"] + CAMISP_PLAN["provider_objects"])
RESEARCH_OBJECTS += tuple(CAMISP_PLAN["research_objects"])
PROVIDER_OBJECTS = tuple(dict.fromkeys((*PROVIDER_OBJECTS, *CAMISP_PLAN["provider_objects"])))
CAMISP_ENABLE = tuple(CAMISP_PLAN["required_enabled"])
CAMISP_RESOURCE_MANIFEST = "patches/camera-camisp/resources/STAGING.json"
CAMISP_RESOURCE_CHECK = "patches/camera-camisp/resources/check.py"


def camisp_resource_staging(root):
    spec = importlib.util.spec_from_file_location("camisp_resource_check", root / CAMISP_RESOURCE_CHECK)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    data = json.loads((root / CAMISP_RESOURCE_MANIFEST).read_text())
    checker.staging_contract(data)
    return data


CAMISP_RESOURCE_PLAN = camisp_resource_staging(Path(__file__).resolve().parents[1])
if set(CAMISP_RESOURCE_PLAN["sources"].values()) & set(RESEARCH_SOURCES.values()):
    raise ValueError("duplicate CAMISP resource staging destination")
RESEARCH_SOURCES.update(CAMISP_RESOURCE_PLAN["sources"])
CAMISP_RESOURCE_OBJECTS = tuple(CAMISP_RESOURCE_PLAN["research_objects"])
RESEARCH_OBJECTS += CAMISP_RESOURCE_OBJECTS
CAMISP_RESOURCE_ENABLE = tuple(CAMISP_RESOURCE_PLAN["required_enabled"])
CAMISP_RESOURCE_REACHABLE = tuple(CAMISP_RESOURCE_PLAN["required_reachable"])
CAMISP_RESOURCE_INPUTS = tuple("patches/camera-camisp/resources/" + name for name in (
    "STAGING.json", "evidence.json", "generate.py", "check.py", "test-source.py",
    "check-dt.py", "test-dt.py", "clock-providers.patch", "disabled-description.patch"))
CAMISP_SUPPLIER_MANIFEST = "patches/camera-camisp/resources/SUPPLIER-STAGING.json"
CAMISP_SUPPLIER_PLAN = json.loads((Path(__file__).resolve().parents[1] / CAMISP_SUPPLIER_MANIFEST).read_text())
if (CAMISP_SUPPLIER_PLAN["candidate"]["runtime_activation"] != "disabled" or
        CAMISP_SUPPLIER_PLAN["blocked_ownership"]["boot_allowed"] is not False or
        len(CAMISP_SUPPLIER_PLAN["sources"]) != 5):
    raise ValueError("camera supplier candidates must not activate hardware or become boot inputs")
for source, destination in CAMISP_SUPPLIER_PLAN["sources"].items():
    if (not source.startswith("patches/camera-camisp/resources/") or
            not destination.startswith("arch/arm64/boot/dts/mediatek/") or
            ".." in Path(source).parts or ".." in Path(destination).parts or
            destination in RESEARCH_SOURCES.values()):
        raise ValueError("unsafe/duplicate supplier DT staging destination")
RESEARCH_SOURCES.update(CAMISP_SUPPLIER_PLAN["sources"])
CAMISP_POWER_MANIFEST = "patches/camera-camisp/power/STAGING.json"
CAMISP_POWER_CHECK = "patches/camera-camisp/power/check.py"


def camisp_power_staging(root):
    spec = importlib.util.spec_from_file_location("camisp_power_check", root / CAMISP_POWER_CHECK)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    data = json.loads((root / CAMISP_POWER_MANIFEST).read_text())
    checker.staging_contract(data)
    return data


CAMISP_POWER_PLAN = camisp_power_staging(Path(__file__).resolve().parents[1])
if set(CAMISP_POWER_PLAN["sources"].values()) & set(RESEARCH_SOURCES.values()):
    raise ValueError("duplicate CAMISP power staging destination")
RESEARCH_SOURCES.update(CAMISP_POWER_PLAN["sources"])
CAMISP_POWER_OBJECTS = tuple(CAMISP_POWER_PLAN["research_objects"])
RESEARCH_OBJECTS += CAMISP_POWER_OBJECTS
CAMISP_POWER_ENABLE = tuple(CAMISP_POWER_PLAN["required_enabled"])
CAMISP_POWER_REACHABLE = tuple(CAMISP_POWER_PLAN["required_reachable"])
CAMISP_POWER_INPUTS = tuple("patches/camera-camisp/power/" + name for name in (
    "STAGING.json", "evidence.json", "trace.py", "check.py", "test_source.py",
    "leaf-transactions.patch"))
CAMISP_SHARED_MANIFEST = "patches/camera-camisp/power/SHARED-STAGING.json"
CAMISP_SHARED_CHECK = "patches/camera-camisp/power/check_supplier.py"
CAMISP_SHARED_PLAN = json.loads((Path(__file__).resolve().parents[1] / CAMISP_SHARED_MANIFEST).read_text())
CAMISP_SHARED_DIR = CAMISP_SHARED_PLAN["object_smoke"]["supplier_directory"]
if (CAMISP_SHARED_DIR != "drivers/pmdomain/mediatek/tetris-vmm-supplier-smoke" or
        CAMISP_SHARED_PLAN["config_variants"] != [{"KUNIT": "y"}, {"KUNIT": "n"}] or
        CAMISP_SHARED_PLAN["runtime_activation"] != "disabled"):
    raise ValueError("invalid shared VMM object-only staging")
CAMISP_SHARED_SOURCES = {
    "patches/camera-camisp/power/" + name: f"{CAMISP_SHARED_DIR}/{name}"
    for name in ("mt6878-vmm-supplier.c", "mt6878-vmm-supplier.h")
}
if set(CAMISP_SHARED_SOURCES.values()) & set(RESEARCH_SOURCES.values()):
    raise ValueError("duplicate shared VMM staging destination")
RESEARCH_SOURCES.update(CAMISP_SHARED_SOURCES)
CAMISP_SHARED_OBJECTS = (f"{CAMISP_SHARED_DIR}/mt6878-vmm-supplier.o",)
RESEARCH_OBJECTS += CAMISP_SHARED_OBJECTS
CAMISP_POWER_ENABLE += tuple(CAMISP_SHARED_PLAN["required_enabled"]) + ("KUNIT",)
CAMISP_SHARED_INPUTS = tuple("patches/camera-camisp/power/" + name for name in (
    "SHARED-STAGING.json", "supplier-evidence.json", "check_supplier.py",
    "test_supplier.py", "Kbuild.shared"))


def block(source, key):
    matches = re.findall(rf'^{key}="\n(.*?)^"$', source, re.M | re.S)
    if len(matches) != 1:
        raise ValueError(f"expected one literal {key} block")
    return matches[0]


def plan(package):
    source = (package / "APKBUILD").read_text()
    commits = re.findall(r'^_commit="([0-9a-f]{40})"$', source, re.M)
    if len(commits) != 1:
        raise ValueError("kernel source must have an immutable commit")
    commit = commits[0]
    entries = block(source, "source").split()
    if entries[0] != "$pkgname-$_commit.tar.gz::https://github.com/MT6878-mainline/$_repository/archive/$_commit.tar.gz":
        raise ValueError("unsupported kernel archive expression")
    hashes = {}
    for row in block(source, "sha512sums").splitlines():
        if not row.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{128})  ([A-Za-z0-9_.-]+)", row.strip())
        if not match or match[2] in hashes:
            raise ValueError("invalid or duplicate package checksum")
        hashes[match[2]] = match[1]
    patches = [entry for entry in entries if entry.endswith(".patch")]
    if not patches or len(set(patches)) != len(patches):
        raise ValueError("empty or duplicated kernel patch stack")
    for name in [CONFIG, *patches]:
        if Path(name).name != name or name not in hashes:
            raise ValueError(f"untracked package source: {name}")
        if hashlib.sha512((package / name).read_bytes()).hexdigest() != hashes[name]:
            raise ValueError(f"package checksum mismatch: {name}")
    archive = f"linux-postmarketos-mediatek-mt6878-{commit}.tar.gz"
    return {"kernel_commit": commit, "archive": archive,
            "archive_sha512": hashes[archive], "patches": patches,
            "source_sha512": {name: hashes[name] for name in [CONFIG, *patches]},
            "application": "package default for historical stack; fuzz=0 for new backends",
            "objects": OBJECTS, "module_options": MODULES, "dtbs": DTBS}


def compile_dtbs(make, output, report):
    # Compile the real packaged trees before the expensive kernel image build.
    run([*make, *DTBS])
    identities = {}
    destination = report / "dtbs"
    destination.mkdir(parents=True, exist_ok=True)
    for name in DTBS:
        dtb = output / "arch/arm64/boot/dts" / name
        if not dtb.is_file() or not dtb.stat().st_size:
            raise ValueError(f"missing compiled DTB: {name}")
        run(["python3", "ci/check-ccci-metadata-dt.py", dtb])
        identities[name] = hashlib.sha256(dtb.read_bytes()).hexdigest()
        shutil.copyfile(dtb, destination / Path(name).name)
    return identities


def compile_hif_dtb(make, kernel, output, report):
    source = Path(HIF_DT_SOURCE)
    target = kernel / "arch/arm64/boot/dts/mediatek" / source.name
    if target.exists():
        raise ValueError("HIF DT staging would replace an existing source")
    shutil.copyfile(source, target)
    run([*make, HIF_DTB])
    dtb = output / "arch/arm64/boot/dts" / HIF_DTB
    normal = output / "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dtb"
    run(["python3", "patches/modem/drafts/runtime-hif-dt/check.py", normal, dtb])
    destination = report / "dtbs" / dtb.name
    if destination.exists() or not dtb.is_file() or not dtb.stat().st_size:
        raise ValueError("missing or nonunique checked HIF DTB")
    shutil.copyfile(dtb, destination)
    return {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "dtb_sha256": hashlib.sha256(dtb.read_bytes()).hexdigest(),
            "scope": "separate DT: HIF resources only, shipping modem remains disabled"}


def compile_camisp_resource_dtb(make, output, report):
    board = CAMISP_RESOURCE_PLAN["diagnostic_board"]
    if board["compile_only"] is not True or board["activation"] != \
            "forbidden; disables existing SPM/MM_INFRA":
        raise ValueError("CAMISP board is not restricted to compilation")
    run([*make, board["target"]])
    dtb = output / "arch/arm64/boot/dts" / board["target"]
    base = output / "arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dtb"
    if not dtb.is_file() or not dtb.stat().st_size:
        raise ValueError("missing compiled CAMISP board fixture")
    raw = report / "unvalidated-nonbootable-dtbs"
    raw.mkdir(exist_ok=False)
    shutil.copyfile(dtb, raw / dtb.name)
    run(["python3", board["validator"], "--base", base, "--fixture", dtb])
    # Never put this nonbootable fixture alongside FIT packaging inputs.
    destination = report / "nonbootable-dtbs"
    destination.mkdir(exist_ok=False)
    shutil.copyfile(dtb, destination / dtb.name)
    return {"dtb_sha256": hashlib.sha256(dtb.read_bytes()).hexdigest(),
            "target": board["target"], "install_allowed": False,
            "scope": "compiled disabled camera graph only; SPM/MM_INFRA disabled; never boot"}


def compile_camisp_supplier_dtbs(make, output, report):
    plan = CAMISP_SUPPLIER_PLAN
    base = output / "arch/arm64/boot/dts" / plan["base"]
    outcomes = {}
    for name in ("candidate", "blocked_ownership"):
        board = plan[name]
        run([*make, board["target"]])
        dtb = output / "arch/arm64/boot/dts" / board["target"]
        if not dtb.is_file() or not dtb.stat().st_size:
            raise ValueError("missing compiled supplier DT: " + board["target"])
        raw = report / "unvalidated-supplier-dtbs"
        raw.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dtb, raw / dtb.name)
        run(["python3", plan["validator"], "--profile", board["profile"],
             "--base", base, "--fixture", dtb])
        destination = report / ("dormant-supplier-dtbs" if name == "candidate" else "nonbootable-dtbs")
        destination.mkdir(exist_ok=True)
        shutil.copyfile(dtb, destination / dtb.name)
        outcomes[name] = dict(target=board["target"], dtb_sha256=hashlib.sha256(dtb.read_bytes()).hexdigest(),
                              install_allowed=False, hardware_activated=False)
    return outcomes


def compile_md_pmic(kernel, work, report):
    draft = Path("patches/modem/md-pmic-supplier")
    vendor = Path("out/infra-vendor").resolve()
    if not vendor.is_dir():
        vendor = work / "md-pmic-vendor"
        run(["git", "init", vendor])
        run(["git", "-C", vendor, "fetch", "--depth=1",
             "https://github.com/NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878.git",
             "ee2be53cb75670b548948636a0db1d1ff112bf12"])
    run(["env", "TETRIS_VENDOR_TREE=" + str(vendor), "TETRIS_KERNEL_TREE=" + str(kernel),
         "python3", draft / "test_static.py"])
    run(["python3", draft / "stage.py", "--prepared-kernel", kernel, "--ci-apply"])
    output = work / "md-pmic-objects"
    output.mkdir(exist_ok=False)
    result = {"scope": "real native regulator object only; no registration, DT activation or hardware test", "variants": {}}
    for unit in ("y", "n"):
        shutil.copyfile(Path(PACKAGE) / CONFIG, output / ".config")
        run([kernel / "scripts/config", "--file", output / ".config",
             "-e", "REGULATOR_MT6363", "-e", "MFD_MT6363",
             "-e" if unit == "y" else "-d", "KUNIT"])
        make = ["make", "-j4", "-C", kernel, "O=" + str(output), "ARCH=arm64", "LLVM=1"]
        run([*make, "olddefconfig"])
        config = (output / ".config").read_text().splitlines()
        if "CONFIG_REGULATOR_MT6363=y" not in config or "CONFIG_MFD_MT6363=y" not in config or \
                ("CONFIG_KUNIT=y" in config) != (unit == "y"):
            raise ValueError("native modem PMIC configuration failed to resolve")
        name = "drivers/regulator/mt6363-regulator.o"
        run([*make, name])
        destination = report / "native-modem-pmic" / ("kunit-" + unit)
        destination.mkdir(parents=True, exist_ok=False)
        target = destination / "mt6363-regulator.o"
        shutil.copyfile(output / name, target)
        shutil.copyfile(output / ".config", destination / "config")
        result["variants"][unit] = {**object_identity(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    plan = json.loads((draft / "STAGING.json").read_text())
    result["staged_sources_sha256"] = {
        name: hashlib.sha256((kernel / name).read_bytes()).hexdigest()
        for name in plan["staged_after_sha256"]
    }
    return result


def gnss_tx_stage():
    draft = Path("patches/gnss/write-boundary").resolve()
    spec = importlib.util.spec_from_file_location("gnss_tx_stage", draft / "generate.py")
    stage = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stage)
    return stage, json.loads((draft / "STAGING.json").read_text())


def gnss_archive_identity(device_modules=False):
    source = (PACKAGE / "APKBUILD").read_text()
    variable, prefix, repository = (
        ("_devmods_commit", "android-kernel-device-modules-",
         "android_kernel_device_modules_6.1_nothing_mt6878") if device_modules else
        ("_connmods_commit", "android-kernel-modules-", "android_kernel_modules_nothing_mt6878"))
    pins = re.findall(r'^' + variable + r'="([0-9a-f]{40})"$', source, re.M)
    if len(pins) != 1:
        raise ValueError("missing immutable GNSS supplier pin: " + variable)
    archive_name = prefix + pins[0] + ".tar.gz"
    expression = (prefix + "$" + variable + ".tar.gz::https://github.com/NothingOSS/" +
                  repository + "/archive/$" + variable + ".tar.gz")
    if expression not in block(source, "source").split():
        raise ValueError("unsupported GNSS supplier archive expression")
    checksums = re.findall(r"^([0-9a-f]{128})  " + re.escape(archive_name) + r"$", source, re.M)
    if len(checksums) != 1:
        raise ValueError("missing exact GNSS source archive identity")
    return {"commit": pins[0], "archive": archive_name, "sha512": checksums[0],
            "repository": repository,
            "url": "https://github.com/NothingOSS/" + repository + "/archive/" + pins[0] + ".tar.gz"}


def fetch_gnss_archive(identity, work):
    archive = work / identity["archive"]
    with urllib.request.urlopen(identity["url"], timeout=120) as response, archive.open("wb") as dest:
        shutil.copyfileobj(response, dest)
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha512").hexdigest() != identity["sha512"]:
            raise ValueError("GNSS source archive checksum mismatch")
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    return work / (identity["repository"] + "-" + identity["commit"])


def prepare_gnss_tx_sources(work):
    stage, plan = gnss_tx_stage()
    identity = gnss_archive_identity()
    if identity["commit"] != stage.PIN or plan["connectivity_commit"] != stage.PIN:
        raise ValueError("GNSS package pin differs from reviewed TX fixture")
    vendor = fetch_gnss_archive(identity, work)
    for patch in stage.stack():
        if patch.name.startswith("1005-"):
            clock = vendor / (stage.BASE + "linux/gps_dl_linux_clock_mng.c")
            clock.write_bytes(clock.read_bytes().replace(b"\r\n", b"\n"))
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", vendor, "-i", patch])
    for name, digest in plan["stacked_source_sha512"].items():
        if hashlib.sha512((vendor / name).read_bytes()).hexdigest() != digest:
            raise ValueError("GNSS compiler preimage differs from reviewed TX fixture: " + name)
    if hashlib.sha512(stage.PATCH.read_bytes()).hexdigest() != plan["patch_sha512"]:
        raise ValueError("GNSS reviewed TX patch identity changed")
    return stage, vendor, plan, identity


def apply_gnss_tx(stage, vendor):
    expected = {name: stage.transform(name, (vendor / name).read_text()).encode() for name in stage.SOURCES}
    run(["patch", "--batch", "--fuzz=0", "-p1", "-d", vendor, "-i", stage.PATCH])
    for name, content in expected.items():
        if (vendor / name).read_bytes() != content:
            raise ValueError("actual GNSS compiler source differs from reviewed TX fixture: " + name)


def compile_gnss_tx(kernel, work, report):
    stage, vendor, _, identity = prepare_gnss_tx_sources(work)
    apply_gnss_tx(stage, vendor)
    output = work / "gnss-tx-objects"
    output.mkdir(exist_ok=False)
    shutil.copyfile(PACKAGE / CONFIG, output / ".config")
    make = ["make", "-j4", "-C", kernel, "O=" + str(output), "ARCH=arm64", "LLVM=1"]
    run([*make, "olddefconfig"])
    run([*make, "modules_prepare"])
    gps = vendor / "connectivity/gps/data_link/plat/v051"
    # Use the actual vendor Kbuild and its existing packaged compatibility
    # stack, not standalone fixtures or private header/prototype stubs.
    module_make = [*make, "M=" + str(gps), "CONFIG_MTK_GPS_SUPPORT=y",
                   "CONFIG_ARM64=y", "CONFIG_MTK_COMBO=y", "CONFIG_MTK_CONNINFRA=m",
                   "CONFIG_CONNINFRA_PLAT_BUILD_MODE=module", "MTK_PLATFORM=mt6878",
                   "MTK_CONSYS_ADIE=MT6631", "TARGET_BUILD_VARIANT=user",
                   "KCFLAGS=-DCONFIG_MTK_COMBO_CHIP_CONSYS_6878=1 -Wno-error=format "
                   "-Wno-error=format-extra-args -Wno-error=missing-prototypes"]
    names = ("gps_each_link.o", "linux/gps_each_device.o")
    run([*module_make, *names])
    destination = report / "gnss-tx-objects"
    destination.mkdir(exist_ok=False)
    shutil.copyfile(output / ".config", destination / "config")
    identities = {}
    for name in names:
        target = gps / name
        saved = destination / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, saved)
        identities[name] = {**object_identity(saved), "sha256": hashlib.sha256(saved.read_bytes()).hexdigest()}
    if list(gps.rglob("*.ko")):
        raise ValueError("GNSS object-only gate must not produce runtime modules")
    return {"scope": "real ARM64 v051 translation units; no modpost, installation or hardware test",
            "connectivity_commit": stage.PIN, "archive_sha512": identity["sha512"],
            "patch_sha512": hashlib.sha512(stage.PATCH.read_bytes()).hexdigest(),
            "objects": identities}


def gnss_module_plan():
    stage, staged = gnss_tx_stage()
    prerequisites = stage.stack()
    connectivity = gnss_archive_identity()
    device = gnss_archive_identity(True)
    if connectivity["commit"] != stage.PIN:
        raise ValueError("GNSS package pin differs from reviewed TX fixture")
    adapter_patch = PACKAGE / "1000-vendor-connectivity-adapter-linux-6.18.patch.vendor"
    digest = hashlib.sha512(adapter_patch.read_bytes()).hexdigest()
    source = (PACKAGE / "APKBUILD").read_text()
    if (adapter_patch.name not in block(source, "source").split() or
            re.findall(r"^([0-9a-f]{128})  " + re.escape(adapter_patch.name) + r"$", source, re.M) != [digest]):
        raise ValueError("GNSS adapter patch checksum mismatch")
    if hashlib.sha512(stage.PATCH.read_bytes()).hexdigest() != staged["patch_sha512"]:
        raise ValueError("GNSS reviewed TX patch identity changed")
    return {"scope": "full ARM64 v051 baseline/candidate link and strict real-export modpost only",
            "status": "pending", "shipping_activation": False, "hardware_tested": False,
            "phone_abi_compatible": False, "connectivity": connectivity, "device_modules": device,
            "prerequisites": [path.name for path in prerequisites],
            "prerequisite_sha512": staged["prerequisite_sha512"],
            "adapter_patch_sha512": digest, "patch_sha512": staged["patch_sha512"],
            "suppliers": ["kernel vmlinux/modules", "connadp", "conninfra"],
            "variants": ["baseline-1001-1008", "candidate-1009"]}


def gnss_connectivity_make(make, kernel, output, module, device, top):
    # Mirror APKBUILD _connectivity_make, with separate source/output trees.
    return [*make, "M=" + str(module), "KERNEL_SRC=" + str(kernel),
            "KERNEL_OUT=" + str(output), "KO_CODE_PATH=" + str(module),
            "DEVICE_MODULES_PATH=" + str(device), "TOP=" + str(top),
            "MTK_PLATFORM=mt6878", "MTK_PLATFORM_WMT=mt6878", "CONFIG_MTK_PLATFORM=mt6878",
            "TARGET_BOARD_PLATFORM_WMT=mt6878", "TARGET_BUILD_VARIANT=user", "CONFIG_ARM64=y",
            "CONFIG_MTK_COMBO=y", "CONFIG_MTK_COMBO_WIFI=m", "CONFIG_MTK_COMBO_CHIP_CONSYS_6878=y",
            "CONFIG_MTK_COMBO_WIFI_HIF=axi", "CONFIG_MTK_BTIF=n", "CONFIG_MTK_CONNINFRA=m",
            "CONFIG_CONNINFRA_PLAT_BUILD_MODE=module", "CONFIG_WLAN_DRV_BUILD_IN=n",
            "MTK_CONSYS_ADIE=MT6631",
            "KCFLAGS=-DCONFIG_MTK_COMBO_CHIP_CONSYS_6878=1 -Wno-error=format "
            "-Wno-error=format-extra-args -Wno-error=missing-prototypes"]


def prepare_gnss_adapter(device):
    targets = {
        "drivers/misc/mediatek/connectivity/common/wmt_build_in_adapter.c": "CONN_DBG_DEVICE_NAME",
        "drivers/misc/mediatek/connectivity/power_throttling/adapter.c": "CONN_PWR_DEVICE_NAME",
    }
    expected, identities = {}, {}
    for name, argument in targets.items():
        before = (device / name).read_bytes()
        old = ("class_create(THIS_MODULE, " + argument + ")").encode()
        if before.count(old) != 1:
            raise ValueError("absent or ambiguous pinned adapter API: " + name)
        expected[name] = before.replace(old, ("class_create(" + argument + ")").encode(), 1)
        identities[name] = {"before_sha256": hashlib.sha256(before).hexdigest()}
    # This legacy patch uses abuild's default context fuzz. Verify the entire
    # postimage instead of requiring mismatched historical log-line context.
    run(["patch", "--batch", "--fuzz=2", "-p1", "-d", device, "-i",
         (PACKAGE / "1000-vendor-connectivity-adapter-linux-6.18.patch.vendor").resolve()])
    for name, after in expected.items():
        if (device / name).read_bytes() != after:
            raise ValueError("adapter patch changed more than the reviewed API: " + name)
        identities[name]["after_sha256"] = hashlib.sha256(after).hexdigest()
    return identities


def gnss_module_evidence(module, symvers):
    identity = object_identity(module)
    if identity["format"] != "ELF":
        raise ValueError("GNSS final module must be ARM64 ELF")
    exports = {}
    for table in symvers:
        if not table.is_file() or not table.stat().st_size:
            raise ValueError("missing built GNSS supplier exports: " + str(table))
        for line in table.read_text().splitlines():
            fields = line.split()
            if len(fields) < 4 or not re.fullmatch(r"0x[0-9a-fA-F]{8}", fields[0]):
                raise ValueError("invalid built GNSS supplier export row: " + str(table))
            if fields[1] in exports:
                raise ValueError("duplicate GNSS supplier export: " + fields[1])
            exports[fields[1]] = {"table": str(table), "row": fields}
    symbols = subprocess.check_output(["llvm-nm", "--undefined-only", module], text=True)
    imports, weak = set(), set()
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) != 2 or fields[0] not in ("U", "w", "v"):
            raise ValueError("unexpected GNSS undefined-symbol row: " + line)
        (imports if fields[0] == "U" else weak).add(fields[1])
    missing = sorted(imports - exports.keys())
    if missing:
        raise ValueError("GNSS imports absent from real supplier exports: " + ", ".join(missing))
    return {**identity, "sha256": hashlib.sha256(module.read_bytes()).hexdigest(),
            "imports": {name: exports[name] for name in sorted(imports)},
            "weak_imports": sorted(weak)}


def compile_gnss_tx_module(kernel, work, report):
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("full GNSS module compilation is CI-only")
    destination = report / "gnss-tx-module"
    destination.mkdir(exist_ok=False)
    manifest = gnss_module_plan()
    manifest["status"] = "started"
    manifest_file = destination / "MODULE-MANIFEST.json"

    def save():
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")

    def step(phase, command):
        manifest.update(phase=phase, command=list(map(str, command)))
        save()
        with (destination / (phase + ".log")).open("w") as log:
            print("+ " + " ".join(map(str, command)), flush=True)
            subprocess.run(list(map(str, command)), stdout=log, stderr=subprocess.STDOUT, check=True)

    def retain_exports(table, name):
        if not table.is_file() or not table.stat().st_size:
            raise ValueError("missing built GNSS supplier exports: " + str(table))
        saved = destination / (name + ".symvers")
        shutil.copyfile(table, saved)
        manifest.setdefault("supplier_symvers_sha256", {})[saved.name] = hashlib.sha256(saved.read_bytes()).hexdigest()
        save()

    save()
    try:
        manifest["phase"] = "source-preparation"
        save()
        stage, vendor, staged, _ = prepare_gnss_tx_sources(work)
        device = fetch_gnss_archive(manifest["device_modules"], work)
        manifest["adapter_source"] = prepare_gnss_adapter(device)
        save()
        top = work / "android-top"
        connectivity = top / "vendor/mediatek/kernel_modules/connectivity"
        connectivity.parent.mkdir(parents=True)
        connectivity.symlink_to(vendor / "connectivity", target_is_directory=True)
        output = work / "gnss-module-kernel"
        output.mkdir()
        shutil.copyfile(PACKAGE / CONFIG, output / ".config")
        make = ["make", "-j4", "-C", kernel, "O=" + str(output), "ARCH=arm64", "LLVM=1",
                "KBUILD_MODPOST_WARN=", "KBUILD_MODPOST_NOFINAL=", "KBUILD_EXTRA_SYMBOLS="]
        manifest["phase"] = "compiler-identity"
        save()
        compiler = subprocess.check_output(["clang", "--version"], text=True)
        if not re.search(r"clang version 21\.", compiler):
            raise ValueError("GNSS module gate requires package-matching LLVM 21")
        manifest["compiler"] = compiler.strip()
        step("kernel-config", [*make, "olddefconfig"])
        shutil.copyfile(output / ".config", destination / "kernel.config")
        manifest["config_sha256"] = hashlib.sha256((output / ".config").read_bytes()).hexdigest()
        # modules_prepare cannot generate Module.symvers; build the actual kernel.
        step("kernel-exports", [*make, "vmlinux", "modules"])
        manifest["kernel_identity"] = object_identity(output / "vmlinux")
        with (output / "vmlinux").open("rb") as stream:
            manifest["kernel_identity"]["sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        tables = [output / "Module.symvers"]
        retain_exports(tables[0], "kernel")
        suppliers = (("connadp", device / "drivers/misc/mediatek/connectivity"),
                     ("conninfra", vendor / "connectivity/conninfra"))
        for name, module in suppliers:
            # Require every preceding supplier's real exports before invoking modpost.
            for table in tables:
                if not table.is_file() or not table.stat().st_size:
                    raise ValueError("missing built GNSS supplier exports: " + str(table))
            command = gnss_connectivity_make(make, kernel, output, module, device, top)
            if name == "connadp":
                command = [arg for arg in command if arg != "CONFIG_MTK_COMBO=y"]
                command.append("CONFIG_MTK_COMBO=m")
            else:
                command.append("KBUILD_EXTRA_SYMBOLS=" + " ".join(map(str, tables[1:])))
            step(name, [*command, "modules"])
            manifest[name] = gnss_module_evidence(module / (name + ".ko"), tables)
            tables.append(module / "Module.symvers")
            retain_exports(tables[-1], name)
        gps = vendor / "connectivity/gps/data_link/plat/v051"
        command = gnss_connectivity_make(make, kernel, output, gps, device, top)
        command += ["CONFIG_MTK_GPS_SUPPORT=y",
                    "KBUILD_EXTRA_SYMBOLS=" + " ".join(map(str, tables[1:]))]
        for variant in manifest["variants"]:
            if variant == "candidate-1009":
                step("gnss-clean", [*command, "clean"])
                manifest["phase"] = "apply-1009"
                save()
                apply_gnss_tx(stage, vendor)
            else:
                manifest["phase"] = "baseline-source-check"
                save()
                for name, digest in staged["stacked_source_sha512"].items():
                    if hashlib.sha512((vendor / name).read_bytes()).hexdigest() != digest:
                        raise ValueError("GNSS baseline source changed: " + name)
            step(variant, [*command, "modules"])
            manifest[variant] = gnss_module_evidence(gps / "gps_drv_dl_v051.ko", tables)
            manifest[variant]["source_sha512"] = {
                name: hashlib.sha512((vendor / name).read_bytes()).hexdigest()
                for name in staged["stacked_source_sha512"]}
            manifest[variant]["kbuild_sha256"] = hashlib.sha256((gps / "Kbuild").read_bytes()).hexdigest()
            save()
        manifest["status"] = "passed"
        save()
        return manifest
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        save()
        raise


def compile_dt_only(kernel, package, work, report, manifest):
    output = work / "dt-only-output"
    output.mkdir(exist_ok=False)
    shutil.copyfile(package / CONFIG, output / ".config")
    make = ["make", "-j4", "-C", kernel, "O=" + str(output), "ARCH=arm64", "LLVM=1"]
    run([*make, "olddefconfig"])
    manifest.update(objects=[], scope="compiled DT only; no driver/kernel image/link or hardware execution")
    manifest["dtb_sha256"] = compile_dtbs(make, output, report)
    manifest["hif_dt"] = compile_hif_dtb(make, kernel, output, report)
    manifest["status"] = "passed"
    return manifest


def run(command):
    print("+ " + " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True)


def stage_research_sources(kernel, root=Path(".")):
    directories = {str(Path(name).parent) for name in RESEARCH_OBJECTS}
    destinations = [*RESEARCH_SOURCES.values(), *(f"{name}/Makefile" for name in directories)]
    for destination in destinations:
        if (kernel / destination).exists():
            raise ValueError(f"research destination already exists: {destination}")
    for source in RESEARCH_SOURCES:
        if not (root / source).is_file():
            raise ValueError(f"research source is missing: {source}")
    for source, destination in RESEARCH_SOURCES.items():
        target = kernel / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / source, target)
    for directory in sorted(directories):
        names = [Path(name).name for name in RESEARCH_OBJECTS if str(Path(name).parent) == directory]
        makefile = "obj-y += " + " ".join(names) + "\n"
        if directory == INFRA_CLOCK_DIR:
            makefile += "ccflags-y += -I$(srctree)/drivers/clk/mediatek\n"
        if directory == str(Path(CAMISP_POWER_OBJECTS[0]).parent):
            makefile += "ccflags-y += -I$(srctree)/" + CAMISP_POWER_PLAN["include_directory"] + "\n"
        if directory == CAMISP_SHARED_DIR:
            makefile += ("ccflags-y += -I$(srctree)/drivers/pmdomain/mediatek "
                         "-I$(srctree)/" + str(Path(CAMISP_POWER_OBJECTS[0]).parent) + "\n")
        (kernel / directory / "Makefile").write_text(makefile)


def research_compile_flags(kernel):
    # Direct object targets may bypass the isolated child Makefile.
    headers = (Path(next(iter(CAMERA_SOURCES.values()))).parent,
               Path("drivers/clk/mediatek"),
               Path(CAMISP_RESOURCE_PLAN["include_directory"]),
               Path(CAMISP_POWER_OBJECTS[0]).parent)
    return "KCFLAGS=" + " ".join(f"-I{kernel / path}" for path in headers)


def stage_camera_overlays(kernel, root=Path(".")):
    destination = kernel / Path(next(iter(CAMERA_SOURCES.values()))).parent
    graph = kernel / CAMERA_GRAPH
    staged = destination / graph.name
    if not graph.is_file() or staged.exists():
        raise ValueError("camera overlay requires unique packaged graph source")
    # Basename overlays share the isolated closure; keep the graph's production
    # Kbuild target, never introduce a duplicate object or replace parent Kbuild.
    shutil.copyfile(graph, staged)
    try:
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", kernel,
             "-i", (root / CAMERA_REVIEW_PATCHES[0]).resolve()])
        for name in CAMERA_REVIEW_PATCHES[1:]:
            run(["patch", "--batch", "--fuzz=0", "-p1", "-d", destination,
                 "-i", (root / name).resolve()])
        shutil.copyfile(staged, graph)
    finally:
        staged.unlink()


def stage_camera_repeat(kernel, root=Path(".")):
    destination = kernel / Path(next(iter(CAMERA_SOURCES.values()))).parent
    for name in CAMERA_REPEAT_PATCHES:
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", destination,
             "-i", (root / name).resolve()])


def stage_camisp(kernel, root=Path(".")):
    run(["python3", root / CAMISP_CHECK, "--kernel-tree", kernel])
    run(["patch", "--batch", "--fuzz=0", "-p1", "-d", kernel,
         "-i", (root / CAMISP_PLAN["provider_overlay"]).resolve()])
    destination = kernel / Path(CAMISP_PLAN["consumer_source"]).parent
    run(["patch", "--batch", "--fuzz=0", "-p1", "-d", destination,
         "-i", (root / CAMISP_PLAN["consumer_overlay"]).resolve()])
    run(["python3", root / CAMISP_CHECK, "--staged-tree", kernel])


def object_identity(target):
    with target.open("rb") as stream:
        magic = stream.read(4)
    if magic in (b"BC\xc0\xde", b"\xde\xc0\x17\x0b"):
        # Shipping ThinLTO emits LLVM IR for built-in translation units.
        ir = subprocess.check_output(["llvm-dis", "-o", "-", target], text=True)
        triples = re.findall(r'^target triple = "([^"]+)"$', ir, re.M)
        if len(triples) != 1 or not triples[0].startswith("aarch64-"):
            raise ValueError(f"wrong bitcode architecture: {target.name}")
        return {"format": "LLVM bitcode", "target_triple": triples[0]}
    header = subprocess.check_output(["llvm-readelf", "-h", target], text=True)
    if magic != b"\x7fELF" or not re.search(r"Machine:\s+AArch64", header):
        raise ValueError(f"wrong object architecture: {target.name}")
    return {"format": "ELF", "machine": "AArch64"}


def config_options(kernel, output, research_owners):
    options = [kernel / "scripts/config", "--file", output / ".config"]
    enabled = ENABLE + (CAMERA_SELECTORS + CAMERA_ENABLE + CAM_MAIN_ENABLE +
                        CAM_MAIN_REACHABLE + CAMISP_ENABLE + CAMISP_RESOURCE_ENABLE +
                        CAMISP_RESOURCE_REACHABLE + CAMISP_POWER_ENABLE +
                        CAMISP_POWER_REACHABLE if research_owners else ())
    for symbol in dict.fromkeys(enabled):
        options.extend(["-e", symbol])
    for symbol in MODULES:
        options.extend(["-m", symbol])
    return options


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--dt-only", action="store_true",
                        help="compile checked native/HIF DTs without rebuilding any driver or kernel image")
    parser.add_argument("--prepare-only", action="store_true",
                        help="prepare exact packaged provider sources without compiling any objects")
    parser.add_argument("--research-owners", action="store_true",
                        help="also compile frozen default-off owners without shipping wiring")
    parser.add_argument("--gnss-tx-module", action="store_true",
                        help="CI-only full v051 baseline and staged TX module link with real suppliers")
    parser.add_argument("--work", type=Path, default=Path("/tmp/tetris-kernel-smoke"))
    args = parser.parse_args()
    if sum((args.dt_only, args.prepare_only, args.research_owners, args.gnss_tx_module)) > 1:
        parser.error("DT-only, source-only, driver-owner and GNSS module modes are separate experiments")
    package = PACKAGE.resolve()
    manifest = plan(package)
    objects = OBJECTS
    if args.gnss_tx_module:
        args.work = args.work.resolve()
        manifest.update(objects=[], dtbs=[], gnss_nonblocking_tx_module=gnss_module_plan())
    if args.research_owners:
        objects += RESEARCH_OBJECTS + PROVIDER_OBJECTS
        manifest["objects"] = objects
        manifest["research_source_sha256"] = {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in RESEARCH_SOURCES
        }
        manifest["research_source_sha256"][CAMERA_MANIFEST] = hashlib.sha256(
            Path(CAMERA_MANIFEST).read_bytes()).hexdigest()
        manifest["research_source_sha256"][CAMERA_JOINT_MANIFEST] = hashlib.sha256(
            Path(CAMERA_JOINT_MANIFEST).read_bytes()).hexdigest()
        joint_check = "patches/camera-joint-reset/check.py"
        manifest["research_source_sha256"][joint_check] = hashlib.sha256(
            Path(joint_check).read_bytes()).hexdigest()
        manifest["research_source_sha256"][PROVIDER_PATCH] = hashlib.sha256(
            Path(PROVIDER_PATCH).read_bytes()).hexdigest()
        for name in CAMERA_REVIEW_PATCHES:
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in (CAMERA_REPEAT_MANIFEST, CAMERA_REPEAT_CHECK,
                     "patches/camera-repeat-capture/test-completion-order.py",
                     "patches/camera-repeat-capture/generate-overlays.py", *CAMERA_REPEAT_PATCHES):
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in (CAM_MAIN_MANIFEST, CAM_MAIN_CHECK, CAM_MAIN_PLAN["overlay"]):
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in (CAMISP_MANIFEST, CAMISP_CHECK, "patches/camera-camisp/test-source.py",
                     "patches/camera-camisp/generate-overlays.py",
                     CAMISP_PLAN["provider_overlay"], CAMISP_PLAN["consumer_overlay"]):
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        for name in CAMISP_RESOURCE_INPUTS:
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        manifest["camisp_resource_config_variants"] = CAMISP_RESOURCE_PLAN["config_variants"]
        for name in CAMISP_POWER_INPUTS:
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        manifest["camisp_power_config_variants"] = CAMISP_POWER_PLAN["config_variants"]
        shared_check = subprocess.check_output(["python3", CAMISP_SHARED_CHECK], text=True)
        for name, expected in CAMISP_SHARED_PLAN["source_sha256"].items():
            actual = hashlib.sha256(Path(name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"shared VMM payload hash mismatch: {name}")
            manifest["research_source_sha256"][name] = actual
        for name in CAMISP_SHARED_INPUTS:
            manifest["research_source_sha256"][name] = hashlib.sha256(Path(name).read_bytes()).hexdigest()
        manifest["camisp_shared_supplier"] = {
            "scope": "object-only; shared composite/vmlinux link untested",
            "config_variants": CAMISP_SHARED_PLAN["config_variants"],
            "payload_sha256": CAMISP_SHARED_PLAN["source_sha256"],
            "source_check": {"status": "passed", "output": shared_check.strip()},
            "staged_sources": {**CAMISP_POWER_PLAN["sources"], **CAMISP_SHARED_SOURCES},
            "objects": CAMISP_POWER_OBJECTS + CAMISP_SHARED_OBJECTS,
            "excluded_from_staging": ["Kbuild.shared"],
        }
    if args.plan_only:
        print(json.dumps(manifest, indent=2))
        return
    if os.environ.get("GITHUB_ACTIONS") != "true":
        parser.error("native kernel compilation is CI-only")
    args.work.mkdir(parents=True, exist_ok=False)
    report = Path("out/kernel-object-smoke")
    report.mkdir(parents=True, exist_ok=True)
    manifest.update(commit=os.environ["GITHUB_SHA"], status="started",
                    scope="object-only; no linking, installation or hardware test")
    if args.gnss_tx_module:
        manifest["scope"] = manifest["gnss_nonblocking_tx_module"]["scope"]
    manifest_file = report / "BUILD-MANIFEST.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
    archive = args.work / manifest["archive"]
    url = f'https://github.com/MT6878-mainline/linux/archive/{manifest["kernel_commit"]}.tar.gz'
    with urllib.request.urlopen(url, timeout=120) as response, archive.open("wb") as dest:
        shutil.copyfileobj(response, dest)
    with archive.open("rb") as stream:
        if hashlib.file_digest(stream, "sha512").hexdigest() != manifest["archive_sha512"]:
            raise ValueError("kernel archive checksum mismatch")
    with tarfile.open(archive) as tar:
        tar.extractall(args.work, filter="data")
    kernel = args.work / f'linux-{manifest["kernel_commit"]}'
    md_pristine = args.work / "md-native-pristine"
    if args.research_owners or args.prepare_only:
        md_pristine.mkdir()
        for name in ("drivers/pmdomain/mediatek/mtk-pm-domains.c",
                     "drivers/pmdomain/mediatek/mtk-pm-domains.h"):
            target = md_pristine / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(kernel / name, target)
        run(["python3", "patches/modem/md-pm-integration/stage.py", "--kernel", md_pristine])
    if args.research_owners:
        run(["python3", "patches/camera-camisp/generate-overlays.py",
             "--check", "--kernel-tree", kernel])
        run(["python3", "patches/camera-camisp/resources/generate.py", "--check"])
        run(["python3", "patches/camera-camisp/resources/test-source.py"])
        run(["python3", "patches/camera-camisp/resources/test-dt.py"])
        run(["python3", "patches/camera-camisp/resources/check-supplier.py"])
        run(["python3", "patches/camera-camisp/resources/test-supplier.py"])
        run(["python3", CAMISP_POWER_CHECK])
        run(["python3", "patches/camera-camisp/power/test_source.py"])
        run(["python3", "patches/camera-camisp/power/test_supplier.py"])
        manifest["camisp_shared_supplier"]["source_tests"] = "passed"
    for patch in manifest["patches"]:
        # Match abuild default_prepare for legacy patches, not a different build.
        flags = ["--fuzz=0"] if patch in STRICT_PATCHES else []
        run(["patch", "--batch", *flags, "-p1", "-d", kernel, "-i", package / patch])
    if args.gnss_tx_module:
        try:
            manifest["gnss_nonblocking_tx_module"] = compile_gnss_tx_module(kernel, args.work, report)
        except Exception as error:
            manifest.update(status="failed", error=str(error))
            manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
            raise
        manifest["status"] = "passed"
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
        return
    if args.research_owners or args.prepare_only:
        source_report = report / "native-provider-inputs"
        source_report.mkdir()
        for name in ("mtk-pm-domains.c", "mtk-pm-domains.h", "mt6878-modem-pm.h"):
            shutil.copyfile(kernel / "drivers/pmdomain/mediatek" / name, source_report / name)
        run(["python3", "patches/modem/md-pm-integration/stage.py", "--kernel", md_pristine,
             "--prepared-kernel", kernel])
    if args.prepare_only:
        manifest.update(status="passed", scope="source preparation and exact native-provider input checks only",
                        objects=[])
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
        return
    if args.dt_only:
        manifest = compile_dt_only(kernel, package, args.work, report, manifest)
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
        return
    if args.research_owners:
        # Built-in translation units: no MODULE define, probe, parent Kbuild
        # linkage or shipping Kconfig change. Preserve exact production bytes.
        manifest["native_modem_pmic"] = compile_md_pmic(kernel, args.work, report)
        manifest["gnss_nonblocking_tx"] = compile_gnss_tx(kernel, args.work, report)
        stage_research_sources(kernel)
        for source, destination in CAMISP_SUPPLIER_PLAN["sources"].items():
            if hashlib.sha256((kernel / destination).read_bytes()).hexdigest() != \
                    CAMISP_SUPPLIER_PLAN["payload_sha256"][Path(source).name]:
                raise ValueError("camera supplier staged source drift: " + source)
        run(["python3", "patches/camera-camisp/resources/check-supplier.py", "--staged-tree", kernel])
        run(["python3", CAMISP_RESOURCE_CHECK, "--staged-tree", kernel,
             "--kernel-tree", kernel])
        manifest["derived_camisp_resource_sources_sha256"] = {
            destination: hashlib.sha256((kernel / destination).read_bytes()).hexdigest()
            for destination in CAMISP_RESOURCE_PLAN["sources"].values()
        }
        manifest["derived_camisp_power_sources_sha256"] = {
            destination: hashlib.sha256((kernel / destination).read_bytes()).hexdigest()
            for destination in CAMISP_POWER_PLAN["sources"].values()
        }
        manifest["camisp_shared_supplier"]["staged_source_sha256"] = {
            destination: hashlib.sha256((kernel / destination).read_bytes()).hexdigest()
            for destination in (*CAMISP_POWER_PLAN["sources"].values(), *CAMISP_SHARED_SOURCES.values())
        }
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", kernel,
             "-i", Path(PROVIDER_PATCH).resolve()])
        stage_camera_overlays(kernel)
        run(["python3", "patches/camera-joint-reset/check.py",
             "--staged-only", "--kernel-tree", kernel])
        # Verify the cold chain first; the repeat worker delegates to that chain.
        run(["python3", CAMERA_REPEAT_CHECK])
        stage_camera_repeat(kernel)
        run(["python3", "patches/camera-camisp/test-source.py"])
        stage_camisp(kernel)
        manifest["derived_camisp_sources_sha256"] = {
            destination: hashlib.sha256((kernel / destination).read_bytes()).hexdigest()
            for destination in ("drivers/memory/mtk-smi.c", "drivers/iommu/mtk_iommu.c",
                                CAMISP_PLAN["consumer_source"], *CAMISP_PLAN["sources"].values())
        }
        manifest["derived_camera_sources_sha256"] = {
            destination: hashlib.sha256((kernel / destination).read_bytes()).hexdigest()
            for destination in (*CAMERA_SOURCES.values(), *CAMERA_JOINT_SOURCES.values(),
                                *CAMERA_REPEAT_SOURCES.values())
        }
        run(["python3", CAM_MAIN_CHECK, "--kernel-tree", kernel])
        run(["patch", "--batch", "--fuzz=0", "-p1", "-d", kernel,
             "-i", Path(CAM_MAIN_PLAN["overlay"]).resolve()])
        run(["python3", CAM_MAIN_CHECK, "--staged-tree", kernel])
        manifest["derived_camera_graph_sha256"] = hashlib.sha256((kernel / CAMERA_GRAPH).read_bytes()).hexdigest()
    output = args.work / "objects"
    output.mkdir()
    shutil.copyfile(package / CONFIG, output / ".config")
    run(config_options(kernel, output, args.research_owners))
    make = ["make", "-C", kernel, f"O={output}", "ARCH=arm64", "LLVM=1", "-j4"]
    if args.research_owners:
        make.append(research_compile_flags(kernel))
    run([*make, "olddefconfig"])
    manifest["dtb_sha256"] = compile_dtbs(make, output, report)
    if args.research_owners:
        manifest["hif_dt"] = compile_hif_dtb(make, kernel, output, report)
        manifest["camisp_resource_dt"] = compile_camisp_resource_dtb(make, output, report)
        manifest["camisp_supplier_dt"] = compile_camisp_supplier_dtbs(make, output, report)
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.copyfile(output / ".config", report / "isolated.config")
    config = (output / ".config").read_text().splitlines()
    for symbol in MODULES:
        if f"CONFIG_{symbol}=m" not in config:
            raise ValueError(f"isolated dependency missing: {symbol}")
    if args.research_owners:
        for symbol in CAMERA_ENABLE:
            if f"CONFIG_{symbol}=y" not in config:
                raise ValueError(f"isolated camera dependency missing: {symbol}")
        for symbol in (*CAMISP_ENABLE, *CAMISP_RESOURCE_ENABLE, *CAMISP_POWER_ENABLE):
            if f"CONFIG_{symbol}=y" not in config:
                raise ValueError(f"isolated CAMISP dependency missing: {symbol}")
        for symbol in (*CAM_MAIN_REACHABLE, *CAMISP_RESOURCE_REACHABLE):
            if not any(f"CONFIG_{symbol}={value}" in config for value in ("y", "m")):
                raise ValueError(f"isolated CAM_MAIN dependency missing: {symbol}")
    run([*make, "-k", *objects])
    identities = {}
    for name in objects:
        target = output / name
        if not target.is_file() or not target.stat().st_size:
            raise ValueError(f"missing object: {name}")
        identities[name] = object_identity(target)
        identities[name]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        print(name + ": " + json.dumps(identities[name]), flush=True)
    if list(output.rglob("*.ko")) or (output / "vmlinux").exists():
        raise ValueError("object-only CI must not produce runtime modules or kernel")
    if args.research_owners:
        # Also compile the real video and clock owners without private KUnit cases.
        # No fixture execution or change to the shipping kernel configuration.
        video_objects = tuple(name for name in CAMERA_OBJECTS
                              if Path(name).name in ("mt6878-native-video.o", "video-smoke.o"))
        if len(video_objects) != 2:
            raise ValueError("video variant requires both explicit objects")
        cam_main_objects = tuple(CAM_MAIN_PLAN["provider_objects"] + CAM_MAIN_PLAN["research_objects"])
        repeat_consumers = tuple(name for name in CAMERA_OBJECTS
                                 if Path(name).name in ("mt6878-native-capture.o", "mt6878-camsv-platform.o"))
        if len(repeat_consumers) != 2:
            raise ValueError("repeat-capture variant requires both actual consumers")
        variant_objects = (video_objects + cam_main_objects + CAMERA_JOINT_OBJECTS +
                           CAMERA_REPEAT_OBJECTS + repeat_consumers + CAMISP_OBJECTS +
                           CAMISP_RESOURCE_OBJECTS + CAMISP_POWER_OBJECTS)
        variant_objects += CAMISP_SHARED_OBJECTS
        run([kernel / "scripts/config", "--file", output / ".config", "-d", "KUNIT"])
        run([*make, "olddefconfig"])
        if any(line.startswith("CONFIG_KUNIT=")
               for line in (output / ".config").read_text().splitlines()):
            raise ValueError("video KUnit-disabled configuration did not resolve")
        shutil.copyfile(output / ".config", report / "video-kunit-disabled.config")
        for name in variant_objects:
            (output / name).unlink()
        run([*make, *variant_objects])
        manifest["video_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in video_objects
        }
        manifest["cam_main_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in cam_main_objects
        }
        manifest["camera_joint_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in CAMERA_JOINT_OBJECTS
        }
        manifest["camera_repeat_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in (*CAMERA_REPEAT_OBJECTS, *repeat_consumers)
        }
        manifest["camisp_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in CAMISP_OBJECTS
        }
        manifest["camisp_resource_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in CAMISP_RESOURCE_OBJECTS
        }
        manifest["camisp_power_kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in CAMISP_POWER_OBJECTS
        }
        manifest["camisp_shared_supplier"]["kunit_enabled_objects"] = {
            name: identities[name] for name in (*CAMISP_POWER_OBJECTS, *CAMISP_SHARED_OBJECTS)
        }
        manifest["camisp_shared_supplier"]["kunit_disabled_objects"] = {
            name: {**object_identity(output / name),
                   "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()}
            for name in (*CAMISP_POWER_OBJECTS, *CAMISP_SHARED_OBJECTS)
        }
    manifest["status"] = "passed"
    manifest["object_identities"] = identities
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
