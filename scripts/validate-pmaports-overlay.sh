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
	bt_extract_service="$device_pkg/nothing-tetris-bluetooth-address-extract.service"
	bt_service_dropin="$device_pkg/nothing-tetris-bluetooth.service.conf"
	bt_extract="$device_pkg/nothing-tetris-bluetooth-address-extract"
	bt_helper="$device_pkg/nothing-tetris-bluetooth-address.c"
	bt_patch="$kernel_pkg/1001-vendor-connectivity-linux-6.18-compat.patch.vendor"
	dts_patch="$kernel_pkg/0004-arm64-dts-mt6878-tetris-disabled-peripherals.patch"
	wifi_powersave="$device_pkg/20-nothing-tetris-wifi-powersave.conf"
	preset="$device_pkg/89-nothing-tetris.preset"
	modules_initfs="$device_pkg/modules-initfs"
	wifi_cfg="$device_pkg/wifi.cfg"

	if grep -Fq 'wmt_drv' "$setup" "$kernel_apkbuild"; then
		echo "wmt_drv must not be loaded or packaged; it conflicts with conninfra" >&2
		return 1
	fi
	if grep -Fq '_conn"/common' "$kernel_apkbuild"; then
		echo "radio modules must resolve connlog symbols from conninfra, not legacy common" >&2
		return 1
	fi

	grep -Fq 'nothing-tetris-wifi-nvram-load' "$setup"
	grep -Fq 'modprobe "$module"' "$setup"
	grep -Fq 'partial radio state detected; reboot before retrying' "$setup"
	grep -Fq 'bring_up_radios' "$setup"
	grep -Fq 'load_modules bluetooth bt_drv_6878' "$setup"
	grep -Fq '[ ! -d /sys/class/bluetooth/hci0 ]' "$setup"
	grep -Fq "printf '1' > /dev/wmtWifi" "$setup"
	grep -Fq 'Before=NetworkManager.service bluetooth.service iwd.service' "$service"
	grep -Fq 'ExecStart=/usr/libexec/nothing-tetris-connectivity-setup all' "$service"
	grep -Fq 'Requires=nothing-tetris-wifi-nvram.service' "$service"
	grep -Fq 'Requires=dev-disk-by\x2dpartlabel-nvdata.device' "$nvram_service"
	if grep -Fq '/APCFG/APRDEB/BT_Addr' "$device_pkg/nothing-tetris-wifi-nvram-extract"; then
		echo "Bluetooth factory data must not block Wi-Fi NVRAM extraction" >&2
		return 1
	fi
	grep -Fq '/APCFG/APRDEB/BT_Addr' "$bt_extract"
	grep -Fq 'Requires=dev-disk-by\x2dpartlabel-nvdata.device' "$bt_extract_service"
	grep -Fq 'Requires=nothing-tetris-bluetooth-address-extract.service nothing-tetris-connectivity.service' "$bt_address_service"
	grep -Fq 'Before=bluetooth.service' "$bt_address_service"
	grep -Fq 'Requires=nothing-tetris-bluetooth-address.service' "$bt_service_dropin"
	grep -Fq 'MGMT_OP_SET_PUBLIC_ADDRESS' "$bt_helper"
	grep -Fq 'HCI_QUIRK_INVALID_BDADDR' "$bt_patch"
	grep -Fq 'hdev->set_bdaddr = btmtk_set_public_address' "$bt_patch"
	grep -Fxq '[connection]' "$wifi_powersave"
	grep -Fxq 'wifi.powersave=3' "$wifi_powersave"
	grep -Fq '/usr/lib/NetworkManager/conf.d/20-nothing-tetris-wifi-powersave.conf' \
		"$device_pkg/APKBUILD"
	grep -Fq 'DBGLOG(SW4, TRACE, TEMP_LOG_TEMPLATE' "$bt_patch"
	grep -Fq 'DBGLOG(HAL, TRACE, "%s\n", buf)' "$bt_patch"
	grep -Fq '+		consys_emi: mblock-41-consys_emi_reserved {' "$dts_patch"
	grep -Fq '+		wifi_reserved: mblock-42-shared-dma-pool_wifi-reserve-memory_dma {' "$dts_patch"
	grep -Fq '+		memory-region = <&consys_emi>;' "$dts_patch"
	grep -Fq '+		memory-region = <&wifi_reserved>;' "$dts_patch"
	grep -Fq '+		mediatek,main-pmic = <&main_pmic>;' "$dts_patch"
	grep -Fq '+		mediatek,secondary-pmic = <&second_pmic>;' "$dts_patch"
	for supply in \
		mt6363_vcn13 \
		mt6363_vrfio18 \
		mt6369_vcn33_1 \
		mt6369_vcn33_2 \
		mt6369_vant18; do
		grep -Fq "+		$supply-supply = <&$supply>;" "$dts_patch"
	done
	grep -Fq '+		vcn13-supply = <&mt6363_vcn13>;' "$dts_patch"
	grep -Fq '+		vrfio18-supply = <&mt6363_vrfio18>;' "$dts_patch"
	grep -Fq '+		vcn33-1-supply = <&mt6369_vcn33_1>;' "$dts_patch"
	grep -Fq '+		vcn33-2-supply = <&mt6369_vcn33_2>;' "$dts_patch"
	test "$(grep -c '^+.*status = "okay";' "$dts_patch")" -ge 3
	grep -Fxq 'enable nothing-tetris-wifi-nvram.service' "$preset"
	grep -Fxq 'enable nothing-tetris-connectivity.service' "$preset"
	grep -Fxq 'enable nothing-tetris-bluetooth-address-extract.service' "$preset"
	grep -Fxq 'enable nothing-tetris-bluetooth-address.service' "$preset"
	grep -Fxq 'deviceinfo_usb_network_function="ncm.usb0"' \
		"$device_pkg/deviceinfo"
	test "$(cat "$modules_initfs")" = usb_f_ncm
	test "$(grep -Ev '^[[:space:]]*(#|$)' "$wifi_cfg")" = \
		'DbgLevel0 0xffffffff 0x0f'
	if grep -Fq 'multi-user.target.wants/nothing-tetris-' "$device_pkg/APKBUILD"; then
		echo "device package must use systemd presets instead of packaged enablement links" >&2
		return 1
	fi
}

validate_power_and_audio_config() {
	config="$kernel_pkg/config-postmarketos-mediatek-mt6878.aarch64"
	apkbuild="$kernel_pkg/APKBUILD"
	cpu_patch="$kernel_pkg/0019-arm64-dts-mt6878-shallow-cpuidle.patch"
	pmdomain_patch="$kernel_pkg/0018-pmdomain-mediatek-mt6878-audio.patch"
	audio_patch="$kernel_pkg/0010-audio-mt6878-aw88261.patch"
	audio_vendor_patch="$kernel_pkg/1102-vendor-audio-linux-6.18-api.patch.vendor"
	audio_clock_patch="$kernel_pkg/1103-vendor-audio-mt6685-clock.patch.vendor"
	audio_modules="$device_pkg/nothing-tetris-audio.conf"
	audio_pulse="$device_pkg/nothing-tetris-audio.pa"
	audio_policy="$device_pkg/nothing-tetris-audio-policy"
	audio_policy_unit="$device_pkg/nothing-tetris-audio-policy.service"
	audio_user_preset="$device_pkg/89-nothing-tetris-user.preset"
	audio_ucm="$device_pkg/HiFi.conf"
	audio_ucm_card="$device_pkg/mt6878-mt6369.conf"

	for option in \
		CONFIG_BT_RFCOMM=m \
		CONFIG_BT_RFCOMM_TTY=y \
		CONFIG_BT_BNEP=m \
		CONFIG_BT_BNEP_MC_FILTER=y \
		CONFIG_BT_BNEP_PROTO_FILTER=y \
		CONFIG_CPU_IDLE=y \
		CONFIG_CPU_IDLE_GOV_MENU=y \
		CONFIG_DT_IDLE_STATES=y \
		CONFIG_ARM_PSCI_CPUIDLE=y \
		CONFIG_SND_DYNAMIC_MINORS=y \
		CONFIG_SND_MAX_CARDS=32; do
		grep -Fxq "$option" "$config"
	done

	grep -Fq 'export PATH="/usr/lib/llvm21/bin:$PATH"' "$apkbuild"
	grep -Fq 'make ARCH="$_carch" LLVM=1 olddefconfig' "$apkbuild"
	grep -Eq '^\+[[:space:]]*infracfg_ao: syscon@10001000 \{' "$pmdomain_patch"
	grep -Eq '^\+[[:space:]]*infracfg = <&infracfg_ao>;' "$pmdomain_patch"
	grep -Fq '+#define MTK_SCPD_STATUS_IN_CTL' "$pmdomain_patch"
	grep -Fq '+#define PWR_ACK_BIT' "$pmdomain_patch"
	grep -Fq '+#define PWR_ACK_2ND_BIT' "$pmdomain_patch"
	grep -Eq '^\+[[:space:]]*if \(MTK_SCPD_CAPS\(pd, MTK_SCPD_STATUS_IN_CTL\)\) \{' \
		"$pmdomain_patch"
	grep -Fxq '# CONFIG_ARM_PSCI_CPUIDLE_DOMAIN is not set' "$config"
	test "$(grep -c '^+.*compatible = "arm,cortex-a55";' "$cpu_patch")" -eq 4
	test "$(grep -c '^+.*compatible = "arm,cortex-a78";' "$cpu_patch")" -eq 4

	expected_audio_modules=$(printf 'mtk_spmi_pmic_adc\nnvmem_mt635x_efuse\nmt6685_core\nmt6685_audclk\nsnd_soc_mt6878_afe\nmt6878_mt6369')
	actual_audio_modules=$(grep -Ev '^[[:space:]]*(#|$)' "$audio_modules")
	if [ "$actual_audio_modules" != "$expected_audio_modules" ]; then
		echo "audio module autoload order must load calibration and MT6685 clock suppliers before AFE and the machine driver" >&2
		return 1
	fi

	grep -Fq 'compatible = "mediatek,mt6685";' "$audio_patch"
	grep -Fq 'reg = <0x9 SPMI_USID>;' "$audio_patch"
	grep -Fq 'mt6685_set_dcxo_mode(0);' "$audio_clock_patch"
	grep -Fq 'mt6685_set_dcxo(false);' "$audio_clock_patch"
	grep -Fq 'MT6878_AFE_GPIO_CLK_MOSI_ON' "$audio_clock_patch"
	grep -Fq 'mt6878_afe_gpio_select(afe, MT6878_AFE_GPIO_CLK_MOSI_ON)' \
		"$audio_clock_patch"
	grep -Fq -- '-DCONFIG_MT6685_AUDCLK_MODULE=1' "$apkbuild"
	grep -Fq 'mt6685-core.ko mt6685-audclk.ko' "$apkbuild"
	grep -Fq '"$_devmods_dir"/drivers/mfd/mt6685-core.ko' "$apkbuild"
	grep -Fq '"$_devmods_dir"/drivers/mfd/mt6685-audclk.ko' "$apkbuild"
	grep -Eq '^[[:space:]]+alsa-ucm-conf$' "$device_pkg/APKBUILD"
	grep -Fq 'usr/share/alsa/ucm2/MediaTek/mt6878-mt6369/HiFi.conf' \
		"$device_pkg/APKBUILD"
	grep -Fq 'etc/pulse/default.pa.d/90-nothing-tetris-audio.pa' \
		"$device_pkg/APKBUILD"
	grep -Fq 'SectionUseCase."HiFi"' "$audio_ucm_card"
	for device in Speaker Earpiece Mic; do
		grep -Fq "SectionDevice.\"$device\"" "$audio_ucm"
	done
	grep -Fxq 'Syntax 6' "$audio_ucm"
	test "$(grep -c 'PlaybackPCM "hw:${CardId},6"' "$audio_ucm")" -eq 2
	test "$(grep -c 'PlaybackChannels 2' "$audio_ucm")" -eq 2
	test "$(grep -c 'PlaybackChannelPos0 FL' "$audio_ucm")" -eq 2
	test "$(grep -c 'PlaybackChannelPos1 FR' "$audio_ucm")" -eq 2
	grep -Fq "name='PCM Playback Volume' 0" "$audio_ucm"
	if grep -Eq 'LibraryConfig|type (dshare|route)' "$audio_ucm"; then
		echo "audio UCM must use the live-validated direct DL6 transport" >&2
		return 1
	fi
	grep -Fq 'unload-module module-stream-restore' "$audio_pulse"
	grep -Fq 'load-module module-stream-restore restore_device=false' "$audio_pulse"
	grep -Fq 'load-module module-remap-sink sink_name=tetris_mono_speaker' \
		"$audio_pulse"
	grep -Fq 'master=alsa_output.platform-sound.HiFi__Speaker__sink' \
		"$audio_pulse"
	grep -Fq 'channels=1 channel_map=mono master_channel_map=front-left' \
		"$audio_pulse"
	grep -Fq 'device.class=filter' "$audio_pulse"
	grep -Fq 'device.class=sound' "$audio_pulse"
	grep -Fq 'set-default-sink tetris_mono_speaker' "$audio_pulse"
	sh -n "$audio_policy"
	grep -Fq 'pactl subscribe' "$audio_policy"
	grep -Fq "Event 'new' on sink #" "$audio_policy"
	grep -Fq 'pactl set-default-sink "$mono_sink"' "$audio_policy"
	grep -Fq 'ExecStart=/usr/libexec/nothing-tetris-audio-policy' \
		"$audio_policy_unit"
	grep -Fxq 'WantedBy=default.target' "$audio_policy_unit"
	grep -Fxq 'enable nothing-tetris-audio-policy.service' \
		"$audio_user_preset"
	grep -Fq 'I2SOUT4_CH1 DL6_CH1' "$audio_ucm"
	grep -Fq "name='RCV Mux' 'Voice Playback'" "$audio_ucm"
	grep -Fq "name='PGA_L_Mux' AIN0" "$audio_ucm"
	grep -Fq "name='PGA_R_Mux' AIN2" "$audio_ucm"

	grep -Fq '+	.mute_stream = aw88261_mute_stream,' "$audio_patch"
	grep -Fq '+				topckgen = <&topckgen>;' "$audio_patch"
	grep -Fq '+				apmixedsys = <&apmixedsys>;' "$audio_patch"
	grep -Fq '+		audio_sram: sram@11059000 {' "$audio_patch"
	grep -Fq '+#include "clk-gate.h"' "$audio_patch"
	grep -Fq '+#define CLK_AUDDIV_2' "$audio_patch"
	grep -Fq '+	FACTOR(CLK_TOP_ARMPLL_26M, "armpll_26m_ck",' \
		"$audio_patch"
	grep -Fq '+			"None", 1, 1),' "$audio_patch"
	grep -Fq '+	DIV_GATE(CLK_TOP_APLL12_DIV_SI1, "apll12_div_si1",' \
		"$audio_patch"
	grep -Fq '+		"apll_SI1_m_sel", CLK_AUDDIV_0, 1,' "$audio_patch"
	grep -Fq '+		CLK_AUDDIV_2, 8, 8),' "$audio_patch"
	if grep -Fq 'GATE_TOP(CLK_TOP_APLL12_DIV_SI1' "$audio_patch"; then
		echo "I2SIN1 MCK must be a programmable CCF divider, not a gate" >&2
		return 1
	fi
	grep -Fq '+	.composite_clks = top_aud_divs,' "$audio_patch"
	grep -Fq '+	.num_composite_clks = ARRAY_SIZE(top_aud_divs),' "$audio_patch"
	for clock in \
		CLK_TOP_APLL_SI1_MCK_SEL \
		CLK_TOP_APLL_FMI2S_MCK_SEL \
		CLK_TOP_APLL12_DIV_SI1 \
		CLK_TOP_APLL12_DIV_FMI2S; do
		grep -Fq "$clock" "$audio_patch"
	done
	for property in \
		'etdm-out-ch = <2>;' \
		'etdm-in-ch = <2>;' \
		'etdm-out-sync = <0>;' \
		'etdm-in-sync = <1>;' \
		'etdm-ip-mode = <0>;' \
		'etdm-align-mode = <1>;'; do
		grep -Fq "+				$property" "$audio_patch"
	done
	test "$(grep -c '^+.*return ret;' "$audio_vendor_patch")" -ge 2
	if grep -Fq 'mute_unmute_on_trigger' "$audio_patch"; then
		echo "AW88261 must not run its sleeping mute callback from the atomic trigger path" >&2
		return 1
	fi
	for pin in \
		PINMUX_GPIO42__FUNC_I2SIN4_BCK \
		PINMUX_GPIO43__FUNC_I2SIN4_LRCK \
		PINMUX_GPIO44__FUNC_I2SOUT4_DATA0 \
		PINMUX_GPIO45__FUNC_I2SIN4_DATA0; do
		grep -Fq "+				 <$pin>" "$audio_patch" ||
			grep -Fq "+			pinmux = <$pin>" "$audio_patch"
	done
	grep -Fq 'The composite I2SIN4 state owns BCK, LRCK and both data pins.' \
		"$audio_vendor_patch"
	if grep -Eq '^\+.*MT6878_AFE_GPIO_I2SOUT4_(ON|OFF)' "$audio_vendor_patch"; then
		echo "mainline AFE must select the composite I2S4 state only once" >&2
		return 1
	fi
}

validate_usb_role() {
	kernel_config="$kernel_pkg/config-postmarketos-mediatek-mt6878.aarch64"
	usb_patch="$kernel_pkg/0021-usb-mtu3-native-role-switch.patch"

	grep -Fxq 'CONFIG_USB_MTU3_DUAL_ROLE=y' "$kernel_config"
	grep -Fxq '# CONFIG_USB_MTU3_GADGET is not set' "$kernel_config"
	grep -Fxq 'CONFIG_USB_ROLE_SWITCH=y' "$kernel_config"
	grep -Fq '+			usb-role-switch;' "$usb_patch"
	grep -Fq '+			role-switch-default-mode = "peripheral";' "$usb_patch"
	grep -Fq '+					remote-endpoint = <&typec_hs>;' "$usb_patch"
	grep -Fxq 'deviceinfo_usb_network_function="ncm.usb0"' \
		"$device_pkg/deviceinfo"
	test "$(cat "$device_pkg/modules-initfs")" = usb_f_ncm
}

validate_haptics() {
	haptic_patch="$kernel_pkg/0011-input-rt6010-haptics-tetris.patch"
	feedbackd_rule="$device_pkg/72-nothing-tetris-feedbackd.rules"
	modules_load="$device_pkg/nothing-tetris-haptics.conf"

	for setting in \
		'RT6010_LIST_BASE_ADDR 0x0400' \
		'RT6010_WAVE_BASE_ADDR 0x0420' \
		'RT6010_FIFO_AE 0x0200' \
		'RT6010_FIFO_AF 0x0300' \
		'RT6010_DEFAULT_GAIN 0x7f' \
		'RT6010_MAX_GAIN 0x7f' \
		'RT6010_DEFAULT_BOOST 0x08' \
		'RT6010_PLAY_MODE_RAM 0x01' \
		'RT6010_RAM_REPEAT_COUNT 0x7f' \
		'RT6010_RAM_WAVE_INDEX 0x01'; do
		name=${setting% *}
		value=${setting#* }
		grep -Eq "^\\+#define ${name}[[:space:]]+${value}$" "$haptic_patch"
	done

	grep -Eq '^\+[[:space:]]+schedule_work\(&rt->play_work\);$' "$haptic_patch"
	grep -Eq '^\+[[:space:]]+error = devm_request_threaded_irq\(dev, client->irq, NULL,$' \
		"$haptic_patch"
	grep -Fq '+static DEFINE_SIMPLE_DEV_PM_OPS(rt6010_pm_ops,' "$haptic_patch"
	grep -Eq '^\+[[:space:]]+error = rt6010_write_ram\(rt, RT6010_LIST_BASE_ADDR, playlist,$' \
		"$haptic_patch"
	grep -Eq '^\+[[:space:]]+RT6010_PLAY_MODE_RAM\);$' "$haptic_patch"
	if grep -Eq '^\+[[:space:]]+cancel_delayed_work_sync\(&rt->stop_work\);$' \
		"$haptic_patch"; then
		echo "RT6010 FF callback must not perform synchronous work cancellation in atomic context" >&2
		return 1
	fi
	grep -Fq 'ATTRS{name}=="RT6010 haptics"' "$feedbackd_rule"
	grep -Fq 'ENV{FEEDBACKD_TYPE}="vibra"' "$feedbackd_rule"
	[ "$(cat "$modules_load")" = "rt6010" ]
	grep -Fq '/usr/lib/udev/rules.d/72-nothing-tetris-feedbackd.rules' \
		"$device_pkg/APKBUILD"
	grep -Fq '/usr/lib/modules-load.d/nothing-tetris-haptics.conf' \
		"$device_pkg/APKBUILD"
}

validate_ci_rootfs_module_checks() {
	workflow="$repo_root/.github/workflows/ci.yml"

	grep -Eq '^[[:space:]]+dtc file findutils git kmod linux-headers' "$workflow"
	grep -Fq 'modinfo -b "$rootfs" -k "$release" "$@"' "$workflow"
	grep -Fq 'test "$(rootfs_modinfo -F name gps_drv_dl_v050)"' "$workflow"
	grep -Fq 'if rootfs_modinfo -F depends "$radio_module"' "$workflow"
	if grep -Fq 'test "$(modinfo -F' "$workflow" ||
		grep -Fq 'if modinfo -F' "$workflow"; then
		echo "CI must resolve target modules through the target rootfs/release" >&2
		return 1
	fi
}

validate_connectivity_firmware() {
	config="$firmware_pkg/conninfra.cfg"
	expected_config=$(printf 'co_clock_flag=1\npre_cal_mode=0')
	actual_config=$(cat "$config")
	if [ "$actual_config" != "$expected_config" ]; then
		echo "conninfra.cfg must enable joint Wi-Fi/BT pre-calibration" >&2
		return 1
	fi

	for item in \
		connsys_bt_mt6878_mt6631.bin:740956 \
		connsys_gnss_mt6878_mt6631.bin:523368 \
		connsys_wifi_mt6878_mt6631.bin:1526820; do
		file=${item%:*}
		expected=${item#*:}
		actual=$(wc -c < "$firmware_pkg/$file")
		if [ "$actual" -ne "$expected" ]; then
			echo "invalid extracted firmware size: $file: $actual != $expected" >&2
			return 1
		fi
	done
}

validate_connectivity_build() {
	workflow="$repo_root/.github/workflows/ci.yml"
	gnss_patch="$kernel_pkg/1002-vendor-gnss-linux-6.18-compat.patch.vendor"

	grep -Eq '^  PMBOOTSTRAP_COMMIT: [0-9a-f]{40}$' "$workflow"
	grep -Eq '^  PMAPORTS_COMMIT: [0-9a-f]{40}$' "$workflow"
	grep -Eq '^  TETRIS_UBOOT_COMMIT: [0-9a-f]{40}$' "$workflow"
	grep -Eq '^  TETRIS_UBOOT_SHA256: [0-9a-f]{64}$' "$workflow"
	grep -Fq 'fetch --depth=1 origin "$PMBOOTSTRAP_COMMIT"' "$workflow"
	grep -Fq 'fetch --depth=1 origin "$PMAPORTS_COMMIT"' "$workflow"
	grep -Fq 'refs/remotes/origin/main "$PMAPORTS_COMMIT"' "$workflow"
	if grep -Fq 'CONFIG_SUPPORT_PRE_ON_PHY_ACTION=n' "$kernel_apkbuild"; then
		echo "WLAN must retain the MT6878 joint pre-calibration callbacks" >&2
		exit 1
	fi
	grep -Fq "'-DCONFIG_MTK_COMBO_CHIP_CONSYS_6878=1 '" "$kernel_apkbuild"
	grep -Fq 'gps/data_link/plat/v050' "$kernel_apkbuild"
	grep -Fq 'CONFIG_MTK_GPS_SUPPORT=y' "$kernel_apkbuild"
	grep -Fq 'gps_drv_dl_v050.ko' "$kernel_apkbuild"
	if grep -Eq 'gps/data_link/plat/v06(0|1)|gps_drv_dl_v06(0|1)' \
			"$kernel_apkbuild" "$gnss_patch"; then
		echo "Tetris must use the MT6878 GNSS v050 profile" >&2
		return 1
	fi
	if grep -Fq 'gps_drv_dl_v050' "$device_pkg/nothing-tetris-connectivity-setup"; then
		echo "GNSS must remain manual until position data and suspend are validated" >&2
		return 1
	fi
	grep -Fq 'gzip -cd "$rootfs/boot/vmlinuz"' "$workflow"
	grep -Fq 'nothing-tetris-radio-live.tar.zst' "$workflow"
	grep -Fq 'name: nothing-tetris-radio-live' "$workflow"
	if grep -F 'clang version 21' "$workflow" | grep -Fq 'boot_image.itb'; then
		echo "compiler identity cannot be searched in the compressed FIT image" >&2
		return 1
	fi
}

validate_sums "$kernel_pkg"
validate_sums "$device_pkg"
validate_sums "$firmware_pkg"
validate_source_files "$kernel_pkg"
validate_source_files "$device_pkg"
validate_source_files "$firmware_pkg"
validate_vendor_baseline
validate_connectivity_boot
validate_power_and_audio_config
validate_usb_role
validate_haptics
validate_ci_rootfs_module_checks
validate_connectivity_firmware
validate_connectivity_build

echo "pmaports overlay validation passed"
