#!/usr/bin/env python3
"""Full real native supplier/provider/CCCI linkage, confined to Linux GitHub CI."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

import abi

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
MODULES_PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
PREFIX = "drivers/misc/mediatek/"
UTIL = PREFIX + "ccci_util/"
API_EXPORTS = ("mt6878_md_native_on_validate", "mt6878_md_native_on_latch")
LEGACY_EXPORTS = ("mt6878_ccci_start_alloc", "mt6878_ccci_first_start", "mt6878_ccci_start_result")
MAP_EXPORT = "mtk_ccci_owned_mapped_copy"
MODULES = ("eccci/ccci_md_all", "eccci/ccci_auxadc", "eccci/hif/ccci_ccif",
           "eccci/hif/ccci_dpmaif", "eccci/hif/ccci_cldma", "eccci/fsm/ccci_fsm_scp",
           "ccmni/ccmni", "rps/rps_perf")
STRICT = ("KBUILD_MODPOST_WARN=", "KBUILD_MODPOST_NOFINAL=", "KBUILD_MODPOST_SKIP=")
FORBIDDEN_ENV = ("KBUILD_MODPOST_WARN", "KBUILD_MODPOST_NOFINAL", "KBUILD_MODPOST_SKIP",
                 "KBUILD_EXTRA_SYMBOLS", "KBUILD_KCONFIG", "KCONFIG_CONFIG", "KBUILD_OUTPUT",
                 "MAKEFLAGS", "KCFLAGS", "KCPPFLAGS", "CFLAGS_KERNEL", "CFLAGS_MODULE",
                 "KBUILD_CFLAGS", "KBUILD_LDFLAGS", "LDFLAGS_MODULE", "LDFLAGS_vmlinux",
                 "CC", "LD", "ARCH", "CROSS_COMPILE", "LLVM", "LLVM_IAS", "M", "MO")
BLOCKERS = (
    "Artifacts are not installed or loaded; shipping consumer and rails remain disabled.",
    "Trusted loader final DT, authenticated retained firmware/NC/cache/tag lifetime and matching secure profile must be supplied.",
    "Historical secure SMEM policy is not a fresh NS access grant or exclusion of independent secure/DMA writers.",
    "AP-only util exports do not prove its skipped legacy logging/sysfs/runtime initializers ran; actual CCCI registration still needs runtime validation.",
    "Operational HIF probes/getters, IRQ/DMA/clock lifetime and physical native first-START must be validated; resource-only HIF providers are incompatible.",
    "AFC/UFC calibration needs a real hold owner if requested by firmware; DBG remains excluded and no unowned release is added.",
    "Forced detach, STOP/restart, exception recovery, teardown and suspend remain unsupported; boot-lifetime pins are not safe removal.",
    "Actual BROM/POWER0 returns are not HS1/HS2/READY/SIM/network proof; controlled hardware, clean-install, lifecycle and SKU gates remain open.",
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    start = load("native_link_start_stage", HERE.parent / "native-start/stage.py")
    previous = sys.modules.get("stage")
    sys.modules["stage"] = start
    try:
        candidate = load("native_link_start_ci", HERE.parent / "native-start/ci.py")
    finally:
        if previous is None:
            del sys.modules["stage"]
        else:
            sys.modules["stage"] = previous
    return start, candidate.real_ci(), load("native_link_existing_closure",
        ROOT / "patches/modem/drafts/runtime-link-closure/link_full.py")


def require_ci(real):
    real.require_ci()
    for name in FORBIDDEN_ENV:
        abi.require(not os.environ.get(name), "inherited build override forbidden: " + name)


def verify_manifest():
    expected = json.loads((HERE / "STAGING.json").read_text())["files_sha256"]
    actual = {path.name: abi.sha(path) for path in HERE.iterdir()
              if path.is_file() and path.name != "STAGING.json"}
    abi.require(actual == expected, "native-link manifest closure differs")


def input_path(value):
    original = Path(value).absolute()
    cursor = Path(original.anchor)
    # Inspect components before collapsing '..', including cancelled symlinks.
    for part in original.parts[1:]:
        cursor = cursor / part
        abi.require(not cursor.is_symlink(), "input traverses symlink: " + str(cursor))
    path = Path(os.path.abspath(original))
    abi.require(path.resolve() == path, "input traverses symlink: " + str(original))
    return path


def source_inputs(vendor, pristine):
    vendor, pristine = input_path(vendor), input_path(pristine)
    start, real, closure = helpers()
    start.verify_manifest()
    start.pristine_inputs(pristine)
    bundles = start.build(vendor, pristine)
    for name, (patch, _, _) in bundles.items():
        abi.require((start.HERE / name).read_text() == patch, "frozen native-start source drift: " + name)
    package = load("native_link_metadata_package", ROOT / "patches/modem/drafts/runtime-metadata/package_metadata.py")
    metadata, metadata_after = package.build(vendor)
    abi.require(metadata == (PACKAGE / "ccci-owned-metadata.overlay").read_text(), "shipping AP-only overlay differs")
    consumer = load("native_link_smem_consumer", ROOT / "patches/modem/drafts/runtime-smem-consumer/check_consumer.py")
    providers = consumer.build(vendor)
    for name, (patch, _, _) in providers.items():
        abi.require(patch == (consumer.HERE / name).read_text(), "mapped provider overlay differs: " + name)
    return start, real, closure, bundles, metadata, metadata_after, providers


def apply_checked(real, root, patch, before, after):
    for name, text in before.items():
        abi.require((root / name).read_text() == text, "actual staged source differs: " + name)
    real.apply_source(root, patch.encode(), strict=True, check_only=True)
    real.apply_source(root, patch.encode(), strict=True)
    for name, text in after.items():
        abi.require((root / name).read_text() == text, "actual patched source differs: " + name)


def stage_vendor(vendor_git, destination, inputs):
    start, real, closure, bundles, metadata, metadata_after, providers = inputs
    receipt = {}
    manifest, smoke = closure.stage(vendor_git, destination, receipt)
    abi.require(manifest["vendor_commit"] == VENDOR and manifest["kernel"]["kernel_commit"] == LINUX,
                "not the exact shipping B4.1/d84 closure")
    patch, before, after = bundles["ccci-native-start.patch.vendor"]
    apply_checked(real, destination, patch, before, after)
    # The one util module comes from the genuine packaged AP-only + mapped
    # provider implementations. Never link another legacy util beside it.
    real.apply_source(destination, metadata.encode(), strict=True, check_only=True)
    real.apply_source(destination, metadata.encode(), strict=True)
    for name, text in metadata_after.items():
        abi.require((destination / name).read_text() == text, "AP-only provider source differs: " + name)
    provider_patch, provider_before, provider_after = providers["provider.overlay"]
    apply_checked(real, destination, provider_patch, provider_before, provider_after)
    abi.require((destination / PREFIX / "include/mt-plat/tetris_ccci_smem.h").read_text() ==
                providers["common.overlay"][2][PREFIX + "include/mt-plat/tetris_ccci_smem.h"],
                "provider/consumer private-copy ABI differs")
    receipt["native_start_patch_sha256"] = hashlib.sha256(patch.encode()).hexdigest()
    receipt["provider_patches_sha256"] = {"metadata": hashlib.sha256(metadata.encode()).hexdigest(),
                                         "mapped_copy": hashlib.sha256(provider_patch.encode()).hexdigest()}
    receipt["source_sha256"] = {str(path.relative_to(destination)): abi.sha(path)
        for path in sorted(destination.rglob("*")) if path.is_file() and
        (path.suffix in (".c", ".h") or path.name in ("Makefile", "Kbuild", "Kconfig"))}
    return manifest, smoke, receipt


def native_composition(text):
    parts = [Path(value).as_posix() for value in text.split()]
    abi.require(any(value.endswith("/fsm/ccci_tetris_native_start.o") for value in parts),
                "actual core composite omitted native first-START object")
    for suffix in ("/fsm/ccci_tetris_owner.o", "/hif/ccci_tetris_hif_owned.o"):
        abi.require(not any(value.endswith(suffix) for value in parts), "legacy OFF composition leaked into native core")
    return parts


def require_exports(table, names, owner):
    for name in names:
        abi.require(name in table and abi.owner_name(table[name]["owner"]) == owner and
                    table[name]["export"] == "EXPORT_SYMBOL_GPL", "actual GPL export missing/wrong owner: " + name)


def source_check(vendor, pristine):
    vendor, pristine = input_path(vendor), input_path(pristine)
    inputs = source_inputs(vendor, pristine)
    start, _, _, bundles, _, _, _ = inputs
    for patch, before, after in bundles.values():
        start.apply_check(patch, before, after)
    with tempfile.TemporaryDirectory(prefix="tetris-native-link-source-") as directory:
        _, _, receipt = stage_vendor(vendor, Path(directory) / "vendor", inputs)
    return {"validation": "source/strict patch application only; no compiler, ELF or target execution",
            "vendor_commit": VENDOR, "linux_commit": LINUX,
            "source_count": len(receipt["source_sha256"]),
            "native_start_patch_sha256": receipt["native_start_patch_sha256"],
            "provider_patches_sha256": receipt["provider_patches_sha256"]}


def recorded_inputs(args, start):
    smoke = load("native_link_smoke_plan", ROOT / "ci/kernel-object-smoke.py")
    package = smoke.plan(PACKAGE)
    abi.require(package["kernel_commit"] == LINUX, "shipping Linux pin changed")
    normal = json.loads(args.normal_report.read_text())
    abi.require(normal.get("status") == "passed" and "research_source_sha256" not in normal and
                normal.get("kernel_commit") == LINUX and normal.get("archive_sha512") == package["archive_sha512"] and
                normal.get("source_sha512") == package["source_sha512"], "requires successful ordinary packaged smoke inputs")
    native = json.loads(args.native_report.read_text())
    abi.require(native.get("status") == "passed" and native.get("pristine_linux") == LINUX,
                "requires successful actual native-start compiler report")
    variant = native["variants"]["native-start"]
    cfg = args.native_output / ".config"
    abi.require(abi.sha(cfg) == variant["config_sha256"], "native-start configured output changed")
    obj = args.native_output / "drivers/pmdomain/mediatek/mtk-pm-domains.o"
    abi.require(abi.sha(obj) == variant["objects"]["native_supplier"]["sha256"], "native supplier object differs from compile report")
    shipping = abi.config((PACKAGE / smoke.CONFIG).read_text())
    candidate = abi.config(cfg.read_text())
    security = abi.security_profile(shipping, candidate)
    for name in ("ARM64", "MODULES", "PM", "PM_SLEEP", "REGULATOR", "MTK_SCPSYS_PM_DOMAINS",
                 "MTK_MT6878_NATIVE_VMM", "MTK_MT6878_MODEM_REAL_BOOT_STAGING",
                 "MTK_MT6878_MODEM_NATIVE_START_STAGING"):
        abi.require(candidate.get(name) == "y", "actual native kernel dependency missing: " + name)
    for name in ("SCSI_UFS_MEDIATEK_DBG", "OF_DYNAMIC", "OF_OVERLAY", "OF_UNITTEST", "CPU_IDLE",
                 "KEXEC", "KEXEC_FILE", "KEXEC_CORE"):
        abi.require(candidate.get(name, "n") == "n", "unsafe native kernel profile: " + name)
    with args.kernel_archive.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha512").hexdigest()
    abi.require(actual == package["archive_sha512"], "not the genuine pinned shipping kernel archive")
    return package, native, cfg, candidate, security


def reconstruct_kernel(args, destination, inputs, package, step):
    start, real, _, bundles, _, _, _ = inputs
    source = destination / "source"
    source.mkdir()
    with tarfile.open(args.kernel_archive) as archive:
        archive.extractall(source, filter="data")
    kernel = source / ("linux-" + LINUX)
    pristine = source / "pristine"
    for name in start.pristine_inputs(args.pristine_kernel):
        path = pristine / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(kernel / name, path)
    abi.require(start.pristine_inputs(pristine) == start.pristine_inputs(args.pristine_kernel),
                "three-file pristine input differs from archive reconstruction")
    smoke = load("native_link_shipping_patch_rules", ROOT / "ci/kernel-object-smoke.py")
    for name in package["patches"]:
        flags = ["--fuzz=0"] if name in smoke.STRICT_PATCHES else []
        step("kernel-source-patches", ["patch", "--batch", *flags, "-p1", "-d", kernel, "-i", PACKAGE / name])
    real_receipt = real.prepare(kernel, "packaged", True)
    patch, before, after = bundles["native-on-api.patch"]
    apply_checked(real, kernel, patch, before, after)
    for name, text in after.items():
        abi.require((args.prepared_kernel / name).read_text() == text,
                    "provided native-start tree differs from reconstructed source: " + name)
    return kernel, real_receipt


def build(args):
    start, real, _ = helpers()
    require_ci(real)
    abi.require(args.enable_native_link, "full native linking requires explicit --enable-native-link")
    verify_manifest()
    start.verify_manifest()
    destination = real.isolated(args.destination)
    abi.require(not destination.exists(), "native-link destination must be fresh")
    abi.require(ROOT.resolve() not in destination.parents,
                "native-link needs an external disposable directory, not a checkout descendant")
    for name in ("prepared_kernel", "pristine_kernel", "native_output", "kernel_archive",
                 "vendor", "normal_report", "native_report"):
        path = input_path(getattr(args, name))
        setattr(args, name, path)
        abi.require(path != destination and destination not in path.parents and
                    path not in destination.parents, "input aliases or overlaps native-link destination")
    destination.mkdir(parents=True, exist_ok=False)
    report = {"status": "started", "phase": "input-admission", "source_commit": os.environ.get("GITHUB_SHA"),
              "scope": "actual full native kernel + mapped provider + eight vendor modules; no install/boot",
              "hardware_status": "untested", "hardware_blockers": list(BLOCKERS),
              "pins": {"linux": LINUX, "vendor": VENDOR, "companion_modules": MODULES_PIN}}
    target = destination / "BUILD-MANIFEST.json"
    def save():
        target.write_text(json.dumps(report, indent=2) + "\n")
    def step(phase, command):
        report.update(phase=phase, command=list(map(str, command)))
        save()
        with (destination / (phase + ".log")).open("ab") as log:
            subprocess.run(list(map(str, command)), check=True, stdout=log, stderr=subprocess.STDOUT)
    save()
    try:
        # Fail before an expensive full build when the real prior compiler gate failed.
        package, native, inherited, cfg, security = recorded_inputs(args, start)
        report.update(security_profile=security, crc_status="enforced_by_inherited_config" if
                      cfg.get("MODVERSIONS") == "y" else "disabled_by_inherited_config",
                      input_report_sha256={"ordinary_smoke": abi.sha(args.normal_report),
                                           "native_start": abi.sha(args.native_report)},
                      shipping_source=package, inherited_config_sha256=abi.sha(inherited))
        report["compiler"] = subprocess.check_output(["clang", "--version"], text=True).strip()
        abi.require(re.search(r"clang version 21\.", report["compiler"]), "package-matching LLVM 21 required")
        # Load the existing structured ELF reader before invoking any compiler.
        from elftools.elf.elffile import ELFFile
        report["elf_reader"] = ELFFile.__module__
        inputs = source_inputs(args.vendor, args.pristine_kernel)
        report["phase"] = "source-reconstruction"
        save()
        kernel, receipt = reconstruct_kernel(args, destination, inputs, package, step)
        report["real_on_recipe"] = receipt
        report["native_patches_sha256"] = {name: hashlib.sha256(value[0].encode()).hexdigest()
                                           for name, value in inputs[3].items()}
        abi.require(report["native_patches_sha256"] == native["patches_sha256"], "native compiler/source recipe mismatch")
        configured = destination / "kernel-output"
        configured.mkdir()
        shutil.copyfile(inherited, configured / ".config")
        make = ["make", "-j2", "-C", kernel, "O=" + str(configured), "ARCH=arm64", "LLVM=1", *STRICT]
        step("kernel-config", [*make, "olddefconfig"])
        abi.require((configured / ".config").read_bytes() == inherited.read_bytes(), "full build changed inherited native config")
        abi.security_profile(abi.config((PACKAGE / "config-postmarketos-mediatek-mt6878.aarch64").read_text()),
                             abi.config((configured / ".config").read_text()))
        # A real full build is required: modules_prepare cannot produce exports.
        step("kernel-full-link", [*make, "vmlinux", "modules"])
        kernel_table = abi.symvers((configured / "Module.symvers").read_text())
        vmlinux = abi.elf(configured / "vmlinux", module=False)
        require_exports(kernel_table, API_EXPORTS, "vmlinux")
        abi.require(set(API_EXPORTS) <= vmlinux["definitions"], "native APIs missing from actual linked vmlinux")
        report["native_kernel"] = {"vmlinux_sha256": vmlinux["sha256"],
            "config_sha256": abi.sha(configured / ".config"), "symvers_sha256": abi.sha(configured / "Module.symvers"),
            "release": (configured / "include/config/kernel.release").read_text().strip(),
            "native_api_exports": {name: kernel_table[name] for name in API_EXPORTS}}
        step("disabled-dtb", [*make, "mediatek/" + Path(real.DTB).name])
        dt = real.module("native_link_compiled_dt", "ci/check-native-modem-image-dt.py").hif
        report["disabled_consumers"] = real.disabled_consumer_rails(dt.read_tree(configured / real.DTB))
        report["dtb_sha256"] = abi.sha(configured / real.DTB)
        vendor = destination / "vendor"
        report["phase"] = "vendor-source-staging"
        save()
        manifest, _, vendor_receipt = stage_vendor(args.vendor, vendor, inputs)
        for path, digest in native["compiled_vendor_sources"].items():
            abi.require(abi.sha(vendor / path) == digest, "vendor source changed after native compiler gate: " + path)
        report["vendor_source"] = vendor_receipt
        util = vendor / UTIL
        common = ["KERNEL_SRC=" + str(kernel), "KERNEL_OUT=" + str(configured),
                  "DEVICE_MODULES_PATH=" + str(vendor), "CONFIG_ARM64=y", "CONFIG_MTK_ECCCI_DRIVER=m",
                  "CONFIG_MTK_SECURITY_SW_SUPPORT=n", "CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n",
                  "CONFIG_MTK_AEE_IPANIC=n"]
        flags = manifest["vendor_kcflags"] + " -I" + str(vendor / "include")
        flags += " -Werror=implicit-function-declaration -Werror=incompatible-pointer-types -Werror=int-conversion"
        provider_flags = flags + " -I" + str(vendor / PREFIX / "include")
        provider_flags += " -DCONFIG_MTK_ECCCI_TETRIS_METADATA_ONLY=1 -DCONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY=1"
        provider_flags += " -DCONFIG_TETRIS_CCCI_SMEM_MAP_ONLY=1 -DCONFIG_TETRIS_CCCI_SMEM_PROVIDER=1"
        step("mapped-provider-link", [*make, "M=" + str(util), *common, "KBUILD_EXTRA_SYMBOLS=",
                                      "KCFLAGS=" + provider_flags, "ccci_util_lib.ko"])
        provider_table = abi.symvers((util / "Module.symvers").read_text())
        require_exports(provider_table, (MAP_EXPORT,), "ccci_util_lib")
        modules = destination / "modules"
        modules.mkdir()
        shutil.copyfile(HERE / "Kbuild", modules / "Kbuild")
        for name in ("eccci", "ccmni", "rps"):
            shutil.copytree(vendor / PREFIX / name, modules / name)
        native_flags = flags + " -DCONFIG_MTK_ECCCI_TETRIS_OWNER=1 -DCONFIG_MTK_ECCCI_TETRIS_NATIVE_START=1"
        native_flags += " -DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=1"
        step("native-composites-link", [*make, "M=" + str(modules), *common,
            "CONFIG_MTK_ECCCI_TETRIS_OWNER=y", "CONFIG_MTK_ECCCI_TETRIS_NATIVE_START=y",
            "CONFIG_MTK_NET_CCMNI=m", "CONFIG_MTK_NET_RPS=m", "CONFIG_DEVICE_MODULES_MEDIATEK_MT6577_AUXADC=m",
            "KBUILD_EXTRA_SYMBOLS=" + str(util / "Module.symvers"), "KCFLAGS=" + native_flags, "modules"])
        report["vendor_kcflags"] = {"provider": provider_flags, "native_composites": native_flags}
        report["core_composition"] = native_composition((modules / "eccci/ccci_md_all.mod").read_text())
        table = abi.symvers((modules / "Module.symvers").read_text())
        require_exports(table, ("ccci_tetris_native_first_start", "ccci_tetris_register_prepared",
                               "ccci_tetris_hif_claim", "ccci_tetris_hif_register"), "ccci_md_all")
        exports = abi.export_index({"kernel": kernel_table, "mapped_provider": provider_table, "native_vendor": table})
        report["phase"] = "actual-ELF-export-closure"
        save()
        paths = {name: modules / (name + ".ko") for name in MODULES}
        paths["provider/ccci_util_lib"] = util / "ccci_util_lib.ko"
        inspect_artifacts(paths, exports, cfg, configured, vmlinux, report)
        abi.require(abi.sha(configured / ".config") == report["inherited_config_sha256"], "native config changed during linkage")
        for path, digest in vendor_receipt["source_sha256"].items():
            abi.require(abi.sha(vendor / path) == digest, "source mutated during module build: " + path)
        report["export_tables_sha256"] = {"kernel": abi.sha(configured / "Module.symvers"),
            "mapped_provider": abi.sha(util / "Module.symvers"), "native_vendor": abi.sha(modules / "Module.symvers")}
        artifacts = destination / "artifacts"
        artifacts.mkdir()
        for name, path in paths.items():
            saved = artifacts / (name + ".ko")
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, saved)
        for label, path in (("kernel", configured / "Module.symvers"),
                            ("mapped-provider", util / "Module.symvers"), ("native-vendor", modules / "Module.symvers")):
            shutil.copyfile(path, artifacts / (label + ".Module.symvers"))
        shutil.copyfile(configured / "drivers/pmdomain/mediatek/mtk-pm-domains.o",
                        artifacts / "native-supplier.o")
        for owner, record in report["kernel_module_dependencies"].items():
            saved = artifacts / "kernel-dependencies" / (owner + ".ko")
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(record["path"], saved)
        report.update(status="passed", phase="actual-link-export-closure-complete")
        report["artifact_selection"] = {"include": ["artifacts/**/*.ko", "artifacts/*.Module.symvers",
            "artifacts/native-supplier.o", "BUILD-MANIFEST.json", "*.log"],
            "exclude": ["source/**", "vendor/**", "modules/**", "kernel-output/**", "vmlinux"]}
        save()
    except Exception as error:
        report.update(status="failed", error=str(error))
        log = destination / (report["phase"] + ".log")
        if log.exists():
            report["first_build_diagnostics"] = [line for line in log.read_text(errors="replace").splitlines()
                                                 if re.search(r"ERROR:|error:|undefined!|no CRC!", line)][:100]
        save()
        raise
    return report


def inspect_artifacts(paths, exports, cfg, configured, vmlinux, report):
    images = {name: abi.elf(path, cfg) for name, path in paths.items()}
    core = images["eccci/ccci_md_all"]
    abi.require(set((*API_EXPORTS, MAP_EXPORT)) <= core["imports"].keys(), "core did not retain real native/provider imports")
    for image in images.values():
        abi.require(not (set(LEGACY_EXPORTS) & image["imports"].keys()), "obsolete virtual-OFF backend dependency remains")
    abi.require("ccci_tetris_native_first_start" in core["definitions"] and
                "ccci_tetris_owner_start" in core["definitions"], "actual native start implementation missing")
    provider = images["provider/ccci_util_lib"]
    abi.require(MAP_EXPORT in provider["definitions"], "actual mapped-copy implementation missing")
    release = report["native_kernel"]["release"]
    vermagic = provider["metadata"]["vermagic"][0]
    abi.require(vermagic.startswith(release + " "), "module/kernel release mismatch")
    owners = {"vmlinux": vmlinux}
    for name, image in images.items():
        actual_name = image["metadata"]["name"][0]
        abi.require(actual_name == Path(name).name.replace("-", "_"), "module identity mismatch: " + name)
        abi.require(actual_name not in owners, "duplicate actual module identity")
        owners[actual_name] = image
        abi.require(image["metadata"]["vermagic"] == [vermagic], "module vermagic mismatch: " + name)
    # Kernel Module.symvers can also name real kernel-built modules. Verify the
    # provider ELF for every used export instead of treating a table row as code.
    report["modules"], report["kernel_module_dependencies"] = {}, {}
    for name, image in images.items():
        result = abi.closure(image, exports, cfg)
        for symbol, row in result["imports"].items():
            owner = abi.owner_name(row["owner"])
            if owner not in owners:
                abi.require(row["table"] == "kernel" and not Path(row["owner"]).is_absolute() and
                            ".." not in Path(row["owner"]).parts, "unexpected export provider path")
                path = configured / (row["owner"] + ".ko")
                actual = abi.elf(path, cfg)
                abi.require(actual["metadata"]["name"] == [owner] and actual["metadata"]["vermagic"] == [vermagic],
                            "kernel module dependency identity/ABI mismatch")
                owners[owner] = actual
                report["kernel_module_dependencies"][owner] = {"path": str(path), "sha256": actual["sha256"]}
            abi.require(symbol in owners[owner]["definitions"] and
                        "__ksymtab_" + symbol in owners[owner]["definitions"],
                        "export table has no actual linked provider definition: " + symbol)
        report["modules"][name] = {**result, "sha256": image["sha256"], "vermagic": vermagic,
                                   "machine": image["machine"], "elf_type": image["elf_type"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-check", action="store_true")
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--pristine-kernel", type=Path, required=True)
    parser.add_argument("--prepared-kernel", type=Path)
    parser.add_argument("--kernel-archive", type=Path)
    parser.add_argument("--normal-report", type=Path)
    parser.add_argument("--native-report", type=Path)
    parser.add_argument("--native-output", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--enable-native-link", action="store_true")
    args = parser.parse_args()
    if args.source_check:
        verify_manifest()
        print(json.dumps(source_check(args.vendor, args.pristine_kernel), indent=2))
    else:
        for name in ("prepared_kernel", "kernel_archive", "normal_report", "native_report", "native_output", "destination"):
            if getattr(args, name) is None:
                parser.error("--" + name.replace("_", "-") + " is required for full linkage")
        build(args)


if __name__ == "__main__":
    main()
