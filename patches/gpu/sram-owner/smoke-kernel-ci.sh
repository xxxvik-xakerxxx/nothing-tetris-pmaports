#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'GPUEB SRAM kernel object smoke is CI-only.' >&2
    exit 2
fi
: "${TETRIS_KERNEL_TREE:?prepared kernel source required}"
: "${TETRIS_KERNEL_OUT:?configured ARM64 kernel output required}"
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
# Copy only production files. No test macro, activation or shared tree edits.
cp "$dir/mt6878-gpueb-sram.c" "$dir/mt6878-gpueb-sram.h" \
   "$dir/mt6878-gpueb-sram-core.c" "$dir/mt6878-gpueb-sram-core.h" \
   "$dir/Makefile" "$tmp/"
make -C "$TETRIS_KERNEL_TREE" O="$TETRIS_KERNEL_OUT" ARCH=arm64 \
    M="$tmp" mt6878-gpueb-sram-core.o mt6878-gpueb-sram.o
