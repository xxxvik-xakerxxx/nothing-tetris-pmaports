#!/bin/sh
# CI only: actual Unix datagram delivery/ownership, no GNSS devices or engine.
set -eu
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$directory/b41_agps_host.c" "$directory/test_b41_agps_host.c" \
    -Wl,--wrap=send -o "$temporary/test-agps-host"
"$temporary/test-agps-host"
