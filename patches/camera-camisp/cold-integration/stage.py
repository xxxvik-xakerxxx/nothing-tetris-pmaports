#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the actual normal prepared kernel against the pinned package profile."""
import argparse
from pathlib import Path
import subprocess

import check
import generate as gen


def verify_prepared(kernel, base, output):
    hashes = {}
    for path, text in base.items():
        data = (kernel / path).read_bytes()
        if data != text.encode():
            raise ValueError("prepared input differs from verified archive/package profile: " + path)
        hashes[path] = gen.sha(data)
    for path in output.keys() - base.keys():
        if (kernel / path).exists():
            raise ValueError("candidate path already exists; require unstaged prepared kernel: " + path)
    return hashes


def apply(kernel, base, output):
    hashes = verify_prepared(kernel, base, output)
    patch = gen.HERE / 'cold-integration.patch'
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=kernel, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=kernel, check=True)
    for path, text in output.items():
        if (kernel / path).read_bytes() != text.encode():
            raise ValueError("staged output drift: " + path)
    return hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    gen.stream.arguments(parser, explicit=True)
    parser.add_argument('--prepared-kernel', type=Path, required=True)
    args = parser.parse_args()
    base, output, _ = check.check(args.kernel_archive, args.device_repo, args.modules_repo)
    verify_prepared(args.prepared_kernel, base, output)
    subprocess.run(['git', 'apply', '--check', str(gen.HERE / 'cold-integration.patch')],
                   cwd=args.prepared_kernel, check=True)
    print('PASS: actual prepared input hashes and patch applicability; no prepared-tree edits or compilation')


if __name__ == '__main__':
    main()
