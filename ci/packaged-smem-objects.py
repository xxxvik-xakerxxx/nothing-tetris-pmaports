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


def link_private_consumer(staging, smoke, manifest, work, parent, kernel, output,
                          isolated, command, flags, saved, release, report):
    directory = ROOT / 'patches/modem/drafts/runtime-smem-consumer'
    review = staging.review(directory)
    candidate = staging.load('private_smem_consumer', directory / 'check_consumer.py')
    bundles = candidate.build(work / 'vendor-git-source')
    for name, (text, before, _) in bundles.items():
        if text != (directory / name).read_text():
            raise ValueError('private consumer frozen overlay drift: ' + name)
        candidate.apply_check(text, before)
    # Preserve the original 64-object staging and all default profile artifacts.
    vendor = parent / 'consumer-vendor'
    shutil.copytree(work / 'runtime-vendor', vendor,
                    ignore=shutil.ignore_patterns('*.o', '*.ko', '*.cmd', '*.mod',
                                                 '*.mod.c', 'Module.symvers', 'modules.order'))
    for name in ('common.overlay', 'consumer.overlay'):
        staging.run(['git', 'apply', '--check', '-'], cwd=vendor, input=bundles[name][0], text=True)
        staging.run(['git', 'apply', '-'], cwd=vendor, input=bundles[name][0], text=True)
    consumer_manifest = dict(manifest, vendor_kcflags=manifest['vendor_kcflags'] +
                             ' -DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=1')
    staging.compile_objects(work / ('linux-' + manifest['kernel']['kernel_commit']),
                            work / 'objects', vendor, consumer_manifest, smoke)
    report['private_consumer_objects'] = consumer_manifest['object_identities']
    for name, original in bundles['provider.overlay'][1].items():
        relative = name.removeprefix(PREFIX)
        if (isolated / relative).read_text() != original:
            raise ValueError('provider input differs from mapped profile: ' + relative)
    for name, source in bundles['provider.overlay'][2].items():
        (isolated / name.removeprefix(PREFIX)).write_text(source)
    common = vendor / candidate.COMMON
    provider_flags = flags + ' -I' + str(vendor / 'drivers/misc/mediatek/include') + \
        ' -DCONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY=1' \
        ' -DCONFIG_TETRIS_CCCI_SMEM_MAP_ONLY=1 -DCONFIG_TETRIS_CCCI_SMEM_PROVIDER=1'
    staging.run([*command, 'KCFLAGS=' + provider_flags, 'ccci_util_lib.ko'])
    provider = isolated / 'ccci_util_lib.ko'
    exports = isolated / 'Module.symvers'
    symbols = subprocess.check_output(['llvm-nm', '--defined-only', str(provider)], text=True)
    if not re.search(r'\bmtk_ccci_owned_mapped_copy$', symbols, re.M) or \
            not re.search(r'\bmtk_ccci_owned_mapped_copy\b.*\bEXPORT_SYMBOL_GPL\b', exports.read_text()):
        raise ValueError('checked provider missing genuine GPL export')
    if subprocess.check_output(['modinfo', '-F', 'vermagic', str(provider)], text=True).strip() != release or \
            subprocess.check_output(['modinfo', '-F', 'depends', str(provider)], text=True).strip() or \
            subprocess.check_output(['modinfo', '-F', 'license', str(provider)], text=True).strip() != 'GPL':
        raise ValueError('private provider ABI/dependency/license differs from r181')
    binding = parent / 'private-binding'
    binding.mkdir(exist_ok=False)
    for name in ('Kbuild', 'consumer.h', 'private-binding-smoke.c'):
        shutil.copyfile(directory / name, binding / name)
    staging.run([*command[:command.index('M=' + str(isolated))], 'M=' + str(binding),
                 'TETRIS_VENDOR_ROOT=' + str(vendor), 'KBUILD_EXTRA_SYMBOLS=' + str(exports),
                 'KBUILD_MODPOST_WARN=', 'KCFLAGS=' + manifest['vendor_kcflags'] +
                 ' -Werror=implicit-function-declaration -Werror=incompatible-pointer-types'
                 ' -Werror=int-conversion', 'modules'])
    module = binding / 'private-binding-smoke.ko'
    imports = subprocess.check_output(['llvm-nm', '--undefined-only', str(module)], text=True)
    if not re.search(r'\bmtk_ccci_owned_mapped_copy$', imports, re.M):
        raise ValueError('private binding does not use the real provider')
    for forbidden in ('modem_sys', 'ccci_md_alloc', 'ccci_init', 'ccci_md_config',
                      'ioremap_prot', 'iounmap', 'memcpy_fromio', 'memcpy_toio',
                      'arm_smccc_smc', 'arm_smccc_hvc'):
        if re.search(r'\b' + forbidden + r'$', imports, re.M):
            raise ValueError('private copy binding has forbidden dependency: ' + forbidden)
    if subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip() != release or \
            subprocess.check_output(['modinfo', '-F', 'depends', str(module)], text=True).strip() != 'ccci_util_lib' or \
            subprocess.check_output(['modinfo', '-F', 'license', str(module)], text=True).strip() != 'GPL':
        raise ValueError('private binding ABI/provider dependency/license differs')
    for path in (provider, module):
        if smoke.object_identity(path)['machine'] != 'AArch64':
            raise ValueError('private binding module architecture differs')
    shutil.copyfile(provider, saved / 'ccci-util-smem-provider.ko')
    shutil.copyfile(exports, saved / 'smem-provider.Module.symvers')
    shutil.copyfile(module, saved / module.name)
    report['private_smem_binding'] = dict(provider_sha256=staging.sha(provider),
        consumer_sha256=staging.sha(module), provider_symvers_sha256=staging.sha(exports),
        common_header_sha256=staging.sha(common), review_sha256=review,
        vermagic=release, baseline_commit=BASELINE,
        scope='real r181 module binding and private copies only; no full CCCI link, HIF, SMEM access or START')


def link_r181(staging, smoke, manifest, work, package, util, report, gpueb_analysis=False,
              smem_consumer=False):
    """Use actual full-build exports, never the research config or mocked symvers."""
    old_apk = subprocess.check_output(['git', 'show', BASELINE + ':' +
        str((package / 'APKBUILD').relative_to(ROOT))], cwd=ROOT, text=True)
    old_hashes = {name: digest for digest, name in re.findall(
        r'^([0-9a-f]{128})  ([A-Za-z0-9_.-]+)$', smoke.block(old_apk, 'sha512sums'), re.M)}
    old_patches = [name for name in smoke.block(old_apk, 'source').split() if name.endswith('.patch')]
    baseline_package = work / 'r181-package-snapshot'
    baseline_package.mkdir(exist_ok=False)
    (baseline_package / 'APKBUILD').write_text(old_apk)
    for name in (smoke.CONFIG, *old_patches):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
            raise ValueError('unsafe baseline source name')
        source = subprocess.check_output(['git', 'show', BASELINE + ':' +
            str((package / name).relative_to(ROOT))], cwd=ROOT)
        if hashlib.sha512(source).hexdigest() != old_hashes.get(name):
            raise ValueError('r181 snapshot checksum mismatch: ' + name)
        (baseline_package / name).write_bytes(source)
    baseline = smoke.plan(baseline_package)
    if baseline['archive'] != manifest['kernel']['archive']:
        raise ValueError('staged archive cannot supply the original r181 kernel')
    if old_hashes.get(manifest['kernel']['archive']) != manifest['kernel']['archive_sha512']:
        raise ValueError('kernel archive differs from r181')
    with (work / baseline['archive']).open('rb') as stream:
        if hashlib.file_digest(stream, 'sha512').hexdigest() != baseline['archive_sha512']:
            raise ValueError('original r181 archive checksum mismatch')
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
    with tarfile.open(work / baseline['archive']) as archive:
        archive.extractall(parent, filter='data')
    kernel = parent / ('linux-' + baseline['kernel_commit'])
    for name in baseline['patches']:
        flags = ['--fuzz=0'] if name in smoke.STRICT_PATCHES else []
        staging.run(['patch', '--batch', *flags, '-p1', '-d', kernel, '-i', baseline_package / name])
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
    if re.search(r'\btetris_smem_export_mapped_private$', symbols, re.M):
        raise ValueError('AP-only module contains mapped export')
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
    if re.search(r'\btetris_smem_export_mapped_private$', reservation_symbols, re.M):
        raise ValueError('reservation-only consumer contains mapped export')
    if subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip() != release or \
            subprocess.check_output(['modinfo', '-F', 'depends', str(module)], text=True).strip() or \
            subprocess.check_output(['modinfo', '-F', 'license', str(module)], text=True).strip() != 'GPL':
        raise ValueError('reservation module ABI/dependency/license changed')
    shutil.copyfile(module, saved / 'ccci-util-smem-reservation.ko')
    report['reservation_module'] = dict(report['linked_module'], sha256=staging.sha(module),
        scope='exact r181 exports; kernel iomem claims only; no mappings, memory access, NS grant or START')
    staging.run([*command, 'KCFLAGS=' + flags +
        ' -DCONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY=1 -DCONFIG_TETRIS_CCCI_SMEM_INITIAL_READ=1',
        'ccci_util_lib.ko'])
    if b'Tetris CCCI: initial NC read completed' not in module.read_bytes():
        raise ValueError('initial-read consumer missing from linked module')
    initial_symbols = subprocess.check_output(['llvm-nm', '--defined-only', str(module)], text=True)
    for forbidden in ('tetris_smem_map_private', 'tetris_smem_export_mapped_private',
                      'tetris_smem_publish_private', 'tetris_smem_export_private'):
        if re.search(r'\b' + forbidden + r'$', initial_symbols, re.M):
            raise ValueError('initial-read consumer contains mapping transaction: ' + forbidden)
    if subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip() != release or \
            subprocess.check_output(['modinfo', '-F', 'depends', str(module)], text=True).strip() or \
            subprocess.check_output(['modinfo', '-F', 'license', str(module)], text=True).strip() != 'GPL':
        raise ValueError('initial-read module ABI/dependency/license changed')
    shutil.copyfile(module, saved / 'ccci-util-nc-initial-read.ko')
    report['initial_read_module'] = dict(report['linked_module'], sha256=staging.sha(module),
        scope='exact r181 exports; opt-in single NC word read; EL1 and historical boot evidence; no runtime grant or START')
    staging.run([*command, 'KCFLAGS=' + flags +
        ' -DCONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY=1 -DCONFIG_TETRIS_CCCI_SMEM_MAP_ONLY=1',
        'ccci_util_lib.ko'])
    mapped_symbols = subprocess.check_output(['llvm-nm', '--defined-only', str(module)], text=True)
    for required in ('tetris_smem_map_private', 'tetris_smem_export_mapped_private'):
        if not re.search(r'\b' + required + r'$', mapped_symbols, re.M):
            raise ValueError('mapped consumer missing from linked module: ' + required)
    for forbidden in ('tetris_smem_publish_private', 'tetris_smem_export_private',
                      'tetris_smem_slot_init', 'initial_nc_read'):
        if re.search(r'\b' + forbidden + r'$', mapped_symbols, re.M):
            raise ValueError('mapped consumer contains forbidden transaction: ' + forbidden)
    mapped_imports = subprocess.check_output(['llvm-nm', '--undefined-only', str(module)], text=True)
    # Pinned ARM64 io.h lowers ioremap_wc() to ioremap_prot(PROT_NORMAL_NC).
    for required in ('ioremap_prot', 'iounmap'):
        if not re.search(r'\b' + required + r'$', mapped_imports, re.M):
            raise ValueError('mapped consumer missing real mapping boundary: ' + required)
    # The AP tag importer reads its own retained tag buffer in every profile;
    # the SMEM translation unit must contain only map/unmap boundaries.
    smem_imports = subprocess.check_output(['llvm-nm', '--undefined-only',
        str(isolated / 'tetris_runtime_smem/smem.o')], text=True)
    for forbidden in ('readl', 'writel', 'memcpy_fromio', 'memcpy_toio',
                      'arm_smccc_smc', 'arm_smccc_hvc'):
        if re.search(r'\b' + forbidden + r'$', smem_imports, re.M):
            raise ValueError('mapped SMEM contains forbidden access: ' + forbidden)
    if subprocess.check_output(['modinfo', '-F', 'vermagic', str(module)], text=True).strip() != release or \
            subprocess.check_output(['modinfo', '-F', 'depends', str(module)], text=True).strip() or \
            subprocess.check_output(['modinfo', '-F', 'license', str(module)], text=True).strip() != 'GPL':
        raise ValueError('mapped module ABI/dependency/license changed')
    shutil.copyfile(module, saved / 'ccci-util-smem-map-only.ko')
    report['map_only_module'] = dict(report['linked_module'], sha256=staging.sha(module),
        scope='exact r181 exports; opt-in private WC mappings and copied tables; EL1/trustedboot evidence; no SMEM access, publication, runtime grant or START')
    report['r181_kernel_sources'] = baseline['source_sha512']
    if smem_consumer:
        link_private_consumer(staging, smoke, manifest, work, parent, kernel, output,
                              isolated, command, flags, saved, release, report)
    if gpueb_analysis:
        source = ROOT / 'patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c'
        analysis = parent / 'gpueb-analysis'
        analysis.mkdir(exist_ok=False)
        shutil.copyfile(source, analysis / source.name)
        (analysis / 'Makefile').write_text('obj-m += gpueb-flat-analysis.o\n')
        staging.run([*make, 'M=' + str(analysis), 'KBUILD_MODPOST_WARN=',
            'KCFLAGS=-Werror', 'modules'])
        gpu_module = analysis / 'gpueb-flat-analysis.ko'
        if smoke.object_identity(gpu_module)['machine'] != 'AArch64' or \
                subprocess.check_output(['modinfo', '-F', 'vermagic', str(gpu_module)], text=True).strip() != release or \
                subprocess.check_output(['modinfo', '-F', 'depends', str(gpu_module)], text=True).strip() or \
                subprocess.check_output(['modinfo', '-F', 'license', str(gpu_module)], text=True).strip() != 'GPL':
            raise ValueError('GPUEB analysis module ABI/dependency/license mismatch')
        shutil.copyfile(gpu_module, saved / gpu_module.name)
        report['gpueb_analysis_module'] = dict(report['linked_module'],
            sha256=staging.sha(gpu_module), source_sha256=staging.sha(source),
            scope='exact r181 exports; ordinary reserved authenticated DRAM analysis only; no GPU start')


def main():
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('actual ARM64 C compilation is GitHub CI-only')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--link-r181', action='store_true')
    parser.add_argument('--gpueb-analysis', action='store_true')
    parser.add_argument('--smem-consumer', action='store_true')
    args = parser.parse_args()
    if args.gpueb_analysis and not args.link_r181:
        parser.error('--gpueb-analysis requires exact --link-r181 exports')
    if args.smem_consumer and not args.link_r181:
        parser.error('--smem-consumer requires exact --link-r181 exports')
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
            link_r181(staging, smoke, manifest, work, package, util, report,
                       args.gpueb_analysis, args.smem_consumer)
            report['scope'] = 'actual packaged ARM64 objects and module linked against real r181 exports; no installation or hardware test'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        target.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
