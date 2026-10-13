#!/usr/bin/env python3
"""Source-contract and mutation tests, not execution of the staged C helper."""

import json
from pathlib import Path
import re
import unittest

import audit


ROOT = Path(__file__).resolve().parent
HEADER = (ROOT / "mt6878-modem-post-off.h").read_text()
KCONFIG = (ROOT / "Kconfig").read_text()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(header=HEADER, config=KCONFIG):
    code = re.sub(r"/\*.*?\*/", "", header, flags=re.S)
    owner = audit.native.function(code, "mt6878_md_post_off_owner")
    acquire = audit.native.function(code, "mt6878_md_post_off_top_acquire")
    gate = audit.native.function(code, "mt6878_md_post_off_top_gate")
    require(re.search(r"^\s*default n$", config, re.M) is not None, "default must be off")
    require(not re.search(r"^\s*(?:select|default [ym])\b", config, re.M), "implicit enable")
    require("#define MT6878_MD_POST_OFF_TOP_REG 0" in code, "wrong TOP offset")
    require("#define MT6878_MD_POST_OFF_TOP_MASK (BIT(8) | BIT(9))" in code, "wrong mask")
    for body in (acquire, gate):
        require(body.lstrip().startswith(
            "u32 width;\n\tint ret;" if body == acquire else "int ret;"), "unexpected declarations")
        audit.native.ordered(body,
            "if (!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_POST_OFF_TOP_STAGING))",
            "return -EOPNOTSUPP;", "mt6878_md_post_off_owner(pd, owner)")
        require("return mt6878_md_adopt_fault(owner, ret);" in body, "lost first errno")
    audit.native.ordered(owner, "lockdep_assert_held(&mt6878_md_first_off_lock)",
                         "lockdep_assert_held(&owner->lock)", "if (owner->first_error)",
                         "return owner->first_error;", "owner != mt6878_md_first_off_owner",
                         "owner->supplier != pd->scpsys->dev", "return -EXDEV;",
                         "owner->state != MT6878_MD_FIRST_OFF_COMPLETE || owner->attached",
                         "return -EBUSY;")
    audit.native.ordered(acquire, "top->owner && top->owner != owner", "return -EXDEV;",
                         "top->acquire_attempted", "return -EALREADY;",
                         "top->owner = owner;", "top->acquire_attempted = true;",
                         "mt6878_md_first_off_profile(pd)", "mt6878_md_adopt_binding(",
                         "mt6878_md_adopt_revalidate_resources(",
                         'of_count_phandle_with_args(owner->modem, "ccci-topckgen", NULL) != 1',
                         'of_parse_phandle(owner->modem, "ccci-topckgen", 0)',
                         '"mediatek,mt6878-topckgen", 0x10000000',
                         "of_device_is_available(top->node)", "device_node_to_regmap(top->node)",
                         "PTR_ERR(top->map)", "regmap_get_val_bytes(top->map)",
                         "width != sizeof(u32)", "top->acquired = true;")
    require(not re.search(r"\bregmap_(?:read|write|set_bits|clear_bits)\(", acquire),
            "mapping performed hardware operation")
    audit.native.ordered(gate, "top->owner != owner", "return -EXDEV;", "!top->acquired",
                         "return -ENODATA;", "top->gate_attempted", "return -EALREADY;",
                         "top->gate_attempted = true;", "mt6878_md_first_off_readback(pd, top->off)",
                         "regmap_set_bits(top->map, MT6878_MD_POST_OFF_TOP_REG,",
                         "MT6878_MD_POST_OFF_TOP_MASK);", "regmap_read(top->map,",
                         "&top->value);", "ret = -EIO;", "top->top_only_complete = true;")
    for call in (
        r"mt6878_md_first_off_readback\(pd, top->off\)",
        r"regmap_set_bits\(top->map, MT6878_MD_POST_OFF_TOP_REG,\s*MT6878_MD_POST_OFF_TOP_MASK\)",
        r"regmap_read\(top->map, MT6878_MD_POST_OFF_TOP_REG, &top->value\)",
    ):
        require(re.search(r"ret = " + call + r";\s*if \(ret\)\s*goto fault;", gate) is not None,
                "unchecked hardware return")
    require("(top->value & MT6878_MD_POST_OFF_TOP_MASK) != MT6878_MD_POST_OFF_TOP_MASK" in gate,
            "missing actual gate readback")
    require(gate.count("regmap_set_bits(") == 1 and gate.count("regmap_read(") == 1,
            "unbounded or duplicate TOP operations")
    require(not re.search(r"\b(?:for|while|do)\b", gate), "retry/poll loop")
    for forbidden in ("arm_smccc", "regmap_clear_bits", "regmap_write", "ioremap", "writel",
                      "regulator_", "ccci_ufs_io_operate", "flight_mode_set_by_atf",
                      "power_on", "MD_KERNEL_BOOT_UP", "of_node_put", "kfree", "devm_",
                      "usleep", "mdelay", "inhibited =", "inhibit_ack"):
        require(forbidden not in code, "unowned operation or false proof: " + forbidden)
    return True


class PostOffStaticTests(unittest.TestCase):
    def test_implementation_contract(self):
        self.assertTrue(validate())

    def test_exact_source_objects_and_manifest(self):
        self.assertEqual(audit.evidence(), json.loads((ROOT / "SOURCE-EVIDENCE.json").read_text()))

    def test_staging_is_unintegrated_and_explicit(self):
        staging = json.loads((ROOT / "STAGING.json").read_text())
        self.assertFalse(staging["default_enabled"])
        self.assertEqual(set(staging["files"]), {p.name for p in ROOT.iterdir() if p.is_file()})
        self.assertEqual(len(staging["prerequisites_not_implemented"]), 3)
        for path in (ROOT.parent / "mt6878-modem-adopt.h", ROOT.parent / "stage.py",
                     ROOT.parent / "native-on-adoption.patch"):
            self.assertNotIn("mt6878-modem-post-off.h", path.read_text())

    def test_mutations_reject_default_enable(self):
        with self.assertRaises(ValueError):
            validate(config=KCONFIG.replace("default n", "default y"))

    def test_mutations_reject_missing_compile_guard(self):
        with self.assertRaises(ValueError):
            validate(HEADER.replace("if (!IS_ENABLED(CONFIG_MTK_MT6878_MODEM_POST_OFF_TOP_STAGING))",
                                    "if (false)"))

    def test_mutations_reject_wrong_mask_and_offset(self):
        for old, new in (("(BIT(8) | BIT(9))", "BIT(8)"),
                         ("MT6878_MD_POST_OFF_TOP_REG 0", "MT6878_MD_POST_OFF_TOP_REG 4")):
            with self.subTest(new=new), self.assertRaises(ValueError):
                validate(HEADER.replace(old, new))

    def test_mutations_reject_unchecked_write(self):
        with self.assertRaises(ValueError):
            validate(HEADER.replace("ret = regmap_set_bits(", "regmap_set_bits("))

    def test_mutations_reject_unchecked_read(self):
        with self.assertRaises(ValueError):
            validate(HEADER.replace("ret = regmap_read(", "regmap_read("))

    def test_mutations_reject_overwritten_errno(self):
        with self.assertRaises(ValueError):
            validate(HEADER.replace("mt6878_md_adopt_fault(owner, ret)",
                                    "mt6878_md_adopt_fault(owner, -EIO)"))

    def test_mutations_reject_enum_only_off(self):
        with self.assertRaises(ValueError):
            validate(HEADER.replace("mt6878_md_first_off_readback(pd, top->off)", "0"))

    def test_mutations_reject_false_readback_success(self):
        with self.assertRaises(ValueError):
            validate(HEADER.replace("(top->value & MT6878_MD_POST_OFF_TOP_MASK) != MT6878_MD_POST_OFF_TOP_MASK",
                                    "false"))

    def test_mutations_reject_lost_one_attempt_latch(self):
        with self.assertRaises(ValueError):
            validate(HEADER.replace("top->gate_attempted = true;", "top->gate_attempted = false;"))

    def test_mutations_reject_retry(self):
        with self.assertRaises(ValueError):
            validate(HEADER.replace("ret = regmap_set_bits(", "while (true) ret = regmap_set_bits("))

    def test_mutations_reject_ungate_or_secure_proof(self):
        for action in ("regmap_clear_bits(top->map, 0, BIT(8));", "inhibit_ack = true;",
                       "arm_smccc_smc(0);", "regulator_enable(rail);"):
            with self.subTest(action=action), self.assertRaises(ValueError):
                validate(HEADER.replace("top->top_only_complete = true;", action + "\n" +
                                        "top->top_only_complete = true;"))


if __name__ == "__main__":
    unittest.main()
