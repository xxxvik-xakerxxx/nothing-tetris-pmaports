#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ] || [ "${GITHUB_ACTIONS:-}" != true ]; then
    printf '%s\n' 'CI-only: DRAM object compilation and mock faults are forbidden locally.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -B "$here/ci_dram.py" --check
python3 -B "$here/test_dram.py" -v
if command -v apk >/dev/null 2>&1; then
    apk add --no-cache clang21-rtlib
    export HOSTCC=clang
fi
export PATH="/usr/lib/llvm21/bin:$PATH"
python3 -B "$here/ci_dram.py" "$@"
