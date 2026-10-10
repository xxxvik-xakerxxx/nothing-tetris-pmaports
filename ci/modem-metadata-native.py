#!/usr/bin/env python3
"""Run pinned producer/import fixtures in CI and preserve the first failure."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_stock(directory):
    stock = load('metadata_public_stock', ROOT / 'ci/extract-stock-modem.py')
    image = directory / 'md1img.bin'
    evidence = json.loads((directory / 'BUILD-MANIFEST.json').read_text())
    if (evidence.get('release') != stock.RELEASE or
            evidence.get('archive_sha256') != stock.ARCHIVE_SHA256 or
            evidence.get('sha256') != stock.IMAGE_SHA256 or
            image.stat().st_size != evidence.get('size') or digest(image) != stock.IMAGE_SHA256):
        raise ValueError('public modem extraction identity mismatch')
    return image, evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vendor', required=True, type=Path)
    parser.add_argument('--uboot', required=True, type=Path)
    parser.add_argument('--stock', type=Path, default=ROOT / 'out/stock-modem')
    parser.add_argument('--report', type=Path, default=ROOT / 'out/modem-metadata-native/RESULT.json')
    args = parser.parse_args()
    if os.environ.get('CI') != 'true' or os.environ.get('GITHUB_ACTIONS') != 'true':
        parser.error('native C fixtures are GitHub CI-only')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {'status': 'started', 'commit': os.environ.get('GITHUB_SHA'),
              'scope': 'native producer/import fixtures; no hardware, firmware execution or attestation'}
    try:
        image, stock = verify_stock(args.stock)
        objects = load('metadata_native_objects', ROOT /
                       'patches/modem/drafts/runtime-object-ci/check_objects.py')
        directory = ROOT / 'patches/modem/drafts/runtime-metadata'
        report.update(stock=stock, metadata_review_sha256=objects.review(directory))
        command = [sys.executable, '-B', str(directory / 'check_metadata.py'),
                   '--vendor', str(args.vendor.resolve()), '--uboot', str(args.uboot.resolve()),
                   '--native-ci', '--stock-container', str(image)]
        with (args.report.parent / 'native.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        report['status'] = 'passed'
    except BaseException as failure:
        report.update(status='failed', error=str(failure))
        raise
    finally:
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
