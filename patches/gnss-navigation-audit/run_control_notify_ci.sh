#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
"${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_control_notify.c" "$here/test_b41_control_notify.c" \
    -Wl,--wrap=socket -Wl,--wrap=sendto -Wl,--wrap=close \
    -o "$out/test_control_notify"
"$out/test_control_notify"
