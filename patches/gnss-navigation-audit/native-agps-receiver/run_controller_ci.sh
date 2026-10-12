#!/bin/sh
# Compile the production controller closure; never execute the vendor engine.
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Controller link checks are CI-only; local compilation refused' >&2
    exit 2
fi
if [ "$#" -ne 2 ] || [ "$1" != --bionic-compile ]; then
    echo 'usage: run_controller_ci.sh --bionic-compile OUTPUT_DIRECTORY' >&2
    exit 2
fi
: "${BIONIC_CC:?Set API28 AArch64 Bionic compiler}"
directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
audit=$(CDPATH= cd -- "$directory/.." && pwd)
output=$2
mkdir -p "$output"
for fixture in native_receiver_host native_arguments; do
    if [ "$fixture" = native_receiver_host ]; then
        set -- -Wl,--wrap=write
    else
        set --
    fi
    "$BIONIC_CC" -std=c11 -D_DEFAULT_SOURCE -O2 -Wall -Wextra -Werror -pthread \
        "$audit/b41_native_arguments.c" "$audit/b41_native_receiver_host.c" \
        "$audit/b41_slot6_service.c" "$audit/b41_engine_arguments.c" \
        "$audit/b41_library_association.c" "$audit/b41_gpsdl_identity.c" \
        "$audit/b41_startup_adapter.c" "$audit/b41_agps_host.c" \
        "$audit/b41_frame_worker.c" "$audit/b41_navigation_output.c" \
        "$directory/b41_agps_decode.c" "$directory/b41_agps_receiver.c" \
        "$directory/b41_agps_native.c" "$audit/test_b41_${fixture}.c" \
        "$@" -o "$output/b41-${fixture}-controller-test"
done
