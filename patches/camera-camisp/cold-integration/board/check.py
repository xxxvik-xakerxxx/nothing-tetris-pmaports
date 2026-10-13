#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Actual source/call-site and application checks, never runtime simulation."""
import argparse
import json
import re
import yaml

import generate as gen


def require(condition, message):
    if not condition:
        raise ValueError(message)


def contracts(base, output, linux):
    code = output[gen.DEST + 'mt6878-cold-board.c']
    function = gen.cold.function
    probe = function(code, 'static int mt6878_cold_board_probe(')
    require('mt6878_cold_capture_register' not in probe and 'mt6878_cold_board_publish' not in probe,
            'constructor called before genuine bound point')
    bound = function(code, 'static struct mt6878_cold_board *board_bound(')
    require('pdev->dev.driver != &mt6878_cold_board_driver.driver' in bound and
            '!device_is_bound(&pdev->dev)' in bound and
            bound.index('!device_is_bound') < bound.index('platform_get_drvdata'),
            'actual bound driver must be identified before casting storage')
    require(bound.index('device_unlock(') < bound.index('return board'),
            'device lock retained across constructor pin_supplier')
    framework = function(linux['drivers/base/dd.c'], 'bool device_is_bound(')
    require('klist_node_attached(&dev->p->knode_driver)' in framework,
            'pinned bound point contract changed')
    soc = gen.cold.block(linux['arch/arm64/boot/dts/mediatek/mt6878.dtsi'], 'soc: soc@0')
    prefix = soc.split('performance:', 1)[0]
    require('#address-cells = <1>;' in prefix and '#size-cells = <1>;' in prefix,
            'native soc reg-cell contract changed')
    gic = gen.cold.block(soc, 'gic: interrupt-controller@')
    require('#interrupt-cells = <4>;' in gic, 'native GIC interrupt-cell contract changed')
    publish = function(code, 'int mt6878_cold_board_publish(')
    for anchor in ('board_bound(pdev)', '!layout || !config', 'return -ENODATA;',
                   'if (config->flags)', 'return -EOPNOTSUPP;', 'board->first_error || board->video',
                   'board->suppliers.layout = *layout;', 'board->suppliers.config = *config;',
                   'mt6878_camera_vmm_validate_domain(', 'mt6878_cold_capture_register(&board->suppliers, &board->video)',
                   'board->first_error = ret;'):
        require(anchor in publish, 'real producer/publication contract missing: ' + anchor)
    require(publish.index('mt6878_camera_vmm_validate_domain') < publish.index('mt6878_cold_capture_register'),
            'publication ignores actual VMM attachment admission')
    require('memset' not in publish and not re.search(r'config->\w+\s*=(?!=)', publish),
            'caller rewrites producer configuration to pass admission')
    require(not re.search(r'4000|3000|4096|2304|750|576|BAYER8|BAYER10', code),
            'root invents frame/PDAF layout')
    require('platform_data' not in code and 'dev_get_platdata' not in code,
            'uninstalled platform-data producer substituted for publication')
    require(not re.search(r'\b(?:device_bind_driver|driver_bound|regulator_enable|regulator_set_voltage|'
                          r'clk_set_rate|clk_set_parent|writel|readl|arm_smccc_smc)\(', code),
            'root changes binding/hardware/firmware outside the real owner')
    supplier = function(code, 'static struct device *board_supplier(')
    for anchor in ('of_parse_phandle', 'node == dev->of_node', 'of_device_is_compatible(node, compatible)',
                   'of_find_device_by_node', 'device_is_bound(&supplier->dev)',
                   'devm_add_action_or_reset(dev, board_put_supplier, &supplier->dev)'):
        require(anchor in supplier, 'supplier reference/identity gate missing: ' + anchor)
    require('device_property_present(dev, "iommus")' in probe,
            'root duplicates logical DMA ownership')
    require('fwnode_graph_get_remote_port_parent(endpoint)' in probe and
            'strcmp(receiver_port, "1")' in probe and 'port != 1' in probe,
            'main IMX882 receiver/CSI1 graph evidence lost')
    require('.suppress_bind_attrs = true' in code and 'builtin_platform_driver(' in code and '.remove' not in code,
            'borrowed root lifetime can be freed through unbind/remove')
    retire = function(code, 'int mt6878_cold_board_retire(')
    require('ret = mt6878_native_video_unregister(board->video);\n\tif (!ret)' in retire and
            'board->first_error = -ESHUTDOWN;' in retire, 'retirement loses retained error owner')
    for symbol in ('mt6878_cold_board_publish', 'mt6878_cold_board_wait', 'mt6878_cold_board_retire'):
        require('EXPORT_SYMBOL_GPL(' + symbol + ')' in code, 'missing actual caller export: ' + symbol)
    kconfig = output[gen.DEST + 'Kconfig']
    require('\tbool ' in kconfig and '\tdefault n\n' in kconfig and
            'VIDEO_MT6878_COLD_CAPTURE=y' in kconfig, 'board selector must be built-in and default off')
    require('obj-$(CONFIG_VIDEO_MT6878_COLD_BOARD) += board/' in output[gen.cold.DIR + 'Makefile'],
            'board root not linked to existing real Kbuild')
    fixture = output[gen.DT]
    require('status = "disabled";' in fixture and 'remote-endpoint' not in fixture,
            'incomplete receiver graph must remain unactivated, without invented endpoint')
    require('iommus =' not in fixture and 'regulator-' not in fixture and 'layout' not in fixture,
            'board fragment changes unrelated DMA/voltage or invents layout')
    schema = yaml.safe_load(output[gen.BINDING])
    require(schema['additionalProperties'] is False, 'binding accepts unreviewed layout/ownership properties')
    for name in ('nothing,dma-owner', 'nothing,cam-main-owner', 'nothing,smi-reset-owner'):
        require(schema['properties'][name]['$ref'].endswith('/phandle') and name in schema['required'],
                'missing explicit supplier phandle schema: ' + name)
    require(schema['properties']['nothing,csi-port']['const'] == 1,
            'binding differs from NOS main sensor CSI1')
    require(set(output) == {gen.DEST + n for n in gen.SOURCES[:4]} |
            {gen.DT, gen.BINDING, gen.cold.DIR + 'Kconfig', gen.cold.DIR + 'Makefile'},
            'board delta modifies an unrelated frozen implementation')


def check(archive, device_repo, modules_repo):
    base, output, linux, vendor, patch, evidence = gen.build(archive, device_repo, modules_repo)
    require((gen.HERE / 'board-owner.patch').read_text() == patch, 'stale board patch')
    require(json.loads((gen.HERE / 'evidence.json').read_text()) == evidence, 'stale board evidence')
    contracts(base, output, linux)
    return base, output, linux, vendor, evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    gen.cold.stream.arguments(parser)
    args = parser.parse_args()
    check(args.kernel_archive, args.device_repo, args.modules_repo)
    print('PASS: exact board/producer pins, post-bind caller, retained lifetime and strict patch application')
    print('OPEN: producer RAW10-to-Bayer8/config adapter, receiver endpoint and VMM/MMUP handoff; no activation')
