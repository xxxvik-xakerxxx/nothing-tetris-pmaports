#!/bin/sh
set -eu
[ "${CI:-}" = true ] || { echo 'CI-only native compilation' >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT HUP INT TERM
${CC:-cc} -std=c11 -Wall -Wextra -Werror -pthread \
    -ffunction-sections -fdata-sections -Wl,--gc-sections \
    -fsanitize=undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
    -I"$here" "$here/test_b41_mipc_sealed_launch.c" \
    "$here/b41_mipc_sealed_isolate.c" "$here/b41_mipc_loader_root.c" \
    "$here/b41_mipc_supervised_child.c" "$here/b41_native_receiver_host.c" \
    -o "$build/sealed-launch"
# A real systemd cgroup-v2 scope is mandatory. No environment variable bypass
# of production memory_bound(), namespace creation, or child policy is allowed.
# The root CI host must grant CAP_SYS_ADMIN and CAP_SYS_PTRACE (the latter only
# for the fixture parent's observation of the nondumpable child).
command -v systemd-run >/dev/null
sudo -n systemd-run --quiet --wait --pipe --collect \
    --property=MemoryMax=128M --property=MemorySwapMax=0 \
    --property=RuntimeMaxSec=45s --property=KillMode=control-group \
    timeout --signal=KILL 40 "$build/sealed-launch"
