#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    printf '%s\n' 'Native compilation is CI-only' >&2
    exit 2
fi
cd "$(dirname "$0")"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
timeout 60 "${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
    ${CFLAGS:--O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer} \
    b41_mipc_checked_tag.c test_b41_mipc_checked_tag.c \
    -o "$tmp/test_checked_tag" ${LDFLAGS:-}
timeout 15 "$tmp/test_checked_tag"
