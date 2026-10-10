#!/usr/bin/env python3
"""CI-only native callback fixture from the exact four-overlay vendor staging."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from check_objects import HERE, ROOT, load, plan, sha, stage_vendor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--report', type=Path,
        default=ROOT / 'out/kernel-object-smoke/native-runtime-callbacks.json')
    args = parser.parse_args()
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('native callbacks are GitHub CI-only')
    manifest, _, package = plan()
    manifest.update(status='started', commit=os.environ.get('GITHUB_SHA'))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='runtime-native-staged-') as temp:
            staged = Path(temp) / 'vendor'
            stage_vendor(args.vendor.resolve(), staged, package, manifest,
                         args.report.parent / 'runtime-generation-diagnostics')
            lifecycle = load('native_runtime_lifecycle', HERE.parent / 'runtime-lifecycle/check_lifecycle.py')
            source = staged / lifecycle.SOURCE
            if sha(source) != manifest['lifecycle_source_sha256']:
                raise ValueError('native callback staged source identity drift')
            lifecycle.native_ci(source.read_text())
            manifest.update(status='passed', native_owner_modes=[0, 1],
                            fixture_sha256=sha(HERE.parent / 'runtime-lifecycle/test_callbacks.c'))
    except BaseException as error:
        manifest.update(status='failed', error=str(error))
        raise
    finally:
        args.report.write_text(json.dumps(manifest, indent=2) + '\n')
    print('Actual staged lifecycle native callbacks PASS in owner modes 0/1; no hardware')


if __name__ == '__main__':
    main()
