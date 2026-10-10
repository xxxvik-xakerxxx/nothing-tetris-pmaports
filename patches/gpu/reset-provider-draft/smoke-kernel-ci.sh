#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
[ "${CI:-}" = true ] || { echo 'Kernel compilation is CI-only.' >&2; exit 2; }
: "${TETRIS_KERNEL_TREE:?prepared pinned kernel required}"
: "${TETRIS_KERNEL_OUT:?configured ARM64 output required}"
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
cp "$here/mt6878-gpueb-reset-provider.c" "$here/mt6878-gpueb-reset-provider.h" \
    "$here/Makefile" "$here/../reset-owner-draft/mt6878-gpueb-reset.c" \
    "$here/../reset-owner-draft/mt6878-gpueb-reset.h" \
    "$here/../sram-owner/mt6878-gpueb-sram.h" \
    "$here/../sram-owner/mt6878-gpueb-sram-core.h" "$tmp/"
make -C "$TETRIS_KERNEL_TREE" O="$TETRIS_KERNEL_OUT" ARCH=arm64 \
    M="$tmp" KCFLAGS=-Werror mt6878-gpueb-reset-provider.o mt6878-gpueb-reset.o
