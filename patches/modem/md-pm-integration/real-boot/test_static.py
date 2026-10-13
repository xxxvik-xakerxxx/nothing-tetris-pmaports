#!/usr/bin/env python3
"""Static and patch-application regressions; never compile or execute target C."""

import json
from pathlib import Path
import re
import tempfile
import unittest

import audit
import stage

HERE = Path(__file__).resolve().parent
HEADER = (HERE / "mt6878-modem-real-boot.h").read_text()
CONFIG = (HERE / "Kconfig").read_text()


def validate(header=HEADER, config=CONFIG):
    require = stage.require
    code = re.sub(r"/\*.*?\*/", "", header, flags=re.S)
    body = audit.native.function(code, "mt6878_md_real_boot_post_off")
    submit = audit.native.function(code, "mt6878_md_real_boot_flight_submit")
    on = audit.native.function(code, "mt6878_md_real_boot_power_on")
    rails = audit.native.function(code, "mt6878_md_real_boot_set_rails")
    profile = audit.native.function(code, "mt6878_md_real_boot_rail_profile")
    attach = audit.native.function(code, "mt6878_md_real_boot_attach")
    require("default n" in config and not re.search(r"\bselect\b|default [ym]", config), "implicit enable")
    require("depends on !SCSI_UFS_MEDIATEK_DBG" in config, "missing calibration provider exclusion")
    require("depends on MTK_MT6878_MODEM_POST_OFF_TOP_STAGING" in config, "missing TOP dependency")
    require("ARM64 && ARCH_MEDIATEK && HAVE_ARM_SMCCC" in config, "missing actual SMC dependency")
    audit.native.ordered(body,
        "!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING)",
        "!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_POST_OFF_TOP_STAGING)",
        "IS_ENABLED(CONFIG_SCSI_UFS_MEDIATEK_DBG)", "return -EOPNOTSUPP;",
        "if (!pd || !owner)", "return -EINVAL;",
        "mutex_lock(&mt6878_md_first_off_lock)", "mutex_lock(&owner->lock)",
        "ret = mt6878_md_post_off_owner(pd, owner);", "if (ret)", "goto out;",
        "mutex_trylock(&system_transition_mutex)",
        "if (mt6878_md_real_boot_tail.owner)", "-EALREADY : -EXDEV", "goto transition_out;",
        '"nothing,modem-inhibited-restart-staging"', "ret = -EBUSY;", "goto fault;",
        "mt6878_md_real_boot_tail.owner = owner;",
        "MT6878_MD_REAL_BOOT_TOP_ACQUIRE", "ret = mt6878_md_post_off_top_acquire(",
        "if (ret)", "goto fault;", "MT6878_MD_REAL_BOOT_OFF_READBACK",
        "ret = mt6878_md_first_off_readback(", "if (ret)", "goto fault;",
        "MT6878_MD_REAL_BOOT_FLIGHT_SUBMIT", "ret = mt6878_md_real_boot_flight_submit(",
        "if (ret)", "goto fault;",
        "MT6878_MD_REAL_BOOT_TOP_GATE", "ret = mt6878_md_post_off_top_gate(",
        "if (ret)", "goto fault;", "MT6878_MD_REAL_BOOT_POST_OFF_GATED",
        "ret = 0;", "goto transition_out;", "fault:", "ret = mt6878_md_adopt_fault(owner, ret);",
        "transition_out:", "mutex_unlock(&system_transition_mutex)",
        "out:", "mutex_unlock(&owner->lock)", "mutex_unlock(&mt6878_md_first_off_lock)",
        "return ret;")
    require("#define MT6878_MD_REAL_BOOT_SMC MTK_SIP_SMC_CMD(0x505)" in code, "wrong SiP service")
    require("#define MT6878_MD_REAL_BOOT_FLIGHT 7" in code, "wrong FLIGHT request")
    require(re.search(r"static int mt6878_md_real_boot_flight_submit\(", code), "missing checked FLIGHT result")
    require("arm_smccc_smc(MT6878_MD_REAL_BOOT_SMC, MT6878_MD_REAL_BOOT_FLIGHT,\n"
            "\t\t      mode, 0, 0, 0, 0, 0, &res);" in submit, "wrong real FLIGHT call/argument slots")
    audit.native.ordered(submit, "arm_smccc_smc(", "*a0 = res.a0;", "mode, *a0);",
                         "return *a0 ? -EIO : 0;")
    require(not any(value in code for value in ("res.a1", "res.a2", "res.a3")), "undefined FLIGHT outputs logged/used")
    require(code.count("arm_smccc_smc(") == 1, "additional secure operation")
    require(not re.search(r"\b(?:while|do|bool)\b", code), "retry or invented proof boolean")
    require(body.count("mt6878_md_real_boot_flight_submit(") == 1 and
            body.count("mt6878_md_post_off_top_gate(") == 1, "duplicate operation")
    require(re.search(r"owner->supplier, 1,\s*&mt6878_md_real_boot_tail.flight_off_a0", body),
            "post-OFF used FLIGHT(false)")
    require(re.search(r"owner->supplier, 0,\s*&mt6878_md_real_boot_tail.flight_on_a0", on),
            "ON used FLIGHT(true)")
    audit.native.ordered(on, "owner->first_error", "ret = owner->first_error;", "goto out;",
        "owner != mt6878_md_first_off_owner", "!owner->attached", "goto out;",
        "mt6878_md_first_off_profile(pd)", "mt6878_md_adopt_binding(pd, owner->modem, true)",
        "mt6878_md_adopt_revalidate_resources(pd, owner)", "mt6878_md_first_off_readback(",
        "ret = regmap_read(mt6878_md_real_boot_tail.top.map, 0, &value)",
        "MT6878_MD_REAL_BOOT_ON_RAILS", "ret = mt6878_md_real_boot_set_rails(owner)",
        "if (ret)", "goto fault;", "MT6878_MD_REAL_BOOT_ON_TOP", "ret = regmap_clear_bits(",
        "if (ret)", "goto fault;", "ret = regmap_read(", "if (ret)", "goto fault;",
        "top_on & MT6878_MD_POST_OFF_TOP_MASK", "ret = -EIO;", "MT6878_MD_REAL_BOOT_ON_FLIGHT",
        "ret = mt6878_md_real_boot_flight_submit(", "if (ret)", "goto fault;",
        "MT6878_MD_REAL_BOOT_ON_ISOLATION",
        "ret = regmap_clear_bits(base, MT6878_MD_ISO, MT6878_MD_ISO_MASK)",
        "if (ret)", "goto fault;", "ret = regmap_read(base, MT6878_MD_ISO, &value)",
        "if (value & MT6878_MD_ISO_MASK)", "MT6878_MD_REAL_BOOT_ON_POWER",
        "ret = regmap_set_bits(base, MT6878_MD_CTL, PWR_ON_BIT)", "if (ret)", "goto fault;",
        "ret = regmap_read_poll_timeout(base, MT6878_MD_CTL", "if (ret)", "goto fault;",
        "MT6878_MD_REAL_BOOT_ON_BUS", "for (i = 2; i >= 0; i--)",
        "ret = regmap_write(map, bp->bus_prot_clr, bp->bus_prot_set_clr_mask)",
        "if (ret)", "goto fault;", "ret = regmap_read_poll_timeout(map, bp->bus_prot_sta",
        "if (ret)", "goto fault;", "MT6878_MD_REAL_BOOT_ON_READBACK",
        "ret = mt6878_md_adopt_on(pd, mt6878_md_real_boot_tail.on)", "if (ret)", "goto fault;",
        "owner->state = MT6878_MD_ATTACHED_ON;", "MT6878_MD_REAL_BOOT_ON_COMPLETE", "goto transition_out;",
        "fault:", "ret = mt6878_md_adopt_fault(owner, ret)")
    require("(value & (MT6878_MD_ACK | PWR_ON_BIT)) == (MT6878_MD_ACK | PWR_ON_BIT)" in on,
            "missing actual control ACK/power readback")
    audit.native.ordered(rails, "mt6878_md_real_boot_rail_profile(owner)", "if (ret)", "return ret;",
        "rail_consumer = get_device(owner->attached)",
        "of_regulator_get_optional(mt6878_md_real_boot_tail.rail_consumer, owner->modem",
        "IS_ERR_OR_NULL(rail)", "PTR_ERR(rail)",
        "regulator_is_enabled(rail)", "ret = regulator_set_voltage(", "if (ret)", "return ret;",
        "ret = regulator_sync_voltage(rail)", "if (ret)", "return ret;",
        "ret = regulator_get_voltage(rail)", "if (ret < 0)", "return ret;",
        "(u32)ret != mt6878_md_real_boot_rails[i].uv", "return -EIO;", "regulator_is_enabled(rail)")
    for row in ('"md-vmodem", "md-vmodem-supply", "vbuck2", 800000',
                '"md-vsram", "md-vsram-supply", "vsram-modem", 800000',
                '"md-vdigrf", "md-vdigrf-supply", "vbuck1", 700000'):
        require(row in code, "wrong rail mapping/voltage")
    require('"mediatek,power-flow-config", 0' in profile and
            '"mediatek,mt6363-regulator"' in profile, "missing source profile/controller")
    audit.native.ordered(attach, "mt6878_md_post_off_owner(pd, owner)",
        "dev->bus != &platform_bus_type", "dev->of_node != owner->modem",
        "mt6878_md_adopt_binding(pd, owner->modem, true)", "mt6878_md_adopt_revalidate_resources(",
        "mt6878_md_first_off_readback(", "owner->attached = get_device(dev)")
    for forbidden in ("ccci_ufs_io_operate(", "ufs_mtk_cali_", "pm_runtime_", "regulator_enable(",
                      "regulator_disable(", "ioremap", "writel(", "PWR_ON_2ND", "PWR_RST",
                      "kfree(", "of_node_put(", "put_device(", "devm_", "md_adoption =",
                      "flight_on.a0", "flight_off.a0"):
        require(forbidden not in code, "unowned operation or false readiness: " + forbidden)
    return True


class RealBootStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kernel = stage.REPO.parent / ("linux-" + stage.LINUX)
        cls.temp = tempfile.TemporaryDirectory(prefix=".tests-", dir=HERE)
        cls.tree = Path(cls.temp.name)
        cls.before, _ = stage.baseline(cls.kernel, cls.tree)
        cls.after = stage.candidate(cls.before)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_operation_contract(self):
        self.assertTrue(validate())

    def test_resource_revalidation_is_real_and_separate_from_physical_state(self):
        old = audit.native.function(self.before[stage.ADOPT], "mt6878_md_adopt_revalidate")
        resources = audit.native.function(self.after[stage.ADOPT], "mt6878_md_adopt_revalidate_resources")
        expected = old.replace("mt6878_md_adopt_revalidate(", "mt6878_md_adopt_revalidate_resources(", 1)
        expected = expected.replace("\tif (!ret)\n\t\tret = mt6878_md_adopt_on(pd, now.on);\n", "", 1)
        self.assertEqual(resources, expected)
        self.assertIn("mt6878_md_adopt_reports(owner->modem, &now)", resources)
        self.assertIn("mt6878_md_adopt_reservations(&now)", resources)
        self.assertIn("mt6878_md_adopt_maps(pd)", resources)
        self.assertNotIn("regmap_read", resources)
        wrapper = audit.native.function(self.after[stage.ADOPT], "mt6878_md_adopt_revalidate")
        audit.native.ordered(wrapper, "mt6878_md_adopt_revalidate_resources(pd, owner)",
                             "mt6878_md_adopt_on(pd, on)", "return ret;")

    def test_manifest_covers_only_owned_files(self):
        manifest = json.loads((HERE / "STAGING.json").read_text())
        self.assertEqual(set(manifest["files_sha256"]) | {"STAGING.json"},
                         {p.name for p in HERE.iterdir() if p.is_file()})
        for name, expected in manifest["files_sha256"].items():
            self.assertEqual(stage.digest((HERE / name).read_bytes()), expected, name)

    def test_exact_pins_and_source_census(self):
        self.assertEqual(audit.evidence(), json.loads((HERE / "SOURCE-EVIDENCE.json").read_text()))

    def test_actual_frozen_r188_patch_application(self):
        result = stage.validate(self.kernel)
        self.assertEqual(result["base"], "cbb777d415b564c1e40598740288c0c9d953e745")
        self.assertEqual(result["ack"], "BIT(30)")

    def test_real_callsite_before_publication_and_retained_failure(self):
        after = audit.native.function(self.after[stage.ADOPT], "mt6878_md_adopt_init")
        audit.native.ordered(after, "ret = mt6878_md_first_off(pd, owner);",
            "if (!ret && IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING))",
            "ret = mt6878_md_real_boot_post_off(pd, owner);", "if (ret) {",
            "if (first_off && !owner->supplier)", "return ret;", "pd->md_adoption = owner;")
        self.assertNotIn("mt6878_md_real_boot_post_off", self.before[stage.ADOPT])
        self.assertEqual(audit.native.function(self.after[stage.ADOPT], "mt6878_md_adopt_transition"),
                         audit.native.function(self.before[stage.ADOPT], "mt6878_md_adopt_transition"))
        self.assertEqual(audit.native.function(self.after[stage.ADOPT], "mt6878_md_adopt_attach"),
                         audit.native.function(self.before[stage.ADOPT], "mt6878_md_adopt_attach"))

    def test_frozen_top_helper_is_reused_byte_for_byte(self):
        self.assertEqual(self.after[stage.PREFIX + "mt6878-modem-post-off.h"], stage.frozen_top())
        off = audit.native.function(self.before[stage.ADOPT], "mt6878_md_first_off")
        audit.native.ordered(off, "ret = regmap_set_bits(base, MT6878_MD_ISO,",
                             "usleep_range(4000, 5000);", "mt6878_md_first_off_readback(",
                             "owner->state = MT6878_MD_FIRST_OFF_COMPLETE;")
        top = audit.native.function(stage.frozen_top(), "mt6878_md_post_off_top_gate")
        audit.native.ordered(top, "mt6878_md_first_off_readback(", "regmap_set_bits(",
                             "regmap_read(", "ret = -EIO;")

    def test_kconfig_is_sourced_and_default_off(self):
        for name in ("post-off", "real-boot"):
            config = stage.PREFIX + "mt6878-modem-" + name + ".Kconfig"
            self.assertEqual(self.after[stage.KCONFIG].count('source "' + config + '"'), 1)
            self.assertIn("default n", self.after[config])
        self.assertIn("mt6878_md_real_boot_power_on : mt6878_md_adopt_transition", self.after[stage.CFILE])
        self.assertIn("mt6878_md_real_boot_attach : mt6878_md_adopt_attach", self.after[stage.CFILE])

    def test_patch_rejects_stale_or_ambiguous_caller(self):
        for source in (self.before[stage.ADOPT].replace("ret = mt6878_md_first_off(pd, owner);", "ret = 0;"),
                       self.before[stage.ADOPT] + self.before[stage.ADOPT]):
            with self.subTest(source=source[:20]), self.assertRaises(ValueError):
                stage.candidate(self.before | {stage.ADOPT: source})

    def test_patch_rejects_wrong_frozen_input(self):
        patch = stage.PATCH.read_text()
        wrong = self.before[stage.ADOPT].replace("static void mt6878_md_first_off_publication_fault(",
                                               "static void changed_publication_fault(")
        (self.tree / stage.ADOPT).write_text(wrong)
        try:
            with self.assertRaises(ValueError):
                stage.apply(self.tree, patch, check=True)
        finally:
            (self.tree / stage.ADOPT).write_text(self.before[stage.ADOPT])

    def test_mutation_rejects_missing_real_guard_or_ufs_exclusion(self):
        for old in ("!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_REAL_BOOT_STAGING)",
                    "!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_POST_OFF_TOP_STAGING)",
                    "IS_ENABLED(CONFIG_SCSI_UFS_MEDIATEK_DBG)"):
            with self.subTest(old=old), self.assertRaises(ValueError):
                validate(HEADER.replace(old, "false"))

    def test_mutation_rejects_secure_success_fabrication(self):
        for old, new in (("static int mt6878_md_real_boot_flight_submit", "static void mt6878_md_real_boot_flight_submit"),
                         ("*a0 = res.a0;", "*a0 = 0;"),
                         ("return *a0 ? -EIO : 0;", "return 0;"),
                         ("mode, *a0);", "mode, res.a1);")):
            with self.subTest(new=new), self.assertRaises(ValueError):
                validate(HEADER.replace(old, new))

    def test_mutation_rejects_wrong_smc_or_flight_argument(self):
        for old, new in (("CMD(0x505)", "CMD(0x506)"), ("FLIGHT 7", "FLIGHT 5"),
                         ("mode, 0, 0, 0, 0, 0, &res", "0, 0, 0, 0, 0, 0, &res")):
            with self.subTest(new=new), self.assertRaises(ValueError):
                validate(HEADER.replace(old, new))

    def test_mutation_rejects_unchecked_actual_predecessor(self):
        for call in ("mt6878_md_post_off_owner", "mt6878_md_post_off_top_acquire",
                     "mt6878_md_first_off_readback", "mt6878_md_post_off_top_gate",
                     "mt6878_md_real_boot_flight_submit"):
            with self.subTest(call=call), self.assertRaises(ValueError):
                validate(HEADER.replace("ret = " + call + "(", call + "("))

    def test_mutation_rejects_overwritten_error_and_false_completion(self):
        for old, new in (("mt6878_md_adopt_fault(owner, ret)", "mt6878_md_adopt_fault(owner, -EIO)"),
                         ("ret = mt6878_md_adopt_on(pd, mt6878_md_real_boot_tail.on);", "ret = 0;")):
            with self.subTest(new=new), self.assertRaises(ValueError):
                validate(HEADER.replace(old, new))

    def test_mutation_rejects_unowned_release_enable_and_proof_fields(self):
        for operation in ("ufs_mtk_cali_release();", "regulator_enable(rail);",
                          "bool ready = true;", "pm_runtime_get_sync(dev);", "writel(0, addr);"):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                validate(HEADER.replace("fault:\n", "fault:\n" + operation + "\n"))

    def test_mutation_rejects_retry_and_lifetime_drop(self):
        for operation in ("while (true) { }", "of_node_put(owner->modem);", "put_device(owner->supplier);"):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                validate(HEADER.replace("out:\n", "out:\n" + operation + "\n"))

    def test_mutation_rejects_default_enable(self):
        with self.assertRaises(ValueError):
            validate(config=CONFIG.replace("default n", "default y"))

    def test_mutation_rejects_reverse_order_and_rail_error_suppression(self):
        for old, new in (("for (i = 2; i >= 0; i--)", "for (i = 0; i < 3; i++)"),
                         ("ret = regulator_set_voltage(", "regulator_set_voltage("),
                         ("ret = regulator_sync_voltage(rail);", "regulator_sync_voltage(rail);"),
                         ("ret = regulator_get_voltage(rail);", "ret = 800000;"),
                         ('"vbuck2", 800000', '"vbuck1", 800000')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                validate(HEADER.replace(old, new))


if __name__ == "__main__":
    unittest.main()
