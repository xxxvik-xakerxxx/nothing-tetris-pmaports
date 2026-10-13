#!/usr/bin/env python3
"""Kernel source/application regressions; no compiler or C execution."""
import ast
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import supplier_admission as admission


class SupplierAdmission(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patch, cls.report, cls.before, cls.after = admission.validate()

    def test_actual_kernel_overlay_and_stored_evidence(self):
        self.assertEqual(admission.PATCH.read_text(), self.patch)
        self.assertEqual(json.loads(admission.REPORT.read_text()), self.report)
        self.assertEqual(self.patch.count("diff --git "), 1)
        self.assertIn("b/" + admission.INC, self.patch)
        self.assertFalse(self.report["compiled"])
        self.assertFalse(self.report["hardware_tested"])

    def test_rail_properties_are_not_required_to_detect_firmware_voters(self):
        helper = admission.check.body(self.after, "scpsys_vmm_admit_legacy_node")
        for owner in admission.OWNERS:
            self.assertIn('of_device_is_compatible(node,"' + owner + '")', helper)
        for dependency in ("supply", "pd-id", "power-domains", "of_parse_phandle",
                           "of_find_device_by_node", "device_is_bound", "regulator"):
            self.assertNotIn(dependency, helper)
        self.assertIn("return-EBUSY;", helper)

    def test_owner_veto_cannot_be_bypassed_or_downgraded(self):
        mutants = (
            ('"mediatek,vmm_notifier"', '"unused,vmm_notifier"'),
            ('"mediatek,mtk-mmdvfs-v3"', '"unused,mtk-mmdvfs-v3"'),
            ('"mediatek,vmm_notifier") &&', '"mediatek,vmm_notifier") ||'),
            ("return -EBUSY;\n}", "return 0;\n}"),
            ("ret = scpsys_vmm_admit_legacy_node(scpsys->dev, node);", "ret = 0;"),
            (admission.CALL, admission.CALL.replace("\t\t\tof_node_put(node);\n", "")),
            (admission.CALL, admission.CALL.replace("goto put_rails;", "return ret;")),
            ("if (!of_device_is_available(node))", "if (false)"),
        )
        for old, new in mutants:
            with self.subTest(old=old):
                self.assertIn(old, self.after)
                with self.assertRaises(ValueError):
                    admission.contract(self.after.replace(old, new), self.before)

    def test_owner_veto_must_precede_supply_scan_and_allocation(self):
        code = admission.gen.replace_once(self.after, admission.CALL, "")
        code = admission.gen.replace_once(code, "\t\tfor_each_property_of_node(node, prop) {",
                                          "\t\tfor_each_property_of_node(node, prop) {\n" + admission.CALL)
        with self.assertRaisesRegex(ValueError, "before supply scan"):
            admission.contract(code, self.before)

    def test_existing_power_and_fault_paths_are_byte_preserved(self):
        for name in ("scpsys_vmm_on", "scpsys_vmm_off", "scpsys_vmm_construct",
                     "scpsys_vmm_start", "scpsys_vmm_retain", "scpsys_vmm_unlink"):
            self.assertEqual(admission.check.body(self.before, name),
                             admission.check.body(self.after, name))
        for operation in ("regmap_write(node, 0, 0);", "regulator_enable(NULL);",
                          "arm_smccc_smc(0);", "bool power_ready = true;"):
            for anchor in ("\treturn -EBUSY;\n}", '\tdev_err(dev, "%pOF: legacy VMM'):
                changed = self.after.replace(anchor, "\t" + operation + "\n" + anchor, 1)
                with self.subTest(operation=operation, anchor=anchor), self.assertRaises(ValueError):
                    admission.contract(changed, self.before)

    def test_pinned_nos41_voter_source_drift_is_rejected(self):
        vendor = admission.gen.vendor_inputs()
        admission.source_contract(vendor)
        for path in admission.SOURCE_HASHES:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "exact B4.1 voter source"):
                admission.source_contract({**vendor, path: vendor[path] + b"\n"})

    def test_overlay_rejects_wrong_preimage_and_double_application(self):
        with tempfile.TemporaryDirectory(prefix=".vmm-admission-negative-", dir=admission.HERE) as directory:
            tree = Path(directory)
            target = tree / admission.INC
            target.parent.mkdir(parents=True)
            target.write_text(self.before)
            admission.md.apply_exact(tree, self.patch, {admission.INC: self.after})
            with self.assertRaisesRegex(ValueError, "application failed"):
                admission.md.apply_exact(tree, self.patch, {admission.INC: self.after})
            target.write_text("shifted preimage\n" + self.before)
            with self.assertRaisesRegex(ValueError, "offset/fuzz/skipped"):
                admission.md.apply_exact(tree, self.patch, {admission.INC: self.after})
            self.assertEqual(target.read_text(), "shifted preimage\n" + self.before)

    def test_frozen_cbb777d_camera_artifacts_and_python_syntax(self):
        prefix = str(admission.HERE.relative_to(admission.gen.ROOT)) + "/"
        for name in ("native-provider.patch", "evidence.json", "mt6878-native-vmm.inc"):
            frozen = subprocess.check_output(["git", "show", "cbb777d:" + prefix + name],
                                             cwd=admission.gen.ROOT)
            self.assertEqual((admission.HERE / name).read_bytes(), frozen)
        for name in ("supplier_admission.py", "test_supplier_admission.py"):
            path = admission.HERE / name
            ast.parse(path.read_text(), filename=str(path))


if __name__ == "__main__":
    unittest.main()
