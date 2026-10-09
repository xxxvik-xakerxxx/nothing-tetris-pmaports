#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'Native GPU tests are CI-only.' >&2
    exit 2
fi
: "${TETRIS_KERNEL_TREE:?Set to the unpatched pinned kernel source}"
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
TETRIS_GPU_OBSERVER_TESTS=${TETRIS_GPU_OBSERVER_TESTS:-0}
export TETRIS_GPU_OBSERVER_TESTS
case "$TETRIS_GPU_OBSERVER_TESTS" in
    0) observer_flag= ;;
    1) observer_flag=-DTETRIS_VGPU_OBSERVER_TESTS ;;
    *) printf '%s\n' 'TETRIS_GPU_OBSERVER_TESTS must be 0 or 1' >&2; exit 2 ;;
esac
python3 "$dir/prepare_native.py" "$tmp/mt6315-test-helpers.h"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    $observer_flag \
    -I"$tmp" -I"$TETRIS_KERNEL_TREE/include" \
    "$dir/test_mt6315_native.c" -o "$tmp/test-mt6315"
"$tmp/test-mt6315"
