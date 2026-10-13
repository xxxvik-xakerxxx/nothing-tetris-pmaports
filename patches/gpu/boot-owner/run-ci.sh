#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ] || [ "${GITHUB_ACTIONS:-}" != true ]; then
    printf '%s\n' 'CI-only: GPU join compilation and mock fault execution are not permitted locally.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -B "$here/ci_join.py" --test-static
python3 -B "$here/ci_join.py" --check
# Alpine supplies sanitizer runtimes through Clang, not GCC's libasan package.
if command -v apk >/dev/null 2>&1; then
    apk add --no-cache clang21-rtlib
    export HOSTCC=clang
fi
export PATH="/usr/lib/llvm21/bin:$PATH"
linux_rev=d84b264a54a37611f2f46bc19363cb9b41606205
kernel=${TETRIS_KERNEL_TREE:-/tmp/tetris-kernel-smoke/linux-$linux_rev}
output=${TETRIS_KERNEL_OUT:-/tmp/tetris-kernel-smoke/objects}
python3 -B "$here/ci_join.py" --kernel "$kernel" --output "$output" "$@"
