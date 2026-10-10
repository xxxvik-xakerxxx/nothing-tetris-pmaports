#!/usr/bin/env python3
"""Reuse the research kernel staging; compile the real frozen vendor closure in CI."""
import argparse
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREFIX = 'drivers/misc/mediatek/'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(directory):
    manifest = directory / 'REVIEW.sha256'
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)', line)
        if not match or sha(directory / match[2]) != match[1]:
            raise ValueError(f'frozen manifest mismatch: {directory.name}: {line}')
    return sha(manifest)


def plan():
    staging = json.loads((HERE / 'STAGING.json').read_text())
    if set(staging['objects']) != {'eccci', 'ccmni', 'ccci_util'}:
        raise ValueError('unexpected external Kbuild roots')
    for objects in staging['objects'].values():
        if not objects or len(set(objects)) != len(objects):
            raise ValueError('empty or duplicate object list')
        for name in objects:
            if not re.fullmatch(r'(?:[a-z0-9_]+/)?[a-z0-9_]+\.o', name):
                raise ValueError('unsafe object path')
    smoke = load('runtime_kernel_smoke', ROOT / 'ci/kernel-object-smoke.py')
    kernel_plan = smoke.plan(ROOT / smoke.PACKAGE)
    package = ROOT / smoke.PACKAGE
    apk = (package / 'APKBUILD').read_text()
    pins = re.findall(r'^_devmods_commit="([a-f0-9]{40})"$', apk, re.M)
    if pins != [staging['vendor_commit']]:
        raise ValueError('vendor package/fixture pin mismatch')
    prepare = apk.split('prepare() {', 1)[1].split('\n}\n', 1)[0]
    patches = re.findall(r'patch -p1 -d "\$_devmods_dir" \\\n\s*< "\$srcdir"/([\w.-]+\.patch\.vendor)', prepare)
    calls = re.findall(r'patch[^\n]*"\$_devmods_dir"', prepare)
    if not patches or len(patches) != len(calls) or len(set(patches)) != len(patches):
        raise ValueError('unsupported vendor prepare recipe; review application order')
    checksums = dict((name, digest) for digest, name in re.findall(
        r'^([0-9a-f]{128})  ([A-Za-z0-9_.-]+)$', smoke.block(apk, 'sha512sums'), re.M))
    for name in patches:
        if hashlib.sha512((package / name).read_bytes()).hexdigest() != checksums.get(name):
            raise ValueError(f'package vendor checksum mismatch: {name}')
    flags_body = re.search(r'^_vendor_kcflags\(\) \{\n(.*?)^\}', apk, re.M | re.S)
    if not flags_body:
        raise ValueError('missing shipping vendor flags')
    body = flags_body[1]
    if not re.fullmatch(r"\s*printf '%s'\s*\\\n(?:\s*'[^'\n]+'\s*\\?\n)+", body):
        raise ValueError('vendor flags are no longer a literal printf; review needed')
    flags = ''.join(re.findall(r"'(-[^']*)'", body))
    staging.update(kernel=kernel_plan, vendor_prepare=patches, vendor_kcflags=flags,
        package_sha256=sha(package / 'APKBUILD'), staging_sha256=sha(HERE / 'STAGING.json'),
        frozen_reviews={name: review(HERE.parent / name)
                        for name in ('runtime-ports', 'runtime-prepare', 'runtime-lifecycle')})
    return staging, smoke, package


def run(command, **kwargs):
    print('+', ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def check_generated(name, generated, frozen, diagnostics, manifest):
    record = {
        'generated_sha256': hashlib.sha256(generated.encode()).hexdigest(),
        'frozen_sha256': hashlib.sha256(frozen.encode()).hexdigest(),
        'status': 'passed' if generated == frozen else 'failed',
    }
    manifest.setdefault('generation_reviews', {})[name] = record
    if generated == frozen:
        return
    diagnostics.mkdir(parents=True, exist_ok=True)
    for suffix, text in (('generated.patch', generated), ('frozen.patch', frozen),
        ('diff', ''.join(difflib.unified_diff(frozen.splitlines(True),
            generated.splitlines(True), fromfile=f'{name}.frozen', tofile=f'{name}.generated')))):
        target = diagnostics / f'{name}.{suffix}'
        target.write_text(text)
        record[suffix] = str(target)
    raise ValueError(f'regenerated {name} differs from frozen reviewed patch; '
                     f'exact diagnostic diff: {diagnostics / (name + ".diff")}')


def stage_vendor(vendor, destination, package, manifest, diagnostics=None):
    """Whole exact git snapshot, shipping prepare order, then all three overlays."""
    prepare = load('runtime_prepare_full_stack', HERE.parent / 'runtime-prepare/check_prepare.py')
    generated, _, expected = prepare.build(vendor)
    frozen = (HERE.parent / 'runtime-prepare/runtime-prepare.patch.vendor').read_text()
    diagnostics = diagnostics or destination.parent / 'runtime-generation-diagnostics'
    check_generated('prepare', generated, frozen, diagnostics, manifest)
    ports = load('runtime_ports_full_stack', HERE.parent / 'runtime-ports/check_runtime_ports.py')
    runtime = ports.integration(vendor)
    check_generated('runtime-ports', runtime,
        (HERE.parent / 'runtime-ports/runtime-ports.patch.vendor').read_text(), diagnostics, manifest)
    owner = load('runtime_transport_owner', ROOT / 'patches/modem/check_transport_owner.py')
    destination.mkdir(exist_ok=False)
    archive = destination.parent / 'vendor-source.tar'
    run(['git', '-C', vendor, 'archive', '--format=tar', manifest['vendor_commit'], '-o', archive])
    with tarfile.open(archive) as source:
        source.extractall(destination, filter='data')
    archive.unlink()
    for name in manifest['vendor_prepare']:
        # Same full shipping prepare recipe, not selected mocked/header fragments.
        run(['patch', '--batch', '-p1', '-d', destination, '-i', package / name])
    bundles = [('owner', owner.bundle()), ('runtime-ports', runtime), ('runtime-prepare', frozen)]
    for name, patch in bundles:
        run(['git', 'apply', '--check', '-'], cwd=destination, input=patch, text=True)
        run(['git', 'apply', '-'], cwd=destination, input=patch, text=True)
    for name, text in expected.items():
        if (destination / name).read_text() != text:
            raise ValueError(f'full installed adaptation differs from frozen checker: {name}')
    lifecycle = load('runtime_lifecycle_full_stack', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
    lifecycle_patch, old, new = lifecycle.build(vendor)
    frozen_lifecycle = (HERE.parent / 'runtime-lifecycle/runtime-lifecycle.patch.vendor').read_text()
    check_generated('runtime-lifecycle', lifecycle_patch, frozen_lifecycle, diagnostics, manifest)
    source = destination / lifecycle.SOURCE
    if source.read_text() != old:
        raise ValueError('lifecycle input differs from exact prepared source')
    # The original three-overlay equality check above MUST precede this overlay.
    run(['git', 'apply', '--check', '-'], cwd=destination, input=frozen_lifecycle, text=True)
    run(['git', 'apply', '-'], cwd=destination, input=frozen_lifecycle, text=True)
    if source.read_text() != new:
        raise ValueError('staged lifecycle source differs from reviewed complete-stack bytes')
    bundles.append(('runtime-lifecycle', frozen_lifecycle))
    manifest['lifecycle_source_sha256'] = sha(source)
    manifest['overlays_sha256'] = {name: hashlib.sha256(patch.encode()).hexdigest()
                                  for name, patch in bundles}
    manifest['compiled_source_sha256'] = {
        str(path.relative_to(destination)): sha(path)
        for path in sorted(destination.rglob('*'))
        if path.is_file() and not path.is_symlink() and
           (str(path.relative_to(destination)).startswith(PREFIX) or
            str(path.relative_to(destination)).startswith('include/'))
    }


def compile_objects(kernel, output, vendor, manifest, smoke):
    config = (output / '.config').read_text().splitlines()
    for name, value in manifest['required_kernel'].items():
        if f'CONFIG_{name}={value}' not in config:
            raise ValueError(f'missing research output dependency: {name}={value}')
    if not (kernel / 'include/linux/soc/mediatek/mt6878_ccci_start.h').is_file():
        raise ValueError('packaged first-start public header missing')
    if list(vendor.rglob('*.o')) or list(vendor.rglob('*.ko')):
        raise ValueError('vendor staging must be fresh: no reused objects or modules')
    make = ['make', '-C', kernel, f'O={output}', 'ARCH=arm64', 'LLVM=1', '-j4']
    run([*make, 'modules_prepare'])
    if not (output / 'include/generated/autoconf.h').is_file():
        raise ValueError('missing real generated kernel headers')
    # Same external Kbuild selection used by compile_transport_owner_ci.sh.
    # Vendor Kconfig is not in the upstream autoconf; explicit owner define is
    # isolated to these invocations, NEVER exported into shipping configuration.
    flags = manifest['vendor_kcflags'] + ' -DCONFIG_MTK_ECCCI_TETRIS_OWNER=1'
    flags += ' -Werror=implicit-function-declaration -Werror=incompatible-pointer-types -Werror=int-conversion'
    identities = {}
    for root, objects in manifest['objects'].items():
        directory = vendor / PREFIX / root
        for name in objects:
            if not (directory / Path(name).with_suffix('.c')).is_file():
                raise ValueError(f'production translation unit missing: {root}/{name}')
        command = [*make, f'M={directory}', f'KERNEL_SRC={kernel}', f'KERNEL_OUT={output}',
                   f'DEVICE_MODULES_PATH={vendor}', f'KCFLAGS={flags}']
        command += [f'{name}={value}' for name, value in manifest['external_kbuild'].items()]
        run([*command, *objects])
        for name in objects:
            target = directory / name
            if not target.is_file() or not target.stat().st_size:
                raise ValueError(f'object missing: {root}/{name}')
            key = f'{root}/{name}'
            identities[key] = {**smoke.object_identity(target), 'sha256': sha(target)}
            symbols = manifest['required_defined_symbols'].get(key, [])
            if symbols:
                nm = subprocess.check_output(['llvm-nm', '--defined-only', str(target)], text=True)
                for symbol in symbols:
                    if not re.search(r'\b' + re.escape(symbol) + r'$', nm, re.M):
                        raise ValueError(f'owner/prepare branch not compiled: {key}: {symbol}')
    if list(vendor.rglob('*.ko')) or (output / 'vmlinux').exists() or list(output.rglob('*.ko')):
        raise ValueError('object-only build produced a runtime artifact')
    manifest['object_identities'] = identities
    manifest['config_sha256'] = sha(output / '.config')
    manifest['generated_autoconf_sha256'] = sha(output / 'include/generated/autoconf.h')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--work', type=Path, default=Path('/tmp/tetris-kernel-smoke'))
    parser.add_argument('--vendor', type=Path, help='git source containing the exact vendor commit')
    parser.add_argument('--report', type=Path, default=ROOT / 'out/kernel-object-smoke/runtime-objects.json')
    args = parser.parse_args()
    manifest, smoke, package = plan()
    if args.plan_only:
        print(json.dumps(manifest, indent=2))
        return
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('staging and actual C compilation are GitHub CI-only')
    work = args.work.resolve()
    kernel = work / f'linux-{manifest["kernel"]["kernel_commit"]}'
    output = work / 'objects'
    parent = json.loads((ROOT / 'out/kernel-object-smoke/BUILD-MANIFEST.json').read_text())
    if (parent.get('status') != 'passed' or parent.get('kernel_commit') != manifest['kernel']['kernel_commit']
            or 'research_source_sha256' not in parent):
        raise ValueError('requires successful current research-owner staging')
    for key in ('source_sha512', 'archive_sha512'):
        if parent[key] != manifest['kernel'][key]:
            raise ValueError('research package changed since kernel staging')
    if not kernel.is_dir() or not output.is_dir():
        raise ValueError('research work directory does not exist')
    first_object = 'drivers/soc/mediatek/mt6878-ccci-start.o'
    if sha(output / first_object) != parent['object_identities'][first_object]['sha256']:
        raise ValueError('research first-start object/output drift')
    final_config = ROOT / 'out/kernel-object-smoke/video-kunit-disabled.config'
    if not final_config.is_file() or sha(output / '.config') != sha(final_config):
        raise ValueError('final research configuration/output drift')
    manifest.update(status='started', commit=os.environ.get('GITHUB_SHA'),
                    parent_manifest_sha256=sha(ROOT / 'out/kernel-object-smoke/BUILD-MANIFEST.json'))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(manifest, indent=2) + '\n')
    try:
        vendor = args.vendor.resolve() if args.vendor else work / 'vendor-git-source'
        if not args.vendor:
            vendor.mkdir(exist_ok=False)
            run(['git', 'init', vendor])
            run(['git', '-C', vendor, 'fetch', '--depth=1',
                 'https://github.com/NothingOSS/android_kernel_device_modules_6.1_nothing_mt6878.git',
                 manifest['vendor_commit']])
        destination = work / 'runtime-vendor'
        stage_vendor(vendor, destination, package, manifest,
                     args.report.parent / 'runtime-generation-diagnostics')
        compile_objects(kernel, output, destination, manifest, smoke)
        manifest['status'] = 'passed'
    except BaseException as failure:
        manifest.update(status='failed', error=str(failure))
        raise
    finally:
        args.report.write_text(json.dumps(manifest, indent=2) + '\n')
    print('Actual complete-stack ARM64 runtime objects PASS; no activation or link')


if __name__ == '__main__':
    main()
