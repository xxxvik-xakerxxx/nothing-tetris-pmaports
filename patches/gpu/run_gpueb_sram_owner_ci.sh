#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'Native GPUEB SRAM owner tests are CI-only.' >&2
    exit 2
fi
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
python3 "$dir/test_gpueb_sram_owner.py"
"${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -DGPUEB_SRAM_HOST_TEST "$dir/sram-owner/test-sram-owner.c" -o "$tmp/test"
"$tmp/test"
