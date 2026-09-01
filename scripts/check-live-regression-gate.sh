#!/bin/sh
set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}
mode=${4:-audit}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-regression-gate"
control_path="/tmp/nothing-tetris-regression-$stamp-$$"
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
apk info -vv | sort | grep -E "^(device-nothing-tetris|firmware-nothing-tetris|linux-postmarketos-mediatek-mt6878)"

echo "== hard channels =="
ip -br addr
systemctl is-active sshd NetworkManager bluetooth nothing-tetris-connectivity.service 2>/dev/null

echo "== devices =="
test -d /sys/class/net/usb0 && echo usb0-present || echo usb0-missing
test -d /sys/class/net/wlan0 && echo wlan0-present || echo wlan0-missing
test -d /sys/class/bluetooth/hci0 && echo hci0-present || echo hci0-missing
test -e /dev/input/event0 && echo input-present || echo input-missing
grep -R . /sys/class/leds/*vibrator* /sys/class/leds/*haptic* 2>/dev/null | head -n 20
cat /proc/asound/cards 2>/dev/null
aplay -l 2>/dev/null
arecord -l 2>/dev/null

echo "== failures =="
systemctl --failed --no-pager
dmesg -T | grep -Ei "BUG|WARNING|Oops|panic|usb0|ncm|gadget|wlan0|hci0|conninfra|Bluetooth|audio|snd|rt6010|touch|i2c|regulator" | tail -n 500
' > "$outdir/baseline.txt" 2> "$outdir/baseline.err" ||
	fail "baseline command failed"

grep -q 'usb0-present' "$outdir/baseline.txt" ||
	fail "usb0 missing on phone; USB debug is not gated"
grep -q 'wlan0-present' "$outdir/baseline.txt" ||
	fail "wlan0 missing on phone"
grep -q 'hci0-present' "$outdir/baseline.txt" ||
	fail "hci0 missing on phone"
grep -q 'linux-postmarketos-mediatek-mt6878' "$outdir/baseline.txt" ||
	fail "kernel package version not visible"

if [ "$mode" = transfer ]; then
	dd if=/dev/zero bs=1048576 count=32 2> "$outdir/dd-host.err" |
		sshpass -p "$password" ssh $ssh_opts "$user@$host" \
			'cat > /tmp/nothing-tetris-ncm-transfer.bin && sync && wc -c /tmp/nothing-tetris-ncm-transfer.bin && rm -f /tmp/nothing-tetris-ncm-transfer.bin' \
			> "$outdir/transfer.txt" 2> "$outdir/transfer.err" ||
		fail "32 MiB SSH transfer failed"
	grep -q '^33554432 ' "$outdir/transfer.txt" ||
		fail "32 MiB SSH transfer byte count mismatch"
fi

printf 'PASS: regression gate %s\nlogs: %s\n' "$mode" "$outdir"
