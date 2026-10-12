#!/usr/bin/env python3
"""Compile packaged candidate translation units in CI, never install them."""

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
    "clock-providers.patch", "disabled-description.patch"))
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
    parser.add_argument("--research-owners", action="store_true",
                        help="also compile frozen default-off owners without shipping wiring")
    parser.add_argument("--work", type=Path, default=Path("/tmp/tetris-kernel-smoke"))
    args = parser.parse_args()
    if args.dt_only and args.research_owners:
        parser.error("DT-only and driver-owner modes are separate experiments")
    package = PACKAGE.resolve()
    manifest = plan(package)
    objects = OBJECTS
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
    if args.research_owners:
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
        run(["python3", CAMISP_POWER_CHECK])
        run(["python3", "patches/camera-camisp/power/test_source.py"])
        run(["python3", "patches/camera-camisp/power/test_supplier.py"])
        manifest["camisp_shared_supplier"]["source_tests"] = "passed"
    for patch in manifest["patches"]:
        # Match abuild default_prepare for legacy patches, not a different build.
        flags = ["--fuzz=0"] if patch in STRICT_PATCHES else []
        run(["patch", "--batch", *flags, "-p1", "-d", kernel, "-i", package / patch])
    if args.research_owners:
        source_report = report / "native-provider-inputs"
        source_report.mkdir()
        for name in ("mtk-pm-domains.c", "mtk-pm-domains.h", "mt6878-modem-pm.h"):
            shutil.copyfile(kernel / "drivers/pmdomain/mediatek" / name, source_report / name)
        run(["python3", "patches/modem/md-pm-integration/stage.py", "--kernel", md_pristine,
             "--prepared-kernel", kernel])
    if args.dt_only:
        manifest = compile_dt_only(kernel, package, args.work, report, manifest)
        manifest_file.write_text(json.dumps(manifest, indent=2) + "\n")
        return
    if args.research_owners:
        # Built-in translation units: no MODULE define, probe, parent Kbuild
        # linkage or shipping Kconfig change. Preserve exact production bytes.
        stage_research_sources(kernel)
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
