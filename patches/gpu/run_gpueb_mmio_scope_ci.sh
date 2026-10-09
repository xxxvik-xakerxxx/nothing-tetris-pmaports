#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'Native GPUEB MMIO scope tests are CI-only.' >&2
    exit 2
fi
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
python3 "$dir/test_gpueb_mmio_scope.py"
"${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -DGPUEB_IO_HOST_TEST "$dir/mmio-scope/test-io-core.c" -o "$tmp/test"
"$tmp/test"
