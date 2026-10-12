#!/usr/bin/env python3
"""Read-only pinned-source census; never compiles or executes target code."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


VENDOR = "ee2be53cb75670b548948636a0db1d1ff112bf12"
LINUX = "d84b264a54a37611f2f46bc19363cb9b41606205"
UBOOT = "8d2ccc12e7861c5726e9c37a07f62c4ae18db7b5"
REPO = Path(__file__).resolve().parents[3]
UPSTREAM = REPO.parent
SOURCES = {}
EDGES = []


def source(label, root, path, revision=None):
    if revision:
        data = subprocess.run(
            ["git", "-C", str(root), "show", revision + ":" + path],
            check=True, capture_output=True,
        ).stdout
    else:
        data = (root / path).read_bytes()
    text = data.decode("utf-8")
    SOURCES[label] = {
        "path": path, "revision": revision,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    return text


def anchor(label, text, needle, meaning):
    if text.count(needle) != 1:
        raise ValueError("missing or ambiguous source anchor: " + label + ": " + needle)
    EDGES.append({
        "source": label, "line": text[:text.index(needle)].count("\n") + 1,
        "anchor": needle, "meaning": meaning,
    })


def ordered(text, *needles):
    cursor = 0
    for needle in needles:
        index = text.find(needle, cursor)
        if index < 0:
            raise ValueError("source sequence missing: " + needle)
        cursor = index + len(needle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=UPSTREAM / "android_kernel_device_modules_6.1_nothing_mt6878")
    parser.add_argument("--uboot", type=Path, default=UPSTREAM / "u-boot-mt6878")
    parser.add_argument("--linux", type=Path, default=UPSTREAM / ("linux-" + LINUX))
    args = parser.parse_args()
    board = "board/mediatek/mt6878/"
    bootstrap = source("uboot-bootstrap", args.uboot, board + "tetris_modem_bootstrap.c", UBOOT)
    loaded = source("uboot-owner", args.uboot, board + "tetris_modem_loaded_boot.c", UBOOT)
    tags = source("uboot-tags", args.uboot, board + "tetris_modem_ccci_tags.c", UBOOT)
    brom = source("uboot-board", args.uboot, board + "tetris_modem_brom_board.c", UBOOT)
    evidence = source("uboot-evidence", args.uboot, board + "tetris_modem_smem_evidence.c", UBOOT)
    platform = source("linux-platform", args.linux, "drivers/base/platform.c")
    core = source("linux-genpd", args.linux, "drivers/pmdomain/core.c")
    dvfsrc = source("linux-dvfsrc", args.linux, "drivers/soc/mediatek/mtk-dvfsrc.c")
    vendor_pm = source("vendor-pm", args.vendor, "drivers/soc/mediatek/mtk-scpsys.c", VENDOR)
    vendor_data = source("vendor-pm-data", args.vendor, "drivers/soc/mediatek/mtk-scpsys-mt6878.c", VENDOR)
    vendor_md = source("vendor-md", args.vendor, "drivers/misc/mediatek/eccci/fsm/md_sys1_platform.c", VENDOR)
    package = "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/"
    md_pm = source("native-md-patch", REPO, package + "0113-pmdomain-mediatek-mt6878-modem-power.patch")
    backend = source("native-start-patch", REPO, package + "0117-soc-mediatek-mt6878-ccci-first-start-backend.patch")
    config = source("package-config", REPO, package + "config-postmarketos-mediatek-mt6878.aarch64")
    owner = source("frozen-owner", REPO, "patches/modem/ccci_tetris_owner.c")
    scope = source("scope", REPO, "patches/modem/mt6878_md_startup_scope.c")
    reservation = source("reservation-owner", REPO, "patches/modem/mt6878_md_handoff_reservation.c")

    ordered(bootstrap[bootstrap.index("int tetris_modem_bootstrap_once("):],
            "md_boot_cold_off()", "value | MD_ON", "MD_NEMI_CLR",
            "MD_IFR11_CLR", "MD_IFR9_CLR", "md_boot_ccci(6, 1)",
            "md_boot_ccci(6, 7)", "TETRIS_MD_BOOT_COMPLETE", "return 0;")
    anchor("uboot-bootstrap", bootstrap, "ret = md_boot_ccci(6, 1);", "execution release precedes successful handoff; success has no OFF call")
    anchor("uboot-owner", loaded, "ret = tetris_modem_bootstrap_once(dev, boot);", "real loaded owner calls bootstrap after authentication/copy/services")
    anchor("uboot-owner", loaded, "return tetris_modem_build_smem_evidence(&owner.report, buffer, size);", "evidence producer consumes the retained actual owner report")
    anchor("uboot-board", brom, "/* Independent observation fields; never permission to execute hardware.", "diagnostic fields do not request an operation; validate the actual trusted-loader transaction and region policy")
    anchor("uboot-board", brom, 'ret = disabled(final, "mediatek,mt6878-modem-power-controller");', "installed BROM hook rejects input-DT provider activation before loader execution")
    anchor("uboot-evidence", evidence, "encode32(encoded + 8, TETRIS_MODEM_SMEM_EVIDENCE_SCOPE_BL33);", "EMI evidence is explicitly BL33 scoped")
    tag_names = re.findall(r'TAG\(\d+, "([^\"]+)"', tags)
    if len(tag_names) != 21:
        raise ValueError("installed tag ABI drift")
    anchor("uboot-tags", tags, 'TAG(20, "free_in_kernel", p.scalars + 28, 4);', "exact 21-tag ABI has metadata/CHK, no certificate witness")

    ordered(platform[platform.index("static int platform_probe(struct device *_dev)"):],
            "of_clk_set_defaults", "dev_pm_domain_attach", "ret = drv->probe(dev);")
    anchor("linux-platform", platform, "ret = dev_pm_domain_attach(_dev, PD_FLAG_ATTACH_POWER_ON |", "attach power-on precedes modem driver checks")
    anchor("linux-genpd", core, "static int __genpd_dev_pm_attach(", "single-domain attachment calls genpd_power_on")
    anchor("linux-genpd", core, "static int genpd_power_on(struct generic_pm_domain *genpd, unsigned int depth)", "already-ON domain returns without power callback; permits truthful read-only adoption in principle")
    anchor("native-md-patch", md_pm, "+\t\tret = mt6878_md_check_off(pd);", "supplier rejects inherited ON before domain registration")
    anchor("native-md-patch", md_pm, "+\tpd->md_owned = true;", "write ownership arises only after supplier completes its own ON sequence")
    anchor("vendor-pm-data", vendor_data, "MTK_SCPD_BYPASS_INIT_ON | MTK_SCPD_REMOVE_MD_RSTB,", "vendor MD skips init-on and reset-bit handling")
    anchor("vendor-pm", vendor_pm, "if (MTK_SCPD_CAPS(scpd, MTK_SCPD_BYPASS_INIT_ON))", "vendor bypass seeds software OFF; does not adopt measured physical ON")
    anchor("vendor-md", vendor_md, "static int md_start_platform(struct ccci_modem *md)", "vendor first boot checks BROM then calls physical power-off")
    anchor("native-start-patch", backend, "+\tSTEP(OFF, s->callbacks.verify(s->dev, s->owner, MT6878_CCCI_EXCLUSIVE_OFF_BOOT_INHIBITED));", "backend requires exclusive OFF/inhibit before binding or SMC")
    anchor("frozen-owner", owner, "if (runtime_dev == &md->plat_dev->dev || md->plat_dev->dev.pm_domain ||", "caller rejects normal platform-domain attachment and demands separate virtual genpd device")
    anchor("scope", scope, "dev = get_device(md_scope.supplier);", "scope requires a real completed scoped DVFSRC INIT supplier")
    anchor("reservation-owner", reservation, "return -ENOKEY;", "existing reservation owner cannot authenticate installed firmware")
    anchor("package-config", config, "# CONFIG_MTK_DVFSRC is not set", "packaged native DVFSRC supplier is disabled")
    matches = re.findall(r'\.compatible = "([^\"]+)"', dvfsrc)
    if "mediatek,mt6878-dvfsrc" in matches:
        raise ValueError("native MT6878 DVFSRC support changed; reassess blocker")
    anchor("linux-dvfsrc", dvfsrc, "static const struct of_device_id mtk_dvfsrc_of_match[] = {", "native match table lacks MT6878; existing wrapper cannot create a supplier")

    print(json.dumps({
        "status": "readonly-adoption-design-prepared-first-shutdown-blocked",
        "method": "read-only source anchors and ordering; no target-code execution",
        "pins": {"vendor": VENDOR, "linux_base": LINUX, "uboot_installed_user_supplied": UBOOT},
        "linux_provenance": "local base files hashed; no independently measured running-kernel claim",
        "boot_result": "successful installed-source bootstrap leaves physical ON; live state unmeasured",
        "adoption": "ordinary trusted boot handoff and measured ON can support native observational adoption; final activation and real caller integration still required",
        "trust_correction": "independent Linux signature verification and a generic NS certificate are not imposed for ordinary trusted-loader adoption; see EMI-SOURCE-EVIDENCE.json",
        "installed_tag_names": tag_names, "native_dvfsrc_matches": matches,
        "sources": SOURCES, "causal_edges": EDGES,
        "blockers": [
            "Installed BROM hook requires provider disabled before loader and final handoff leaves it disabled",
            "Managed first shutdown and secure SPM/PCM exclusion lifetime remain unproved",
            "No proven execution-inhibited state after inherited ON is cycled OFF then ON",
            "Frozen caller rejects normal attached MD; backend assumes OFF before first start",
            "Native DVFSRC disabled and no MT6878 match; frozen startup scope supplier absent (not a prerequisite for read-only ON observation)",
        ],
        "hardware_validation": "untested",
    }, indent=2))


if __name__ == "__main__":
    main()
