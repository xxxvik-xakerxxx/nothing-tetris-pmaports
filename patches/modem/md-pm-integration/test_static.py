#!/usr/bin/env python3
"""Source/application tests only: never compile or execute the kernel helper."""

import ast
import json
from pathlib import Path
import re
import unittest

import audit
import audit_restart
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
    transaction = body(stripped, "mt6878_md_first_off")
    require(not re.search(forbidden, stripped.replace(transaction, "", 1)),
            "hardware/activation mutation outside first-OFF transaction")
    mutations = re.findall(r"\b(regmap_\w+)\s*\(", transaction)
    require(mutations == ["regmap_write", "regmap_read_poll_timeout", "regmap_clear_bits",
                          "regmap_read_poll_timeout", "regmap_set_bits"],
            "unexpected first-OFF hardware operations")
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
            attach.index("mt6878_md_adopt_revalidate(pd, owner)") < attach.index("get_device(dev)"),
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
    require("pd->md_adoption->state == MT6878_MD_FIRST_OFF_COMPLETE);" in native,
            "native OFF registration not conditioned on actual first-OFF completion")
    require("mt6878_md_power_on" not in native and "mt6878_md_cleanup" not in native,
            "legacy MD write/cleanup route remains")


def check_first_off(source):
    transaction = body(source, "mt6878_md_first_off")
    audit.ordered(transaction, "mutex_lock(&mt6878_md_first_off_lock)",
                  "if (mt6878_md_first_off_owner)", "mt6878_md_first_off_profile(pd)",
                  "mt6878_md_adopt_revalidate(pd, owner)", "owner->supplier = get_device",
                  "owner->state = MT6878_MD_FIRST_OFF_TAKEOVER",
                  "mt6878_md_first_off_owner = owner", "regmap_write(map, bp->bus_prot_set",
                  "regmap_read_poll_timeout(map, bp->bus_prot_sta", "regmap_clear_bits",
                  "!(value & (MT6878_MD_ACK | PWR_ON_BIT))", "regmap_set_bits",
                  "usleep_range(4000, 5000)", "mt6878_md_first_off_readback(pd, owner->off)",
                  "if (ret)", "goto fault", "owner->state = MT6878_MD_FIRST_OFF_COMPLETE",
                  "fault:", "mt6878_md_adopt_fault(owner, ret)",
                  "owner->state = MT6878_MD_FIRST_OFF_FAILED", "return ret;")
    require("for (i = 0; i < 3; i++)" in transaction, "bus protection order changed")
    require("if (ret)\n\t\t\tgoto fault;" in transaction, "write failure not retained")
    require("regmap_clear_bits(base, MT6878_MD_CTL, PWR_ON_BIT)" in transaction and
            "regmap_set_bits(base, MT6878_MD_ISO, MT6878_MD_ISO_MASK)" in transaction,
            "first-OFF register masks changed")
    for operation in re.finditer(r"ret = (?:regmap_\w+|mt6878_md_first_off_readback)\([^;]*\);", transaction):
        require(re.match(r"\s*if \(ret\)\s*goto fault;", transaction[operation.end():]),
                "first-OFF operation does not stop on its first errno")
    profile = body(source, "mt6878_md_first_off_profile")
    for config in ("CPU_IDLE", "PM_SLEEP", "SUSPEND", "HIBERNATION", "HOTPLUG_CPU",
                   "MTK_DVFSRC", "ARM_PSCI_CHECKER", "KVM", "KEXEC_CORE"):
        require("IS_ENABLED(CONFIG_" + config + ")" in profile, "missing exclusion: " + config)
    require('"nothing,modem-first-off-diagnostic"' in profile and
            '"tetris,modem-first-off-diagnostic"' in profile and
            profile.count("mt6878_md_adopt_empty(") == 2,
            "unpaired or nonempty first-OFF markers")
    observe = body(source, "mt6878_md_first_off_readback")
    require("values[0] & (MT6878_MD_ACK | PWR_ON_BIT)" in observe and
            "(values[1] & MT6878_MD_ISO_MASK) != MT6878_MD_ISO_MASK" in observe and
            "(values[i + 2] & bp->bus_prot_sta_mask) != bp->bus_prot_sta_mask" in observe,
            "incomplete OFF observation")
    require("return 0;" not in transaction, "first-OFF success bypasses recorded result")


def check_restart(source, adoption):
    stripped = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    require(not re.search(r"\b(?:arm_smccc_\w+|regmap_(?:write|raw_write|bulk_write|set_bits|clear_bits|update_bits\w*)|"
                         r"writel\w*|writew\w*|writeb\w*|iowrite\w*|ioremap\w*|"
                         r"regulator_\w+|of_regulator_\w+|clk_\w+|"
                         r"reset_control_\w+|pm_runtime_\w+|platform_device_\w+|"
                         r"dev_pm_domain_attach\w*|memcpy_toio)\s*\(", stripped),
            "restart crossed the active inhibition boundary")
    begin = body(source, "mt6878_md_restart_begin")
    audit.ordered(begin, "if (owner->first_error)", "return owner->first_error",
                  "owner != retained", "owner->supplier != supplier", "return -EXDEV",
                  "owner->restart.attempted", "return -EALREADY",
                  "owner->state != MT6878_MD_FIRST_OFF_COMPLETE || owner->attached",
                  "return -EBUSY", "owner->restart.attempted = true",
                  "owner->restart.step = MT6878_MD_RESTART_HANDOFF", "return 0")
    require("mt6878_md_adopt_fault(owner, error)" in body(source, "mt6878_md_restart_stop"),
            "restart replaced first errno or lost terminal deferral")
    operation = body(source, "mt6878_md_inhibited_restart")
    audit.ordered(operation, "mutex_lock(&mt6878_md_first_off_lock)", "mutex_lock(&owner->lock)",
                  "mt6878_md_restart_begin(owner, mt6878_md_first_off_owner, pd->scpsys->dev)",
                  "if (ret)", "goto out", "mt6878_md_restart_requested(pd, &requested)",
                  'memcmp(status, "disabled", sizeof(status))', "mt6878_md_adopt_binding",
                  "mt6878_md_adopt_revalidate_resources(pd, owner)",
                  "MT6878_MD_RESTART_OFF", "mt6878_md_first_off_readback(pd, owner->restart.off)",
                  "if (ret)", "goto fault", "MT6878_MD_RESTART_RESOURCES",
                  "mt6878_md_restart_resources(owner)", "if (ret)", "goto fault",
                  "MT6878_MD_RESTART_INHIBIT_BOUNDARY", "ret = -EOPNOTSUPP;", "fault:",
                  "mt6878_md_restart_stop(owner, ret)", "out:", "mutex_unlock(&owner->lock)",
                  "mutex_unlock(&mt6878_md_first_off_lock)", "return ret;")
    require("return 0;" not in operation and "owner->state =" not in operation,
            "restart fabricated ON/inhibited/READY success")
    require("ret = -EOPNOTSUPP;" in stripped.split("MT6878_MD_RESTART_INHIBIT_BOUNDARY;", 1)[1],
            "missing terminal inhibit boundary")
    resources = body(source, "mt6878_md_restart_resources")
    audit.ordered(resources, '"mediatek,power-flow-config", 0',
                  'of_count_phandle_with_args(modem, "ccci-topckgen", NULL) != 1',
                  "restart->top_node = of_parse_phandle", "mt6878_md_adopt_map_node(restart->top_node",
                  '"mediatek,mt6878-topckgen", 0x10000000', "if (ret)", "return ret;",
                  "restart->top = device_node_to_regmap(restart->top_node)", "IS_ERR_OR_NULL(restart->top)",
                  "restart->rail_nodes[i] = of_parse_phandle", "of_device_is_available(restart->rail_nodes[i])",
                  "restart->rail_nodes[i] == restart->rail_nodes[j]",
                  "of_property_read_u32_array", "if (ret)", "return ret;",
                  "restart->voltage[i][0] != voltage[i] || restart->voltage[i][1] != voltage[i]")
    require("{ 800000, 800000, 700000 }" in resources, "not pinned MT6878 voltages")
    require("of_node_put(" not in resources and "devm_" not in resources,
            "resource references released during failed post-OFF probe")
    selector = body(source, "mt6878_md_restart_requested")
    require(selector.count("mt6878_md_adopt_empty(") == 2 and
            '"nothing,modem-inhibited-restart-staging"' in selector and
            '"tetris,modem-inhibited-restart-staging"' in selector and
            "mt6878_md_first_off_profile(pd)" in selector,
            "unpaired restart marker or missing persistent exclusion profile")
    init = body(adoption, "mt6878_md_adopt_init")
    audit.ordered(init, "mt6878_md_restart_requested(pd, &restart)", "if (ret)", "return ret;",
                  "mt6878_md_first_off(pd, owner)", "if (!ret && restart)",
                  "ret = mt6878_md_inhibited_restart(pd, owner);", "if (ret)",
                  "if (first_off && !owner->supplier)", "return ret;", "pd->md_adoption = owner")


class StaticAdoption(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch, cls.before, cls.after, cls.inputs = stage.validate(KERNEL)
        cls.source = cls.after[stage.ADOPT]
        cls.native = cls.after[stage.CFILE]
        cls.restart = cls.after[stage.RESTART]

    def test_actual_packaged_patch_application(self):
        self.assertIn(stage.MD_PATCH, [p["patch"] for p in self.inputs])
        self.assertEqual(self.after[stage.ADOPT], (HERE / "mt6878-modem-adopt.h").read_text())
        self.assertNotIn("static int mt6878_md_power_on", self.after[stage.DATA])
        self.assertNotIn("MTK_SCPD_KEEP_DEFAULT_OFF", self.after[stage.DATA])
        self.assertIn('.suppress_bind_attrs = true', self.native)
        self.assertEqual(json.loads((HERE / "STAGING.json").read_text()),
                         stage.contract(self.patch, self.before, self.after, self.inputs))

    def test_real_native_domain_and_no_callback_transitions(self):
        check_source(self.source, self.native)
        check_first_off(self.source)
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
            check_source(self.source, self.native.replace("pd->md_adoption->state == MT6878_MD_FIRST_OFF_COMPLETE);",
                                                         "true);"))

    def test_mutant_consumer_and_wire_storage_rejected(self):
        with self.assertRaises(ValueError):
            check_source(self.source.replace("dev->bus != &platform_bus_type", "false"), self.native)
        with self.assertRaises(ValueError):
            check_source(self.source.replace("evidence[336]", "evidence[335]"), self.native)

    def test_python_sources_parse_without_bytecode_or_native_build(self):
        for path in HERE.glob("*.py"):
            ast.parse(path.read_text(), filename=str(path))
        self.assertNotIn("native_ci", (HERE / "stage.py").read_text())

    def test_first_shutdown_runtime_error_is_not_physical_off(self):
        core = (KERNEL / "drivers/pmdomain/core.c").read_text()
        physical = body(core, "genpd_power_off")
        runtime = body(core, "genpd_runtime_suspend")
        self.assertRegex(core, r"static void genpd_power_off\(")
        audit.ordered(physical, "if (_genpd_power_off(genpd, true))", "return;",
                      "genpd->status = GENPD_STATE_OFF;")
        audit.ordered(runtime, "genpd_lock(genpd);", "genpd_power_off(genpd, true, 0);",
                      "genpd_unlock(genpd);", "return 0;")
        evidence = json.loads((HERE / "SOURCE-EVIDENCE.json").read_text())["first_shutdown"]
        self.assertIn("pm_runtime_put_sync success", evidence["not_substitutes"])
        self.assertIn("first-error", " ".join(evidence["minimal_next_operation"]))

    def test_first_shutdown_idle_exclusion_must_outlive_temporary_pause(self):
        idle = (KERNEL / "drivers/cpuidle/cpuidle.c").read_text()
        psci = (KERNEL / "drivers/cpuidle/cpuidle-psci.c").read_text()
        audit.ordered(body(idle, "cpuidle_pause_and_lock"),
                      "mutex_lock(&cpuidle_lock)", "cpuidle_uninstall_idle_handler()")
        audit.ordered(body(idle, "cpuidle_resume_and_unlock"),
                      "cpuidle_install_idle_handler()", "mutex_unlock(&cpuidle_lock)")
        self.assertIn("psci_cpu_suspend_enter", body(psci, "psci_enter_idle_state"))
        record = json.loads((HERE / "SOURCE-EVIDENCE.json").read_text())
        for label, source in (("linux-cpuidle", idle), ("linux-psci-idle", psci)):
            self.assertEqual(stage.digest(source.encode()), record["sources"][label]["sha256"])
        boundary = record["first_shutdown"]
        self.assertIn("shipping", boundary["status"])
        self.assertIn("FLIGHT", boundary["not_substitutes"])
        self.assertIn("CPU_IDLE", boundary["secure_idle_boundary"])
        # This evidence closes source ordering only, not a runtime exclusion API.
        self.assertIn("-EOPNOTSUPP", body(self.source, "mt6878_md_adopt_transition"))

    def test_first_off_error_owner_survives_probe_failure(self):
        init = body(self.source, "mt6878_md_adopt_init")
        self.assertIn("first_off ? kzalloc(sizeof(*owner), GFP_KERNEL)", init)
        self.assertIn("if (first_off && !owner->supplier)", init)
        self.assertNotIn("devm_add_action", body(self.source, "mt6878_md_first_off"))
        fault = body(self.source, "mt6878_md_adopt_fault")
        self.assertIn("if (!owner->first_error)", fault)
        self.assertIn("return owner->first_error", fault)
        self.assertIn("mt6878_md_first_off_publication_fault(scpsys, ret);", self.native)
        self.assertIn("owner->supplier == scpsys->dev && error < 0",
                      body(self.source, "mt6878_md_first_off_publication_fault"))

    def test_first_off_requires_persistent_compiled_profile(self):
        fragment = (HERE / "first-off.config").read_text()
        profile = json.loads((HERE / "STAGING.json").read_text())["first_off"]
        for symbol, value in profile["required_resolved_config"].items():
            self.assertEqual(value, "n")
            self.assertIn("# CONFIG_" + symbol + " is not set", fragment)
        manifest = json.loads((HERE / "STAGING.json").read_text())
        observation = manifest["ci"]["required_resolved_config"]
        self.assertNotIn("CPU_IDLE", observation)
        self.assertNotIn("PM_SLEEP", observation)
        self.assertFalse(set(observation) & set(profile["required_resolved_config"]))
        for selector in ("SUSPEND", "HIBERNATION", "HIBERNATE_CALLBACKS", "PM_SLEEP_SMP",
                         "KEXEC", "KEXEC_FILE", "KEXEC_CORE"):
            self.assertEqual(profile["required_resolved_config"][selector], "n")
        diagnostic = (HERE / "diagnostic.config").read_text()
        for symbol, value in manifest["ci"]["required_resolved_config"].items():
            expected = ("CONFIG_" + symbol + "=y" if value == "y" else
                        "# CONFIG_" + symbol + " is not set")
            self.assertIn(expected, diagnostic)
        power = (KERNEL / "kernel/power/Kconfig").read_text()
        self.assertIn("depends on SUSPEND || HIBERNATE_CALLBACKS", power)
        self.assertRegex(power, r"config HIBERNATION\n[\s\S]*?select HIBERNATE_CALLBACKS")
        self.assertRegex(power, r"config PM_SLEEP_SMP\n[\s\S]*?depends on PM_SLEEP\n\tselect HOTPLUG_CPU")
        psci = (KERNEL / "drivers/firmware/psci/psci.c").read_text()
        self.assertIn("#ifdef CONFIG_CPU_IDLE\nstatic noinstr int psci_suspend_finisher", psci)
        self.assertIn("if (!IS_ENABLED(CONFIG_SUSPEND))\n\t\treturn;",
                      body(psci, "psci_init_system_suspend"))
        arm = (KERNEL / "arch/arm64/kernel/psci.c").read_text()
        self.assertIn("#ifdef CONFIG_HOTPLUG_CPU\nstatic bool cpu_psci_cpu_can_disable", arm)
        self.assertIn("psci_ops.cpu_off(state)", body(arm, "cpu_psci_cpu_die"))
        main = (KERNEL / "init/main.c").read_text()
        audit.ordered(body(main, "kernel_init_freeable"), "smp_init();", "do_basic_setup();")

    def test_first_off_mutants_rejected(self):
        for old, new in (("IS_ENABLED(CONFIG_CPU_IDLE)", "false"),
                         ("IS_ENABLED(CONFIG_HOTPLUG_CPU)", "false"),
                         ("!(value & (MT6878_MD_ACK | PWR_ON_BIT))", "true"),
                         ("mt6878_md_adopt_revalidate(pd, owner)", "0"),
                         ("ret = mt6878_md_first_off_readback(pd, owner->off);", "ret = 0;"),
                         ("regmap_clear_bits(base, MT6878_MD_CTL, PWR_ON_BIT)",
                          "regmap_clear_bits(base, MT6878_MD_CTL, PWR_RST_B_BIT)")):
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_first_off(self.source.replace(old, new))
        with self.assertRaises(ValueError):
            check_first_off(self.source.replace("if (ret)\n\t\t\tgoto fault;",
                                                "if (ret)\n\t\t\tret = 0;", 1))

    def test_restart_resource_operation_and_publication_boundary(self):
        check_restart(self.restart, self.source)
        self.assertNotIn("mt6878_md_adopt_on", body(self.source, "mt6878_md_adopt_revalidate_resources"))
        self.assertIn('mt6878-modem-restart.h', self.source)
        self.assertIn('mt6878-modem-restart-test.h', self.source)
        for path in (stage.RESTART, stage.RESTART_TEST):
            self.assertEqual(self.after[path], (HERE / Path(path).name).read_text())

    def test_restart_pinned_vendor_chain_and_hidden_regulator_activation(self):
        record = audit_restart.evidence()
        self.assertEqual(record, json.loads((HERE / "RESTART-SOURCE-EVIDENCE.json").read_text()))
        self.assertEqual(record["pins"]["vendor"], audit.VENDOR)
        self.assertEqual(record["pins"]["linux"], audit.LINUX)
        self.assertIn("regulator_get", record["explicit_boundary"])
        self.assertIn("FIRST_OFF_COMPLETE", record["not_grants"])
        self.assertTrue(any("REMOVE_MD_RSTB" in value for value in record["why_blocked"]))

    def test_restart_kunit_exercises_actual_admission_without_hardware(self):
        tests = self.after[stage.RESTART_TEST]
        self.assertIn("#if IS_BUILTIN(CONFIG_KUNIT)", tests)
        self.assertIn('"mt6878-md-inhibited-restart-owner"', tests)
        self.assertEqual(tests.count("KUNIT_CASE("), 4)
        self.assertIn("-EPROBE_DEFER, -ESTALE, -EINVAL, -ENODEV, -EIO, -ETIMEDOUT, -EOPNOTSUPP", tests)
        self.assertIn("mt6878_md_restart_begin(owner, NULL, NULL)", tests)
        self.assertNotIn("mt6878_md_inhibited_restart(", tests)
        self.assertNotIn("mt6878_md_restart_resources(", tests)
        self.assertNotIn("struct device supplier =", tests)
        self.assertIn("mt6878_md_adopt_transition(&pd->genpd), -EOPNOTSUPP", tests)
        self.assertIn("mt6878_md_adopt_transition(&pd->genpd), -EIO", tests)

    def test_restart_mutants_reject_grants_retries_and_resource_loss(self):
        for old, new in (("ret = -EOPNOTSUPP;", "ret = 0;"),
                         ("owner->restart.attempted = true", "owner->restart.attempted = false"),
                         ("owner != retained", "false"),
                         ("owner->supplier != supplier", "false"),
                         ("owner->state != MT6878_MD_FIRST_OFF_COMPLETE", "false"),
                         ("return owner->first_error", "return -EALREADY"),
                         ("mt6878_md_adopt_fault(owner, error)", "error"),
                         ("mt6878_md_first_off_readback(pd, owner->restart.off)", "0"),
                         ("mt6878_md_adopt_revalidate_resources(pd, owner)", "0"),
                         ("restart->rail_nodes[i] == restart->rail_nodes[j]", "false"),
                         ("mt6878_md_adopt_map_node(restart->top_node,", "mutant_map(restart->top_node,"),
                         ("restart->top = device_node_to_regmap(restart->top_node)", "restart->top = NULL"),
                         ("{ 800000, 800000, 700000 }", "{ 825000, 825000, 700000 }"),
                         ("return 0;\n}", "of_node_put(restart->top_node);\n\treturn 0;\n}")):
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_restart(self.restart.replace(old, new), self.source)
        for operation in ("regmap_set_bits(map, 0xe00, 4)",
                          "of_regulator_get_optional(dev, node, name)",
                          "pm_runtime_resume_and_get(dev)"):
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                check_restart(self.restart + "\nvoid mutant(void) { " + operation + "; }\n", self.source)
        with self.assertRaises(ValueError):
            check_restart(self.restart, self.source.replace("if (!ret && restart)", "if (restart)"))


if __name__ == "__main__":
    unittest.main()
