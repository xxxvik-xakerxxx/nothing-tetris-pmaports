#!/bin/sh
# Native builds are CI-only. Do not run this on the developer host.
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/b41_startup_adapter.c" "$directory/test_b41_startup_adapter.c" \
    -o "$temporary/test-startup-adapter"
for scenario in normal busy oversize invalid unsupported full; do
    "$temporary/test-startup-adapter" "$scenario"
done
