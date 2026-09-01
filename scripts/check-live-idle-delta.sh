#!/bin/sh
set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}
duration=${4:-600}

case "$duration" in
	''|*[!0-9]*) echo "duration must be an integer number of seconds" >&2; exit 2 ;;
esac
[ "$duration" -ge 10 ] || {
	echo "duration must be at least 10 seconds" >&2
	exit 2
}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-idle-delta"
control_path="/tmp/nothing-tetris-idle-$stamp-$$"
ssh_opts="-o ConnectTimeout=10 -o PreferredAuthentications=keyboard-interactive,password -o KbdInteractiveAuthentication=yes -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ControlMaster=auto -o ControlPersist=$((duration + 60)) -o ControlPath=$control_path"

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

snapshot() {
	label=$1
	ssh_phone sh -s -- "$label" "$password" <<'EOF'
label=$1
password=$2

echo "== snapshot $label =="
date -u +%Y-%m-%dT%H:%M:%SZ
uname -a
cat /proc/sys/kernel/random/boot_id
uptime
ip -br addr show usb0

echo "== battery =="
for property in status voltage_now current_now charge_counter capacity temp; do
	path=/sys/class/power_supply/mt6375-gauge/$property
	if [ -r "$path" ]; then
		printf '%s=' "$property"
		cat "$path"
	fi
done

echo "== system sleep =="
for path in /sys/power/state /sys/power/mem_sleep /sys/power/wakeup_count \
	/sys/kernel/debug/suspend_stats/*; do
	if [ -r "$path" ]; then
		printf '%s=' "$path"
		cat "$path"
	fi
done

echo "== cpuidle =="
for state in /sys/devices/system/cpu/cpu[0-9]*/cpuidle/state*; do
	[ -d "$state" ] || continue
	printf '%s ' "$state"
	for property in name usage time; do
		if [ -r "$state/$property" ]; then
			printf '%s=' "$property"
			tr '\n' ' ' < "$state/$property"
		fi
	done
	echo
done

echo "== interrupts =="
cat /proc/interrupts

echo "== wakeup sources =="
if [ -r /sys/kernel/debug/wakeup_sources ]; then
	cat /sys/kernel/debug/wakeup_sources
else
	printf '%s\n' "$password" | sudo -S cat /sys/kernel/debug/wakeup_sources
fi

echo "== selected runtime pm =="
for link in /sys/class/net/wlan0/device /sys/class/net/usb0/device \
	/sys/class/drm/card0/device /sys/class/sound/card0/device; do
	device=$(readlink -f "$link" 2>/dev/null || true)
	[ -n "$device" ] || continue
	echo "### $link -> $device"
	while [ "$device" != /sys/devices ] && [ "$device" != / ]; do
		for property in runtime_status runtime_active_time runtime_suspended_time control; do
			path=$device/power/$property
			if [ -r "$path" ]; then
				printf '%s=' "$path"
				cat "$path"
			fi
		done
		device=${device%/*}
	done
done

echo "== clock summary =="
echo "skipped: clk_summary blocks on the current MT6878 clock provider"
EOF
}

ssh_phone true > "$outdir/ssh-probe.txt" 2> "$outdir/ssh.err" ||
	fail "SSH is not reachable on $host"

snapshot start > "$outdir/start.txt" 2> "$outdir/start.err" ||
	fail "start snapshot failed"
grep -q '^usb0[[:space:]].*UP' "$outdir/start.txt" ||
	fail "usb0 is not up at the start of the idle interval"

sleep "$duration"

snapshot end > "$outdir/end.txt" 2> "$outdir/end.err" ||
	fail "end snapshot failed"
grep -q '^usb0[[:space:]].*UP' "$outdir/end.txt" ||
	fail "usb0 is not up at the end of the idle interval"

start_boot=$(sed -n '/^== snapshot start ==$/{n;n;n;p;q;}' "$outdir/start.txt")
end_boot=$(sed -n '/^== snapshot end ==$/{n;n;n;p;q;}' "$outdir/end.txt")
[ -n "$start_boot" ] && [ "$start_boot" = "$end_boot" ] ||
	fail "boot ID changed during the idle interval"

printf 'PASS: %s-second idle delta capture\nlogs: %s\n' "$duration" "$outdir"
