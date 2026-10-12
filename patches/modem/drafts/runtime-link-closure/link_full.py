#!/usr/bin/env python3
"""Source checks locally; full OWNER+CONSUMER module linkage only in GitHub CI."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
VENDOR = 'ee2be53cb75670b548948636a0db1d1ff112bf12'
LINUX = 'd84b264a54a37611f2f46bc19363cb9b41606205'
BASELINE = 'e0c67c561ff7c1a0472da851edfafd5a0abb6cec'
CONFIG_SHA = 'edcbdf45d3201aef8ab71157bb485c074bc5c3457f564f0341a7eb410b9382a2'
EXPORTS_SHA = '2e58e05288219f07094e88da49b9f12b1c06d2bf5875e87e1f557bc36c4e7cf3'
PREFIX = 'drivers/misc/mediatek/'
BACKEND = 'drivers/soc/mediatek/mt6878-ccci-start.c'
HEADER = 'include/linux/soc/mediatek/mt6878_ccci_start.h'
BACKEND_EXPORTS = ('mt6878_ccci_start_alloc', 'mt6878_ccci_first_start',
                   'mt6878_ccci_start_result')
MODULES = ('eccci/ccci_md_all', 'eccci/ccci_auxadc', 'eccci/hif/ccci_ccif',
           'eccci/hif/ccci_dpmaif', 'eccci/hif/ccci_cldma',
           'eccci/fsm/ccci_fsm_scp', 'ccmni/ccmni', 'rps/rps_perf')
PROVIDER_EXPORT = 'mtk_ccci_owned_mapped_copy'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, **kwargs):
    return subprocess.run(list(map(str, command)), check=True, **kwargs)


def output(command):
    return subprocess.check_output(list(map(str, command)), text=True).strip()


def symvers(path):
    result = {}
    for row in path.read_text().splitlines():
        fields = row.split()
        if len(fields) not in (4, 5) or not re.fullmatch(r'0x[0-9a-fA-F]{8}', fields[0]):
            raise ValueError('malformed genuine export table: ' + str(path))
        if fields[1] in result:
            raise ValueError('duplicate export: ' + fields[1])
        result[fields[1]] = fields
    if not result:
        raise ValueError('empty export table: ' + str(path))
    return result


def backend_sources():
    """Extract the two complete new files via git apply, from the r181 commit."""
    package = 'pmaports/device/testing/linux-postmarketos-mediatek-mt6878/'
    patch = output(['git', '-C', ROOT, 'show', BASELINE + ':' + package +
                    '0117-soc-mediatek-mt6878-ccci-first-start-backend.patch']) + '\n'
    sections = re.split(r'(?=^diff --git )', patch, flags=re.M)
    selected = ''.join(section for section in sections
                       if any(section.startswith(f'diff --git a/{name} b/{name}\n')
                              for name in (BACKEND, HEADER)))
    with tempfile.TemporaryDirectory(prefix='ccci-link-backend-') as temp:
        run(['git', 'apply', '--check', '-'], cwd=temp, input=selected, text=True)
        run(['git', 'apply', '-'], cwd=temp, input=selected, text=True)
        sources = {name: (Path(temp) / name).read_bytes() for name in (BACKEND, HEADER)}
    code = sources[BACKEND].decode()
    for symbol in BACKEND_EXPORTS:
        if f'EXPORT_SYMBOL_GPL({symbol});' not in code:
            raise ValueError('backend export drift: ' + symbol)
    if any(token in code for token in ('module_init(', 'module_platform_driver(', 'subsys_initcall(')):
        raise ValueError('backend gained an automatic entry point')
    return sources


def stage(vendor, destination, report):
    staging = load('link_full_staging', HERE.parent / 'runtime-object-ci/check_objects.py')
    manifest, smoke, package = staging.plan()
    if manifest['vendor_commit'] != VENDOR or manifest['kernel']['kernel_commit'] != LINUX:
        raise ValueError('source pins differ')
    staging.stage_vendor(vendor, destination, package, manifest)
    consumer_dir = HERE.parent / 'runtime-smem-consumer'
    report['consumer_review_sha256'] = staging.review(consumer_dir)
    consumer = load('link_full_consumer', consumer_dir / 'check_consumer.py')
    bundles = consumer.build(vendor)
    for name, (patch, before, _) in bundles.items():
        if patch != (consumer_dir / name).read_text():
            raise ValueError('consumer/provider generation drift: ' + name)
        consumer.apply_check(patch, before)
    for name in ('common.overlay', 'consumer.overlay'):
        patch = bundles[name][0]
        run(['git', 'apply', '--check', '-'], cwd=destination, input=patch, text=True)
        run(['git', 'apply', '-'], cwd=destination, input=patch, text=True)
    # Preserve the frozen public/private registration and lifecycle denials.
    for name, expected in bundles['consumer.overlay'][2].items():
        if (destination / name).read_text() != expected:
            raise ValueError('complete consumer source differs: ' + name)
    report['vendor_source_sha256'] = {
        str(path.relative_to(destination)): sha(path)
        for path in sorted(destination.rglob('*'))
        if path.is_file() and not path.is_symlink() and
        (str(path.relative_to(destination)).startswith(PREFIX) or
         str(path.relative_to(destination)).startswith('include/'))}
    report['vendor_prepare'] = manifest['vendor_prepare']
    report['frozen_reviews'] = manifest['frozen_reviews']
    report['overlays_sha256'] = manifest['overlays_sha256']
    report['package_sha256'] = manifest['package_sha256']
    return manifest, smoke


def native_symbols(path, option):
    return {line.split()[-1] for line in output(['llvm-nm', option, path]).splitlines()
            if line.split()}


def module_identity(path, smoke, vermagic):
    identity = smoke.object_identity(path)
    if identity['machine'] != 'AArch64':
        raise ValueError('wrong module architecture: ' + str(path))
    values = {field: output(['modinfo', '-F', field, path])
              for field in ('name', 'vermagic', 'license', 'depends')}
    if values['vermagic'] != vermagic or values['license'] != 'GPL':
        raise ValueError('wrong module ABI/license: ' + str(path))
    return dict(identity, **values, sha256=sha(path))


def dependency_names(value):
    return {name.replace('-', '_') for name in value.split(',') if name}


def logged_build(command, log_path, report):
    with log_path.open('w') as log:
        result = subprocess.run(list(map(str, command)), stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        report['link_errors'] = [line for line in log_path.read_text().splitlines()
                                 if 'ERROR:' in line or 'error:' in line or 'undefined!' in line]
        raise ValueError('strict build failed; see ' + str(log_path))


def build_ci(args, report):
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('full C compilation/linkage is GitHub CI-only')
    for key in ('KBUILD_MODPOST_WARN', 'KBUILD_MODPOST_NOFINAL', 'KBUILD_MODPOST_SKIP',
                'KBUILD_EXTRA_SYMBOLS', 'KBUILD_KCONFIG', 'KCONFIG_CONFIG', 'MAKEFLAGS'):
        if os.environ.get(key):
            raise ValueError('inherited build override forbidden: ' + key)
    work = args.work.resolve()
    parent = work / 'r181-module'
    kernel = parent / ('linux-' + LINUX)
    configured = parent / 'kernel-output'
    provider = parent / 'util'
    evidence = json.loads((ROOT / 'out/kernel-object-smoke/packaged-smem.json').read_text())
    binding = evidence.get('private_smem_binding', {})
    if evidence.get('status') != 'passed' or binding.get('baseline_commit') != BASELINE:
        raise ValueError('requires completed --link-r181 --smem-consumer evidence')
    if sha(configured / '.config') != CONFIG_SHA or sha(configured / 'Module.symvers') != EXPORTS_SHA:
        raise ValueError('requires unchanged genuine full-build r181 config and exports')
    for path, key in ((provider / 'ccci_util_lib.ko', 'provider_sha256'),
                      (provider / 'Module.symvers', 'provider_symvers_sha256')):
        if sha(path) != binding.get(key):
            raise ValueError('provider differs from successful private-copy binding: ' + str(path))
    provider_exports = symvers(provider / 'Module.symvers')
    if PROVIDER_EXPORT not in provider_exports or provider_exports[PROVIDER_EXPORT][3] != 'EXPORT_SYMBOL_GPL':
        raise ValueError('genuine checked provider export missing')
    if any(Path(row[2]).name != 'ccci_util_lib' for row in provider_exports.values()):
        raise ValueError('provider table contains unrelated exports')
    native_exports = symvers(configured / 'Module.symvers')
    if any(symbol in native_exports for symbol in BACKEND_EXPORTS):
        raise ValueError('unexpected first-start exports in r181 baseline')
    sources = backend_sources()
    for name, data in sources.items():
        if (kernel / name).read_bytes() != data:
            raise ValueError('r181 backend/header source drift: ' + name)
    report.update(config_sha256=CONFIG_SHA, kernel_symvers_sha256=EXPORTS_SHA,
                  provider=binding, backend_source_sha256={name: hashlib.sha256(data).hexdigest()
                                                          for name, data in sources.items()})
    destination = args.destination.resolve()
    if not report.get('destination_created') or not destination.is_dir():
        raise ValueError('missing owned failure-report destination')
    vendor = destination / 'vendor'
    manifest, smoke = stage(args.vendor.resolve(), vendor, report)
    if report['consumer_review_sha256'] != binding['review_sha256'] or \
            sha(vendor / PREFIX / 'include/mt-plat/tetris_ccci_smem.h') != binding['common_header_sha256']:
        raise ValueError('provider/consumer reviewed ABI differs')
    report['provider_identity'] = module_identity(provider / 'ccci_util_lib.ko', smoke, binding['vermagic'])
    backend = destination / 'backend'
    backend.mkdir()
    shutil.copyfile(HERE / 'backend.Kbuild', backend / 'Kbuild')
    shutil.copyfile(kernel / BACKEND, backend / 'mt6878-ccci-start.c')
    make = ['make', '-j2', '-C', kernel, 'O=' + str(configured), 'ARCH=arm64', 'LLVM=1',
            'KBUILD_MODPOST_WARN=', 'KBUILD_MODPOST_NOFINAL=', 'KBUILD_MODPOST_SKIP=']
    logged_build([*make, 'M=' + str(backend), 'KBUILD_EXTRA_SYMBOLS=', 'KCFLAGS=-Werror', 'modules'],
                 destination / 'backend-link.log', report)
    backend_table = symvers(backend / 'Module.symvers')
    if set(backend_table) != set(BACKEND_EXPORTS):
        raise ValueError('real backend export set differs')
    report['backend'] = module_identity(backend / 'mt6878-ccci-start.ko', smoke, binding['vermagic'])
    if report['backend']['depends']:
        raise ValueError('backend unexpectedly requires another module')
    report['backend_symvers_sha256'] = sha(backend / 'Module.symvers')
    link = destination / 'modules'
    link.mkdir()
    shutil.copyfile(HERE / 'Kbuild', link / 'Kbuild')
    for name in ('eccci', 'ccmni', 'rps'):
        (link / name).symlink_to(vendor / PREFIX / name, target_is_directory=True)
    flags = manifest['vendor_kcflags'] + ' -I' + str(vendor / 'include') + \
        ' -DCONFIG_MTK_ECCCI_TETRIS_OWNER=1 -DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=1' \
        ' -Werror=implicit-function-declaration -Werror=incompatible-pointer-types -Werror=int-conversion'
    command = [*make, 'M=' + str(link), 'KERNEL_SRC=' + str(kernel),
               'KERNEL_OUT=' + str(configured), 'DEVICE_MODULES_PATH=' + str(vendor),
               'CONFIG_ARM64=y', 'CONFIG_MTK_ECCCI_DRIVER=m', 'CONFIG_MTK_ECCCI_TETRIS_OWNER=y',
               'CONFIG_MTK_NET_CCMNI=m', 'CONFIG_MTK_NET_RPS=m',
               'CONFIG_DEVICE_MODULES_MEDIATEK_MT6577_AUXADC=m',
               'CONFIG_MTK_SECURITY_SW_SUPPORT=n', 'CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n',
               'CONFIG_MTK_AEE_IPANIC=n', 'KCFLAGS=' + flags,
               'KBUILD_EXTRA_SYMBOLS=' + str(provider / 'Module.symvers') + ' ' +
               str(backend / 'Module.symvers'), 'modules']
    report['command'] = list(map(str, command))
    # Preserve the first compiler/modpost error, including unresolved native symbols.
    logged_build(command, destination / 'full-link.log', report)
    exports = symvers(link / 'Module.symvers')
    modules = {name: module_identity(link / (name + '.ko'), smoke, binding['vermagic'])
               for name in MODULES}
    report['modules'] = modules
    report['full_symvers_sha256'] = sha(link / 'Module.symvers')
    core = link / 'eccci/ccci_md_all.ko'
    imports = native_symbols(core, '--undefined-only')
    if not set((*BACKEND_EXPORTS, PROVIDER_EXPORT)) <= imports:
        raise ValueError('complete OWNER+CONSUMER native dependencies not retained')
    for symbol in ('ccci_tetris_owner_bind', 'ccci_tetris_register_prepared'):
        if symbol not in exports or Path(exports[symbol][2]).name != 'ccci_md_all':
            raise ValueError('owner/preparation module export missing: ' + symbol)
    deps = dependency_names(modules['eccci/ccci_md_all']['depends'])
    if not {'ccci_util_lib', 'mt6878_ccci_start', 'ccmni', 'ccci_auxadc'} <= deps:
        raise ValueError('core is missing genuine module dependencies')
    for key, symbols in manifest['required_defined_symbols'].items():
        defined = native_symbols(vendor / PREFIX / key, '--defined-only')
        if not set(symbols) <= defined:
            raise ValueError('owner/private preparation objects missing: ' + key)
    tables = (native_exports, provider_exports, backend_table, exports)
    report['imports'] = {}
    for name in MODULES:
        required = native_symbols(link / (name + '.ko'), '--undefined-only')
        owners = {symbol: [table[symbol][2] for table in tables if symbol in table]
                  for symbol in sorted(required)}
        if any(len(matches) != 1 for matches in owners.values()):
            raise ValueError('missing or ambiguous genuine export in ' + name)
        report['imports'][name] = owners
    if sha(configured / '.config') != CONFIG_SHA or sha(configured / 'Module.symvers') != EXPORTS_SHA:
        raise ValueError('r181 baseline changed during link')
    if sha(provider / 'ccci_util_lib.ko') != binding['provider_sha256']:
        raise ValueError('provider changed during link')
    artifacts = destination / 'artifacts'
    artifacts.mkdir()
    for name in MODULES:
        target = artifacts / (name + '.ko')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(link / (name + '.ko'), target)
    for directory, label, module in ((provider, 'provider', 'ccci_util_lib.ko'),
                                     (backend, 'backend', 'mt6878-ccci-start.ko')):
        target = artifacts / label
        target.mkdir()
        shutil.copyfile(directory / module, target / module)
        shutil.copyfile(directory / 'Module.symvers', target / 'Module.symvers')
    shutil.copyfile(link / 'Module.symvers', artifacts / 'Module.symvers')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--source-check', action='store_true')
    parser.add_argument('--work', type=Path, default=Path('/tmp/tetris-kernel-smoke'))
    parser.add_argument('--destination', type=Path, default=Path('/tmp/tetris-ccci-full-link'))
    args = parser.parse_args()
    report = dict(status='started', vendor_commit=VENDOR, linux_commit=LINUX,
                  baseline_commit=BASELINE, scope='full real modules; no load, DT, HIF or START execution',
                  helper_sha256=sha(Path(__file__)), kbuild_sha256=sha(HERE / 'Kbuild'),
                  backend_kbuild_sha256=sha(HERE / 'backend.Kbuild'))
    if args.source_check:
        with tempfile.TemporaryDirectory(prefix='ccci-link-source-') as temp:
            stage(args.vendor.resolve(), Path(temp) / 'vendor', report)
            backend_sources()
        print('Source-only complete stack and exact r181 backend PASS; full link remains CI-pending')
        return
    try:
        args.destination = args.destination.resolve()
        args.destination.mkdir(parents=True, exist_ok=False)
        report['destination_created'] = True
        build_ci(args, report)
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        if report.get('destination_created'):
            (args.destination / 'full-link.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
