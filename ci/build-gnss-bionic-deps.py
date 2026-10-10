#!/usr/bin/env python3
"""CI-only build of real API28 ARM64 XML/crypto dependencies for our GNSS code."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
SOURCES = {
    'openssl-3.5.9': {
        'url': 'https://github.com/openssl/openssl/releases/download/openssl-3.5.9/openssl-3.5.9.tar.gz',
        'sha256': '603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a',
        'max_bytes': 64 * 1024 * 1024,
    },
    'libxml2-2.15.4': {
        'url': 'https://download.gnome.org/sources/libxml2/2.15/libxml2-2.15.4.tar.xz',
        'sha256': '98087fd181d9070724f3fbc65c7377db03038eb92bd882374daff44940138821',
        'max_bytes': 8 * 1024 * 1024,
    },
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def extract(archive, destination, name):
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if (not members or len(members) > 50000 or sum(member.size for member in members) > 1024 ** 3 or
                any(not Path(member.name).parts or Path(member.name).parts[0] != name or Path(member.name).is_absolute() or
                    '..' in Path(member.name).parts or not (member.isfile() or member.isdir() or
                    member.issym() or member.islnk()) for member in members)):
            raise ValueError('unexpected source archive shape')
        source.extractall(destination, filter='data')
    return destination / name


def run(command, log, manifest, **kwargs):
    command = list(map(str, command))
    manifest.setdefault('commands', []).append(command)
    print('+', ' '.join(command), flush=True)
    subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT,
                   timeout=900, **kwargs)


def library_identity(readelf, path, export):
    header = subprocess.check_output([str(readelf), '-h', str(path)], text=True)
    dynamic = subprocess.check_output([str(readelf), '-d', str(path)], text=True)
    symbols = subprocess.check_output([str(readelf), '--dyn-syms', str(path)], text=True)
    if not re.search(r'Machine:\s+AArch64', header) or not re.search(r'Type:\s+DYN', header):
        raise ValueError('dependency is not a real ARM64 shared library: ' + str(path))
    if not any('GLOBAL' in line and ' UND ' not in line and
               re.search(r'\b' + export + r'(?:@|$)', line) for line in symbols.splitlines()):
        raise ValueError('required implementation missing: ' + export)
    needed = re.findall(r'\(NEEDED\).*\[([^]]+)\]', dynamic)
    if set(needed) - {'libc.so', 'libm.so', 'libdl.so'} or 'GLIBC_' in symbols:
        raise ValueError('unowned or host dependency: ' + str(needed))
    return {'sha256': digest(path), 'size': path.stat().st_size, 'needed': needed,
            'required_defined_export': export}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ndk', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--prefix', required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('dependency C builds are GitHub CI-only')
    ndk, work, prefix = args.ndk.resolve(), args.work.resolve(), args.prefix.resolve()
    tools = ndk / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    if not (tools / 'aarch64-linux-android28-clang').is_file() or work.exists() or prefix.exists():
        parser.error('requires real r27d NDK and fresh work/prefix directories')
    properties = (ndk / 'source.properties').read_text()
    if not re.search(r'^Pkg.Revision\s*=\s*27\.3\.13750724\s*$', properties, re.M):
        parser.error('unexpected NDK revision')
    work.mkdir(parents=True)
    prefix.mkdir(parents=True)
    manifest = {'status': 'started', 'commit': os.environ.get('GITHUB_SHA'),
                'ndk': 'r27d', 'abi': 'arm64-v8a', 'api': 28, 'sources': SOURCES,
                'scope': 'real dependency build/link inputs; no target execution or vendor engine'}
    report = prefix / 'BUILD-MANIFEST.json'
    try:
        with (prefix / 'build.log').open('w') as log:
            sources = {}
            for name, pin in SOURCES.items():
                archive = work / (name + '.archive')
                run(['curl', '--fail', '--location', '--proto', '=https', '--tlsv1.2',
                     '--max-time', '300', '--max-filesize', str(pin['max_bytes']),
                     '--output', archive, pin['url']], log, manifest)
                if not 0 < archive.stat().st_size <= pin['max_bytes'] or digest(archive) != pin['sha256']:
                    raise ValueError('official source archive identity mismatch: ' + name)
                sources[name] = extract(archive, work, name)
            env = dict(os.environ, ANDROID_NDK_ROOT=str(ndk), PATH=str(tools) + ':' + os.environ['PATH'])
            run(['perl', 'Configure', 'android-arm64', '-D__ANDROID_API__=28', 'shared',
                 'no-tests', 'no-apps', 'no-module', 'no-engine', '--libdir=lib',
                 '--prefix=' + str(prefix)], log, manifest, cwd=sources['openssl-3.5.9'], env=env)
            run(['make', '-j4', 'build_libs'], log, manifest, cwd=sources['openssl-3.5.9'], env=env)
            run(['make', 'install_sw'], log, manifest, cwd=sources['openssl-3.5.9'], env=env)
            build = work / 'xml-build'
            run(['cmake', '-S', sources['libxml2-2.15.4'], '-B', build, '-G', 'Ninja',
                 '-DCMAKE_TOOLCHAIN_FILE=' + str(ndk / 'build/cmake/android.toolchain.cmake'),
                 '-DANDROID_ABI=arm64-v8a', '-DANDROID_PLATFORM=android-28',
                 '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + str(prefix),
                 '-DCMAKE_INSTALL_LIBDIR=lib', '-DBUILD_SHARED_LIBS=ON',
                 '-DLIBXML2_WITH_PROGRAMS=OFF', '-DLIBXML2_WITH_TESTS=OFF',
                 '-DLIBXML2_WITH_PYTHON=OFF', '-DLIBXML2_WITH_ICONV=OFF',
                 '-DLIBXML2_WITH_ICU=OFF', '-DLIBXML2_WITH_ZLIB=OFF',
                 '-DLIBXML2_WITH_MODULES=OFF'], log, manifest)
            run(['cmake', '--build', build, '--parallel', '4'], log, manifest)
            run(['cmake', '--install', build], log, manifest)
        manifest['libraries'] = {
            'lib/libcrypto.so': library_identity(tools / 'llvm-readelf', prefix / 'lib/libcrypto.so', 'EVP_Digest'),
            'lib/libxml2.so': library_identity(tools / 'llvm-readelf', prefix / 'lib/libxml2.so', 'xmlReadMemory'),
        }
        manifest['installed_files_sha256'] = {
            str(path.relative_to(prefix)): digest(path) for path in sorted(prefix.rglob('*'))
            if path.is_file() and path.name != 'BUILD-MANIFEST.json'
        }
        manifest['status'] = 'passed'
    except BaseException as failure:
        manifest.update(status='failed', error=str(failure))
        raise
    finally:
        report.write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
