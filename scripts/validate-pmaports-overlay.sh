#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
kernel_pkg="$repo_root/pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
device_pkg="$repo_root/pmaports/device/testing/device-nothing-tetris"
firmware_pkg="$repo_root/pmaports/device/testing/firmware-nothing-tetris"
kernel_apkbuild="$kernel_pkg/APKBUILD"

# Nothing OS 4.1 (Tetris-B4.1-260415-1709) is the minimum accepted vendor
# baseline. Keep these immutable pins in sync with docs/NOTHINGOSS_SOURCES.md.
connmods_b41=e96f60dc081ae3525ef43d4bcf0ee5ee97e53835
devmods_b41=ee2be53cb75670b548948636a0db1d1ff112bf12

validate_sums() {
	pkgdir=$1
	awk '
		BEGIN { in_sums = 0 }
		/^sha512sums="/ { in_sums = 1; next }
		in_sums && /^"$/ { exit }
		in_sums && NF >= 2 { print $1 "  " $2 }
	' "$pkgdir/APKBUILD" |
	while read -r expected file; do
		case "$file" in
			http://*|https://*|*::*|*.tar|*.tar.*)
				continue
				;;
		esac

		if [ ! -f "$pkgdir/$file" ]; then
			echo "missing source: $pkgdir/$file" >&2
			return 1
		fi

		actual=$(sha512sum "$pkgdir/$file" | awk '{ print $1 }')
		if [ "$actual" != "$expected" ]; then
			echo "checksum mismatch: $pkgdir/$file" >&2
			echo "expected: $expected" >&2
			echo "actual:   $actual" >&2
			return 1
		fi
	done
}

validate_source_files() {
	pkgdir=$1
	awk '
		BEGIN { in_source = 0 }
		/^source="/ { in_source = 1; next }
		in_source && /^"$/ { exit }
		in_source && NF >= 1 { print $1 }
	' "$pkgdir/APKBUILD" |
	while read -r source; do
		case "$source" in
			http://*|https://*|*::*|\$*)
				continue
				;;
		esac

		if [ ! -f "$pkgdir/$source" ]; then
			echo "missing source entry: $pkgdir/$source" >&2
			return 1
		fi
	done
}

validate_vendor_baseline() {
	if ! grep -Fq "_connmods_commit=\"$connmods_b41\"" "$kernel_apkbuild"; then
		echo "connectivity sources must be pinned to Nothing OS 4.1 commit $connmods_b41" >&2
		return 1
	fi

	if ! grep -Fq "_devmods_commit=\"$devmods_b41\"" "$kernel_apkbuild"; then
		echo "device-module sources must be pinned to Nothing OS 4.1 commit $devmods_b41" >&2
		return 1
	fi
}

validate_connectivity_boot() {
	setup="$device_pkg/nothing-tetris-connectivity-setup"
	service="$device_pkg/nothing-tetris-connectivity.service"
	nvram_service="$device_pkg/nothing-tetris-wifi-nvram.service"
	bt_address_service="$device_pkg/nothing-tetris-bluetooth-address.service"
	bt_service_dropin="$device_pkg/nothing-tetris-bluetooth.service.conf"
	bt_helper="$device_pkg/nothing-tetris-bluetooth-address.c"
	bt_patch="$kernel_pkg/1001-vendor-connectivity-linux-6.18-compat.patch.vendor"

	if grep -Fq 'wmt_drv' "$setup" "$kernel_apkbuild"; then
		echo "wmt_drv must not be loaded or packaged; it conflicts with conninfra" >&2
		return 1
	fi

	grep -Fq 'nothing-tetris-wifi-nvram-load' "$setup"
	grep -Fq 'load_modules bluetooth bt_drv_6878' "$setup"
	grep -Fq "printf '1' > /dev/wmtWifi" "$setup"
	grep -Fq 'Before=NetworkManager.service bluetooth.service iwd.service' "$service"
	grep -Fq 'Requires=nothing-tetris-wifi-nvram.service' "$service"
	grep -Fq 'Requires=dev-disk-by\x2dpartlabel-nvdata.device' "$nvram_service"
	grep -Fq '/APCFG/APRDEB/BT_Addr' "$device_pkg/nothing-tetris-wifi-nvram-extract"
	grep -Fq 'Before=bluetooth.service' "$bt_address_service"
	grep -Fq 'Requires=nothing-tetris-bluetooth-address.service' "$bt_service_dropin"
	grep -Fq 'MGMT_OP_SET_PUBLIC_ADDRESS' "$bt_helper"
	grep -Fq 'HCI_QUIRK_INVALID_BDADDR' "$bt_patch"
	grep -Fq 'hdev->set_bdaddr = btmtk_set_public_address' "$bt_patch"
}

validate_sums "$kernel_pkg"
validate_sums "$device_pkg"
validate_sums "$firmware_pkg"
validate_source_files "$kernel_pkg"
validate_source_files "$device_pkg"
validate_source_files "$firmware_pkg"
validate_vendor_baseline
validate_connectivity_boot

echo "pmaports overlay validation passed"
