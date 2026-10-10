#!/bin/sh
set -eu
[ "${CI:-}" = true ] || { echo 'CI-only native build/executable fixture' >&2; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo 'Dedicated root CI process required' >&2; exit 2; }
[ "$(uname -s)" = Linux ] && [ "$(uname -m)" = aarch64 ] || {
    echo 'Actual ARM64 Linux required; no x86 loader/emulator substitution' >&2; exit 2;
}
: "${TETRIS_B41_SELECTED_STOCK:?absolute selected stock CI artifact root required}"
: "${TETRIS_B41_PROBE_ARTIFACT:?absolute independent pinned probe artifact root required}"
: "${TETRIS_CGROUP_PARENT:?explicit memory-delegated cgroup-v2 parent required}"
: "${TETRIS_MNL_LAYOUT:?explicit selected vendor libmnl layout required}"
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# /tmp is deliberately unsuitable for trusted_parent ancestor admission.
build=$(mktemp -d /run/b41-sealed-cli-ci-XXXXXX)
chmod 700 "$build"
# Retain code/logs on failure or quarantine. No parent-only timeout/kill trap.
printf 'CLI build/results retained at %s\n' "$build"
${CC:-cc} -std=c11 -Wall -Wextra -Werror -pthread \
    -ffunction-sections -fdata-sections -Wl,--gc-sections -I"$here" \
    "$here/b41_sealed_probe_parent.c" "$here/b41_mipc_sealed_isolate.c" \
    "$here/b41_mipc_loader_root.c" "$here/b41_mipc_supervised_child.c" \
    "$here/b41_native_receiver_host.c" -o "$build/parent"
chmod 500 "$build/parent"
PYTHONDONTWRITEBYTECODE=1 python3 "$here/test_b41_sealed_probe_ci.py"
PYTHONDONTWRITEBYTECODE=1 python3 "$here/b41_sealed_probe_ci.py" \
    --selected-stock "$TETRIS_B41_SELECTED_STOCK" \
    --probe-artifact "$TETRIS_B41_PROBE_ARTIFACT" \
    --parent "$build/parent" --results "$build/results" \
    --cgroup-parent "$TETRIS_CGROUP_PARENT" --mnl-layout "$TETRIS_MNL_LAYOUT"
