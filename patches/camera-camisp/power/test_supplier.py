#!/usr/bin/env python3
"""Negative source tests only; these do not simulate or execute the driver."""
import copy
import json
import unittest

import check_supplier as check


class SharedSupplierTests(unittest.TestCase):
    def setUp(self):
        self.code = (check.HERE / "mt6878-vmm-supplier.c").read_text()
        self.header = (check.HERE / "mt6878-vmm-supplier.h").read_text()
        self.plan = json.loads((check.HERE / "SHARED-STAGING.json").read_text())

    def reject(self, old, new):
        self.assertIn(old, self.code)
        with self.assertRaises(ValueError):
            check.source_contract(self.code.replace(old, new), self.header)

    def test_candidate(self):
        check.source_contract(self.code, self.header)
        check.staging_contract(self.plan)

    def test_cannot_bypass_first_failure(self):
        for old, new in [("if (ret)\n\t\tgoto fault;", "if (false) goto fault;"),
                         ("if (!vmm->first_error)", "if (true)"),
                         ("if (vmm->first_error)", "if (false)"),
                         ("return vmm->first_error;", "return 0;")]:
            with self.subTest(mutant=new):
                self.reject(old, new)

    def test_no_early_isolation_release_or_disable(self):
        for old, new in [("regulator_enable(vmm->buck)", "regulator_disable(vmm->buck)"),
                         ("mt6878_vmm_iso_set(vmm->spm, true)", "mt6878_vmm_iso_set(vmm->spm, false)"),
                         ("vmm_check_rail(vmm, false)", "vmm_check_rail(vmm, true)")]:
            with self.subTest(mutant=new):
                self.reject(old, new)

    def test_shared_users_require_exclusive_owner(self):
        self.reject('regulator_get_exclusive(dev, "vmm")', 'regulator_get(dev, "vmm")')

    def test_inherited_state_and_read_errors_fail_closed(self):
        for old, new in [("if (enabled < 0)", "if (false)"),
                         ("if (enabled)\n\t\treturn vmm_fail(vmm, -EBUSY);", ""),
                         ("pm_genpd_init(&vmm->genpd, NULL, !enabled)",
                          "pm_genpd_init(&vmm->genpd, NULL, true)"),
                         ("GENMASK(26, 24)", "BIT(24)"),
                         ("if (ret < 0)", "if (false)")]:
            with self.subTest(mutant=new):
                self.reject(old, new)

    def test_cached_on_fault_and_leaf_unwind_guard(self):
        for old, new in [("ret = mt6878_vmm_check(guard->supplier);", "ret = 0;"),
                         ("return notifier_from_errno(ret);", "return NOTIFY_OK;"),
                         ("ret = mt6878_vmm_fail_child(guard->supplier, -EIO);", "ret = 0;"),
                         ("ret = vmm_fail(vmm, error);", "ret = error;"),
                         ("guard->pending = event;", "guard->pending = 0;")]:
            with self.subTest(mutant=new):
                self.reject(old, new)

    def test_all_children_use_real_guarded_parent(self):
        for old, new in [("child->status != GENPD_STATE_OFF", "false"),
                         ("child->flags & GENPD_FLAG_IRQ_SAFE", "0"),
                         ("guard_dev->pm_domain != &child->domain", "false"),
                         ("ret = dev_pm_genpd_add_notifier(guard_dev, &guard->nb);", "ret = 0;"),
                         ("ret = pm_genpd_add_subdomain(&vmm->genpd, child);", "ret = 0;")]:
            with self.subTest(mutant=new):
                self.reject(old, new)

    def test_fault_retains_mm_infra_parent(self):
        self.reject("ret = pm_genpd_add_subdomain(mm_infra, &vmm->genpd);", "ret = 0;")

    def reject_leaf(self, old, new):
        start = self.code.index("int mt6878_vmm_cam_ctl_set(")
        end = self.code.index("static int vmm_child_notify(", start)
        leaf = self.code[start:end]
        self.assertIn(old, leaf)
        mutant = self.code[:start] + leaf.replace(old, new) + self.code[end:]
        with self.assertRaises(ValueError):
            check.source_contract(mutant, self.header)

    def test_cam_control_validates_owner_and_domain_before_io(self):
        for old, new in [("!vmm || !vmm->initialized", "!vmm"),
                         ("domain != MT6878_POWER_DOMAIN_CAM_MAIN &&", "false &&"),
                         ("domain != MT6878_POWER_DOMAIN_CAM_VCORE", "false")]:
            with self.subTest(mutant=new):
                self.reject_leaf(old, new)

    def test_cam_control_checks_supplier_for_both_directions(self):
        for old, new in [("if (ret)\n\t\tgoto out;", "if (false) goto out;"),
                         ("ret = vmm_check_rail(vmm, true);", "ret = 0;"),
                         ("ret = vmm_check_isolation(vmm, false);", "ret = 0;"),
                         ("ret = vmm_check_rail(vmm, true);",
                          "ret = on ? vmm_check_rail(vmm, true) : 0;")]:
            with self.subTest(mutant=new):
                self.reject_leaf(old, new)

    def test_cam_control_uses_owned_spm_and_requested_transition(self):
        for old, new in [("mt6878_cam_ctl_set(vmm->spm, domain, on)",
                          "mt6878_cam_ctl_set(NULL, domain, on)"),
                         ("mt6878_cam_ctl_set(vmm->spm, domain, on)",
                          "mt6878_cam_ctl_set(vmm->spm, domain, !on)"),
                         ("mt6878_cam_ctl_set(vmm->spm, domain, on)", "0")]:
            with self.subTest(mutant=new):
                self.reject_leaf(old, new)

    def test_cam_control_latches_original_errno_before_unlock_and_return(self):
        for old, new in [("if (ret)\n\t\tgoto fault;", "if (false) goto fault;"),
                         ("ret = vmm_fail(vmm, ret);", "ret = vmm_fail(vmm, -EIO);"),
                         ("ret = vmm_fail(vmm, ret);", "return ret;"),
                         ("return ret;", "return 0;"),
                         ("fault:\n\t/* Latch the actual leaf errno before genpd notifies/unwinds its parents. */\n"
                          "\tret = vmm_fail(vmm, ret);\nout:\n\tmutex_unlock(&vmm->lock);",
                          "fault:\n\tmutex_unlock(&vmm->lock);\n\treturn vmm_fail(vmm, ret);\n"
                          "out:\n\tmutex_unlock(&vmm->lock);")]:
            with self.subTest(mutant=new):
                self.reject_leaf(old, new)

    def test_cam_control_cannot_release_lock_before_leaf_io(self):
        self.reject_leaf("ret = mt6878_cam_ctl_set(vmm->spm, domain, on);",
                         "mutex_unlock(&vmm->lock);\n"
                         "\tret = mt6878_cam_ctl_set(vmm->spm, domain, on);\n"
                         "\tmutex_lock(&vmm->lock);")

    def test_cam_control_declaration_required(self):
        declaration = ("int mt6878_vmm_cam_ctl_set(struct mt6878_vmm_supplier *vmm,\n"
                       "\t\t\t   unsigned int domain, bool on);")
        self.assertIn(declaration, self.header)
        with self.assertRaises(ValueError):
            check.source_contract(self.code, self.header.replace(declaration, ""))

    def test_no_unsafe_unwind_or_invented_policy(self):
        for call in ("regulator_put(vmm->buck);", "regulator_set_voltage(vmm->buck, 1, 1);",
                     "vmm->first_error = 0;", "of_genpd_add_provider_simple(np, &vmm->genpd);"):
            with self.subTest(call=call), self.assertRaises(ValueError):
                check.source_contract(self.code + call, self.header)

    def test_staging_cannot_activate_or_drop_native_dependencies(self):
        for key, value in (("runtime_activation", "enabled"), ("sources", {}),
                           ("source_sha256", {}), ("link_plan", {}),
                           ("required_enabled", ["PM"]),
                           ("research_objects", ["drivers/pmdomain/mediatek/mtk-pm-domains.o"])):
            plan = copy.deepcopy(self.plan)
            plan[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                check.staging_contract(plan)


if __name__ == "__main__":
    unittest.main()
