#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo "Native GPUEB session tests require CI=true" >&2
    exit 2
fi
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
python3 "$dir/test_gpueb_session.py"
python3 "$dir/test_gpueb_session.py" --extract "$tmp/gpueb-session-helpers.h"
"${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer -I "$tmp" "$dir/test_gpueb_session.c" -o "$tmp/test"
"$tmp/test"
