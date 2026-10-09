#!/bin/sh
set -eu
if [ "${CI:-}" != true ]; then
    echo "Native GPUEB firmware staging tests require CI=true" >&2
    exit 2
fi
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
python3 "$dir/test_gpueb_fw_staging.py"
python3 "$dir/test_gpueb_fw_staging.py" --extract "$tmp/gpueb-fw-staging.h"
"${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror -fsanitize=address,undefined \
    -fno-omit-frame-pointer -I "$tmp" "$dir/test_gpueb_fw_staging.c" -o "$tmp/test"
"$tmp/test"
