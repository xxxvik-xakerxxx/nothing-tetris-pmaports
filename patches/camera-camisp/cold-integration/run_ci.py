#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""CI-only compile AND native vmlinux link, never DT activation or hardware."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import check
import generate as gen
import stage

ENABLE = ('MEDIA_SUPPORT', 'MEDIA_CAMERA_SUPPORT', 'MEDIA_PLATFORM_SUPPORT',
          'MEDIA_PLATFORM_DRIVERS', 'VIDEO_DEV', 'MEDIA_CONTROLLER', 'I2C',
          'OF', 'PM', 'PM_GENERIC_DOMAINS', 'GPIOLIB', 'REGULATOR', 'NVMEM',
          'PINCTRL_MT6878', 'MTK_SMI', 'MTK_IOMMU', 'MTK_SCPSYS_PM_DOMAINS',
          'COMMON_CLK', 'COMMON_CLK_MEDIATEK', 'COMMON_CLK_MT6878',
          'COMMON_CLK_MT6878_CAM', 'VIDEO_MT6878_COLD_CAPTURE')
SELECTED = ('VIDEO_IMX882_TETRIS', 'VIDEO_MT6878_SENINF_GRAPH',
            'REGULATOR_TETRIS_CAMERA_GPIO', 'MTK_MT6878_NATIVE_VMM',
            'VIDEOBUF2_DMA_CONTIG', 'VIDEOBUF2_V4L2', 'VIDEO_V4L2_SUBDEV_API', 'V4L2_FWNODE')
PROVIDERS = ('drivers/memory/mtk-smi.o', 'drivers/iommu/mtk_iommu.o',
             'drivers/clk/mediatek/clk-mt6878-cam.o',
             'drivers/clk/mediatek/clk-mt6878-camisp-resources.o',
             'drivers/pmdomain/mediatek/mtk-pm-domains.o',
             'drivers/pmdomain/mediatek/native-vmm/mt6878-cam-power.o',
             'drivers/pmdomain/mediatek/native-vmm/mt6878-vmm-supplier.o',
             'drivers/media/i2c/imx882-tetris-stream.o',
             'drivers/regulator/tetris-camera-gpio-regulator.o',
             'drivers/pinctrl/mediatek/pinctrl-mtk-common-v2.o',
             'drivers/pinctrl/mediatek/pinctrl-paris.o',
             'drivers/pinctrl/mediatek/pinctrl-mt6878.o')
EXPORTS = ('mt6878_cold_capture_register', 'mt6878_native_video_unregister',
           'mt6878_native_video_wait_ready', 'mt6878_camera_vmm_check', 'mt6878_camera_vmm_validate_domain',
           'mt6878_cam_main_prepare', 'mt6878_cam_main_regmap', 'mt6878_cam_main_retire',
           'mtk_smi_camera_reset_clamp', 'mt6878_camisp_dma_idle')


def ci_only():
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('native cold capture compilation/linking is CI-only')


def run(command, *, cwd=None):
    subprocess.run(list(map(str, command)), check=True, cwd=cwd)


def security_profile(text):
    result = {}
    families = ('LTO', 'CFI', 'SHADOW_CALL_STACK', 'STACKPROTECTOR',
                'ARM64_PTR_AUTH', 'ARM64_BTI', 'RANDOMIZE')
    for symbol, value, disabled in re.findall(r'^CONFIG_(\w+)=(.+)$|^# CONFIG_(\w+) is not set$', text, re.M):
        symbol, value = (symbol, value) if symbol else (disabled, 'n')
        if any(symbol == name or symbol.startswith(name + '_') for name in families):
            result[symbol] = value
    return result


def verify_security(original, resolved):
    expected, actual = security_profile(original), security_profile(resolved)
    if expected.get('LTO_CLANG_THIN') != 'y' or expected.get('CFI') != 'y':
        raise ValueError('shipping ThinLTO/CFI profile missing')
    for symbol, value in expected.items():
        if actual.get(symbol, 'n') != value:
            raise ValueError('security profile changed: ' + symbol)
    return expected


def separate_paths(*paths):
    for i, left in enumerate(paths):
        for right in paths[i + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError('prepared kernel/output/report must be disjoint')


def defined_symbols(artifact):
    text = subprocess.check_output(['llvm-nm', '--defined-only', '--format=posix', str(artifact)], text=True)
    return {line.split()[0] for line in text.splitlines() if line.split()}


def main():
    ci_only()  # Before parsing, subprocesses, mutation or creation of reports.
    parser = argparse.ArgumentParser(description=__doc__)
    gen.stream.arguments(parser, explicit=True)
    parser.add_argument('--prepared-kernel', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--include-board', action='store_true')
    args = parser.parse_args()
    for key in ('KBUILD_EXTRA_SYMBOLS', 'KBUILD_KCONFIG', 'KCONFIG_CONFIG', 'MAKEFLAGS',
                'KCFLAGS', 'KCPPFLAGS', 'LDFLAGS', 'CFLAGS', 'CC', 'LD', 'ARCH', 'LLVM', 'CROSS_COMPILE'):
        if os.environ.get(key):
            raise ValueError('inherited build override forbidden: ' + key)
    base, output, evidence = check.check(args.kernel_archive, args.device_repo, args.modules_repo)
    kernel, work, report = (p.resolve() for p in (args.prepared_kernel, args.output, args.report))
    separate_paths(kernel, work, report)
    if work.exists() or report.exists():
        raise ValueError('require fresh output and report directories')
    before = stage.verify_prepared(kernel, base, output)
    shipping = (gen.PACKAGE / 'config-postmarketos-mediatek-mt6878.aarch64').read_text()
    profile = verify_security(shipping, shipping)
    report.mkdir(parents=True)
    manifest = {'status': 'started', 'scope': 'native built-in compile/link only; no boot, modules load or DT activation',
                'kernel_commit': gen.KERNEL, 'device_modules_commit': gen.DEVICE, 'modules_commit': gen.MODULES,
                'prepared_input_sha256': before, 'payload_sha256': evidence['payload_sha256'],
                'patch_sha256': evidence['patch_sha256'], 'security_profile': profile,
                'shipping_config_sha256': gen.sha(shipping.encode()), 'objects': {}}
    manifest_path = report / 'BUILD-MANIFEST.json'
    try:
        work.mkdir(parents=True)
        source = work / 'kernel-source'
        objects_dir = work / 'kernel-output'
        shutil.copytree(kernel, source, ignore=shutil.ignore_patterns('.git'), symlinks=True)
        stage.apply(source, base, output)
        extra_exports = ()
        extra_objects = ()
        if args.include_board:
            board = gen.HERE / 'board'
            run([sys.executable, '-B', board / 'stage.py',
                 '--kernel-archive', args.kernel_archive,
                 '--device-repo', args.device_repo, '--modules-repo', args.modules_repo,
                 '--cold-staged-kernel', source])
            run(['git', 'apply', '--check', board / 'board-owner.patch'], cwd=source)
            run(['git', 'apply', board / 'board-owner.patch'], cwd=source)
            board_evidence = json.loads((board / 'evidence.json').read_text())
            for path, expected in board_evidence['payload_sha256'].items():
                if gen.sha((source / path).read_bytes()) != expected:
                    raise ValueError('board staged output differs: ' + path)
            manifest['board_patch_sha256'] = gen.sha((board / 'board-owner.patch').read_bytes())
            extra_exports = ('mt6878_cold_board_publish', 'mt6878_cold_board_wait',
                             'mt6878_cold_board_retire')
            extra_objects = (gen.DIR + 'board/mt6878-cold-board.o',)
        objects_dir.mkdir()
        (objects_dir / '.config').write_text(shipping)
        config = [source / 'scripts/config', '--file', objects_dir / '.config']
        for symbol in ENABLE:
            config += ['-e', symbol]
        if args.include_board:
            config += ['-e', 'VIDEO_MT6878_COLD_BOARD']
        run(config)
        make = ['make', '-C', source, f'O={objects_dir}', 'ARCH=arm64', 'LLVM=1', '-j4']
        manifest['compiler'] = subprocess.check_output(['clang', '--version'], text=True).splitlines()[0]
        run([*make, 'olddefconfig'])
        resolved = (objects_dir / '.config').read_text()
        verify_security(shipping, resolved)
        for symbol in (*ENABLE, *SELECTED):
            if f'CONFIG_{symbol}=y' not in resolved.splitlines():
                raise ValueError('actual unresolved Kconfig leaf: ' + symbol)
        if args.include_board and 'CONFIG_VIDEO_MT6878_COLD_BOARD=y' not in resolved.splitlines():
            raise ValueError('actual unresolved Kconfig leaf: VIDEO_MT6878_COLD_BOARD')
        shutil.copyfile(objects_dir / '.config', report / 'isolated.config')
        smoke = gen.load('cold_object_identity', gen.ROOT / 'ci/kernel-object-smoke.py')
        objects = [gen.DIR + unit for unit in evidence['production_units']] + list(PROVIDERS) + list(extra_objects)
        symbols = set()
        for target in objects:
            manifest['current_target'] = target
            run([*make, target])
            artifact = objects_dir / target
            identity = smoke.object_identity(artifact)  # Real AArch64 bitcode or ELF, unchanged ThinLTO.
            symbols.update(defined_symbols(artifact))
            manifest['objects'][target] = {'sha256': gen.sha(artifact.read_bytes()), 'identity': identity}
        for name in (*EXPORTS, *extra_exports):
            if name not in symbols:
                raise ValueError('actual object export/definition missing: ' + name)
        manifest['current_target'] = 'vmlinux'
        run([*make, 'vmlinux'])  # Resolves the real native Kbuild closure, not an isolated smoke stub.
        identity = smoke.object_identity(objects_dir / 'vmlinux')
        if identity.get('format') != 'ELF':
            raise ValueError('linked vmlinux must be actual AArch64 ELF')
        linked = defined_symbols(objects_dir / 'vmlinux')
        for name in (*EXPORTS, *extra_exports):
            if name not in linked or '__ksymtab_' + name not in linked:
                raise ValueError('actual native link lost export: ' + name)
        manifest.update(status='passed-native-link', vmlinux_identity=identity,
                        vmlinux_sha256=gen.sha((objects_dir / 'vmlinux').read_bytes()),
                        config_sha256=gen.sha(resolved.encode()), checked_exports=list((*EXPORTS, *extra_exports)))
    except Exception as error:
        manifest.update(status='failed', error=str(error))
        raise
    finally:
        try:
            stage.verify_prepared(kernel, base, output)
        except Exception as error:
            manifest['input_recheck_error'] = str(error)
            if manifest['status'] != 'failed':
                manifest.update(status='failed', error=str(error))
                raise
        finally:
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
