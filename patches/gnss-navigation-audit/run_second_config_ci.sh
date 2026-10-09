#!/bin/sh
# CI only; constructor and copied state, no fd/device/native engine operations.
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/b41_startup_adapter.c" "$directory/b41_second_config.c" \
    "$directory/test_b41_second_config.c" -o "$temporary/test-second-config"
"$temporary/test-second-config"
