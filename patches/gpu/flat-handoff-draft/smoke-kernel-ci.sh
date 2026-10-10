#!/bin/sh
set -eu
test "${CI:-}" = true || { echo 'Kernel object build is CI-only.' >&2; exit 2; }
: "${TETRIS_KERNEL_TREE:?prepared kernel source}"
: "${TETRIS_KERNEL_OUT:?configured ARM64 output}"
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
cp "$dir/gpueb-flat-analysis.c" "$dir/Makefile.kernel" "$out/"
mv "$out/Makefile.kernel" "$out/Makefile"
make -C "$TETRIS_KERNEL_TREE" O="$TETRIS_KERNEL_OUT" ARCH=arm64 M="$out" gpueb-flat-analysis.o
