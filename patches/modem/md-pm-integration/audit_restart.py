#!/usr/bin/env python3
"""Derive the post-first-OFF boundary from exact pinned source; no hardware."""

import hashlib
import json
from pathlib import Path
import subprocess

import audit


HERE = Path(__file__).resolve().parent
UPSTREAM = HERE.parents[3]


def evidence():
    sources = {}
    edges = []

    def read(label, root, path, revision):
        data = subprocess.run(["git", "-C", str(root), "show", revision + ":" + path],
                              check=True, capture_output=True).stdout if revision else (root / path).read_bytes()
        sources[label] = {"path": path, "revision": revision,
                          "sha256": hashlib.sha256(data).hexdigest()}
        return data.decode()

    def anchor(label, text, needle, meaning):
        if text.count(needle) != 1:
            raise ValueError("missing/ambiguous restart anchor: " + label + ": " + needle)
        edges.append({"source": label, "line": text[:text.index(needle)].count("\n") + 1,
                      "anchor": needle, "meaning": meaning})

    vendor = UPSTREAM / "android_kernel_device_modules_6.1_nothing_mt6878"
    linux = UPSTREAM / ("linux-" + audit.LINUX)
    md = read("vendor-md", vendor, "drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c", audit.VENDOR)
    consumer = read("vendor-consumer", vendor, "drivers/misc/mediatek/eccci/fsm/modem_sys1.c", audit.VENDOR)
    secure = read("vendor-secure-abi", vendor, "drivers/misc/mediatek/eccci/inc/modem_secure_base.h", audit.VENDOR)
    pm = read("vendor-pm", vendor, "drivers/soc/mediatek/mtk-scpsys.c", audit.VENDOR)
    domain = read("vendor-domain", vendor, "drivers/soc/mediatek/mtk-scpsys-mt6878.c", audit.VENDOR)
    dts = read("vendor-dts", vendor, "arch/arm64/boot/dts/mediatek/mt6878.dts", audit.VENDOR)
    regulator = read("linux-regulator", linux, "drivers/regulator/core.c", None)
    regulator_of = read("linux-regulator-of", linux, "drivers/regulator/of_regulator.c", None)
    syscon = read("linux-syscon", linux, "drivers/mfd/syscon.c", None)

    on = audit.function(md, "md_cd_power_on")
    audit.ordered(on, "md1_pmic_setting_on();", "md_cd_topclkgen_on(md)",
                  "md_cd_srcclkena_setting(md)", "mtk_ccci_cfg_srclken_o1_on(md)",
                  "md_cd_plat_val_ptr.md_gen == 6298", "flight_mode_set_by_atf(md, false)",
                  "pm_runtime_get_sync(&md->plat_dev->dev)", "md_pll_setting(md)")
    audit.ordered(audit.function(consumer, "md_cd_start"), "plat_ptr->power_on(md)",
                  "ccci_set_mem_access_protection_1st_stage(md)", "plat_ptr->let_md_go(md)",
                  "wdt_enable_irq(md)")
    audit.ordered(audit.function(pm, "scpsys_md_power_on"),
                  "scpsys_regulator_enable(scpd)", "scpsys_extb_iso_down(scpd)",
                  "scpsys_clk_enable(scpd->clk", "MTK_SCPD_REMOVE_MD_RSTB",
                  "val |= PWR_ON_BIT", "scpsys_bus_protect_disable(scpd, MAX_STEPS - 1)")
    off = audit.function(md, "md_cd_power_off")
    audit.ordered(off, "pm_runtime_put_sync", "ccci_ufs_io_operate(0)", "mdelay(4)",
                  "flight_mode_set_by_atf(md, true)", "md_cd_topclkgen_off(md)")
    if "MD_KERNEL_BOOT_UP" not in audit.function(md, "md_cd_let_md_go"):
        raise ValueError("vendor execution release changed")
    anchor("vendor-md", md, "static int md_cd_let_md_go(struct ccci_modem *md)",
           "POWER/0 execution release is separate from md_cd_power_on; this does not prove an inhibited restart")
    anchor("vendor-secure-abi", secure, "MD_KERNEL_BOOT_UP,", "POWER/0 release opcode")
    anchor("vendor-domain", domain, "MTK_SCPD_BYPASS_INIT_ON | MTK_SCPD_REMOVE_MD_RSTB,",
           "MD domain omits reset-bit handling; reset deassert/assert cannot be invented as inhibition")
    anchor("vendor-md", md, "static void flight_mode_set_by_atf(struct ccci_modem *md,",
           "vendor FLIGHT setter logs secure returns but provides no inhibit acknowledgement")
    anchor("vendor-md", md, "static void md1_pmic_setting_on(void)",
           "vendor PMIC setter continues after voltage/sync errors; new owner must preserve first errno")
    anchor("vendor-dts", dts, "md-vmodem = <800000 800000>;", "exact MT6878 vmodem pair, not table fallback 825000")
    anchor("vendor-dts", dts, "md-vsram = <800000 800000>;", "exact MT6878 vsram pair")
    anchor("vendor-dts", dts, "md-vdigrf = <700000 700000>;", "exact MT6878 RF pair")
    anchor("vendor-dts", dts, 'compatible = "mediatek,mt6878-topckgen", "syscon";',
           "TOP is the actual source-described shared syscon, not a fabricated modem MMIO window")
    anchor("vendor-dts", dts,
           'topckgen_clk: syscon@10000000 {\n\t\tcompatible = "mediatek,mt6878-topckgen", "syscon";\n\t\treg = <0 0x10000000 0 0x1000>;',
           "source-backed TOP geometry validated before map acquisition")
    modem = dts.split("mddriver:mddriver@d180000 {", 1)[1].split("\n\t\t};", 1)[0]
    rails = dts.split("&mddriver {", 1)[1].split("\n};", 1)[0]
    for profile in (modem, rails):
        for absent in ("mediatek,power-flow-config", "mediatek,srclken-o1", "md-vnr-supply", "md-vmdfe-supply"):
            if absent in profile:
                raise ValueError("pinned MT6878 resource profile changed: " + absent)
    anchor("vendor-md", md, "md_cd_plat_val_ptr.power_flow_config = 0;",
           "absent MT6878 flow selector means zero; SRC/O1/PLL/sequencer paths do not apply")

    common = audit.function(regulator, "_regulator_get_common")
    resolve = audit.function(regulator, "regulator_resolve_supply")
    audit.ordered(common, "regulator_resolve_supply(rdev)", "create_regulator(rdev, dev, id)")
    audit.ordered(resolve, "if (rdev->use_count)", "regulator_enable(rdev->supply)")
    audit.ordered(audit.function(regulator_of, "_of_regulator_get"),
                  "of_regulator_dev_lookup(dev, node, id)", "_regulator_get_common(r, dev, id, get_type)")
    anchor("linux-regulator-of", regulator_of, "struct regulator *of_regulator_get_optional(struct device *dev,",
           "real native supplier can acquire disabled-anchor rails without creating a fake modem device, but acquisition is deferred at inhibition boundary")
    anchor("linux-regulator", regulator, "static int regulator_resolve_supply(struct regulator_dev *rdev)",
           "regulator_get can enable a newly resolved upstream supply; it is not an observation-only acquisition")
    audit.ordered(audit.function(syscon, "of_syscon_register"), "regmap_init_mmio(NULL, base", "list_add_tail(&syscon->list, &syscon_list)")
    anchor("linux-syscon", syscon, "struct regmap *device_node_to_regmap(struct device_node *np)",
           "native TOP mapping is cached for boot lifetime; staging retains its actual DT node and map without reading/writing TOP")

    return {
        "schema": 1, "pins": {"vendor": audit.VENDOR, "linux": audit.LINUX},
        "method": "exact vendor git objects and hashed pristine Linux sources; source-only",
        "sources": sources, "causal_edges": edges,
        "gen6299_chain": ["first MTCMOS OFF", "UFS unblock", "settle >=4ms", "FLIGHT true", "TOP bits8/9 gate",
                          "PMIC voltage/sync", "TOP bits8/9 ungate", "flow0 skips SRC/O1/sequencer",
                          "FLIGHT false", "native isolation down then PWR_ON/ACK then reverse bus release",
                          "optional staged EMI", "separate POWER/0 execution release", "WDT enable"],
        "implemented_operation": ["one retained first-OFF owner", "unchanged actual handoff and NOMAP",
                                  "complete current OFF readback", "acquire cached native TOP map",
                                  "retain distinct available DT rail nodes and exact voltage pairs",
                                  "terminal -EOPNOTSUPP at missing active execution-inhibit owner"],
        "explicit_boundary": "before regulator_get, PMIC setter, TOP ungate, FLIGHT, MTCMOS ON or execution release",
        "why_blocked": ["native first-OFF has not implemented full UFS/FLIGHT/TOP shutdown",
                        "pinned REMOVE_MD_RSTB chain provides no AP reset/inhibit owner or readback",
                        "separate POWER/0 call and initial BROM do not establish inhibition after cycling power",
                        "regulator acquisition may enable an upstream rail before the explicit voltage setter"],
        "not_grants": ["DT markers", "FIRST_OFF_COMPLETE", "initial BROM/BL33 EMI", "FLIGHT result", "AP mutex"],
        "status": "resource-staging-implemented; active-inhibited-ON-blocked; hardware-untested",
    }


if __name__ == "__main__":
    print(json.dumps(evidence(), indent=2))
