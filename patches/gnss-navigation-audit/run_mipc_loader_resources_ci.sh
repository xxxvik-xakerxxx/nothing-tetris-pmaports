#!/bin/sh
set -eu
[ "${CI:-}" = true ] || { echo 'CI-only native compilation' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT HUP INT TERM
case "${1:-}" in
    providers)
        : "${TETRIS_B41_STOCK_ROOT:?set independent stock artifact root}"
        : "${TETRIS_BIONIC_ROOT:?set independent Bionic artifact root}"
        python3 -c 'import os; assert hasattr(os, "memfd_create")'
        PYTHONDONTWRITEBYTECODE=1 timeout 20 python3 "$here/test_b41_mipc_provider_resources.py"
        exit
        ;;
    xml)
        : "${TETRIS_B41_STOCK_ROOT:?set independent provider stock artifact root}"
        : "${TETRIS_BIONIC_ROOT:?set independent Bionic/probe artifact root}"
        : "${TETRIS_B41_XML_ROOT:?set independent stock XML artifact root}"
        python3 -c 'import os; assert hasattr(os, "memfd_create")'
        PYTHONDONTWRITEBYTECODE=1 timeout 30 python3 "$here/test_b41_mipc_probe_resources.py"
        exit
        ;;
    mounts) ;;
    *) echo 'usage: run_mipc_loader_resources_ci.sh providers|xml|mounts' >&2; exit 2 ;;
esac
${CC:-cc} -std=c11 -Wall -Wextra -Werror -I"$here" \
    -c "$here/b41_mipc_sealed_isolate.c" -o "$build/sealed-isolate.o"
${CC:-cc} -std=c11 -Wall -Wextra -Werror \
    -pthread -ffunction-sections -fdata-sections -Wl,--gc-sections \
    -fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer -I"$here" \
    "$here/b41_mipc_loader_root.c" "$here/test_b41_mipc_loader_root.c" \
    "$here/b41_mipc_supervised_child.c" "$here/b41_native_receiver_host.c" \
    -o "$build/root-fixture"
# Requires a CI host granting CAP_SYS_ADMIN. No silent skip/root-policy downgrade.
if [ "$(id -u)" -eq 0 ]; then
    timeout 15 "$build/root-fixture"
else
    sudo -n timeout 15 "$build/root-fixture"
fi
