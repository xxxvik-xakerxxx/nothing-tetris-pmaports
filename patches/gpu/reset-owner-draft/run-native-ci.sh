#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
if [ "${CI:-}" != true ] || [ "${GITHUB_ACTIONS:-}" != true ]; then
    echo 'CI-only: native GPU mailbox fixture is not permitted locally' >&2
    exit 2
fi
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
"${CC:-cc}" -std=gnu11 -O1 -g -Wall -Wextra -Werror -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    -DGPUEB_RESET_HOST_TEST -DGPUEB_SRAM_HOST_TEST \
    -I"$dir" -I"$dir/../sram-owner" "$dir/test-mailbox.c" -o "$tmp/test"
ASAN_OPTIONS=detect_leaks=1 UBSAN_OPTIONS=halt_on_error=1 "$tmp/test"
