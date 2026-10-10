#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native arguments builds are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_native_arguments.c" "$here/b41_native_receiver_host.c" \
    "$here/test_b41_native_arguments.c" -o "$out/test_native_arguments"
timeout --signal=TERM --kill-after=2 20 "$out/test_native_arguments"
