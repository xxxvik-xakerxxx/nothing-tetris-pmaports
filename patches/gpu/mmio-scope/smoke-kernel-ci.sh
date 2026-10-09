#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'GPUEB MMIO scope kernel object smoke is CI-only.' >&2
    exit 2
fi
: "${TETRIS_KERNEL_TREE:?prepared kernel source required}"
: "${TETRIS_KERNEL_OUT:?configured ARM64 kernel output required}"
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
cp "$dir/mt6878-gpueb-io.c" "$dir/mt6878-gpueb-io.h" \
   "$dir/mt6878-gpueb-io-core.c" "$dir/mt6878-gpueb-io-core.h" \
   "$dir/Makefile" "$dir/../sram-adoption/mt6878-gpueb-adoption.h" \
   "$dir/../sram-owner/mt6878-gpueb-sram.h" \
   "$dir/../sram-owner/mt6878-gpueb-sram-core.h" "$tmp/"
make -C "$TETRIS_KERNEL_TREE" O="$TETRIS_KERNEL_OUT" ARCH=arm64 \
    M="$tmp" KCFLAGS="${KCFLAGS:-} -DCONFIG_MTK_MT6878_GPUEB_ADOPTION=1" \
    mt6878-gpueb-io-core.o mt6878-gpueb-io.o
