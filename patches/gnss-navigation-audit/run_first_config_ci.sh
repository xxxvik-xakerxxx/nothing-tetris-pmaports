#!/bin/sh
# Native builds are CI-only; separate from frozen adapter snapshot.
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/b41_first_config.c" "$directory/test_b41_first_config.c" \
    -o "$temporary/test-first-config"
"$temporary/test-first-config"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/b41_first_config.c" "$directory/b41_first_queries.c" \
    "$directory/test_b41_first_queries.c" \
    -o "$temporary/test-first-queries"
"$temporary/test-first-queries"
