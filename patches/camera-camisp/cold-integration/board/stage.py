#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only application check on the actual cold-staged CI copy, no compile."""
import argparse
from pathlib import Path
import subprocess

import check
import generate as gen


def verify(kernel, base, output):
    for path, text in base.items():
        if (kernel / path).read_bytes() != text.encode():
            raise ValueError('cold-staged input mismatch: ' + path)
    for path in output.keys() - base.keys():
        if (kernel / path).exists():
            raise ValueError('board candidate path already present: ' + path)
    subprocess.run(['git', 'apply', '--check', str(gen.HERE / 'board-owner.patch')], cwd=kernel, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    gen.cold.stream.arguments(parser, explicit=True)
    parser.add_argument('--cold-staged-kernel', type=Path, required=True)
    args = parser.parse_args()
    base, output, _, _, _ = check.check(args.kernel_archive, args.device_repo, args.modules_repo)
    verify(args.cold_staged_kernel, base, output)
    print('PASS: actual cold-staged source hashes and board patch applicability; no source/config edits or compilation')
