#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

usage() {
	echo "usage: $0 /path/to/downloaded-radio-artifact [expected-github-sha]" >&2
	exit 2
}

[ "$#" -ge 1 ] && [ "$#" -le 2 ] || usage

artifact_dir=${1%/}
expected_sha=${2:-}

[ -d "$artifact_dir" ] || {
	echo "artifact directory is missing: $artifact_dir" >&2
	exit 1
}

find_one() {
	name=$1
	matches=$(find "$artifact_dir" -maxdepth 2 -type f -name "$name" -print)
	count=$(printf '%s\n' "$matches" | sed '/^$/d' | wc -l | tr -d ' ')
	if [ "$count" != 1 ]; then
		echo "expected exactly one $name below $artifact_dir, found $count" >&2
		printf '%s\n' "$matches" >&2
		exit 1
	fi
	printf '%s\n' "$matches"
}

manifest=$(find_one nothing-tetris-radio-live.MANIFEST)
payload=$(find_one nothing-tetris-radio-live.tar.zst)

require_manifest_key() {
	key=$1
	grep -Eq "^$key=[^[:space:]]+$" "$manifest" || {
		echo "missing or malformed radio manifest key: $key" >&2
		exit 1
	}
}

for key in \
	github_sha \
	kernel_release \
	pmbootstrap_commit \
	pmaports_commit \
	connectivity_source \
	device_modules_source \
	required_uboot_commit \
	required_uboot_sha256; do
	require_manifest_key "$key"
done

github_sha=$(sed -n 's/^github_sha=//p' "$manifest")
if [ -n "$expected_sha" ] && [ "$github_sha" != "$expected_sha" ]; then
	echo "radio artifact github_sha mismatch: got $github_sha expected $expected_sha" >&2
	exit 1
fi

case "$(sed -n 's/^kernel_release=//p' "$manifest")" in
	6.18.*) ;;
	*)
		echo "unexpected kernel_release in radio manifest" >&2
		exit 1
		;;
esac

payload_hash=$(sed -n "s#  .*/$(basename "$payload")\$##p" "$manifest")
[ -n "$payload_hash" ] || {
	echo "radio manifest does not record payload checksum" >&2
	exit 1
}
printf '%s  %s\n' "$payload_hash" "$payload" | sha256sum -c -

list=$(mktemp)
trap 'rm -f "$list"' EXIT
tar --zstd -tf "$payload" > "$list"

require_payload() {
	path=$1
	grep -Fx "$path" "$list" >/dev/null || {
		echo "radio payload is missing: $path" >&2
		exit 1
	}
}

for path in \
	lib/modules/6.18.0/extra/mediatek-connectivity/connadp.ko \
	lib/modules/6.18.0/extra/mediatek-connectivity/conninfra.ko \
	lib/modules/6.18.0/extra/mediatek-connectivity/connfem.ko \
	lib/modules/6.18.0/extra/mediatek-connectivity/wmtWifi.ko \
	lib/modules/6.18.0/extra/mediatek-connectivity/wlan_drv_gen4m_6878.ko \
	lib/modules/6.18.0/extra/mediatek-connectivity/bt_drv_6878.ko \
	lib/modules/6.18.0/extra/mediatek-connectivity/gps_drv_dl_v051.ko \
	usr/lib/firmware/connsys_wifi_mt6878_mt6631.bin \
	usr/lib/firmware/connsys_bt_mt6878_mt6631.bin \
	usr/lib/firmware/connsys_gnss_mt6878_mt6631.bin \
	usr/lib/systemd/system/nothing-tetris-connectivity.service \
	usr/lib/systemd/system/nothing-tetris-wifi-nvram.service \
	usr/lib/systemd/system/nothing-tetris-bluetooth-address.service \
	usr/lib/systemd/system-preset/89-nothing-tetris.preset; do
	require_payload "$path"
done

if grep -E '(^|/)(ccci|dpmaif|ccmni|modem|wwan|mnl|gpsd|geoclue)' "$list" >/dev/null; then
	echo "radio payload contains modem or navigation userspace runtime unexpectedly" >&2
	grep -E '(^|/)(ccci|dpmaif|ccmni|modem|wwan|mnl|gpsd|geoclue)' "$list" >&2
	exit 1
fi

cat <<EOF
Radio live artifact verification passed
github_sha=$github_sha
kernel_release=$(sed -n 's/^kernel_release=//p' "$manifest")
connectivity_source=$(sed -n 's/^connectivity_source=//p' "$manifest")
device_modules_source=$(sed -n 's/^device_modules_source=//p' "$manifest")
required_uboot_commit=$(sed -n 's/^required_uboot_commit=//p' "$manifest")
payload_sha256=$payload_hash
payload_entries=$(wc -l < "$list" | tr -d ' ')
runtime_scope=Wi-Fi/Bluetooth/GNSS transport payload only; no modem/CCCI/DPMAIF/WWAN or navigation userspace
EOF
