#!/bin/sh
set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-thermal-gate"
ssh_opts='-o ConnectTimeout=10 -o PreferredAuthentications=password -o PubkeyAuthentication=no -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

mkdir -p "$outdir"

fail() {
	echo "FAIL: $*" >&2
	echo "logs: $outdir" >&2
	exit 1
}

sshpass -p "$password" ssh $ssh_opts "$user@$host" 'set +e
echo "== identity =="
uname -a
apk info -vv | sort | grep -E "^(device-nothing-tetris|firmware-nothing-tetris|linux-postmarketos-mediatek-mt6878)"

echo "== usb invariant =="
ip -br addr show usb0
systemctl is-active sshd NetworkManager bluetooth nothing-tetris-connectivity.service 2>/dev/null

echo "== thermal zones =="
find -L /sys/class/thermal -maxdepth 2 -type f \( -name type -o -name temp -o -name mode -o -name policy \) -print -exec cat {} \; 2>/dev/null

echo "== hwmon thermal =="
find -L /sys/class/hwmon -maxdepth 3 -type f \( -name name -o -name "temp*_input" -o -name "temp*_label" \) -print -exec cat {} \; 2>/dev/null

echo "== lvts log =="
dmesg -T | grep -Ei "lvts|thermal|devinfo|nvmem|usb0|ncm|gadget|BUG|WARNING|Oops|panic" | tail -n 700
' > "$outdir/thermal.txt" 2> "$outdir/ssh.err" ||
	fail "thermal gate SSH command failed"

grep -q '/sys/class/thermal/thermal_zone' "$outdir/thermal.txt" ||
	fail "no thermal zones exposed"
grep -Eq '/sys/class/thermal/thermal_zone[0-9]+/temp' "$outdir/thermal.txt" ||
	fail "no thermal zone temp files exposed"
grep -q 'usb0' "$outdir/thermal.txt" ||
	fail "usb0 is not visible during thermal gate"
if grep -Eiq 'BUG|Oops|panic' "$outdir/thermal.txt"; then
	fail "kernel fatal pattern present in thermal log"
fi

awk '
	/\/sys\/class\/thermal\/thermal_zone[0-9]+\/temp/ {
		getline value
		if (value ~ /^-?[0-9]+$/) {
			count++
			if (value < -20000 || value > 120000)
				bad++
		}
	}
	END {
		if (count < 24)
			exit 2
		if (bad > 0)
			exit 3
	}
' "$outdir/thermal.txt" ||
	fail "fewer than 24 thermal temperatures are present or a value is outside the conservative range"

printf 'PASS: thermal gate\nlogs: %s\n' "$outdir"
