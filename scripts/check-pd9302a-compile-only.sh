#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

if [ "$#" -ne 1 ]; then
	echo "usage: $0 /path/to/linux-6.18" >&2
	exit 2
fi

kernel_tree=${1%/}
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(dirname "$script_dir")
patch_dir="$repo_dir/pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
binding_patch="$patch_dir/0046-dt-bindings-media-i2c-pd9302a.patch"
driver_patch="$patch_dir/0047-media-i2c-pd9302a-vcm.patch"
binding_applied=0
driver_applied=0
config_backup=

cleanup() {
	set +e
	rm -f "$kernel_tree/drivers/media/i2c/pd9302a.o" \
		"$kernel_tree/drivers/media/i2c/.pd9302a.o.cmd"
	if [ "$driver_applied" -eq 1 ]; then
		patch -R -s -p1 -d "$kernel_tree" < "$driver_patch"
	fi
	if [ "$binding_applied" -eq 1 ]; then
		patch -R -s -p1 -d "$kernel_tree" < "$binding_patch"
	fi
	if [ -n "$config_backup" ]; then
		cp "$config_backup" "$kernel_tree/.config"
		make -s -C "$kernel_tree" ARCH=arm64 LLVM=1 olddefconfig
		rm -f "$config_backup"
	fi
}
trap cleanup EXIT HUP INT TERM

test -f "$kernel_tree/Makefile"
test -f "$kernel_tree/.config"
test "$(sed -n 's/^VERSION = //p' "$kernel_tree/Makefile")" = 6
test "$(sed -n 's/^PATCHLEVEL = //p' "$kernel_tree/Makefile")" = 18
clang --version | grep -q 'clang version 21\|clang version 21\.'

patch --dry-run -s -p1 -d "$kernel_tree" < "$binding_patch"
patch --dry-run -s -p1 -d "$kernel_tree" < "$driver_patch"
patch -s -p1 -d "$kernel_tree" < "$binding_patch"
binding_applied=1
patch -s -p1 -d "$kernel_tree" < "$driver_patch"
driver_applied=1

config_backup=$(mktemp "${TMPDIR:-/tmp}/pd9302a-config.XXXXXX")
cp "$kernel_tree/.config" "$config_backup"
"$kernel_tree/scripts/config" --file "$kernel_tree/.config" \
	-e MEDIA_SUPPORT \
	-e MEDIA_CAMERA_SUPPORT \
	-e MEDIA_CONTROLLER \
	-e VIDEO_DEV \
	-e VIDEO_V4L2_SUBDEV_API \
	-e VIDEO_CAMERA_LENS \
	-m VIDEO_PD9302A

make -C "$kernel_tree" ARCH=arm64 LLVM=1 olddefconfig
make -C "$kernel_tree" ARCH=arm64 LLVM=1 \
	drivers/media/i2c/pd9302a.o

test -s "$kernel_tree/drivers/media/i2c/pd9302a.o"
test ! -e "$kernel_tree/drivers/media/i2c/pd9302a.ko"
echo "PD9302A compile-only validation passed"
