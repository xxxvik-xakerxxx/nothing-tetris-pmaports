#!/bin/sh
set -eu
test "$#" -eq 1 || { echo "usage: $0 B4.1-device-modules-repository" >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
git -C "$1" archive ee2be53cb75670b548948636a0db1d1ff112bf12 \
    drivers/misc/mediatek/ccmni/ccmni.c \
    drivers/misc/mediatek/rps/rps_perf.c \
    drivers/misc/mediatek/eccci/fsm/ap_md_mem.c \
    drivers/misc/mediatek/eccci/hif/ccci_dpmaif_com.h \
    drivers/misc/mediatek/eccci/hif/ccci_dpmaif_page_pool.c > "$tmp/source.tar"
tar -xf "$tmp/source.tar" -C "$tmp"
for candidate in \
    0001-ccmni-linux-6.18.patch.vendor \
    0002-rps-linux-6.18-headers.patch.vendor \
    0003-mdss-optional-mrdump.patch.vendor \
    0004-dpmaif-page-pool-linux-6.18.patch.vendor \
    0005-dpmaif-page-pool-dma-length.patch.vendor
do
    (cd "$tmp" && git apply --check "$here/$candidate")
    (cd "$tmp" && git apply "$here/$candidate")
done
echo 'PASS: five modem candidates apply to exact B4.1 files; no hardware execution'
file=drivers/misc/mediatek/eccci/hif/ccci_dpmaif_page_pool.c
awk '/^int skb_alloc_from_pool\(/ { active=1 }
     active { print } active && /^}/ { exit }' "$tmp/$file" > "$tmp/allocation.h"
"${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror -I"$tmp" \
    "$here/page-pool-dma-test.c" -o "$tmp/test"
"$tmp/test"
cp "$tmp/allocation.h" "$tmp/allocation.original"
ulimit -c 0
for mutant in length capacity
do
    if test "$mutant" = length; then
        sed 's/skb_data_size(\*ppskb), DMA_FROM_DEVICE/1500, DMA_FROM_DEVICE/' \
            "$tmp/allocation.original" > "$tmp/allocation.h"
    else
        sed 's/if (unlikely(pkt_buf_sz > skb_data_size(\*ppskb)))/if (unlikely(pkt_buf_sz > UINT_MAX))/' \
            "$tmp/allocation.original" > "$tmp/allocation.h"
    fi
    "${CC:-cc}" -std=gnu11 -Wall -Wextra -Werror -I"$tmp" \
        "$here/page-pool-dma-test.c" -o "$tmp/mutant"
    if "$tmp/mutant" > "$tmp/mutant.out" 2>&1; then
        echo "FAIL: $mutant mutant accepted" >&2
        exit 1
    fi
    echo "PASS: $mutant mutant rejected"
done
