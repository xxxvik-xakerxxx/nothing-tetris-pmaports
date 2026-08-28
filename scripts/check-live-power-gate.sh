#!/bin/sh
set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}
mode=${4:-audit}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-power-gate"
ssh_opts='-o ConnectTimeout=10 -o PreferredAuthentications=password -o PubkeyAuthentication=no -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

mkdir -p "$outdir"

fail() {
	echo "FAIL: $*" >&2
	echo "logs: $outdir" >&2
	exit 1
}

supply_has_property() {
	awk -v supply="$1" -v property="$2" '
		/^### / {
			in_supply = ($0 == "### " supply)
			next
		}
		in_supply && index($0, property "=") == 1 { found = 1 }
		END { exit !found }
	' "$outdir/power.txt"
}

supply_property_value() {
	awk -v supply="$1" -v property="$2" '
		/^### / {
			in_supply = ($0 == "### " supply)
			next
		}
		in_supply && index($0, property "=") == 1 {
			print substr($0, length(property) + 2)
			exit
		}
	' "$outdir/power.txt"
}

require_supply_range() {
	value=$(supply_property_value "$1" "$2")
	case "$value" in
		''|*[!0-9-]*) fail "$1 $2 is absent or non-numeric: $value" ;;
	esac
	[ "$value" -ge "$3" ] && [ "$value" -le "$4" ] ||
		fail "$1 $2 is outside [$3, $4]: $value"
}

require_supply_value() {
	value=$(supply_property_value "$1" "$2")
	[ "$value" = "$3" ] || fail "$1 $2 expected $3, got ${value:-missing}"
}

require_supply_status() {
	value=$(supply_property_value "$1" status)
	case "$value" in
		Charging|Discharging|"Not charging"|Full) ;;
		*) fail "$1 status is absent or invalid: ${value:-missing}" ;;
	esac
}

if ! sshpass -p "$password" ssh $ssh_opts "$user@$host" sh -s -- "$password" \
	> "$outdir/power.txt" 2> "$outdir/ssh.err" <<'EOF'
password=$1

echo "== identity =="
uname -a
cat /proc/cmdline
uptime

echo "== power supplies =="
for supply in /sys/class/power_supply/*; do
	echo "### ${supply##*/}"
	for property in type scope status online usb_type voltage_now voltage_max \
		current_now current_max input_current_limit \
		constant_charge_current input_voltage_limit \
		constant_charge_voltage charge_term_current charge_behaviour \
		charge_counter capacity temp; do
		if [ -r "$supply/$property" ]; then
			printf '%s=' "$property"
			cat "$supply/$property"
		fi
	done
done

echo "== upower display device =="
upower -i /org/freedesktop/UPower/devices/DisplayDevice

echo "== type-c =="
for property in /sys/class/typec/port*/data_role \
	/sys/class/typec/port*/power_role \
	/sys/class/typec/port*/power_operation_mode \
	/sys/class/typec/port*/orientation /sys/class/usb_role/*/role; do
	if [ -r "$property" ]; then
		printf '%s=' "$property"
		cat "$property"
	fi
done

echo "== mt6375 adc =="
for device in /sys/bus/iio/devices/iio:device*; do
	[ -r "$device/name" ] || continue
	[ "$(cat "$device/name")" = mt6375-adc ] || continue
	echo "device=$device"
	for property in in_current5_raw in_current5_scale \
		in_current6_raw in_current6_scale in_current16_raw \
		in_current16_scale in_temp8_raw in_temp8_scale \
		in_temp8_offset in_voltage4_raw in_voltage4_scale \
		in_voltage1_raw in_voltage1_scale; do
		if [ -r "$device/$property" ]; then
			printf '%s=' "$property"
			cat "$device/$property"
		fi
	done
done

echo "== mt6375 battery auxadc =="
for device in /sys/bus/iio/devices/iio:device*; do
	[ -r "$device/name" ] || continue
	[ "$(cat "$device/name")" = mt6375-auxadc ] || continue
	echo "device=$device"
	for property in "$device"/in_voltage*_raw "$device"/in_voltage*_scale; do
		if [ -r "$property" ]; then
			printf '%s=' "${property##*/}"
			cat "$property"
		fi
	done
done

echo "== charger registers =="
printf '%s\n' "$password" | sudo -S sh -c '
	registers=/sys/kernel/debug/regmap/5-0034/registers
	if [ -r "$registers" ]; then
		sed -n "/^0120:/p; /^0122:/p; /^0123:/p; /^0125:/p; /^0126:/p; /^0127:/p; /^0128:/p; /^012a:/p; /^0134:/p" "$registers"
	fi
' 2>&1

echo "== cpuidle =="
for state in /sys/devices/system/cpu/cpu0/cpuidle/state*; do
	echo "### $state"
	for property in name disable usage time; do
		if [ -r "$state/$property" ]; then
			printf '%s=' "$property"
			cat "$state/$property"
		fi
	done
done

echo "== failures =="
systemctl --failed --no-pager
dmesg -T | grep -Ei 'mt6375|charger|battery|tcpm|typec|usb0|ncm|BUG:|WARNING:|Oops:|Kernel panic' | tail -n 400
EOF

then
	fail "power gate SSH command failed"
fi

grep -Eq '^### (tetris-battery|mt6375-gauge)$' "$outdir/power.txt" ||
	fail "battery power supply is missing"
grep -q '^device=/sys/bus/iio/devices/iio:device' "$outdir/power.txt" ||
	fail "MT6375 ADC is missing"
grep -q '^0122:' "$outdir/power.txt" ||
	fail "MT6375 AICR register is not readable"
grep -q '^0126:' "$outdir/power.txt" ||
	fail "MT6375 ICHG register is not readable"
awk '
	/^== mt6375 adc ==$/ { in_adc = 1; next }
	/^== charger registers ==$/ { in_adc = 0 }
	in_adc && /^in_temp8_raw=/ { split($0, a, "="); raw = a[2] }
	in_adc && /^in_temp8_offset=/ { split($0, a, "="); offset = a[2] }
	END {
		if (raw == "" || offset == "")
			exit 2
		temperature = raw + offset
		if (temperature < -20 || temperature > 100)
			exit 3
	}
' "$outdir/power.txt" ||
	fail "MT6375 die temperature is absent or implausible"
if [ "$mode" = charger ]; then
	grep -q '^### mt6375-gauge$' "$outdir/power.txt" ||
		fail "MT6375 battery gauge power supply is missing"
	supply_has_property mt6375-gauge scope ||
		fail "MT6375 telemetry scope is missing"
	supply_has_property mt6375-gauge current_now ||
		fail "MT6375 signed battery current is missing"
	supply_has_property mt6375-gauge temp ||
		fail "MT6375 battery temperature is missing"
	supply_has_property mt6375-gauge charge_counter ||
		fail "MT6375 coulomb counter is missing"
	require_supply_range mt6375-gauge voltage_now 3000000 4500000
	require_supply_range mt6375-gauge current_now -5000000 5000000
	require_supply_range mt6375-gauge temp -100 700
	require_supply_range mt6375-gauge charge_counter -1000000000000 1000000000000
	require_supply_range mt6375-gauge capacity 0 100
	require_supply_value mt6375-gauge scope System
	require_supply_status mt6375-gauge
	awk '
		/^== upower display device ==$/ { in_upower = 1; next }
		/^== type-c ==$/ { in_upower = 0 }
		in_upower && /power supply:/ && /yes/ { system_battery = 1 }
		in_upower && /percentage:/ {
			gsub(/%/, "", $2)
			percentage = $2 + 0
			if ($2 ~ /^[0-9]+([.][0-9]+)?$/ &&
			    percentage >= 0 && percentage <= 100)
				valid_percentage = 1
		}
		in_upower && /battery-missing-symbolic/ { missing_icon = 1 }
		END { exit !(system_battery && valid_percentage && !missing_icon) }
	' "$outdir/power.txt" ||
		fail "UPower does not expose a valid system battery"
	grep -q '^### mt6375-charger$' "$outdir/power.txt" ||
		fail "MT6375 charger power supply is missing"
	supply_has_property mt6375-charger input_current_limit ||
		fail "MT6375 charger AICR property is missing"
	supply_has_property mt6375-charger constant_charge_current ||
		fail "MT6375 charger ICHG property is missing"
	supply_has_property mt6375-charger charge_term_current ||
		fail "MT6375 charger termination property is missing"
	supply_has_property mt6375-charger input_voltage_limit ||
		fail "MT6375 charger MIVR property is missing"
	supply_has_property mt6375-charger constant_charge_voltage ||
		fail "MT6375 charger CV property is missing"
	require_supply_value mt6375-charger input_current_limit 1000000
	require_supply_value mt6375-charger constant_charge_current 500000
	require_supply_value mt6375-charger input_voltage_limit 4500000
	require_supply_value mt6375-charger constant_charge_voltage 4350000
	require_supply_value mt6375-charger charge_term_current 0
fi
if grep -Eiq 'BUG:|Oops:|Kernel panic' "$outdir/power.txt"; then
	fail "kernel fatal pattern present in power log"
fi

printf 'PASS: power gate %s\nlogs: %s\n' "$mode" "$outdir"
