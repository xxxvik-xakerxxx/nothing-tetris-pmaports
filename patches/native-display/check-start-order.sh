#!/bin/sh
set -eu
test "$#" -eq 1 || { echo "usage: $0 linux-source-tree" >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
file=drivers/gpu/drm/mediatek/mtk_crtc.c
pkg="$repo/pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
test "$(git hash-object "$1/$file")" = c4c6d0249df562f0073d42a5336c3b45edeb1dc9 || {
    echo 'FAIL: unexpected base CRTC source; use pinned unmodified 6.18 file' >&2
    exit 1
}
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mkdir -p "$tmp/drivers/gpu/drm/mediatek"
cp "$1/$file" "$tmp/$file"
for header in mtk_ddp_comp.h mtk_disp_drv.h mtk_crtc.h; do
    cp "$1/drivers/gpu/drm/mediatek/$header" "$tmp/drivers/gpu/drm/mediatek/$header"
done
awk '/^source="/ { active=1; next } active && /^"$/ { exit }
     active && $1 ~ /\.patch$/ { print $1 }' "$pkg/APKBUILD" |
while read -r patch; do
    if grep -Eq '^\+\+\+ b/drivers/gpu/drm/mediatek/(mtk_crtc.c|mtk_ddp_comp.h|mtk_disp_drv.h|mtk_crtc.h)$' "$pkg/$patch"; then
        (cd "$tmp" && git apply --include="$file" \
            --include=drivers/gpu/drm/mediatek/mtk_ddp_comp.h \
            --include=drivers/gpu/drm/mediatek/mtk_crtc.h \
            --include=drivers/gpu/drm/mediatek/mtk_disp_drv.h "$pkg/$patch")
    fi
done
(cd "$tmp" && git apply --check "$here/0002-mt6878-configure-chain-before-start.patch")
(cd "$tmp" && git apply "$here/0002-mt6878-configure-chain-before-start.patch")
if [ -n "${START_ORDER_BUILD_DIR:-}" ]; then
    mkdir -p "$START_ORDER_BUILD_DIR"
    for name in mtk_crtc.c mtk_ddp_comp.h mtk_disp_drv.h mtk_crtc.h; do
        cp "$tmp/drivers/gpu/drm/mediatek/$name" "$START_ORDER_BUILD_DIR/$name"
    done
fi
awk '/bool config_before_start =/ { print; getline; print }
     /Configure the whole MT6878 chain/ { active=1 }
     /Initially configure all planes/ { active=0 }
     active { print }' "$tmp/$file" > "$tmp/start-order-source.h"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$tmp" \
    "$here/start-order-test.c" -o "$tmp/start-order-test"
"$tmp/start-order-test"
sed 's/if (!config_before_start)/if (config_before_start)/' \
    "$tmp/start-order-source.h" > "$tmp/mutant.h"
mv "$tmp/mutant.h" "$tmp/start-order-source.h"
"${CC:-cc}" -std=c11 -Wall -Wextra -Werror -I"$tmp" \
    "$here/start-order-test.c" -o "$tmp/start-order-mutant"
ulimit -c 0
if "$tmp/start-order-mutant" > "$tmp/mutant.out" 2>&1; then
    echo 'FAIL: early MT6878 start was accepted' >&2
    exit 1
fi
echo 'PASS: rejected interleaved MT6878 startup (not hardware quiescence proof)'
