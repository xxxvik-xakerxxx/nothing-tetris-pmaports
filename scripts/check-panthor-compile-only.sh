#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

if [ "$#" -ne 3 ]; then
	echo "usage: $0 /path/to/prepared-linux-6.18 /path/to/device-modules /path/to/modules" >&2
	exit 2
fi

kernel_tree=${1%/}
devmods_tree=${2%/}
modules_tree=${3%/}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(dirname "$script_dir")
kernel_pkg="$repo_dir/pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
kernel_config="$kernel_pkg/config-postmarketos-mediatek-mt6878.aarch64"
device_pkg="$repo_dir/pmaports/device/testing/device-nothing-tetris"
kernel_commit=d84b264a54a37611f2f46bc19363cb9b41606205
devmods_commit=ee2be53cb75670b548948636a0db1d1ff112bf12
modules_commit=e96f60dc081ae3525ef43d4bcf0ee5ee97e53835
vendor_dts=arch/arm64/boot/dts/mediatek/mt6878.dts

test -f "$kernel_tree/Makefile"
test -f "$kernel_tree/.config"
test "$(sed -n 's/^VERSION = //p' "$kernel_tree/Makefile")" = 6
test "$(sed -n 's/^PATCHLEVEL = //p' "$kernel_tree/Makefile")" = 18
clang --version | grep -q 'clang version 21\|clang version 21\.'

grep -Fqx "_commit=\"$kernel_commit\"" "$kernel_pkg/APKBUILD"
grep -Fqx "_devmods_commit=\"$devmods_commit\"" "$kernel_pkg/APKBUILD"
grep -Fqx "_connmods_commit=\"$modules_commit\"" "$kernel_pkg/APKBUILD"
grep -Fxq 'CONFIG_DRM_PANTHOR=m' "$kernel_config"
grep -Fxq 'CONFIG_DRM_PANTHOR=m' "$kernel_tree/.config"

git -C "$devmods_tree" cat-file -e "$devmods_commit^{commit}"
git -C "$modules_tree" cat-file -e "$modules_commit^{commit}"

vendor_gpu=$(git -C "$devmods_tree" show "$devmods_commit:$vendor_dts")
printf '%s\n' "$vendor_gpu" | grep -Fq 'mali: mali@13000000 {'
printf '%s\n' "$vendor_gpu" | grep -Fq 'reg = <0 0x13000000 0 0x480000>;'
printf '%s\n' "$vendor_gpu" | grep -Fq '<GIC_SPI 271 IRQ_TYPE_LEVEL_HIGH 0>,'
printf '%s\n' "$vendor_gpu" | grep -Fq '<GIC_SPI 270 IRQ_TYPE_LEVEL_HIGH 0>,'
printf '%s\n' "$vendor_gpu" | grep -Fq '<GIC_SPI 269 IRQ_TYPE_LEVEL_HIGH 0>,'
printf '%s\n' "$vendor_gpu" | grep -Fq 'vgpu-supply = <&mt6319_6_vbuck2>;'
printf '%s\n' "$vendor_gpu" | grep -Fq 'vsram-supply = <&mt6363_vsram_cpum>;'

if grep -REl '^[[:space:]]*(panthor|modprobe[[:space:]]+panthor)[[:space:]]*$' \
	"$device_pkg" >/dev/null 2>&1; then
	echo "Panthor must not be autoloaded" >&2
	exit 1
fi

if grep -REl '^\+[[:space:]]*(gpu|mali):?[[:space:]]+[^[:space:]]*@13000000[[:space:]]*\{' \
	"$kernel_pkg"/*.patch >/dev/null 2>&1; then
	echo "the shipped patch series must not add an MT6878 GPU DT node" >&2
	exit 1
fi

make -C "$kernel_tree" ARCH=arm64 LLVM=1 \
	M=drivers/gpu/drm/panthor panthor.o
test -s "$kernel_tree/drivers/gpu/drm/panthor/panthor.o"

echo "Panthor compile-only/default-off validation passed"
