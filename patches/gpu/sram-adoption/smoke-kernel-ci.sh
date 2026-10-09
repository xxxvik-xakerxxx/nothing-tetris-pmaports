#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'GPUEB adoption kernel object smoke is CI-only.' >&2
    exit 2
fi
: "${TETRIS_KERNEL_TREE:?prepared kernel source required}"
: "${TETRIS_KERNEL_OUT:?configured ARM64 kernel output required}"
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir -p "$tmp/include/linux/soc/mediatek"
# Stage exact frozen caller inputs and their public session header once.
python3 "$dir/prepare_migration.py" --stage "$tmp/stage" \
    --session-header "$tmp/include/linux/soc/mediatek/mt6878-gpueb-session.h"
cp "$dir/../sram-owner/mt6878-gpueb-sram.c" \
   "$dir/../sram-owner/mt6878-gpueb-sram.h" \
   "$dir/../sram-owner/mt6878-gpueb-sram-core.c" \
   "$dir/../sram-owner/mt6878-gpueb-sram-core.h" \
   "$dir/mt6878-gpueb-adoption.c" "$dir/mt6878-gpueb-adoption.h" \
   "$dir/Makefile" "$tmp/"
cp "$tmp"/*.h "$tmp/include/linux/soc/mediatek/"
cp "$tmp/stage/drivers/mailbox/mtk-gpueb-mailbox.c" \
   "$tmp/stage/drivers/pmdomain/mediatek/mt6878-gpueb-session.c" "$tmp/"
make -C "$TETRIS_KERNEL_TREE" O="$TETRIS_KERNEL_OUT" ARCH=arm64 \
    M="$tmp" KCFLAGS="${KCFLAGS:-} -I$tmp/include -DCONFIG_MTK_MT6878_GPUEB_ADOPTION=1" \
    mt6878-gpueb-sram-core.o mt6878-gpueb-sram.o mt6878-gpueb-adoption.o \
    mtk-gpueb-mailbox.o mt6878-gpueb-session.o
