#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
asset=${1:?supply verified vendor/etc/MNL_Config.xml}
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
# Main owns dependencies/workflow. Require real pkg-config discovery; never
# silently replace libxml2 or digest checks with a permissive fallback.
cflags=$(pkg-config --cflags libxml-2.0 libcrypto)
libs=$(pkg-config --libs libxml-2.0 libcrypto)
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    $cflags \
    "$here/b41_xml_config.c" "$here/test_b41_xml_config.c" \
    $libs -o "$out/test_xml_config"
PYTHONDONTWRITEBYTECODE=1 "${PYTHON:-python3}" "$here/test_b41_xml_native.py" \
    "$out/test_xml_config" "$asset"
