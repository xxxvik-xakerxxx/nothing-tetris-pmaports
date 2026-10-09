#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
asset=${1:?supply verified B4.1 MNL_Config.xml}
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
cflags=$(pkg-config --cflags libxml-2.0 libcrypto)
libs=$(pkg-config --libs libxml-2.0 libcrypto)
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer $cflags \
    "$here/b41_first_config.c" "$here/b41_xml_config.c" "$here/b41_runtime_config.c" \
    "$here/test_b41_runtime_config.c" $libs -o "$out/test_runtime_config"
"$out/test_runtime_config" "$asset"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -g \
    -fsanitize=address,undefined -fno-omit-frame-pointer $cflags \
    "$here/b41_first_config.c" "$here/b41_xml_config.c" "$here/b41_runtime_config.c" \
    "$here/b41_second_config.c" "$here/b41_startup_adapter.c" "$here/b41_startup_bundle.c" \
    "$here/test_b41_startup_bundle.c" $libs -o "$out/test_startup_bundle"
"$out/test_startup_bundle" "$asset"
"${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer \
    "$here/b41_startup_adapter.c" "$here/b41_agps_host.c" "$here/b41_frame_worker.c" \
    "$here/test_b41_frame_worker.c" -Wl,--wrap=send -o "$out/test_frame_worker"
"$out/test_frame_worker"
