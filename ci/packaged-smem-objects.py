#!/usr/bin/env python3
"""Compile the packaged AP-only SMEM integration using existing CI kernel staging."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'patches/modem/drafts/runtime-metadata'))
from package_metadata import build, PREFIX

BASELINE = 'e0c67c561ff7c1a0472da851edfafd5a0abb6cec'
EVIDENCE_ID = 11695564086
EVIDENCE_SHA256 = 'ff350521ca395343c62387e716c2b828e8a68b2606fc1840b7e1e6085d412442'


def link_r181(staging, smoke, manifest, work, package, util, report):
    """Use actual full-build exports, never the research config or mocked symvers."""
    old_apk = subprocess.check_output(['git', 'show', BASELINE + ':' +
        str((package / 'APKBUILD').relative_to(ROOT))], cwd=ROOT, text=True)
    old_hashes = {name: digest for digest, name in re.findall(
        r'^([0-9a-f]{128})  ([A-Za-z0-9_.-]+)$', smoke.block(old_apk, 'sha512sums'), re.M)}
    old_patches = [name for name in smoke.block(old_apk, 'source').split() if name.endswith('.patch')]
    if old_patches != manifest['kernel']['patches']:
        raise ValueError('shipping kernel patch selection changed since r181')
    for name, digest in manifest['kernel']['source_sha512'].items():
        if old_hashes.get(name) != digest:
            raise ValueError('shipping kernel source differs from r181: ' + name)
    if old_hashes.get(manifest['kernel']['archive']) != manifest['kernel']['archive_sha512']:
        raise ValueError('kernel archive differs from r181')
    for name in ('0039-vendor-ccci-util-linux-6.18-api.patch.vendor',
                 '0173-vendor-ccci-smem-map-span.patch.vendor'):
        if hashlib.sha512((package / name).read_bytes()).hexdigest() != old_hashes.get(name):
            raise ValueError('vendor util adaptation differs from r181: ' + name)
    token = os.environ.get('GH_TOKEN')
    if not token:
        raise ValueError('missing read-only CI artifact access token')
    evidence = work / 'r181-kernel-evidence.zip'
    # curl does not forward Authorization across the artifact redirect's host.
    subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
        '--header', 'Authorization: Bearer ' + token, '--output', str(evidence),
        f'https://api.github.com/repos/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/artifacts/{EVIDENCE_ID}/zip'], check=True)
    if staging.sha(evidence) != EVIDENCE_SHA256:
        raise ValueError('full-build kernel evidence archive hash mismatch')
    with zipfile.ZipFile(evidence) as archive:
        identity = json.loads(archive.read('manifest.json'))
        config = archive.read('.config')
        exports = archive.read('Module.symvers')
    if identity['source_commit'] != BASELINE or identity['kernel_release'] != '6.18.0':
        raise ValueError('wrong full-build source or kernel release')
    for name, data in (('.config', config), ('Module.symvers', exports)):
        if hashlib.sha256(data).hexdigest() != identity['sha256'][name]:
            raise ValueError('full-build evidence member hash mismatch: ' + name)
    parent = work / 'r181-module'
    parent.mkdir(exist_ok=False)
    with tarfile.open(work / manifest['kernel']['archive']) as archive:
        archive.extractall(parent, filter='data')
    kernel = parent / ('linux-' + manifest['kernel']['kernel_commit'])
    for name in manifest['kernel']['patches']:
        flags = ['--fuzz=0'] if name in smoke.STRICT_PATCHES else []
        staging.run(['patch', '--batch', *flags, '-p1', '-d', kernel, '-i', package / name])
    output = parent / 'kernel-output'
    output.mkdir()
    (output / '.config').write_bytes(config)
    make = ['make', '-j2', '-C', kernel, 'O=' + str(output), 'ARCH=arm64', 'LLVM=1']
    staging.run([*make, 'olddefconfig', 'modules_prepare'])
    if (output / '.config').read_bytes() != config:
        difference = ''.join(difflib.unified_diff(config.decode().splitlines(True),
            (output / '.config').read_text().splitlines(True), fromfile='r181.full-build.config',
            tofile='prepared.config'))
        (ROOT / 'out/kernel-object-smoke/r181-config.diff').write_text(difference)
        print(difference, flush=True)
        raise ValueError('prepared config differs from the installed full-build config')
    if (output / 'include/config/kernel.release').read_text().strip() != identity['kernel_release']:
        raise ValueError('prepared kernel release differs from full-build evidence')
    (output / 'Module.symvers').write_bytes(exports)
    isolated = parent / 'util'
    isolated.mkdir()
    for source in util.rglob('*'):
        if source.is_file() and (source.suffix in ('.c', '.h') or source.name == 'Makefile'):
            target = isolated / source.relative_to(util)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    vendor = work / 'runtime-vendor'
    flags = manifest['vendor_kcflags'] + ' -I' + str(vendor / 'include') + \
        ' -DCONFIG_MTK_ECCCI_TETRIS_METADATA_ONLY=1' \
        ' -Werror=implicit-function-declaration -Werror=incompatible-pointer-types' \
        ' -Werror=int-conversion'
    command = [*make, 'M=' + str(isolated), 'KERNEL_SRC=' + str(kernel),
        'KERNEL_OUT=' + str(output), 'DEVICE_MODULES_PATH=' + str(vendor),
        'CONFIG_MTK_ECCCI_DRIVER=m', 'CONFIG_MTK_SECURITY_SW_SUPPORT=n',
        'CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n', 'CONFIG_MTK_AEE_IPANIC=n',
        'KBUILD_MODPOST_WARN=']
    staging.run([*command, 'KCFLAGS=' + flags, 'ccci_util_lib.ko'])
    module = isolated / 'ccci_util_lib.ko'
    symbols = subprocess.check_output(['llvm-nm', '--defined-only', str(module)], text=True)
    for forbidden in ('map', 'publish', 'export'):
        if re.search(r'\btetris_smem_' + forbidden + r'_private$', symbols, re.M):
            raise ValueError('AP-only module contains physical SMEM transaction')
    for required in ('mtk_ccci_owned_smem_init', 'tetris_smem_boot_decode'):
        if not re.search(r'\b' + required + r'$', symbols, re.M):
            raise ValueError('SMEM integration missing from linked module: ' + required)
    release = subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip()
    if not release.startswith(identity['kernel_release'] + ' '):
        raise ValueError('linked module vermagic differs from installed kernel')
    if subprocess.check_output(['modinfo', '-F', 'depends', str(module)], text=True).strip():
        raise ValueError('AP-only module has unexpected external module dependencies')
    if subprocess.check_output(['modinfo', '-F', 'license', str(module)], text=True).strip() != 'GPL':
        raise ValueError('unexpected module license')
    staging.run(['llvm-readelf', '-h', module])
    if smoke.object_identity(module)['machine'] != 'AArch64':
        raise ValueError('wrong linked module architecture')
    saved = ROOT / 'out/kernel-object-smoke/packaged-smem-r181'
    saved.mkdir(exist_ok=False)
    shutil.copyfile(module, saved / module.name)
    report['linked_module'] = dict(sha256=staging.sha(module), vermagic=release,
        baseline_commit=BASELINE, evidence_archive_sha256=EVIDENCE_SHA256,
        config_sha256=identity['sha256']['.config'], symvers_sha256=identity['sha256']['Module.symvers'],
        scope='linked against real r181 full-build exports; not loaded or hardware validated')
    # Kbuild command tracking recompiles the same isolated sources for the
    # opt-in resource-only consumer. No shipping configuration is modified.
    staging.run([*command, 'KCFLAGS=' + flags + ' -DCONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY=1',
                 'ccci_util_lib.ko'])
    reservation_symbols = subprocess.check_output(['llvm-nm', '--defined-only', str(module)], text=True)
    for required in ('tetris_smem_extent_preview', 'tetris_smem_reserve_extents',
                     'tetris_smem_release_extents'):
        if not re.search(r'\b' + required + r'$', reservation_symbols, re.M):
            raise ValueError('reservation consumer missing from linked module: ' + required)
    for forbidden in ('map', 'publish', 'export'):
        if re.search(r'\btetris_smem_' + forbidden + r'_private$', reservation_symbols, re.M):
            raise ValueError('reservation-only consumer contains physical SMEM transaction')
    if subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip() != release or \
            subprocess.check_output(['modinfo', '-F', 'depends', str(module)], text=True).strip() or \
            subprocess.check_output(['modinfo', '-F', 'license', str(module)], text=True).strip() != 'GPL':
        raise ValueError('reservation module ABI/dependency/license changed')
    shutil.copyfile(module, saved / 'ccci-util-smem-reservation.ko')
    report['reservation_module'] = dict(report['linked_module'], sha256=staging.sha(module),
        scope='exact r181 exports; kernel iomem claims only; no mappings, memory access, NS grant or START')


def main():
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('actual ARM64 C compilation is GitHub CI-only')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--link-r181', action='store_true')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('packaged_objects',
        ROOT / 'patches/modem/drafts/runtime-object-ci/check_objects.py')
    staging = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(staging)
    manifest, smoke, package = staging.plan()
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
    evidence = util / 'smem_boot_evidence'
    for name in ('boot_evidence.c', 'boot_evidence.h'):
        if (evidence / name).read_bytes() != (ROOT / 'patches/modem/drafts/smem-boot-evidence' / name).read_bytes():
            raise ValueError('packaged decoder differs from reviewed body: ' + name)
    original_vendor = work / 'runtime-vendor'
    objects = ('ccci_util_boot_args.o', 'ccci_util_lib_fo.o', 'ccci_util_lib_main.o',
               'owned_smem_plan.o', 'tetris_runtime_smem/smem.o', 'tetris_runtime_smem/arguments.o',
               'smem_boot_evidence/boot_evidence.o', 'smem_reservation.o', 'smem_extent_preview.o')
    report = dict(commit=os.environ.get('GITHUB_SHA'), scope='actual packaged translation units only; no modpost, install or hardware',
                  overlay_sha256=hashlib.sha256(patch.encode()).hexdigest(), status='started')
    report['boot_evidence_source_sha256'] = {name: staging.sha(evidence / name)
                                           for name in ('boot_evidence.c', 'boot_evidence.h')}
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
                     'tetris_smem_create', 'tetris_smem_from_arguments', 'tetris_smem_preview',
                     'tetris_smem_boot_decode', 'tetris_smem_extent_preview',
                     'tetris_smem_reserve_extents', 'tetris_smem_release_extents'):
            if not any(line.split()[-1:] == [name] for line in symbols.splitlines()):
                raise ValueError('missing actual integration symbol: ' + name)
        undefined = subprocess.check_output(['llvm-nm', '--undefined-only',
            str(util / 'tetris_runtime_smem/smem.o')], text=True)
        if any(name in undefined for name in ('ioremap', 'iounmap')):
            raise ValueError('plan object unexpectedly contains physical mapping')
        report.update(status='passed', object_sha256={name: staging.sha(util / name) for name in objects})
        if args.link_r181:
            link_r181(staging, smoke, manifest, work, package, util, report)
            report['scope'] = 'actual packaged ARM64 objects and module linked against real r181 exports; no installation or hardware test'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        target.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
