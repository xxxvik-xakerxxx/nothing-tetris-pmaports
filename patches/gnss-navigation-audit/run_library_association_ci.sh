#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'Native GNSS association tests are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
lib=${1:?exact pinned B4.1 libmnl.so required}
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_library_association.c" "$here/test_b41_library_association.c" \
    -o "$out/test_association"
"$out/test_association" "$lib"
