#!/bin/sh
set -eu
test "$#" -eq 2 || { echo "usage: $0 linux-source-tree empty-output-dir" >&2; exit 2; }
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/../.." && pwd)
pkg="$repo/pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
kernel=$(CDPATH= cd -- "$1" && pwd)
mkdir -p "$2"
out=$(CDPATH= cd -- "$2" && pwd)
test -z "$(ls -A "$out")" || { echo 'output must be empty' >&2; exit 1; }
destination=$out
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT HUP INT TERM
for file in drivers/gpu/drm/mediatek/mtk_drm_drv.c \
    drivers/soc/mediatek/mtk-mutex.c \
    Documentation/devicetree/bindings/display/mediatek/mediatek,postmask.yaml; do
    mkdir -p "$out/$(dirname "$file")"
    cp "$kernel/$file" "$out/$file"
done
awk '/^source="/ { active=1; next } active && /^"$/ { exit }
     active && $1 ~ /\.patch$/ { print $1 }' "$pkg/APKBUILD" |
while read -r patch; do
    if ! grep -Eq '^\+\+\+ b/(drivers/gpu/drm/mediatek/mtk_drm_drv.c|drivers/soc/mediatek/(mt6878-mmsys.h|mtk-mutex.c)|arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dts|Documentation/devicetree/bindings/display/mediatek/mediatek,postmask.yaml)$' "$pkg/$patch"; then
        continue
    fi
    (cd "$out" && git apply \
        --include=drivers/gpu/drm/mediatek/mtk_drm_drv.c \
        --include=drivers/soc/mediatek/mt6878-mmsys.h \
        --include=drivers/soc/mediatek/mtk-mutex.c \
        --include=arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dts \
        --include=Documentation/devicetree/bindings/display/mediatek/mediatek,postmask.yaml \
        "$pkg/$patch")
done
test -f "$out/drivers/soc/mediatek/mt6878-mmsys.h"
test -f "$out/arch/arm64/boot/dts/mediatek/mt6878-nothing-tetris-native.dts"
cp -R "$out/." "$destination/"
echo "Prepared packaged topology in $destination"
