#!/usr/bin/env python3
"""Exact NOS objects and checksum-pinned Linux evidence; no target execution."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
UPSTREAM = REPO.parent
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
MODULES = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
ATF_CONTRACT = "634789437e3f80a0129f00e5cff922bd8cdbb64b"
ATF_SHA = "05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e"
LINUX_ARCHIVE_SHA512 = (
    "5d809b44f94336549285a559909bfe5d8b2dcc3f213af58c25a52d535cd2cd0345ce"
    "34f44e1d155940cf0d4089fd2ad49fa0d6829fd2b965095084cd1500003c")
spec = importlib.util.spec_from_file_location("real_boot_source_helpers", HERE.parent / "audit.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def object_data(root, revision, path):
    return subprocess.check_output(["git", "-C", str(root), "show", revision + ":" + path])


def grep(root, revision, pattern):
    result = subprocess.run(["git", "-C", str(root), "grep", "-n", "-E", pattern, revision],
                            capture_output=True, text=True)
    require(result.returncode in (0, 1), "git object census failed: " + result.stderr)
    return result.stdout.splitlines()


def linux_sources(linux, archive):
    digest = hashlib.sha512()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    require(digest.hexdigest() == LINUX_ARCHIVE_SHA512, "Linux archive differs from APKBUILD d84 checksum")
    paths = {
        "drivers/pmdomain/mediatek/Kconfig", "drivers/pmdomain/mediatek/mtk-pm-domains.c",
        "include/linux/soc/mediatek/mtk_sip_svc.h", "drivers/mfd/syscon.c",
        "drivers/base/regmap/regmap.c", "include/linux/regmap.h", "drivers/ufs/host/ufs-mediatek.c",
        "drivers/regulator/core.c", "drivers/regulator/of_regulator.c",
        "include/linux/regulator/consumer.h", "drivers/pmdomain/core.c", "drivers/base/platform.c",
    }
    sources = {}
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            path = member.name.partition("/")[2]
            if path not in paths:
                continue
            require(member.isfile() and path not in sources, "duplicate/non-file Linux archive input")
            data = tar.extractfile(member).read()
            require(data == (linux / path).read_bytes(), "Linux checkout differs from pinned archive: " + path)
            sources[path] = data
    require(sources.keys() == paths, "missing pinned Linux archive files")
    return sources


def evidence(vendor=None, modules=None, linux=None, archive=None):
    vendor = vendor or UPSTREAM / "android_kernel_device_modules_6.1_nothing_mt6878"
    modules = modules or UPSTREAM / "android_kernel_modules_nothing_mt6878"
    linux = linux or UPSTREAM / ("linux-" + LINUX)
    archive = archive or UPSTREAM / ("linux-" + LINUX + ".tar.gz")
    sources, edges = {}, []
    # Read committed disassembly conclusions and fixture SOURCE only. Never
    # import the Unicorn fixtures, execute their instructions or access hardware.
    atf_sources = {}
    for name in ("TRANSPORT_OWNER.md", "test-atf-flight-contract.py", "test-atf-power-contract.py"):
        path = "patches/modem/" + name
        data = object_data(REPO, ATF_CONTRACT, path)
        sources["tracked-atf:" + name] = {"path": path, "revision": ATF_CONTRACT,
                                        "sha256": hashlib.sha256(data).hexdigest()}
        atf_sources[name] = data.decode()
    require(ATF_SHA in atf_sources["TRANSPORT_OWNER.md"] and
            'SHA = "' + ATF_SHA + '"' in atf_sources["test-atf-power-contract.py"],
            "tracked ATF payload identity changed")
    for needle in ("0xbf2c", "0xbfa0", "0x1bf58", "0x1efc0", "0x33d3c", "0x33aec", "0x33c5c",
                   "0x5a9fa", "0xf73b4", "Only a0 is defined", "zero-extends w0"):
        require(needle in atf_sources["TRANSPORT_OWNER.md"], "missing tracked ATF contract: " + needle)
    require("status & 0xffffffff" in atf_sources["test-atf-flight-contract.py"] and
            "No defined a1/a2/a3 payload" in atf_sources["test-atf-flight-contract.py"],
            "tracked FLIGHT fixture contract changed")

    def read(label, path):
        data = object_data(vendor, VENDOR, path)
        sources[label] = {"path": path, "revision": VENDOR,
                          "sha256": hashlib.sha256(data).hexdigest()}
        return data.decode()

    def anchor(label, source, needle, meaning):
        require(source.count(needle) == 1, "missing/ambiguous source anchor: " + label)
        edges.append({"source": label, "line": source[:source.index(needle)].count("\n") + 1,
                      "anchor": needle, "meaning": meaning})

    md = read("md-platform", "drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c")
    secure = read("md-request-ids", "drivers/misc/mediatek/eccci/inc/modem_secure_base.h")
    sip = read("sip-ids", "include/linux/soc/mediatek/mtk_sip_svc.h")
    fsm = read("ufs-wrapper", "drivers/misc/mediatek/eccci/fsm/ccci_fsm.c")
    rpc = read("ufs-rpc-caller", "drivers/misc/mediatek/eccci/port/port_rpc.c")
    ufs = read("ufs-provider", "drivers/ufs/ufs-mediatek-dbg.c")
    ufs_make = read("ufs-selection", "drivers/ufs/Makefile")
    start = read("md-start-caller", "drivers/misc/mediatek/eccci/fsm/modem_sys1.c")
    domain = read("md-domain", "drivers/soc/mediatek/mtk-scpsys-mt6878.c")
    pm = read("md-native-sequence", "drivers/soc/mediatek/mtk-scpsys.c")
    dts = read("md-dts", "arch/arm64/boot/dts/mediatek/mt6878.dts")
    native.ordered(native.function(md, "md_cd_power_off"), "pm_runtime_put_sync",
                   "ccci_ufs_io_operate(0)", "mdelay(4)", "flight_mode_set_by_atf(md, true)",
                   "md_cd_topclkgen_off(md)")
    flight = native.function(md, "flight_mode_set_by_atf")
    native.ordered(flight, "MD_FLIGHT_MODE_SET", "flightMode, 0, 0, 0, 0, 0, &res",
                   "res.a0, res.a1, res.a2, res.a3")
    require(not re.search(r"\breturn\b|\bif\s*\(", flight), "FLIGHT void/log-only contract changed")
    native.ordered(native.function(fsm, "ccci_ufs_io_operate"), "int val = -1;",
                   "CONFIG_SCSI_UFS_MEDIATEK_DBG", "op_id == 1 && md_io_block_status == 0",
                   "ufs_mtk_cali_hold()", "if(val == 0)", "md_io_block_status = 1;",
                   "op_id == 0 && md_io_block_status == 1", "ufs_mtk_cali_release()",
                   "if(val == 0)", "md_io_block_status = 0;")
    native.ordered(native.function(ufs, "ufs_mtk_cali_hold"), "pm_runtime_get_sync",
                   "ufs_mtk_scsi_block_requests", "ufs_mtk_wait_for_doorbell_clr", "ret = -EBUSY",
                   "mdelay(15)", "return ret;")
    native.ordered(native.function(ufs, "ufs_mtk_cali_release"), "ufs_mtk_scsi_unblock_requests",
                   "pm_runtime_put", "return 0;")
    native.ordered(native.function(start, "md_cd_start"), "start_platform(md)",
                   "power_on(md)", "if (ret)", "goto out;", "let_md_go(md)")
    native.ordered(native.function(md, "md_cd_power_on"), "md1_pmic_setting_on()",
                   "md_cd_topclkgen_on(md)", "flight_mode_set_by_atf(md, false)",
                   "pm_runtime_get_sync", "md_pll_setting(md)")
    native.ordered(native.function(pm, "scpsys_md_power_on"), "scpsys_regulator_enable(scpd)",
                   "scpsys_extb_iso_down(scpd)", "scpsys_clk_enable", "MTK_SCPD_REMOVE_MD_RSTB",
                   "val |= PWR_ON_BIT", "scpsys_pwr_ack_is_on",
                   "scpsys_bus_protect_disable(scpd, MAX_STEPS - 1)")
    native.ordered(native.function(md, "md1_pmic_setting_on"), "ARRAY_SIZE(md_reg_table)",
                   "regulator_set_voltage", "regulator_sync_voltage", "regulator_get_voltage")
    native.ordered(native.function(md, "md_cd_let_md_go"), "MD_POWER_CONFIG",
                   "MD_KERNEL_BOOT_UP", "res.a0, res.a1, res.a2, res.a3", "return 0;")

    for label, source, needle, meaning in (
        ("md-platform", md, "static void flight_mode_set_by_atf(struct ccci_modem *md,",
         "vendor void API logs four flags, but matched tracked ATF contract defines only zero-extended a0"),
        ("md-platform", md, "ccci_ufs_io_operate(0);", "release only after physical OFF; vendor ignores return"),
        ("md-platform", md, "mdelay(4);", "gen6299 settle precedes FLIGHT and TOP"),
        ("md-platform", md, "reg_value |= ((1<<8) | (1<<9));", "TOP gate sets bits8/9 at offset0"),
        ("md-platform", md, "static int md_cd_power_on(struct ccci_modem *md)",
         "real ON chain requires PMIC settings, TOP ungate, FLIGHT(false), runtime domain and later execution release"),
        ("md-platform", md, "static void md1_pmic_setting_on(void)",
         "void rail setter logs/continues errors; it is not a native owned rail operation"),
        ("md-platform", md, "MD_KERNEL_BOOT_UP, 0, 0, 0, 0, 0, &res);",
         "POWER/0 execution release has no checked secure result in this caller"),
        ("md-request-ids", secure, "\tMD_FLIGHT_MODE_SET,", "enumerated request7 after POWER6; not POWER/5"),
        ("sip-ids", sip, "#define MTK_SIP_KERNEL_CCCI_CONTROL \\\n\tMTK_SIP_SMC_CMD(0x505)", "ARM64 SiP fast SMC 0xc2000505"),
        ("ufs-wrapper", fsm, "int ccci_ufs_io_operate(int op_id)",
         "actual serialized CCCI hold owner; no-op/disabled returns -1 rather than proof of successful release"),
        ("ufs-rpc-caller", rpc, "tmp_data[1] = ccci_ufs_io_operate(op_id);",
         "only dynamic acquisition caller is runtime modem RPC AFC/UFC operation"),
        ("ufs-provider", ufs, "int ufs_mtk_cali_hold(void)",
         "hold blocks storage and takes runtime reference even when doorbell timeout is returned; vendor wrapper loses ownership on that failure"),
        ("ufs-provider", ufs, "int ufs_mtk_cali_release(void)",
         "release drops the real storage PM reference; never call without its acquisition owner"),
        ("md-domain", domain, "MTK_SCPD_BYPASS_INIT_ON | MTK_SCPD_REMOVE_MD_RSTB,",
         "no reset/inhibit owner inferred for genuine boot"),
        ("md-native-sequence", pm, "static int scpsys_md_power_on(struct generic_pm_domain *genpd)",
         "physical ON: isolation down, power bit2, control ACK30, reverse bus release; MD skips reset"),
        ("md-dts", dts, "md-vmodem = <800000 800000>;", "source rail: VBUCK2, 800000uV"),
        ("md-dts", dts, "md-vsram = <800000 800000>;", "source rail: VSRAM_MODEM, 800000uV"),
        ("md-dts", dts, "md-vdigrf = <700000 700000>;", "source rail: VBUCK1, 700000uV"),
        ("md-platform", md, "md_cd_plat_val_ptr.power_flow_config = 0;",
         "absent flow selector means zero; no SRC/O1/PLL/sequencer operation for this profile"),
        ("md-dts", dts, "ccci-topckgen = <&topckgen_clk>;", "actual shared TOP phandle"),
    ):
        anchor(label, source, needle, meaning)
    require("CONFIG_SCSI_UFS_MEDIATEK_DBG" in ufs_make and "ufs-mediatek-dbg.o" in ufs_make,
            "UFS provider Kbuild selection changed")
    ufs_census = grep(vendor, VENDOR, r"ufs_mtk_cali_(hold|release)|ccci_ufs_io_operate")
    require(sum("val = ufs_mtk_cali_hold();" in line for line in ufs_census) == 1,
            "UFS hold caller census changed")
    require(sum("= ccci_ufs_io_operate(op_id);" in line for line in ufs_census) == 1,
            "RPC acquisition caller census changed")
    module_census = grep(modules, MODULES,
        r"MD_FLIGHT_MODE_SET|MTK_SIP_KERNEL_CCCI_CONTROL|ufs_mtk_cali_(hold|release)|ccci_ufs_io_operate")
    require(not module_census, "e96 source has additional secure/UFS owners; re-review")
    module_tree = subprocess.check_output(["git", "-C", str(modules), "rev-parse",
                                          MODULES + "^{tree}"], text=True).strip()
    linux_data = linux_sources(linux, archive)
    core = linux_data["drivers/pmdomain/core.c"].decode()
    native.ordered(native.function(core, "__genpd_dev_pm_attach"), "genpd_add_device(pd, dev, base_dev)",
                   "genpd_lock(pd)", "genpd_power_on(pd, 0)", "genpd_unlock(pd)")
    native.ordered(native.function(core, "genpd_add_device"), "genpd->attach_dev(genpd, dev)",
                   "genpd_lock(genpd)")
    platform = linux_data["drivers/base/platform.c"].decode()
    native.ordered(native.function(platform, "platform_probe"), "dev_pm_domain_attach(", "drv->probe(dev)")
    regulator_of = linux_data["drivers/regulator/of_regulator.c"].decode()
    native.ordered(native.function(regulator_of, "of_regulator_get_optional"),
                   "_of_regulator_get(dev, node, id, OPTIONAL_GET)")
    for path, data in linux_data.items():
        sources["linux:" + path] = {"path": path, "revision": LINUX,
                                    "sha256": hashlib.sha256(data).hexdigest()}
        if path == "drivers/ufs/host/ufs-mediatek.c":
            require(b"ufs_mtk_cali_hold" not in data and b"ufs_mtk_cali_release" not in data,
                    "native Linux now supplies a calibration owner; re-review")
    return {"schema": 1, "pins": {"vendor": VENDOR, "modules": MODULES, "linux": LINUX,
                                  "atf_payload_sha256": ATF_SHA},
            "linux_provenance": {"method": "APKBUILD SHA512-verified d84 archive; selected files byte-compared",
                                 "archive_sha512": LINUX_ARCHIVE_SHA512},
            "sources": sources, "causal_edges": edges, "ufs_callsite_census": ufs_census,
            "modules_census": {"tree": module_tree, "matches": module_census},
            "flight_contract": "matched ATF kernel wrapper zero-extends inner w0; only a0 defined; nonzero fails, zero is not policy/readiness proof",
            "atf_contract": {"provenance": "committed disassembly conclusions and fixture source; no fresh binary decode or Unicorn execution",
                "repo_revision": ATF_CONTRACT, "payload_base": "0x48800000",
                "dispatch": ["0xbf2c", "0xbfa0"], "wrapper": "0x1bf58", "registry_dispatch": "0x1efc0",
                "callbacks": ["0x33d3c", "0x33aec", "0x33c5c"],
                "secure_policy_halfword": "0x5a9fa", "policy_mask": "0x40", "actual_spinlock": "0xf73b4",
                "missing_registry_a0": "0x00000000ffffffff", "null_callback": "terminates successfully without policy guarantee",
                "outer_admission": "separate; not inferred from inner result or physical ON"},
            "ufs_scope": "DBG=n excludes acquisition API and RPC calibration operation; skip release, never fabricate held state",
            "native_on": "real attach-time genpd callback: acquired rail handles/voltage/sync, TOP ungate, checked defined FLIGHT a0, ISO down, PWR_ON/ACK30, reverse bus release, current ON readback",
            "status": "uninstalled real native ON integration; no secure/firmware/transport/lifecycle success claimed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path)
    parser.add_argument("--modules", type=Path)
    parser.add_argument("--linux", type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    actual = evidence(args.vendor, args.modules, args.linux, args.archive)
    if args.emit:
        print(json.dumps(actual, indent=2))
    else:
        require(actual == json.loads((HERE / "SOURCE-EVIDENCE.json").read_text()), "source evidence differs")
        print("exact NOS objects, UFS caller census and checksum-pinned Linux: PASS")


if __name__ == "__main__":
    main()
