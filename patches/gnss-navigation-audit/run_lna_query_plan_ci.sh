#!/bin/sh
# CI-only standalone pure C fixtures, link alongside the frozen first builder.
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/b41_first_config.c" "$directory/b41_lna_query_plan.c" \
    "$directory/test_b41_lna_query_plan.c" -o "$temporary/test-lna-query-plan"
"$temporary/test-lna-query-plan"
