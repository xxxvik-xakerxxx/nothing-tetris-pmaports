#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
pmos="$repo_root/pmaports/device/testing/linux-postmarketos-mediatek-mt6878/config-postmarketos-mediatek-mt6878.aarch64"
stock_gz="$repo_root/local/notes/device-dumps/20260722T111915Z/adb-pull/proc-config.gz"

symbols='CONFIG_DRM_MEDIATEK|CONFIG_DRM_MIPI_DSI|CONFIG_DRM_PANEL|CONFIG_TOUCHSCREEN_EDT_FT5X06|CONFIG_TOUCHSCREEN_GOODIX|CONFIG_TOUCHSCREEN_ELAN|CONFIG_INV_ICM42600_I2C|CONFIG_LTR501|CONFIG_CHARGER_MT6360|CONFIG_MFD_MT6360|CONFIG_TYPEC_MT6360|CONFIG_BT_MTK|CONFIG_BT_MTKUART|CONFIG_GNSS_MTK_SERIAL|CONFIG_MTK_MMSYS|CONFIG_MTK_SCP|CONFIG_RPMSG_MTK_SCP|CONFIG_SCSI_UFS_MEDIATEK'

show_file() {
	label=$1
	file=$2
	printf "\n[%s]\n" "$label"
	rg -n "^($symbols)=|^# ($symbols) is not set" "$file" || true
}

show_gzip() {
	label=$1
	file=$2
	tmp=$(mktemp)
	gzip -cd "$file" > "$tmp"
	show_file "$label" "$tmp"
	rm -f "$tmp"
}

show_file "postmarketOS" "$pmos"
show_gzip "stock Android" "$stock_gz"
