#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only

set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-greeter-display-gate"
ssh_opts='-o ConnectTimeout=10 -o PreferredAuthentications=keyboard-interactive,password -o KbdInteractiveAuthentication=yes -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

mkdir -p "$outdir"

fail() {
	echo "FAIL: $*" >&2
	echo "logs: $outdir" >&2
	exit 1
}

if ! sshpass -p "$password" ssh $ssh_opts "$user@$host" sh -s -- "$password" \
	> "$outdir/greeter-display.txt" 2> "$outdir/ssh.err" <<'EOF'
password=$1

set +e
echo "== identity =="
uname -a
cat /proc/sys/kernel/random/boot_id
apk info -vv | sort | grep -E "^(device-nothing-tetris|linux-postmarketos-mediatek-mt6878|greetd|phoc|phosh)"

echo "== hard channels =="
test -d /sys/class/net/usb0 && echo usb0-present || echo usb0-missing
ip -brief addr show usb0 2>/dev/null
systemctl --failed --no-pager

echo "== greeter package files =="
test -x /usr/libexec/nothing-tetris-greeter-display-policy && echo policy-exec-present
test -f /usr/lib/systemd/user/nothing-tetris-greeter-display-policy.service && echo policy-unit-present
grep -F 'enable nothing-tetris-greeter-display-policy.service' \
	/usr/lib/systemd/user-preset/89-nothing-tetris-user.preset
grep -F 'ConditionUser=greetd' \
	/usr/lib/systemd/user/nothing-tetris-greeter-display-policy.service

echo "== greeter ownership =="
printf '%s\n' "$password" | sudo -S stat -c '%F %U %G %a %n' \
	/var/lib/greetd/.config \
	/var/lib/greetd/.config/dconf \
	/var/lib/greetd/.config/dconf/user 2>/dev/null
printf '%s\n' "$password" | sudo -S -u greetd sh -c \
	'test -w /var/lib/greetd/.config && test -w /var/lib/greetd/.config/dconf && test -w /var/lib/greetd/.config/dconf/user && echo greetd-config-write-ok'

echo "== greeter settings =="
printf '%s\n' "$password" | sudo -S -u greetd env \
	XDG_RUNTIME_DIR=/run/user/104 \
	DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/104/bus \
	gsettings get org.gnome.desktop.session idle-delay
printf '%s\n' "$password" | sudo -S -u greetd env \
	XDG_RUNTIME_DIR=/run/user/104 \
	DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/104/bus \
	gsettings get org.gnome.settings-daemon.plugins.power idle-dim
printf '%s\n' "$password" | sudo -S -u greetd env \
	XDG_RUNTIME_DIR=/run/user/104 \
	DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/104/bus \
	gsettings get org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type
printf '%s\n' "$password" | sudo -S -u greetd env \
	XDG_RUNTIME_DIR=/run/user/104 \
	DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/104/bus \
	gsettings get org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type

echo "== display state =="
cat /sys/class/drm/card0-DSI-1/status 2>/dev/null
cat /sys/class/drm/card0-DSI-1/enabled 2>/dev/null
cat /sys/class/graphics/fb0/blank 2>/dev/null
for backlight in /sys/class/backlight/*; do
	[ -e "$backlight" ] || continue
	printf '%s ' "$backlight"
	cat "$backlight/bl_power" "$backlight/brightness" "$backlight/actual_brightness" 2>/dev/null
done

echo "== greeter processes =="
ps -eo pid,user,rss,pcpu,comm,args | grep -Ei 'greetd|phoc|phosh|dconf-service|pulseaudio|pipewire|wireplumber' | grep -v grep

echo "== recent greeter log =="
journalctl -b --since '-2 min' --no-pager | \
	grep -Ei 'greetd|phoc|phosh|dconf|Permission denied|pulse|pipewire|card0-DSI-1|blank|backlight|BUG:|WARNING:|Oops:|Kernel panic' | tail -n 250
EOF
then
	fail "greeter display gate SSH command failed"
fi

gate="$outdir/greeter-display.txt"

grep -q '^usb0-present$' "$gate" ||
	fail "USB disappeared during greeter display gate"
grep -q '^policy-exec-present$' "$gate" ||
	fail "greeter display policy executable is missing"
grep -q '^policy-unit-present$' "$gate" ||
	fail "greeter display policy unit is missing"
grep -q '^greetd-config-write-ok$' "$gate" ||
	fail "greetd cannot write its private config tree"
grep -q '^uint32 0$' "$gate" ||
	fail "greeter idle-delay is not disabled"
grep -q '^false$' "$gate" ||
	fail "greeter idle-dim is not disabled"
[ "$(grep -c "^'nothing'$" "$gate")" -ge 2 ] ||
	fail "greeter inactive sleep types are not both disabled"
grep -q '^connected$' "$gate" ||
	fail "DSI connector is not connected"
grep -q '^enabled$' "$gate" ||
	fail "DSI connector is not enabled"
grep -q '^0$' "$gate" ||
	fail "framebuffer blank state is not unblanked"
if awk '/== greeter processes ==/ { in_processes = 1; next } /== recent greeter log ==/ { in_processes = 0 } in_processes && $2 == "greetd" && $5 ~ /pulseaudio/ { found = 1 } END { exit found ? 0 : 1 }' "$gate"; then
	fail "greetd owns a PulseAudio process"
fi
if awk '/== recent greeter log ==/ { in_log = 1; next } in_log && /Permission denied|BUG:|Oops:|Kernel panic/ { found = 1 } END { exit found ? 0 : 1 }' "$gate"; then
	fail "fresh greeter log contains permission or kernel fatal errors"
fi

printf 'PASS: greeter display gate\nlogs: %s\n' "$outdir"
