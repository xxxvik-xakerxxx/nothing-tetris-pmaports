#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Focused source regressions and real strict patch application only."""
import argparse
from pathlib import Path
import tempfile
import unittest

import check
import generate as gen
import stage


class BoardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.output, cls.linux, cls.vendor, cls.evidence = check.check(
            ARGS.kernel_archive, ARGS.device_repo, ARGS.modules_repo)

    def mutate(self, path, old, new, error):
        output = dict(self.output)
        self.assertIn(old, output[path])
        output[path] = output[path].replace(old, new, 1)
        with self.assertRaisesRegex(ValueError, error):
            check.contracts(self.base, output, self.linux)

    def code(self, old, new, error):
        self.mutate(gen.DEST + 'mt6878-cold-board.c', old, new, error)

    def test_actual_complete_post_cold_delta(self):
        check.contracts(self.base, self.output, self.linux)
        self.assertEqual(len(self.output), 8)

    def test_constructor_cannot_run_from_probe(self):
        self.code('pm_runtime_enable(dev);',
                  'pm_runtime_enable(dev);\n\tmt6878_cold_board_publish(pdev, NULL, NULL);',
                  'before genuine bound')

    def test_root_not_fakely_bound_by_driver_pointer(self):
        self.code('!device_is_bound(&pdev->dev)', 'false', 'actual bound driver')

    def test_private_storage_requires_our_actual_driver(self):
        self.code('pdev->dev.driver != &mt6878_cold_board_driver.driver',
                  'pdev->dev.driver == NULL', 'actual bound driver')

    def test_no_device_lock_across_constructor(self):
        self.code('device_unlock(&pdev->dev);', '/* still locked */', 'substring not found')

    def test_exact_pinned_bound_point(self):
        linux = dict(self.linux)
        linux['drivers/base/dd.c'] = linux['drivers/base/dd.c'].replace(
            'klist_node_attached(&dev->p->knode_driver)', 'dev->driver != NULL')
        with self.assertRaisesRegex(ValueError, 'bound point contract'):
            check.contracts(self.base, self.output, linux)

    def test_native_gic_four_cells_not_vendor_assumption(self):
        linux = dict(self.linux)
        linux['arch/arm64/boot/dts/mediatek/mt6878.dtsi'] = linux[
            'arch/arm64/boot/dts/mediatek/mt6878.dtsi'].replace('#interrupt-cells = <4>;', '#interrupt-cells = <3>;')
        with self.assertRaisesRegex(ValueError, 'GIC interrupt-cell'):
            check.contracts(self.base, self.output, linux)

    def test_native_soc_reg_cells_not_vendor_assumption(self):
        linux = dict(self.linux)
        linux['arch/arm64/boot/dts/mediatek/mt6878.dtsi'] = linux[
            'arch/arm64/boot/dts/mediatek/mt6878.dtsi'].replace('#size-cells = <1>;', '#size-cells = <2>;')
        with self.assertRaisesRegex(ValueError, 'soc reg-cell'):
            check.contracts(self.base, self.output, linux)

    def test_missing_producer_not_zero_configuration(self):
        self.code('return -ENODATA;', 'return 0;', 'publication contract')

    def test_vendor_init_config_not_rewritten(self):
        self.code('if (config->flags)', 'if (false)', 'publication contract')

    def test_no_guessed_pdaf_geometry(self):
        self.code('board->suppliers.layout = *layout;',
                  'board->suppliers.layout = *layout;\n\tboard->suppliers.layout.pdaf_layout.height = 750;',
                  'root invents')

    def test_real_vmm_attachment_before_registration(self):
        self.code('mt6878_camera_vmm_validate_domain(board->suppliers.cam_main,\n\t\tMT6878_POWER_DOMAIN_CAM_MAIN)',
                  '0', 'publication contract')

    def test_uncertain_owner_not_freed(self):
        self.code('board->first_error = ret;', 'kfree(board);', 'publication contract')

    def test_actual_layout_copied_not_replaced(self):
        self.code('board->suppliers.layout = *layout;', 'board->suppliers.layout.width = 0;', 'publication contract')

    def test_actual_config_copied_not_replaced(self):
        self.code('board->suppliers.config = *config;', 'memset(&board->suppliers.config, 0, sizeof(*config));',
                  'publication contract')

    def test_no_manual_fake_bind(self):
        self.code('return ret;\n}\nEXPORT_SYMBOL_GPL(mt6878_cold_board_publish);',
                  'device_bind_driver(&pdev->dev);\n\treturn ret;\n}\nEXPORT_SYMBOL_GPL(mt6878_cold_board_publish);',
                  'changes binding')

    def test_self_supplier_permanent_error(self):
        self.code('node == dev->of_node', 'false', 'supplier reference')

    def test_supplier_wrong_compatible(self):
        self.code('!of_device_is_compatible(node, compatible)', 'false', 'supplier reference')

    def test_supplier_device_reference_retained(self):
        self.code('devm_add_action_or_reset(dev, board_put_supplier, &supplier->dev)',
                  '0', 'supplier reference')

    def test_root_has_no_own_iommu(self):
        self.code('device_property_present(dev, "iommus")', 'false', 'logical DMA ownership')

    def test_receiver_graph_not_guessed(self):
        self.code('fwnode_graph_get_remote_port_parent(endpoint)',
                  'dev_fwnode(board->suppliers.cam_main)', 'receiver/CSI1')

    def test_main_sensor_is_csi1(self):
        self.code('strcmp(receiver_port, "1")', 'strcmp(receiver_port, "0")', 'receiver/CSI1')

    def test_no_unbind_with_live_borrowed_resources(self):
        self.code('.suppress_bind_attrs = true', '.suppress_bind_attrs = false', 'unbind/remove')

    def test_failed_retirement_keeps_handle(self):
        self.code('ret = mt6878_native_video_unregister(board->video);\n\tif (!ret)',
                  'ret = mt6878_native_video_unregister(board->video);\n\tif (true)', 'retirement loses')

    def test_selector_default_off(self):
        self.mutate(gen.DEST + 'Kconfig', 'default n', 'default y', 'default off')

    def test_board_really_connected_to_kbuild(self):
        self.mutate(gen.cold.DIR + 'Makefile', 'obj-$(CONFIG_VIDEO_MT6878_COLD_BOARD) += board/',
                    'obj-$(CONFIG_VIDEO_MT6878_COLD_BOARD) += isolated-smoke/', 'existing real Kbuild')

    def test_no_automatic_dt_activation(self):
        self.mutate(gen.DT, 'status = "disabled";', 'status = "okay";', 'unactivated')

    def test_no_placeholder_receiver_phandle(self):
        self.mutate(gen.DT, 'tetris_camsv0_sink: endpoint {',
                    'tetris_camsv0_sink: endpoint {\n\t\t\t\tremote-endpoint = <&invented_receiver>;', 'unactivated')

    def test_exact_nos_resource_validation(self):
        vendor = dict(self.vendor)
        key = 'device:' + gen.VENDOR_DEVICE[0]
        vendor[key] = vendor[key].replace('GIC_SPI 669 IRQ_TYPE_LEVEL_HIGH 0', 'GIC_SPI 668 IRQ_TYPE_LEVEL_HIGH 0')
        with self.assertRaisesRegex(ValueError, 'four-IRQ'):
            gen.verify_vendor(vendor)

    def test_pinned_pdaf_remap_not_raw8_assumption(self):
        vendor = dict(self.vendor)
        key = 'modules:' + gen.VENDOR_MODULES[2]
        vendor[key] = vendor[key].replace('MTK_MBUS_FRAME_DESC_REMAP_TO_RAW10', 'RAW8')
        with self.assertRaisesRegex(ValueError, 'PDAF remap'):
            gen.verify_vendor(vendor)

    def write_base(self, root):
        for path, text in self.base.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)

    def test_actual_strict_application_and_no_edits_on_check(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            self.write_base(tree)
            stage.verify(tree, self.base, self.output)
            for path, text in self.base.items():
                self.assertEqual((tree / path).read_text(), text)
            gen.cold.stream.run(['git', 'apply', str(gen.HERE / 'board-owner.patch')], tree)
            for path, text in self.output.items():
                self.assertEqual((tree / path).read_text(), text)

    def test_reject_input_drift_without_editing(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            self.write_base(tree)
            target = tree / (gen.cold.DIR + 'mt6878-native-video.c')
            target.write_text('unverified')
            with self.assertRaisesRegex(ValueError, 'input mismatch'):
                stage.verify(tree, self.base, self.output)
            self.assertEqual(target.read_text(), 'unverified')

    def test_never_overwrite_existing_board_source(self):
        with tempfile.TemporaryDirectory() as directory:
            tree = Path(directory)
            self.write_base(tree)
            target = tree / (gen.DEST + 'mt6878-cold-board.c')
            target.parent.mkdir()
            target.write_text('preexisting')
            with self.assertRaisesRegex(ValueError, 'already present'):
                stage.verify(tree, self.base, self.output)
            self.assertEqual(target.read_text(), 'preexisting')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    gen.cold.stream.arguments(parser)
    ARGS = parser.parse_args()
    unittest.main(argv=[__file__])
