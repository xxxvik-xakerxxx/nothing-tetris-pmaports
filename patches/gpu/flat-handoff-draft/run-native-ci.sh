#!/bin/sh
# SPDX-License-Identifier: GPL-2.0+
set -eu
if [ "${CI:-}" != true ]; then
    echo 'Native compilation is CI-only.' >&2
    exit 2
fi
: "${TETRIS_UBOOT_TREE:?reviewed U-Boot source required}"
: "${TETRIS_GPUEB_FACTORY_CONTAINER:?authenticated public cached B4.1 container required}"
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
board="$TETRIS_UBOOT_TREE/board/mediatek/mt6878"
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
mkdir -p "$out/include/linux"
for h in asn1.h asn1_decoder.h asn1_ber_bytecode.h; do
    ln -s "$TETRIS_UBOOT_TREE/include/linux/$h" "$out/include/linux/$h"
done
cc=${HOSTCC:-cc}
"$cc" -Wall -Wextra -Werror -Wno-unused-but-set-variable -Wno-unused-variable \
    -Wno-unused-parameter -Wno-implicit-fallthrough \
    -I"$out/include" "$TETRIS_UBOOT_TREE/tools/asn1_compiler.c" -o "$out/compiler"
"$out/compiler" "$board/tetris_scp_fields.asn1" "$out/tetris_scp_fields.asn1.c" "$out/tetris_scp_fields.asn1.h"
# Same actual sources in both sanitizer targets. Only LMB/map APIs and SMC are mocked.
set -- -std=gnu11 -g -O1 -fPIC -fsanitize=address,undefined -fno-omit-frame-pointer \
    -Wall -Wextra -Werror -include stddef.h \
    -DTETRIS_SCP_SECURITY_HOST_TEST -DTETRIS_SCP_CRYPTO_HOST_TEST -DTETRIS_GPUEB_HOST_TEST \
    -I"$dir/host" -I"$out/include" -I"$TETRIS_UBOOT_TREE/.github/tests/asn1-host" \
    -I"$out" -I"$board" -I"$dir"
# Warning exceptions apply ONLY to upstream ASN.1/generated translation units.
for source in "$TETRIS_UBOOT_TREE/lib/asn1_decoder.c" "$out/tetris_scp_fields.asn1.c"; do
    name=$(basename "${source%.c}")
    "$cc" "$@" -Wno-unused-but-set-variable -Wno-unused-variable \
        -Wno-unused-parameter -Wno-implicit-fallthrough -Wno-sign-compare \
        -c "$source" -o "$out/$name.o"
done
for source in "$board/tetris_scp_security.c" "$board/tetris_scp_crypto.c" \
    "$board/tetris_gpueb_layout.c" "$dir/test-native.c" "$dir/tetris_gpueb_flat_publish.c"; do
    name=$(basename "${source%.c}")
    "$cc" "$@" -c "$source" -o "$out/$name.o"
done
"$cc" -fsanitize=address,undefined "$out/"*.o -lfdt -Wl,--wrap=malloc -o "$out/faults"
ASAN_OPTIONS=detect_leaks=1 "$out/faults"
"$cc" -fsanitize=address,undefined "$out/"*.o -shared -lfdt -Wl,--wrap=malloc -o "$out/flat.so"
# ctypes runs in an unsanitized interpreter; load the ASAN runtime first.
asan=$("$cc" -print-file-name=libasan.so)
test -f "$asan"
ASAN_OPTIONS=detect_leaks=0 LD_PRELOAD="$asan${LD_PRELOAD:+:$LD_PRELOAD}" \
    "${PYTHON:-python3}" "$dir/test_native.py" "$out/flat.so" -v
