#!/usr/bin/env python3
"""Reject resource regressions without compiling or executing kernel code."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("camisp_resource_check", HERE / "check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class ResourceTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "evidence.json").read_text())
        self.inputs = [(HERE / name).read_text() for name in check.generate.DESTINATIONS]
        self.plan = json.loads((HERE / "STAGING.json").read_text())

    def reject(self, index, old, new):
        self.assertIn(old, self.inputs[index])
        self.inputs[index] = self.inputs[index].replace(old, new, 1)
        with self.assertRaises(ValueError):
            check.source_contract(*self.inputs, self.data)

    def test_current_resources_and_additive_patches(self):
        check.check()

    def test_cam_vcore_is_inverted_rmw(self):
        self.reject(0, "mtk_clk_gate_ops_no_setclr_inv", "mtk_clk_gate_ops_setclr")

    def test_cam_vcore_polarity_cannot_flip(self):
        self.reject(0, "mtk_clk_gate_ops_no_setclr_inv", "mtk_clk_gate_ops_no_setclr")

    def test_cam_vcore_not_adjacent_set_clear_registers(self):
        self.reject(0, ".clr_ofs = 0x2c", ".clr_ofs = 0x30")

    def test_mraw_set_clear_cannot_swap(self):
        self.reject(0, ".set_ofs = 0x4", ".set_ofs = 0x8")

    def test_mraw_shift_cannot_change(self):
        self.reject(0, '"camtm_sel", 2)', '"camtm_sel", 3)')

    def test_camtg_requires_camtm_parent(self):
        self.reject(0, '"camtm_sel", 2)', '"cam_sel", 2)')

    def test_gate_ids_are_bank_local(self):
        self.reject(1, "CLK_CAM_MR_LARBX\t0", "CLK_CAM_MR_LARBX\t20")

    def test_native_remove_is_required(self):
        self.reject(0, ".remove = mtk_clk_simple_remove,", "")

    def test_direct_register_programming_is_not_added(self):
        self.reject(0, ".probe = mtk_clk_simple_probe,", ".probe = mtk_clk_simple_probe, /* writel( */")

    def test_critical_clock_is_not_added(self):
        self.reject(0, ".probe = mtk_clk_simple_probe,", ".probe = mtk_clk_simple_probe, /* CLK_IS_CRITICAL */")

    def test_no_device_may_be_enabled(self):
        for index, match in enumerate(re.finditer('status = "disabled";', self.inputs[2])):
            with self.subTest(index=index):
                mutated = self.inputs[2][:match.start()] + 'status = "okay";' + self.inputs[2][match.end():]
                with self.assertRaises(ValueError):
                    check.source_contract(*self.inputs[:2], mutated, self.data)

    def test_missing_status_is_not_implicitly_enabled(self):
        self.reject(2, 'status = "disabled";', "")

    def test_unproven_genpd_is_not_substituted(self):
        self.reject(2, "reg = <0x1b203000 0x1000>;", "reg = <0x1b203000 0x1000>;\n\t\tpower-domains = <&spm 7>;")

    def test_logical_camisp_has_no_registers(self):
        self.reject(2, "camisp_l13: camisp-l13-1 {", "camisp_l13: camisp-l13-1 {\n\t\treg = <0x1a001000 0x1000>;")

    def test_logical_camisp_has_no_clock_owner(self):
        self.reject(2, "camisp_l14: camisp-l14-1 {", "camisp_l14: camisp-l14-1 {\n\t\tclocks = <&cam_main 0>;")

    def test_logical_port_cannot_use_another_larb(self):
        self.reject(2, "<&disp_iommu 416>", "<&disp_iommu 448>")

    def test_display_larb_is_not_removed_from_iommu(self):
        self.reject(2, "<&smi_larb0>, <&smi_larb13>", "<&smi_larb13>")

    def test_larb13_cannot_link_to_larb14_common(self):
        self.reject(2, "mediatek,smi = <&smi_cam_4x1_sub_comm0>;", "mediatek,smi = <&smi_cam_4x1_sub_comm1>;")

    def test_physical_larb_needs_native_compatible(self):
        self.reject(2, 'compatible = "mediatek,mt6878-smi-larb";', 'compatible = "mediatek,smi_larb13";')

    def test_common31_reset_and_iommu_links_agree(self):
        self.reject(2, "mediatek,smi-supply = <&smi_disp_common>;", "mediatek,smi-supply = <&smi_larb0>;")

    def test_subcommon_requires_all_seven_clocks(self):
        self.reject(2, ",\n\t\t\t <&cam_mraw CLK_CAM_MR_LARBX>", "")

    def test_physical_address_drift_is_rejected(self):
        self.reject(2, "0x1a001000", "0x1a003000")

    def test_manifest_cannot_stage_over_shipping_provider(self):
        source = next(iter(self.plan["sources"]))
        self.plan["sources"][source] = "drivers/clk/mediatek/clk-mt6878-cam.c"
        with self.assertRaisesRegex(ValueError, "closure"):
            check.staging_contract(self.plan)

    def test_manifest_cannot_weaken_config_variants(self):
        self.plan["config_variants"] = [{"KUNIT": "y"}]
        with self.assertRaisesRegex(ValueError, "dual-config"):
            check.staging_contract(self.plan)

    def test_evidence_cannot_hide_vendor_power_dependency(self):
        self.data["nodes"]["smi_larb13"].pop("power-domains")
        with self.assertRaises((ValueError, KeyError)):
            check.evidence_contract(self.data)

    def test_evidence_cannot_rewrite_polarity(self):
        self.data["banks"]["vcore"]["operations"] = "mtk_clk_gate_ops_setclr"
        with self.assertRaisesRegex(ValueError, "semantics"):
            check.evidence_contract(self.data)

    def test_evidence_cannot_change_release_commit(self):
        self.data["provenance"][0]["commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "provenance"):
            check.evidence_contract(self.data)

    def test_evidence_cannot_change_address_and_regenerate(self):
        self.data["nodes"]["smi_larb13"]["reg"] = "<0 0x1a003000 0 0x1000>"
        regenerated = check.generate.outputs(self.data)
        with self.assertRaisesRegex(ValueError, "trace identity"):
            check.source_contract(*(regenerated[name] for name in check.generate.DESTINATIONS), self.data)

    def test_generation_does_not_mutate_frozen_evidence(self):
        original = copy.deepcopy(self.data)
        self.assertEqual(check.generate.outputs(self.data), check.generate.outputs(self.data))
        self.assertEqual(self.data, original)

    def test_staged_provider_bytes_cannot_drift(self):
        with tempfile.TemporaryDirectory() as name:
            tree = Path(name)
            for source, destination in self.plan["sources"].items():
                target = tree / destination
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((check.ROOT / source).read_bytes())
            check.check(staged=tree)
            target = tree / next(iter(self.plan["sources"].values()))
            target.write_text("stale provider\n")
            with self.assertRaisesRegex(ValueError, "staged byte drift"):
                check.check(staged=tree)


if __name__ == "__main__":
    unittest.main()
