#!/bin/sh
# SPDX-License-Identifier: GPL-2.0+
set -eu
if [ "${CI:-}" != true ] || [ "${GITHUB_ACTIONS:-}" != true ]; then
    printf '%s\n' 'Native GPUEB segment tests are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tree=${TETRIS_UBOOT_TREE:-"$here/../../../../u-boot-mt6878"}
"${PYTHON:-python3}" "$here/check_integration.py" --tree "$tree"
board="$tree/board/mediatek/mt6878"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g -O1 \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -DTETRIS_GPUEB_HOST_TEST -I"$board" \
    "$board/tetris_gpueb_segments.c" "$here/test-segments.c" -o "$out/test-segments"
"$out/test-segments"
