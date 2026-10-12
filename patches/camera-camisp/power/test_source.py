#!/usr/bin/env python3
"""Mutation tests of static source gates, not execution of the C transactions."""
import copy
import json
import re
import unittest

import check


class PowerSourceTests(unittest.TestCase):
    def setUp(self):
        self.code, self.header = [(check.HERE / n).read_text() for n in check.PAYLOAD]
        self.data = json.loads((check.HERE / "evidence.json").read_text())
        self.plan = json.loads((check.HERE / "STAGING.json").read_text())

    def reject(self, old, new):
        self.assertIn(old, self.code)
        with self.assertRaises(ValueError):
            check.source_contract(self.code.replace(old, new, 1), self.header, self.data)

    def test_candidate(self):
        check.source_contract(self.code, self.header, self.data)
        check.staging_contract(self.plan)

    def test_each_failed_operation_must_stop(self):
        guards = list(re.finditer(r"if \(ret\)\s+return ret;", self.code))
        self.assertEqual(len(guards), 13)
        for guard in guards:
            with self.subTest(operation=guard.start()):
                mutant = self.code[:guard.start()] + "if (false) return ret;" + self.code[guard.end():]
                with self.assertRaises(ValueError):
                    check.source_contract(mutant, self.header, self.data)

    def test_independent_ack_and_timeout(self):
        for old, new in [("(val & mask) == (on ? mask : 0)", "!!(val & mask) == on"),
                         ("return mt6878_cam_ack(spm, offset, ack, on);", "return 0;"),
                         ("CAM_PWR_ACK_2ND\t\tBIT(31)", "CAM_PWR_ACK_2ND\t\tBIT(30)"),
                         ("CAM_POLL_TIMEOUT_US\t1000000", "CAM_POLL_TIMEOUT_US\t0"),
                         ("udelay(50);", "udelay(1);"),
                         ("CAM_PWR_ACK_2ND, false);", "CAM_PWR_ACK_2ND, true);")]:
            with self.subTest(mutant=new):
                self.reject(old, new)

    def test_invalid_id_before_index(self):
        self.reject("domain != MT6878_POWER_DOMAIN_CAM_VCORE)",
                    "domain < MT6878_POWER_DOMAIN_NR)")

    def test_null_map_rejected(self):
        self.reject("if (!spm)", "if (false)")

    def test_hardware_variant(self):
        for old, new in [("VMM_ISO_CLR\t\t0x0f30", "VMM_ISO_CLR\t\t0x0fac"),
                         ("VMM_EXT_BUCK_ISO\t\tBIT(24)", "VMM_EXT_BUCK_ISO\t\tBIT(20)"),
                         (".ctl_offs = 0x0e5c", ".ctl_offs = 0x0e48"),
                         (".pwr_sta_offs = 0x0e5c", ".pwr_sta_offs = 0x0f50")]:
            with self.subTest(mutant=new):
                self.reject(old, new)

    def test_isolation_order_and_readback(self):
        for old, new in [("isolate ? VMM_EXT_BUCK_ISO : VMM_SRAM_LATCH_ENB",
                          "isolate ? VMM_SRAM_LATCH_ENB : VMM_EXT_BUCK_ISO"),
                         ("(status & VMM_ISO_MASK) != (isolate ? VMM_ISO_MASK : 0)", "false"),
                         ("return -EIO;", "return 0;")]:
            with self.subTest(mutant=new):
                self.reject(old, new)

    def test_bus_protection_order(self):
        self.reject("BUS_PROT_WR_IGN(INFRA, BIT(29)", "BUS_PROT_WR_IGN(INFRA, BIT(30)")

    def test_required_supply(self):
        self.reject("MTK_SCPD_STATUS_IN_CTL | MTK_SCPD_DOMAIN_SUPPLY", "MTK_SCPD_STATUS_IN_CTL")

    def test_no_fake_off_or_ready_state(self):
        for extra in ("MTK_SCPD_KEEP_DEFAULT_OFF", "MTK_SCPD_ALWAYS_ON", "MTK_SCPD_BYPASS_OFF"):
            with self.subTest(flag=extra):
                self.reject(".caps = MTK_SCPD_STATUS_IN_CTL,", ".caps = MTK_SCPD_STATUS_IN_CTL | " + extra + ",")
        with self.assertRaises(ValueError):
            check.source_contract(self.code + "\nstatic bool secure_ready = true;\n", self.header, self.data)

    def test_no_provider_activation_or_foreign_semaphore(self):
        for extra in ("module_init(enable_camera);", "pm_genpd_init(&pd, NULL, false);",
                      "acquire_hw_semaphore(spm);", "arm_smccc_smc(0, 0);"):
            with self.subTest(activation=extra):
                with self.assertRaises(ValueError):
                    check.source_contract(self.code + "\n" + extra, self.header, self.data)

    def test_staging_activation_and_escape(self):
        for key, value in (("runtime_activation", "enabled"), ("research_objects", ["mtk-pm-domains.o"]),
                           ("power_ready", True), ("kernel_commit", "0" * 40)):
            with self.subTest(field=key):
                plan = copy.deepcopy(self.plan)
                plan[key] = value
                with self.assertRaises(ValueError):
                    check.staging_contract(plan)
        self.plan["sources"]["patches/camera-camisp/power/mt6878-cam-power.c"] = "../mtk-pm-domains.c"
        with self.assertRaises(ValueError):
            check.staging_contract(self.plan)

    def test_missing_native_supplier_evidence(self):
        for field, value in (("parent_edges", [["MM_INFRA", "CAM_MAIN"]]),
                             ("vmm_supply", "dummy_vmm"),
                             ("generic_vmm_genpd_notifier_in_soc_dts", True)):
            with self.subTest(field=field):
                data = copy.deepcopy(self.data)
                data[field] = value
                with self.assertRaises(ValueError):
                    check.evidence_contract(data)


if __name__ == "__main__":
    unittest.main()
