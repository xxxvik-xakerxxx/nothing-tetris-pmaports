#!/bin/sh
# Compile the actual existing pure consumers only on the CI host.
set -eu
if [ "${CI:-}" != true ]; then
    echo 'LNA integration native fixtures are CI-only.' >&2
    exit 2
fi
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
audit=$(CDPATH= cd -- "$here/.." && pwd)
asset=${1:?supply verified B4.1 MNL_Config.xml}
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
cflags=$(pkg-config --cflags libxml-2.0 libcrypto)
libs=$(pkg-config --libs libxml-2.0 libcrypto)
"${CC:-cc}" -std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -Werror -g -pthread \
    -fsanitize=address,undefined -fno-omit-frame-pointer $cflags -I"$audit" \
    "$audit/b41_first_config.c" "$audit/b41_first_queries.c" \
    "$audit/b41_lna_query_plan.c" "$audit/b41_xml_config.c" \
    "$audit/b41_runtime_config.c" "$audit/b41_startup_adapter.c" \
    "$audit/b41_second_config.c" "$audit/b41_startup_bundle.c" \
    "$audit/b41_native_arguments.c" "$audit/b41_native_receiver_host.c" \
    "$audit/native-agps-receiver/b41_agps_decode.c" \
    "$audit/native-agps-receiver/b41_agps_receiver.c" \
    "$audit/native-agps-receiver/b41_agps_native.c" "$audit/b41_library_association.c" \
    "$here/test_integration.c" $libs -o "$out/test_lna_integration"
timeout --signal=TERM --kill-after=2 30 "$out/test_lna_integration" "$asset"
