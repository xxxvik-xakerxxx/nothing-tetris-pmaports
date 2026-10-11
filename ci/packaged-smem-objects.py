#!/usr/bin/env python3
"""Compile the packaged AP-only SMEM integration using existing CI kernel staging."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'patches/modem/drafts/runtime-metadata'))
from package_metadata import build, PREFIX


def main():
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('actual ARM64 C compilation is GitHub CI-only')
    spec = importlib.util.spec_from_file_location('packaged_objects',
        ROOT / 'patches/modem/drafts/runtime-object-ci/check_objects.py')
    staging = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(staging)
    manifest, _, package = staging.plan()
    work = Path('/tmp/tetris-kernel-smoke')
    parent = ROOT / 'out/kernel-object-smoke/runtime-objects.json'
    if json.loads(parent.read_text()).get('status') != 'passed':
        raise ValueError('requires successful current runtime object staging')
    vendor = work / 'vendor-git-source'
    kernel = work / ('linux-' + manifest['kernel']['kernel_commit'])
    output = work / 'objects'
    destination = work / 'packaged-smem'
    destination.mkdir(exist_ok=False)
    archive = subprocess.Popen(['git', '-C', str(vendor), 'archive',
        manifest['vendor_commit'], PREFIX], stdout=subprocess.PIPE)
    unpack = subprocess.run(['tar', '-xf', '-', '-C', str(destination)], stdin=archive.stdout)
    archive.stdout.close()
    if archive.wait() or unpack.returncode:
        raise ValueError('cannot export pinned util sources')
    for name in ('0039-vendor-ccci-util-linux-6.18-api.patch.vendor',
                 '0173-vendor-ccci-smem-map-span.patch.vendor'):
        staging.run(['patch', '--batch', '-p1', '-i', package / name], cwd=destination)
    patch, _ = build(vendor)
    if patch != (package / 'ccci-owned-metadata.overlay').read_text():
        raise ValueError('packaged overlay differs from source generator')
    staging.run(['git', 'apply', '--check', '-'], cwd=destination, input=patch, text=True)
    staging.run(['git', 'apply', '-'], cwd=destination, input=patch, text=True)
    util = destination / PREFIX
    original_vendor = work / 'runtime-vendor'
    objects = ('ccci_util_boot_args.o', 'ccci_util_lib_fo.o', 'ccci_util_lib_main.o',
               'owned_smem_plan.o', 'tetris_runtime_smem/smem.o', 'tetris_runtime_smem/arguments.o')
    report = dict(commit=os.environ.get('GITHUB_SHA'), scope='actual packaged translation units only; no modpost, install or hardware',
                  overlay_sha256=hashlib.sha256(patch.encode()).hexdigest(), status='started')
    target = ROOT / 'out/kernel-object-smoke/packaged-smem.json'
    try:
        staging.run(['make', '-j2', '-C', kernel, 'O=' + str(output), 'M=' + str(util),
            'ARCH=arm64', 'LLVM=1', 'KERNEL_SRC=' + str(kernel), 'KERNEL_OUT=' + str(output),
            'DEVICE_MODULES_PATH=' + str(original_vendor),
            'CONFIG_MTK_ECCCI_DRIVER=m', 'CONFIG_MTK_SECURITY_SW_SUPPORT=n',
            'CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n', 'CONFIG_MTK_AEE_IPANIC=n',
            'KCFLAGS=' + manifest['vendor_kcflags'] +
            ' -I' + str(original_vendor / 'include') +
            ' -DCONFIG_MTK_ECCCI_TETRIS_METADATA_ONLY=1'
            ' -Werror=implicit-function-declaration -Werror=incompatible-pointer-types'
            ' -Werror=int-conversion', *objects])
        symbols = subprocess.check_output(['llvm-nm', '--defined-only',
            *(str(util / name) for name in objects)], text=True)
        for name in ('mtk_ccci_owned_banks_copy', 'mtk_ccci_owned_smem_init',
                     'tetris_smem_create', 'tetris_smem_from_arguments', 'tetris_smem_preview'):
            if not any(line.split()[-1:] == [name] for line in symbols.splitlines()):
                raise ValueError('missing actual integration symbol: ' + name)
        undefined = subprocess.check_output(['llvm-nm', '--undefined-only',
            str(util / 'tetris_runtime_smem/smem.o')], text=True)
        if any(name in undefined for name in ('ioremap', 'iounmap')):
            raise ValueError('plan object unexpectedly contains physical mapping')
        report.update(status='passed', object_sha256={name: staging.sha(util / name) for name in objects})
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        target.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
