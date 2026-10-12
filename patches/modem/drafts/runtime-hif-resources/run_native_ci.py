#!/usr/bin/env python3
"""CI-only fault fixture using the exact resource helper bodies; no emulation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from check_resources import HERE, build, sha, review


def fixture():
    production = '\n'.join('\n'.join(line for line in (HERE / name).read_text().splitlines()
                                     if not line.startswith('#include '))
                            for name in ('resources.h', 'supplier.h', 'consumer.h'))
    return (HERE / 'test_resources.c').read_text().replace('/* PRODUCTION */', production)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('native compilation/execution is GitHub CI-only')
    if args.report.exists():
        raise ValueError('refusing to overwrite an existing fixture report')
    report = {'status': 'started', 'scope': 'actual resource helpers; mocked Linux allocation/OF/driver-core boundaries'}
    try:
        review()
        patch, _, _, source = build(args.vendor.resolve())
        if patch != (HERE / 'resources.overlay').read_text():
            raise ValueError('reviewed overlay drift')
        code = fixture()
        report.update(overlay_sha256=sha(patch.encode()), fixture_sha256=sha(code.encode()),
                      source_pins={key: source[key] for key in ('vendor_commit', 'linux_commit', 'baseline_commit')})
        with tempfile.TemporaryDirectory(prefix='tetris-hif-native-') as temp:
            root = Path(temp)
            unit = root / 'resources.c'
            unit.write_text(code)
            flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-fno-omit-frame-pointer',
                     '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined',
                     '-DMODULE=1', '-DCONFIG_MTK_ECCCI_TETRIS_OWNER=1',
                     '-DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=1']
            subprocess.run(['cc', *flags, str(unit), '-o', str(root / 'resources')], check=True)
            env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                       UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
            subprocess.run([str(root / 'resources')], env=env, check=True)
            for invalid in ('-UCONFIG_MTK_ECCCI_TETRIS_OWNER -DCONFIG_MTK_ECCCI_TETRIS_OWNER=0',
                            '-UCONFIG_TETRIS_CCCI_SMEM_CONSUMER -DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=0',
                            '-UMODULE'):
                rejected = subprocess.run(['cc', *flags, *invalid.split(), '-fsyntax-only', str(unit)], capture_output=True)
                if rejected.returncode == 0:
                    raise ValueError('incompatible compile profile accepted: ' + invalid)
        report['status'] = 'passed'
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
