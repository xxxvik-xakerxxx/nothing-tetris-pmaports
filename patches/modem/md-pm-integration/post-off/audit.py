#!/usr/bin/env python3
"""Exact-object post-OFF source audit; no kernel code or hardware execution."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT.parents[4]
VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
spec = importlib.util.spec_from_file_location("native_md_audit", ROOT.parent / "audit.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)


def evidence(vendor=None, linux=None):
    vendor = vendor or UPSTREAM / "android_kernel_device_modules_6.1_nothing_mt6878"
    linux = linux or UPSTREAM / ("linux-" + LINUX)
    sources, edges = {}, []
    restart = json.loads((ROOT.parent / "RESTART-SOURCE-EVIDENCE.json").read_text())
    if restart["pins"] != {"vendor": VENDOR, "linux": LINUX}:
        raise ValueError("restart source pins changed")

    def read(label, path, revision=VENDOR):
        if revision:
            data = subprocess.run(
                ["git", "-C", str(vendor), "show", revision + ":" + path],
                check=True, capture_output=True,
            ).stdout
        else:
            data = (linux / path).read_bytes()
        sources[label] = {"path": path, "revision": revision,
                          "sha256": hashlib.sha256(data).hexdigest()}
        if label in restart["sources"] and sources[label] != restart["sources"][label]:
            raise ValueError("source differs from restart evidence: " + label)
        return data.decode("utf-8")

    def anchor(label, text, needle, meaning):
        if text.count(needle) != 1:
            raise ValueError("missing/ambiguous source anchor: " + label + ": " + needle)
        edges.append({"source": label, "line": text[:text.index(needle)].count("\n") + 1,
                      "anchor": needle, "meaning": meaning})

    md = read("vendor-md", "drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c")
    dts = read("vendor-dts", "arch/arm64/boot/dts/mediatek/mt6878.dts")
    fsm = read("vendor-ufs-wrapper", "drivers/misc/mediatek/eccci/fsm/ccci_fsm.c")
    ufs = read("vendor-ufs-release", "drivers/ufs/ufs-mediatek-dbg.c")
    domain = read("vendor-domain", "drivers/soc/mediatek/mtk-scpsys-mt6878.c")
    syscon = read("linux-syscon", "drivers/mfd/syscon.c", None)
    regmap = read("linux-regmap", "drivers/base/regmap/regmap.c", None)
    regmap_h = read("linux-regmap-api", "include/linux/regmap.h", None)
    off = native.function(md, "md_cd_topclkgen_off")
    native.ordered(off, "regmap_read(", "reg_value |= ((1<<8) | (1<<9));",
                   "regmap_write(", "regmap_read(", "return 0;")
    native.ordered(native.function(md, "md_cd_power_off"), "pm_runtime_put_sync",
                   "ccci_ufs_io_operate(0)", "mdelay(4)",
                   "flight_mode_set_by_atf(md, true)", "md_cd_topclkgen_off(md)")
    native.ordered(native.function(fsm, "ccci_ufs_io_operate"), "int val = -1;",
                   "CONFIG_SCSI_UFS_MEDIATEK_DBG", "op_id == 0 && md_io_block_status == 1",
                   "val = ufs_mtk_cali_release();", "if(val == 0)", "md_io_block_status = 0;")
    native.ordered(native.function(ufs, "ufs_mtk_cali_release"), "if (!hba)",
                   "return -EINVAL;", "ufs_mtk_scsi_unblock_requests(hba);", "pm_runtime_put(",
                   "return 0;")
    flight = native.function(md, "flight_mode_set_by_atf")
    if "return" in flight:
        raise ValueError("FLIGHT return contract changed")
    native.ordered(flight, "MD_FLIGHT_MODE_SET", "flightMode, 0, 0, 0, 0, 0, &res",
                   "res.a0, res.a1, res.a2, res.a3")
    native.ordered(native.function(md, "md_cd_power_on"), "md1_pmic_setting_on();",
                   "md_cd_topclkgen_on(md)", "flight_mode_set_by_atf(md, false)",
                   "pm_runtime_get_sync")
    native.ordered(native.function(regmap, "_regmap_update_bits"),
                   "ret = _regmap_read", "if (ret != 0)", "return ret;",
                   "tmp = orig & ~mask;", "tmp |= val & mask;", "ret = _regmap_write")
    native.ordered(native.function(regmap, "regmap_update_bits_base"), "map->lock(",
                   "ret = _regmap_update_bits", "map->unlock(", "return ret;")
    native.ordered(native.function(syscon, "of_syscon_register"), "regmap_init_mmio(NULL",
                   "list_add_tail(&syscon->list, &syscon_list)")

    for label, text, needle, meaning in (
        ("vendor-md", md, "static int md_cd_topclkgen_off(struct ccci_modem *md)",
         "TOP gate operation; vendor write errno and caller return are ignored"),
        ("vendor-md", md, "reg_value |= ((1<<8) | (1<<9));", "only modem TOP bits8/9 are set"),
        ("vendor-md", md, "ccci_ufs_io_operate(0);", "UFS unblock before gen6299 settle and FLIGHT; caller ignores return"),
        ("vendor-md", md, "mdelay(4);", "settle >=4ms after UFS unblock for gen6299"),
        ("vendor-md", md, "static void flight_mode_set_by_atf(struct ccci_modem *md,",
         "known secure inputs; void/log-only returns do not prove success or inhibition"),
        ("vendor-md", md, 'syscon_regmap_lookup_by_phandle(dev_ptr->dev.of_node,\n\t\t\t"ccci-topckgen");',
         "native shared TOP syscon lookup"),
        ("vendor-md", md, "static int md_cd_power_on(struct ccci_modem *md)",
         "intentional genuine power-on chain is distinct from an inhibited diagnostic promise"),
        ("vendor-md", md, "static int md_cd_let_md_go(struct ccci_modem *md)",
         "separate POWER/0 release is not proof of inhibition before release"),
        ("vendor-dts", dts, 'topckgen_clk: syscon@10000000 {\n\t\tcompatible = "mediatek,mt6878-topckgen", "syscon";\n\t\treg = <0 0x10000000 0 0x1000>;',
         "real TOP compatible/address/size; geometry check does not create an MMIO window"),
        ("vendor-dts", dts, "ccci-topckgen = <&topckgen_clk>;", "actual modem TOP phandle"),
        ("vendor-ufs-wrapper", fsm, "int ccci_ufs_io_operate(int op_id)",
         "release requires tracked held calibration state; -1 when unheld/disabled"),
        ("vendor-ufs-release", ufs, "int ufs_mtk_cali_release(void)",
         "release unblocks requests and drops UFS runtime reference; requires matching owner"),
        ("vendor-domain", domain, "MTK_SCPD_BYPASS_INIT_ON | MTK_SCPD_REMOVE_MD_RSTB,",
         "no fabricated AP reset/inhibit mechanism"),
        ("linux-syscon", syscon, "struct regmap *device_node_to_regmap(struct device_node *np)",
         "same cached native map as frozen resource helper, with DT resource guard"),
        ("linux-regmap", regmap, "static int _regmap_update_bits(struct regmap *map, unsigned int reg,\n\t\t\t       unsigned int mask, unsigned int val,\n\t\t\t       bool *change, bool force_write)\n{",
         "masked RMW preserves unrelated bits and propagates read/write errno"),
        ("linux-regmap", regmap, "int regmap_update_bits_base(struct regmap *map, unsigned int reg,",
         "RMW under shared map lock; not global hardware/secure serialization"),
        ("linux-regmap-api", regmap_h, "static inline int regmap_set_bits(struct regmap *map,",
         "set-only masked RMW API; no ungate"),
    ):
        # A disabled-regmap stub has the same declaration; anchor the enabled API.
        if label == "linux-regmap-api":
            needle += "\n\t\t\t\t  unsigned int reg, unsigned int bits)\n{\n\treturn regmap_update_bits_base(map, reg, bits, bits,"
        anchor(label, text, needle, meaning)

    return {"schema": 1, "pins": {"vendor": VENDOR, "linux": LINUX},
            "method": "exact vendor git objects; hashed pristine pinned Linux files; source-only",
            "sources": sources, "causal_edges": edges,
            "status": "TOP-only implementation; no full shutdown/restart/boot integration"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", action="store_true", help="print manifest; never write files")
    parser.add_argument("--vendor", type=Path)
    parser.add_argument("--linux", type=Path)
    args = parser.parse_args()
    actual = evidence(args.vendor, args.linux)
    if args.emit:
        print(json.dumps(actual, indent=2))
    elif actual != json.loads((ROOT / "SOURCE-EVIDENCE.json").read_text()):
        raise SystemExit("post-OFF exact source evidence mismatch")
    else:
        print("post-OFF exact source hashes, order and anchors: PASS")


if __name__ == "__main__":
    main()
