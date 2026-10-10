#!/bin/sh
set -eu
test "${CI:-}" = true || { echo 'U-Boot object build is CI-only.' >&2; exit 2; }
# Must be a throwaway CI checkout, never the developer's live shared repository.
: "${TETRIS_UBOOT_SMOKE_TREE:?throwaway prepared U-Boot CI checkout}"
: "${TETRIS_UBOOT_OUT:?configured ARM64 output}"
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
board="$TETRIS_UBOOT_SMOKE_TREE/board/mediatek/mt6878"
cp "$dir/tetris_gpueb_flat.c" "$dir/tetris_gpueb_flat.h" \
   "$dir/tetris_gpueb_flat_publish.c" "$dir/tetris_gpueb_flat_publish.h" \
   "$dir/tetris_gpueb_flat_hook.c" "$dir/tetris_gpueb_flat_hook.h" "$board/"
make -C "$TETRIS_UBOOT_SMOKE_TREE" O="$TETRIS_UBOOT_OUT" \
    board/mediatek/mt6878/tetris_gpueb_flat.o \
    board/mediatek/mt6878/tetris_gpueb_flat_publish.o \
    board/mediatek/mt6878/tetris_gpueb_flat_hook.o
