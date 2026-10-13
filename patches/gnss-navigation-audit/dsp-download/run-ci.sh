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
"${CC:-clang}" -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow \
    -O1 -g -frounding-math -ffp-contract=off \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/wire.c" "$here/clock.c" "$here/bootstrap_fields.c" \
    "$here/bootstrap.c" "$here/test_bootstrap.c" -lm -o "$out/test-bootstrap"
"$out/test-bootstrap"
"${CC:-clang}" -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow \
    -O1 -g -frounding-math -ffp-contract=off \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/wire.c" "$here/clock.c" "$here/bootstrap_fields.c" \
    "$here/bootstrap.c" "$here/download.c" "$here/test_download.c" \
    -lm -o "$out/test-download"
"$out/test-download"
"${CC:-clang}" -std=c11 -Wall -Wextra -Werror -Wconversion -Wshadow \
    -O1 -g -frounding-math -ffp-contract=off \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/wire.c" "$here/clock.c" "$here/bootstrap_fields.c" \
    "$here/bootstrap.c" "$here/download.c" "$here/download_linux.c" \
    "$here/test_download_linux.c" -lm \
    -Wl,--wrap=clock_gettime -Wl,--wrap=fcntl -Wl,--wrap=fstat \
    -Wl,--wrap=ioctl -Wl,--wrap=read -Wl,--wrap=write \
    -o "$out/test-download-linux"
"$out/test-download-linux"
