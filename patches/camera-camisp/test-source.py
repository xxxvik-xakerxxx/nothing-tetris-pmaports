#!/usr/bin/env python3
"""Mutation checks of the production lifecycle contract, without a C compiler."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("camisp_check", HERE / "check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class SupplierSource(unittest.TestCase):
    def setUp(self):
        self.sources = [(HERE / name).read_text() for name in
                        ("mt6878-camisp-dma.c", "mt6878-camisp-smi.inc", "mt6878-camisp-iommu.inc")]

    def reject(self, index, old, new):
        self.assertEqual(self.sources[index].count(old), 1)
        self.sources[index] = self.sources[index].replace(old, new, 1)
        with self.assertRaises((AssertionError, ValueError)):
            check.contract(*self.sources)

    def test_actual_sources(self):
        check.contract(*self.sources)

    def test_bind_without_attached_dma_domain(self):
        self.reject(0, "!iommu_is_dma_domain(domain)", "domain->type == IOMMU_DOMAIN_IDENTITY")

    def test_platform_owned_parameters_must_be_retained(self):
        self.reject(0, "dev->dma_parms != &pdev->dma_parms", "dev->dma_parms")

    def test_physical_pm_is_mandatory(self):
        self.reject(0, "!pm_runtime_active(dma->larb)", "false")

    def test_foreign_ports_are_rejected(self):
        self.reject(1, "READ_ONCE(*larb->mmu) != (BIT(0) | BIT(1))", "!READ_ONCE(*larb->mmu)")

    def test_foreign_iommu_bank_is_rejected(self):
        self.reject(1, "READ_ONCE(larb->bank[i])", "0")

    def test_padding_cannot_become_a_register_write(self):
        self.reject(1, "writel(0x370256,", "writel(0, larb->base);\n\twritel(0x370256,")

    def test_internal_busy_bank_cannot_be_omitted(self):
        self.reject(1, "readl(larb->base + 0x500)", "0")

    def test_cycle_detection_is_mandatory(self):
        self.reject(2, "seen[i] == node", "false")

    def test_ancestry_references_are_balanced(self):
        self.reject(2, "of_node_put(seen[--count])", "count--")

    def test_missing_id_cannot_fall_back_to_legacy(self):
        self.reject(1, "else if (ret)\n\t\treturn -EINVAL;", "else if (ret)\n\t\treturn 0;")

    def test_signed_of_count_comparison(self):
        self.reject(1, '"#clock-cells") != (int)count', '"#clock-cells") != count')

    def test_dynamic_common_is_rejected(self):
        self.reject(2, " || of_node_check_flag(node, OF_DYNAMIC)", "")

    def test_busy_logical_supplier_retains_pm(self):
        self.reject(0, "int ret = mt6878_camisp_dma_idle(dma->larb);", "int ret = 0;")

    def test_common31_uses_missing_id_root_exception(self):
        self.reject(1, "of_device_is_available(parent) && camisp_display_root(parent)",
                    '!of_property_read_u32(parent, "mediatek,common-id", &id)')

    def test_present_foreign_root_id_is_rejected(self):
        self.reject(1, '!of_property_read_u32(node, "mediatek,common-id", &id) && !id', "true")

    def test_scope_and_parent_share_exact_root_shape(self):
        self.reject(1, "camisp_display_root(dev->of_node) ? 0 : -EINVAL", "0")

    def test_packaged_display_root_really_has_no_common_id(self):
        package = HERE.parents[1] / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
        patch = (package / "0071-arm64-dts-mediatek-add-MT6878-display-DMA.patch").read_text()
        root = patch.split("smi_disp_common:", 1)[1].split("+\t};", 1)[0]
        self.assertNotIn("mediatek,common-id", root)
        self.assertIn('clock-names = "apb", "smi"', root)
        self.assertNotIn("mediatek,smi", root)


if __name__ == "__main__":
    unittest.main()
