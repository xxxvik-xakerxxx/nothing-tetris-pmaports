#!/usr/bin/env python3
"""Source/application tests only: never compile or execute the kernel helper."""

import ast
import json
from pathlib import Path
import re
import unittest

import stage

HERE = Path(__file__).resolve().parent
KERNEL = stage.ROOT.parent / "linux-d84b264a54a37611f2f46bc19363cb9b41606205"


def body(source, name):
    # Functions here contain no braces inside string literals. Strip comments.
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    match = re.search(r"\b" + re.escape(name) + r"\([^;{}]*\)\s*\{", source)
    if not match:
        raise ValueError("missing function: " + name)
    start = match.end()
    depth, index = 1, start
    while depth:
        depth += (source[index] == "{") - (source[index] == "}")
        index += 1
    return source[start:index - 1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_source(source, native):
    stripped = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    forbidden = (r"\b(?:arm_smccc_\w+|regmap_(?:write|raw_write|bulk_write|update_bits\w*|set_bits|clear_bits)|"
                 r"writel\w*|writew\w*|writeb\w*|iowrite\w*|ioremap\w*|memcpy_toio|"
                 r"regulator_\w+|clk_\w+|reset_control_\w+|pm_runtime_\w+|"
                 r"dev_pm_domain_attach\w*|of_genpd_add_provider\w*|platform_device_register\w*)\s*\(")
    require(not re.search(forbidden, stripped), "hardware/activation mutation in observation helper")
    require("GENPD_FLAG_ALWAYS_ON" not in stripped and "md_owned" not in stripped,
            "fabricated permanent power or transition ownership")
    require("u8 brom[80], evidence[336], descriptor[32];" in source, "wire storage drift")
    transition = body(source, "mt6878_md_adopt_transition")
    require("owner->first_error ? owner->first_error : -EOPNOTSUPP" in transition,
            "transition veto replaced with success")
    require("mutex_lock(&owner->lock)" in transition and "mutex_unlock(&owner->lock)" in transition,
            "transition owner not serialized")
    attach = body(source, "mt6878_md_adopt_attach")
    require("dev->bus != &platform_bus_type" in attach and "dev->of_node != owner->modem" in attach,
            "non-real or foreign consumer admitted")
    require(attach.index("mutex_lock(&owner->lock)") < attach.index("owner->state !=") <
            attach.index("mt6878_md_adopt_on(pd, now.on)") < attach.index("get_device(dev)"),
            "attachment publication before locked validation")
    require("owner->state != MT6878_MD_OBSERVED_ON" in attach, "duplicate/rebound consumer admitted")
    require("mt6878_md_adopt_fault(owner, ret)" in attach, "first attach fault not retained")
    detach = body(source, "mt6878_md_adopt_detach")
    require("owner->state = MT6878_MD_RETIRED" in detach and "-ESHUTDOWN" in detach,
            "detach falsely treated as reusable shutdown")
    require("put_device(held)" in detach, "retained device reference lost")
    require("pd->genpd.power_on = mt6878_md_adopt_transition;" in native and
            "pd->genpd.power_off = mt6878_md_adopt_transition;" in native,
            "native MD has a physical transition route")
    require("pd->genpd.attach_dev = mt6878_md_adopt_attach;" in native and
            "pd->genpd.detach_dev = mt6878_md_adopt_detach;" in native,
            "adoption not wired to real provider")
    require("ret = pm_genpd_init(&pd->genpd, NULL, false);" in native,
            "native registration does not adopt software ON")
    require("mt6878_md_power_on" not in native and "mt6878_md_cleanup" not in native,
            "legacy MD write/cleanup route remains")


class StaticAdoption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch, cls.before, cls.after, cls.inputs = stage.validate(KERNEL)
        cls.source = cls.after[stage.ADOPT]
        cls.native = cls.after[stage.CFILE]

    def test_actual_packaged_patch_application(self):
        self.assertIn(stage.MD_PATCH, [p["patch"] for p in self.inputs])
        self.assertEqual(self.after[stage.ADOPT], (HERE / "mt6878-modem-adopt.h").read_text())
        self.assertNotIn("static int mt6878_md_power_on", self.after[stage.DATA])
        self.assertNotIn("MTK_SCPD_KEEP_DEFAULT_OFF", self.after[stage.DATA])
        self.assertIn('.suppress_bind_attrs = true', self.native)
        self.assertEqual(json.loads((HERE / "STAGING.json").read_text()),
                         stage.contract(self.patch, self.before, self.after, self.inputs))

    def test_real_native_domain_and_no_transitions(self):
        check_source(self.source, self.native)
        self.assertIn(".num_domains = ARRAY_SIZE(mt6878_md_domains)", self.after[stage.DATA])
        self.assertIn("[0] = {", self.after[stage.DATA])
        self.assertIn("!MTK_SCPD_CAPS(pd, MTK_SCPD_MT6878_MD) && scpsys_domain_is_on(pd)", self.native)

    def test_report_validation_precedes_hardware_observation(self):
        init = body(self.source, "mt6878_md_adopt_init")
        names = ["mt6878_md_adopt_binding", "mt6878_md_adopt_reports",
                 "mt6878_md_adopt_reservations", "mt6878_md_adopt_evidence",
                 "mt6878_md_adopt_maps", "mt6878_md_adopt_on", "pd->md_adoption = owner"]
        offsets = [init.index(name) for name in names]
        self.assertEqual(offsets, sorted(offsets))

    def test_exact_brom_and_evidence_abi(self):
        reports = body(self.source, "mt6878_md_adopt_reports")
        for offset in (12, 20, 28, 48, 64, 72):
            self.assertIn("owner->brom + " + str(offset), reports)
        self.assertIn("{ 4, 8, 16, 24, 32 }", reports)
        evidence = body(self.source, "mt6878_md_adopt_evidence")
        for expression in ("get_unaligned_le32(p + 4) != 336", "get_unaligned_le32(p + 24) != 11",
                           "get_unaligned_le32(p + 28) != 15", "get_unaligned_le64(p + 56) != 1",
                           "check_add_overflow(base, size, &end)", "resource_size(r)", "42 + bank"):
            self.assertIn(expression, evidence)

    def test_policy_matches_installed_normal_source(self):
        # The independently derived policy in the checked EMI audit pins the actual
        # source-defined NS CPU field, instead of treating a raw zero as RW.
        audit = json.loads((HERE / "EMI-SOURCE-EVIDENCE.json").read_text())
        table = self.source.split("policies[2][8] = {", 1)[1].split("};", 1)[0]
        rows = re.findall(r"\{([^}]+)\}", table)
        parsed = [[int(v.strip().replace("ULL", ""), 0) for v in row.split(",") if v.strip()]
                  for row in rows]
        self.assertEqual(parsed, [[int(v, 0) for v in slot["policy_words"]] for slot in audit["slots"]])
        self.assertEqual([(row[7] >> 34) & 3 for row in parsed], [3, 3])
        self.assertIn("group < 8", body(self.source, "mt6878_md_adopt_evidence"))

    def test_full_reservations_and_positive_nomap_retention(self):
        reservations = body(self.source, "mt6878_md_adopt_reservations")
        for expression in ("reserved->ops", "reserved->base != r->start", "reserved->size != sizes[i]",
                           "for_each_child_of_node(parent, child)", "child != nodes[j]",
                           "mt6878_md_adopt_overlap", "base > U64_MAX - size", "seen == 15",
                           '"compatible"', '"reusable"', "tetris-modem-boot-sib"):
            self.assertIn(expression, reservations)
        nomap = body(self.source, "mt6878_md_adopt_nomap")
        self.assertLess(nomap.index("walk_iomem_res_desc"), nomap.index("pfn_is_map_memory"))
        self.assertIn("cover.cursor != cover.end", nomap)

    def test_supplier_only_markers_and_disabled_anchor(self):
        self.assertIn('"tetris,modem-native-on-adoption-diagnostic"', self.source)
        self.assertIn('"nothing,modem-inherited-on-adoption"', self.source)
        self.assertIn("&& !length ? 0 : -EBADMSG", body(self.source, "mt6878_md_adopt_empty"))
        init = body(self.source, "mt6878_md_adopt_init")
        self.assertIn('memcmp(status, "disabled", sizeof(status))', init)
        self.assertIn("suppliers != 1", init)
        self.assertIn('"#power-domain-cells", 1', init)
        self.assertIn("of_get_child_count(pd->scpsys->dev->of_node) != 1", init)
        self.assertIn("count != 1", init)
        self.assertIn("CONFIG_OF_DYNAMIC", init)
        binding = body(self.source, "mt6878_md_adopt_binding")
        self.assertIn('!attaching && !of_property_present(modem, "power-domains")', binding)
        self.assertIn("args.np == pd->scpsys->dev->of_node", binding)
        self.assertIn("args.args_count == 1", binding)
        self.assertIn("!args.args[0]", binding)
        self.assertIn("mt6878_md_adopt_binding(pd, dev->of_node, true)", self.source)

    def test_actual_api_unbind_limit(self):
        header = (KERNEL / "include/linux/pm_domain.h").read_text()
        core = (KERNEL / "drivers/pmdomain/core.c").read_text()
        self.assertRegex(header, r"void \(\*detach_dev\)\(struct generic_pm_domain")
        remove = body(core, "genpd_remove_device")
        self.assertLess(remove.index("dev_pm_domain_set(dev, NULL)"), remove.index("genpd->detach_dev(genpd, dev)"))
        add = body(core, "genpd_add_device")
        self.assertLess(add.index("genpd->attach_dev(genpd, dev)"), add.index("genpd_lock(genpd)"))
        self.assertIn("cannot veto consumer unbind", self.source)

    def test_masks_observe_only_complete_on(self):
        observe = body(self.source, "mt6878_md_adopt_on")
        self.assertIn("(values[0] & (MT6878_MD_ACK | PWR_ON_BIT)) != (MT6878_MD_ACK | PWR_ON_BIT)", observe)
        self.assertIn("values[1] & MT6878_MD_ISO_MASK", observe)
        self.assertIn("values[i + 2] & bp->bus_prot_sta_mask", observe)
        self.assertNotIn("poll", observe)

    def test_mutant_write_veto_and_initial_state_rejected(self):
        with self.assertRaises(ValueError):
            check_source(self.source + "\nvoid mutant(void) { regmap_set_bits(map, 0xe00, 4); }\n", self.native)
        with self.assertRaises(ValueError):
            check_source(self.source.replace("owner->first_error ? owner->first_error : -EOPNOTSUPP", "0"), self.native)
        with self.assertRaises(ValueError):
            check_source(self.source, self.native.replace("ret = pm_genpd_init(&pd->genpd, NULL, false);",
                                                         "ret = pm_genpd_init(&pd->genpd, NULL, true);"))

    def test_mutant_consumer_and_wire_storage_rejected(self):
        with self.assertRaises(ValueError):
            check_source(self.source.replace("dev->bus != &platform_bus_type", "false"), self.native)
        with self.assertRaises(ValueError):
            check_source(self.source.replace("evidence[336]", "evidence[335]"), self.native)

    def test_python_sources_parse_without_bytecode_or_native_build(self):
        for path in HERE.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
        self.assertNotIn("native_ci", (HERE / "stage.py").read_text())


if __name__ == "__main__":
    unittest.main()
