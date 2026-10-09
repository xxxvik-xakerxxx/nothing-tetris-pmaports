#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'Native GPS argument tests are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_startup_adapter.c" "$here/b41_engine_arguments.c" \
    "$here/test_b41_engine_arguments.c" -o "$out/test_engine_arguments"
"$out/test_engine_arguments"
