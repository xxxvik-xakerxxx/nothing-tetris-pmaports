#!/bin/sh
set -eu

[ "${CI:-}" = true ] && [ "${GITHUB_ACTIONS:-}" = true ] || {
    printf '%s\n' 'Native fixtures are CI-only.' >&2
    exit 1
}
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-clang}" -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow \
    -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/wire.c" "$here/test_wire.c" -o "$out/test-wire"
"$out/test-wire"
"${CC:-clang}" -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow \
    -O1 -g -frounding-math -ffp-contract=off \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/clock.c" "$here/test_clock.c" -lm -o "$out/test-clock"
"$out/test-clock"
"${CC:-clang}" -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow \
    -O1 -g -frounding-math -ffp-contract=off \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/clock.c" "$here/bootstrap_fields.c" "$here/test_bootstrap_fields.c" \
    -lm -o "$out/test-bootstrap-fields"
"$out/test-bootstrap-fields"
