#!/usr/bin/env python3
"""Source/application tests; native KUnit execution belongs to the parent build."""
import ast
import json
from pathlib import Path
import re
import unittest

import audit_source
import stage


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ordered(text, *needles):
    cursor = 0
    for needle in needles:
        offset = text.find(needle, cursor)
        require(offset >= 0, "missing or out-of-order " + needle)
        cursor = offset + len(needle)


def check_operations(source):
    body = audit_source.function
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    require(not re.search(r"\b(?:arm_smccc_\w+|ioremap\w*|regmap_bulk_write|writel\w*|"
                         r"platform_device_register\w*|regulator_set_voltage(?:_triplet|_time)?|"
                         r"regulator_enable\w*)\s*\(", code), "unexpected voltage/PMIC/activation helper")
    require("ret |=" not in code, "first errno corrupted by combined error")
    control = body(source, "mt6363_md_control")
    ordered(control, "i < 3", "regmap_read(map, info->op_en + i", "if (ret)", "return ret",
            "value != (i == 2 ? 0x80 : 0)", "return -EBUSY", "info->op_en + 5",
            "value != 0x10", "info->sshub_en", "value & BIT(0)")
    require("regmap_write" not in control and "regmap_update_bits" not in control,
            "rewriting boot/hardware control banks")
    selector = body(source, "mt6363_md_selector")
    ordered(selector, "mt6363_md_control(map, info)", "if (ret)", "return ret",
            "regmap_read(map, info->desc.vsel_reg", "if (ret)", "return ret",
            "value &= info->desc.vsel_mask", "value >= info->desc.n_voltages",
            "return -ERANGE", "mt6363_md_control(map, info)", "if (ret)", "return ret")
    admission = body(source, "mt6363_md_write_admit")
    ordered(admission, "state->first_write_error", "return state->first_write_error",
            "state->registering", "return -EOPNOTSUPP", "mt6363_md_control")
    require("if (!state->first_write_error)" in body(source, "mt6363_md_write_fault"), "write errno overwritten")
    enabled = body(source, "mt6363_md_is_enabled")
    ordered(enabled, "mutex_lock", "mt6363_md_control", "if (ret)", "goto out",
            "regulator_is_enabled_regmap", "enabled < 0", "mt6363_md_control",
            "ret = enabled", "mutex_unlock", "return ret")
    setter = body(source, "mt6363_md_set_voltage_sel")
    ordered(setter, "mutex_lock", "mt6363_md_write_admit", "if (ret)", "goto out",
            "selector >= rdev->desc->n_voltages", "regulator_set_voltage_sel_regmap(rdev, selector)",
            "if (ret)", "goto fault", "mt6363_md_selector", "if (ret < 0)", "goto fault",
            "(unsigned int)ret != selector", "fault:", "mt6363_md_write_fault", "mutex_unlock")
    enable = body(source, "mt6363_md_enable_request")
    ordered(enable, "mt6363_md_write_admit", "regulator_is_enabled_regmap", "enabled == enable",
            "!enable && !state->owns_enable", "ret = -EBUSY",
            "regmap_write", "enable_reg + (enable ? 1 : 2)", "enable_mask",
            "if (ret)", "goto fault", "mt6363_md_control", "regulator_is_enabled_regmap",
            "ret != enable", "state->owns_enable = enable", "fault:", "mt6363_md_write_fault")
    mode = body(source, "mt6363_md_read_mode")
    ordered(mode, "if (info->fccm)", "regmap_read(map, info->fccm", "if (ret)", "return ret",
            "REGULATOR_MODE_FAST", "regmap_read(map, info->hw_lp", "if (ret)", "return ret")
    setter = body(source, "mt6363_md_set_mode")
    ordered(setter, "mt6363_md_write_admit", "mode != REGULATOR_MODE_NORMAL && mode != REGULATOR_MODE_IDLE",
            "mt6363_md_read_mode", "if (ret)", "goto out", "current == REGULATOR_MODE_FAST",
            "regmap_read", "if (ret)", "goto out", "ret = -EBUSY",
            "regmap_update_bits", "if (ret)", "goto fault", "udelay(100)",
            "mt6363_md_control", "regmap_read", "fault:", "mt6363_md_write_fault")
    require("return -EOPNOTSUPP" in body(source, "mt6363_md_set_load"), "fabricated DRMS success")
    for name in ("mt6363_md_set_voltage_sel", "mt6363_md_enable_request", "mt6363_md_set_mode"):
        operation = body(source, name)
        for write in re.finditer(r"ret = (?:regmap_write|regmap_update_bits|regulator_set_voltage_sel_regmap)\([^;]*\);", operation):
            require(re.match(r"\s*if \(ret\)\s*goto fault;", operation[write.end():]),
                    "write errno not retained immediately in " + name)
    require("regmap_bulk_write" not in code and "0x5543" not in code and "0x142a" not in code,
            "shared PMIC key touched")
    register = body(source, "mt6363_md_register")
    ordered(register, "for_each_available_child_of_node", "of_node_name_eq", "if (nodes[i])",
            "ret = -EEXIST", "mt6363_md_dt", "nodes[i] = of_node_get(child)",
            "if (!count)", "return 0", "devm_kcalloc", "desc.of_match = NULL",
            "registering = true", "config.of_node = nodes[i]", "of_get_regulator_init_data",
            "if (!config.init_data)", "ret = -EINVAL", "devm_regulator_register", "PTR_ERR(rdev)",
            "registering = false", "out:", "of_node_put(nodes[i])", "return ret")
    require("regmap_" not in register, "probe unconditionally accesses PMIC")
    dt = body(source, "mt6363_md_dt")
    require("for_each_property_of_node" in dt and "return -EOPNOTSUPP" in dt, "unsupported DT controls silently accepted")
    for property_name in ("regulator-boot-on", "regulator-always-on", "regulator-initial-mode", "regulator-allow-set-load"):
        require('"' + property_name + '"' not in dt, "unsafe initial DT control whitelisted")


class NativeModemSupplier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch, cls.before, cls.after, cls.inputs = stage.validate()
        cls.source = cls.after[stage.HELPER]

    def test_exact_packaged_application_and_hashes(self):
        self.assertEqual([item["patch"] for item in self.inputs], list(stage.INPUT_HASHES))
        self.assertEqual(json.loads((stage.HERE / "STAGING.json").read_text()),
                         stage.contract(self.patch, self.before, self.after, self.inputs))
        self.assertEqual(set(self.after), {stage.DRIVER, stage.BINDING, stage.HELPER, stage.TEST, stage.DT})

    def test_connectivity_and_gpu_blocks_are_byte_identical(self):
        restored = self.after[stage.DRIVER].replace('#include "mt6363-modem-regulator.h"\n\n', "", 1)
        restored = restored.replace("return mt6363_md_register(pdev, regmap);", "return 0;", 1)
        restored = restored.removesuffix('\n#include "mt6363-modem-regulator-test.h"\n')
        self.assertEqual(restored.encode(), self.before[stage.DRIVER].encode())
        self.assertEqual(stage.digest(restored.encode()), stage.BEFORE_HASHES[stage.DRIVER])

    def test_pinned_source_evidence(self):
        self.assertEqual(audit_source.evidence(), json.loads((stage.HERE / "SOURCE-EVIDENCE.json").read_text()))

    def test_descriptors_match_correct_pmic_source_fields(self):
        record = audit_source.evidence()["rail_fields"]
        entries = re.findall(r'\.desc = MT6363_MD_DESC\("([^\"]+)", (\d+), (\w+), (\d+),\s*'
                             r'(0x\w+), (\d+), (0x\w+), (0x\w+)\),(.*?)\n\t},', self.source, re.S)
        self.assertEqual(len(entries), 3)
        for name, identifier, ranges, count, en, shift, sel, mask, extra in entries:
            expected = record[name.upper().replace("-", "_")]
            self.assertEqual([int(v, 0) for v in (en, shift, sel, mask)],
                             [expected[key] for key in ("EN_ADDR", "EN_SHIFT", "VOSEL_ADDR", "VOSEL_MASK")])
            attributes = {key: int(value, 0) if not value.startswith("BIT") else
                          1 << int(value[4:-1]) for key, value in
                          re.findall(r"\.(\w+) = (BIT\(\d+\)|0x[\da-f]+)", extra)}
            for key, target in (("op_en", "OP_EN"), ("hw_lp", "HW_LP"), ("lp", "LP_ADDR")):
                self.assertEqual(attributes[key], expected[target])
            self.assertEqual(attributes["lp_mask"], 1 << expected["LP_SHIFT"])
            if name.startswith("vbuck"):
                self.assertEqual(attributes["sshub_en"], expected["SSHUB_EN"])
                self.assertEqual(attributes["fccm"], expected["FCCM"])
                self.assertEqual(attributes["fccm_mask"], 1 << expected["FCCM_SHIFT"])
                self.assertEqual(int(count), 192)
            else:
                self.assertNotIn("fccm", attributes)
                self.assertEqual(int(count), 128)
        self.assertIn("REGULATOR_LINEAR_RANGE(0, 0, 191, 6250)", self.source)
        self.assertIn("REGULATOR_LINEAR_RANGE(400000, 0, 127, 6250)", self.source)

    def test_actual_control_operations_preserve_ownership_and_errno(self):
        check_operations(self.source)

    def test_disabled_metadata_and_no_shipping_inclusion(self):
        dt = self.after[stage.DT]
        self.assertEqual(dt.count('status = "disabled"'), 3)
        for unsafe in ('status = "okay"', "regulator-boot-on", "regulator-always-on", "regulator-initial-mode",
                       "-supply", "gpio", "chosen"):
            self.assertNotIn(unsafe, dt)
        self.assertEqual(dt.count("regulator-min-microvolt = <300000>"), 2)
        self.assertEqual(dt.count("regulator-min-microvolt = <400000>"), 1)
        for name in ("vbuck1", "vbuck2", "vsram-modem"):
            self.assertIn("  " + name + ":\n", self.after[stage.BINDING])
        self.assertNotIn('#include "mt6878-modem-pmic-disabled.dtsi"', self.patch)

    def test_kunit_fixture_uses_actual_standard_helpers_and_callbacks(self):
        source = self.after[stage.TEST]
        self.assertEqual(source.count("KUNIT_CASE("), 8)
        self.assertIn("IS_REACHABLE(CONFIG_KUNIT)", source)
        self.assertIn(".cache_type = REGCACHE_NONE", source)
        self.assertIn("regmap_init(NULL", source)
        for call in ("ops->map_voltage", "ops->list_voltage", "ops->set_voltage_sel", "ops->get_voltage_sel",
                     "mt6363_md_enable", "mt6363_md_disable", "mt6363_md_set_mode", "mt6363_md_get_mode"):
            self.assertIn(call, source)
        self.assertNotIn("static int regulator_", source)
        self.assertIn("fixture->reads, fault", source)
        self.assertIn("fixture->writes, 1U", source)
        self.assertIn("mt6363_md_writer_read_fault_test", source)

    def test_mutants_reject_control_bank_overwrites_and_fake_success(self):
        for old, new in (("state->registering", "false"),
                         ("return state->first_write_error", "return 0"),
                         ("value != (i == 2 ? 0x80 : 0)", "false"),
                         ("value != 0x10", "false"),
                         ("value & BIT(0)", "false"),
                         ("value >= info->desc.n_voltages", "false"),
                         ("(unsigned int)ret != selector", "false"),
                         ("!enable && !state->owns_enable", "false"),
                         ("enable_reg + (enable ? 1 : 2)", "enable_reg"),
                         ("if (info->fccm)", "if (true)"),
                         ("current == REGULATOR_MODE_FAST", "false"),
                         ("udelay(100)", "udelay(1)"),
                         ("if (!state->first_write_error)", "if (true)"),
                         ("desc.of_match = NULL", "desc.of_match = info->desc.of_match"),
                         ("registering = true", "registering = false"),
                         ("return -EOPNOTSUPP;\n}\n\nstatic const struct regulator_ops", "return 0;\n}\n\nstatic const struct regulator_ops")):
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_operations(self.source.replace(old, new))
        with self.assertRaises(ValueError):
            check_operations(self.source + "\nvoid mutant(void) { regmap_bulk_write(map, 0x142a, key, 2); }\n")
        with self.assertRaises(ValueError):
            check_operations(self.source.replace("if (ret)\n\t\tgoto fault;", "if (ret)\n\t\tgoto out;", 1))

    def test_source_only_scripts_and_no_native_build_routes(self):
        for path in stage.HERE.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
        source = (stage.HERE / "stage.py").read_text()
        self.assertIn('os.environ.get("CI") != "true"', source)
        self.assertIn('os.environ.get("GITHUB_ACTIONS") != "true"', source)
        self.assertIn('actual prepared provider differs', source)
        self.assertNotIn('"make"', source)
        self.assertNotIn('"clang"', source)


if __name__ == "__main__":
    unittest.main()
