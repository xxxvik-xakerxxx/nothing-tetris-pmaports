#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}
mode=${4:-readonly}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-gnss-gate"
control_path="/tmp/nothing-tetris-gnss-$stamp-$$"
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

[ "$mode" = readonly ] ||
	fail "unsupported GNSS gate mode: $mode"

ssh_phone true > "$outdir/ssh-probe.txt" 2> "$outdir/ssh.err" ||
	fail "SSH is not reachable on $host"

ssh_phone 'set +e
echo "== baseline =="
hostname
uname -a
cat /proc/sys/kernel/random/boot_id
apk info -vv | sort | grep -E "^(device-nothing-tetris|firmware-nothing-tetris|linux-postmarketos-mediatek-mt6878)"
ip -brief addr show usb0 2>/dev/null
systemctl --failed --no-pager
systemctl is-active nothing-tetris-connectivity.service 2>/dev/null
systemctl is-active nothing-tetris-gnss-transport.service 2>/dev/null
lsmod | grep -Ei "conninfra|gps|gnss|ccci|dpmaif|ccmni|modem|mddp"
ls -l /dev/gps_emi /dev/gpsdl0 /dev/gpsdl1 /dev/wwan* /dev/cdc-wdm* /dev/ccci* 2>/dev/null
fuser /dev/gpsdl0 /dev/gpsdl1 2>/dev/null
' > "$outdir/baseline.txt" 2> "$outdir/baseline.err" ||
	fail "baseline command failed"

grep -q '^usb0[[:space:]]\+UP' "$outdir/baseline.txt" ||
	fail "usb0 is not up before GNSS gate"
if grep -Eq '/dev/(wwan|cdc-wdm|ccci)|(^|[[:space:]])(ccci|dpmaif|ccmni|mddp)' \
		"$outdir/baseline.txt"; then
	fail "modem runtime appeared before GNSS gate"
fi

ssh_phone "printf '%s\n' '$password' | sudo -S systemctl start nothing-tetris-gnss-transport.service" \
	> "$outdir/transport-start.txt" 2> "$outdir/transport-start.err" ||
	fail "GNSS transport service failed to start"

ssh_phone 'set +e
echo "== transport =="
systemctl status nothing-tetris-gnss-transport.service --no-pager
test -d /sys/module/gps_drv_dl_v051 && echo gps-module-present || echo gps-module-missing
test -c /dev/gpsdl0 && echo gpsdl0-present || echo gpsdl0-missing
test -c /dev/gpsdl1 && echo gpsdl1-present || echo gpsdl1-missing
test -c /dev/gps_emi && echo gps-emi-present || echo gps-emi-missing
fuser /dev/gpsdl0 /dev/gpsdl1 2>/dev/null
' > "$outdir/transport.txt" 2> "$outdir/transport.err" ||
	fail "GNSS transport state command failed"

grep -q '^gps-module-present$' "$outdir/transport.txt" ||
	fail "GNSS module is not loaded after transport start"
grep -q '^gpsdl0-present$' "$outdir/transport.txt" ||
	fail "/dev/gpsdl0 missing after transport start"
grep -q '^gpsdl1-present$' "$outdir/transport.txt" ||
	fail "/dev/gpsdl1 missing after transport start"

ssh_phone "printf '%s\n' '$password' | sudo -S /usr/libexec/nothing-tetris-gnss-readonly --probe-link0" \
	> "$outdir/readonly.txt" 2> "$outdir/readonly.err" ||
	fail "GNSS read-only diagnostic failed"

grep -q '^status=0$' "$outdir/readonly.txt" ||
	fail "GNSS read-only status is not zero"
grep -Eq '^fragment_count=([1-9][0-9]?|1[0-9][0-9]|2[0-4][0-9]|25[0-6])$' \
	"$outdir/readonly.txt" ||
	fail "GNSS read-only fragment count is outside validated bounds"
grep -q '^cipher_key=redacted$' "$outdir/readonly.txt" ||
	fail "GNSS diagnostic leaked the cipher key"

ssh_phone 'set +e
echo "== post =="
ip -brief addr show usb0 2>/dev/null
systemctl --failed --no-pager
find /proc/[0-9]*/fd -lname "/dev/gpsdl*" -print 2>/dev/null
ls -l /dev/wwan* /dev/cdc-wdm* /dev/ccci* 2>/dev/null
lsmod | grep -Ei "gps|gnss|ccci|dpmaif|ccmni|modem|mddp"
dmesg -T | grep -Ei "gps|gnss|conninfra|ccci|dpmaif|BUG:|WARNING:|Oops:|Kernel panic|hung task|use-after-free|usb0|ncm" | tail -n 500
' > "$outdir/post.txt" 2> "$outdir/post.err" ||
	fail "post-GNSS state command failed"

grep -q '^usb0[[:space:]]\+UP' "$outdir/post.txt" ||
	fail "usb0 is not up after GNSS gate"
if grep -Eq '^/proc/[0-9]+/fd/' "$outdir/post.txt"; then
	fail "GNSS left a gpsdl file descriptor owner"
fi
if grep -Eq '/dev/(wwan|cdc-wdm|ccci)|(^|[[:space:]])(ccci|dpmaif|ccmni|mddp)' \
		"$outdir/post.txt"; then
	fail "modem runtime appeared during GNSS gate"
fi
if grep -Eq 'BUG:|Oops:|Kernel panic|hung task|use-after-free' "$outdir/post.txt"; then
	fail "critical kernel fault found after GNSS gate"
fi

dd if=/dev/zero bs=1048576 count=32 2> "$outdir/dd-host.err" |
	sshpass -p "$password" ssh $ssh_opts "$user@$host" \
		'cat > /tmp/nothing-tetris-gnss-ncm-transfer.bin && sync && wc -c /tmp/nothing-tetris-gnss-ncm-transfer.bin && rm -f /tmp/nothing-tetris-gnss-ncm-transfer.bin' \
		> "$outdir/transfer.txt" 2> "$outdir/transfer.err" ||
	fail "post-GNSS 32 MiB SSH transfer failed"
grep -q '^33554432 ' "$outdir/transfer.txt" ||
	fail "post-GNSS 32 MiB SSH transfer byte count mismatch"

printf 'PASS: GNSS gate %s\nlogs: %s\n' "$mode" "$outdir"
