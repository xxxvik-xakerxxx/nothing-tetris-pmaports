#!/bin/sh
set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}
mode=${4:-baseline}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-hardware-frontier"
control_path="/tmp/nothing-tetris-frontier-$stamp-$$"
ssh_opts="-o ConnectTimeout=10 -o PreferredAuthentications=keyboard-interactive,password -o KbdInteractiveAuthentication=yes -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlMaster=auto -o ControlPersist=60 -o ControlPath=$control_path"

mkdir -p "$outdir"

cleanup() {
	ssh -S "$control_path" -O exit "$user@$host" >/dev/null 2>&1 || true
	rm -f "$control_path"
}

trap cleanup EXIT HUP INT TERM

ssh_phone() {
	sshpass -p "$password" ssh $ssh_opts "$user@$host" "$@"
}

fail() {
	echo "FAIL: $*" >&2
	echo "logs: $outdir" >&2
	exit 1
}

ssh_phone true > "$outdir/ssh-probe.txt" 2> "$outdir/ssh.err" ||
	fail "SSH is not reachable on $host"

ssh_phone 'set +e
echo "== identity =="
hostname
uname -a
cat /proc/cmdline
apk info -vv | sort | grep -E "^(device-nothing-tetris|firmware-nothing-tetris|linux-postmarketos-mediatek-mt6878|modemmanager|iio-sensor-proxy|mesa|pipewire|pulseaudio|networkmanager|bluez)"

echo "== hard regression channels =="
systemctl --failed --no-pager
ip -br addr
test -d /sys/class/net/usb0 && echo usb0-present || echo usb0-missing
test -d /sys/class/net/wlan0 && echo wlan0-present || echo wlan0-missing
test -d /sys/class/bluetooth/hci0 && echo hci0-present || echo hci0-missing
test -e /dev/input/event0 && echo input-present || echo input-missing

echo "== display touch =="
for property in /sys/class/drm/card*-*/status \
	/sys/class/drm/card*-*/enabled \
	/sys/class/drm/card*-*/modes; do
	[ -r "$property" ] || continue
	printf "%s\n" "$property"
	cat "$property"
done
for blank in /sys/class/graphics/fb*/blank; do
	[ -r "$blank" ] || continue
	printf "%s=" "$blank"
	cat "$blank"
done
grep -A8 -B2 -E "fts_ts|gpio-keys|rt6010" /proc/bus/input/devices 2>/dev/null

echo "== gpu frontier =="
ls -l /dev/dri 2>/dev/null
find /sys/bus/platform/devices -maxdepth 1 \( -iname "*mali*" -o -iname "*panthor*" \) 2>/dev/null

echo "== modem sim frontier =="
mmcli -L 2>/dev/null
ls -l /dev/wwan* /dev/cdc-wdm* /dev/ccci* 2>/dev/null
lsmod | grep -Ei "ccci|dpmaif|ccmni|modem|mddp"

echo "== gnss frontier =="
systemctl status nothing-tetris-gnss-transport.service --no-pager 2>/dev/null
ls -l /dev/gps_emi /dev/gpsdl0 /dev/gpsdl1 2>/dev/null
fuser /dev/gpsdl0 /dev/gpsdl1 2>/dev/null
lsmod | grep -Ei "gps|gnss|conninfra"

echo "== sensors frontier =="
find /sys/bus/iio/devices -maxdepth 2 -type f -name name -print -exec cat {} \; 2>/dev/null
for name in /sys/bus/iio/devices/iio:device*/name; do
	[ -r "$name" ] || continue
	value=$(cat "$name")
	case "$value" in
		*mt6363*|*mt6375*|*pmic*|*auxadc*) ;;
		*) printf "user-sensor-iio-present=%s\n" "$value" ;;
	esac
done
lsmod | grep -Ei "scp|sensor|hf_manager|tinysys|rpmsg|mbox"

echo "== camera frontier =="
ls -l /dev/video* /dev/media* 2>/dev/null
find /sys/bus/i2c/devices -maxdepth 2 -type f -name name -print -exec cat {} \; 2>/dev/null | grep -Ei "imx|gc|sc202|pd9302|cam|ois|eeprom"
lsmod | grep -Ei "imgsensor|camera|seninf|cam|ccu|v4l2|lm3644"

echo "== audio route frontier =="
cat /proc/asound/cards 2>/dev/null
aplay -l 2>/dev/null
arecord -l 2>/dev/null
wpctl status 2>/dev/null
pactl list short sinks 2>/dev/null
pactl list short sources 2>/dev/null

echo "== kernel faults =="
dmesg -T | grep -Ei "BUG:|WARNING:|Oops:|Kernel panic|hung task|refcount|use-after-free|usb0|ncm|drm|dsi|gpu|panthor|mali|gps|gnss|ccci|dpmaif|sensor|scp|camera|imgsensor|v4l2|iio|modem|sim" | tail -n 700
' > "$outdir/frontier.txt" 2> "$outdir/frontier.err" ||
	fail "frontier command failed"

grep -q '^usb0-present$' "$outdir/frontier.txt" ||
	fail "usb0 missing on phone"
grep -q '^wlan0-present$' "$outdir/frontier.txt" ||
	fail "wlan0 missing on phone"
grep -q '^hci0-present$' "$outdir/frontier.txt" ||
	fail "hci0 missing on phone"
grep -q '^input-present$' "$outdir/frontier.txt" ||
	fail "input device missing on phone"
grep -Eq '/sys/class/drm/card[0-9]+-DSI-[0-9]+/status' "$outdir/frontier.txt" ||
	fail "DSI connector status is missing"
grep -A1 -E '/sys/class/drm/card[0-9]+-DSI-[0-9]+/status' "$outdir/frontier.txt" |
	grep -q '^connected$' ||
	fail "DSI connector is not connected"
grep -A1 -E '/sys/class/drm/card[0-9]+-DSI-[0-9]+/enabled' "$outdir/frontier.txt" |
	grep -q '^enabled$' ||
	fail "DSI connector is not enabled"
if grep -Eq 'BUG:|Oops:|Kernel panic|use-after-free' "$outdir/frontier.txt"; then
	fail "critical kernel fault found in hardware frontier log"
fi

case "$mode" in
	baseline)
		if grep -q 'renderD' "$outdir/frontier.txt"; then
			fail "GPU render node appeared in baseline mode; run a GPU-specific gate before promotion"
		fi
		if grep -Eq '/dev/(wwan|cdc-wdm|ccci)' "$outdir/frontier.txt"; then
			fail "modem nodes appeared in baseline mode; run a modem-specific gate before promotion"
		fi
		if grep -Eq '/dev/(video|media)' "$outdir/frontier.txt"; then
			fail "camera nodes appeared in baseline mode; run a camera-specific gate before promotion"
		fi
		if grep -q '^user-sensor-iio-present=' "$outdir/frontier.txt"; then
			fail "sensor IIO nodes appeared in baseline mode; run a sensor-specific gate before promotion"
		fi
		;;
	frontier)
		:
		;;
	*)
		fail "unknown mode: $mode"
		;;
esac

printf 'PASS: hardware frontier gate %s\nlogs: %s\n' "$mode" "$outdir"
