#!/bin/sh
set -eu
[ "${CI:-}" = true ] || { echo 'CI-only native compilation' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT HUP INT TERM
${CC:-cc} -std=c11 -Wall -Wextra -Werror -pthread \
    -ffunction-sections -fdata-sections -Wl,--gc-sections \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$here" "$here/b41_native_receiver_host.c" \
    "$here/b41_mipc_supervised_child.c" "$here/test_b41_mipc_supervised_child.c" \
    -o "$build/supervised"
timeout 15 "$build/supervised"
python3 -c 'import os; assert hasattr(os, "memfd_create"), "Linux sealing required"'
PYTHONDONTWRITEBYTECODE=1 timeout 15 python3 "$here/test_b41_mipc_sealed_stage.py"
