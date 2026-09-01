#!/bin/sh
set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-audit"

mkdir -p "$outdir"

sshpass -p "$password" ssh \
	-o ConnectTimeout=10 \
	-o PreferredAuthentications=keyboard-interactive,password \
	-o KbdInteractiveAuthentication=yes \
	-o PubkeyAuthentication=no \
	-o NumberOfPasswordPrompts=1 \
	-o StrictHostKeyChecking=no \
	-o UserKnownHostsFile=/dev/null \
	"$user@$host" 'set +e
echo "== identity =="
hostname
uname -a
id
cat /etc/os-release
cat /proc/cmdline

echo "== packages =="
apk info -vv | sort | grep -E "^(device-nothing-tetris|firmware-nothing-tetris|linux-postmarketos-mediatek-mt6878|postmarketos-base|bluez|networkmanager|iio-sensor-proxy|alsa|pulseaudio|pipewire)"

echo "== failed units =="
systemctl --failed --no-pager

echo "== key services =="
systemctl status \
	nothing-tetris-connectivity.service \
	nothing-tetris-wifi-nvram.service \
	nothing-tetris-bluetooth-address.service \
	bluetooth.service \
	NetworkManager.service \
	sshd.service \
	--no-pager

echo "== usb/network =="
ip addr
iw dev 2>/dev/null
nmcli -t -f DEVICE,TYPE,STATE,CONNECTION dev 2>/dev/null

echo "== bluetooth =="
bluetoothctl show 2>/dev/null

echo "== audio =="
cat /proc/asound/cards 2>/dev/null
aplay -l 2>/dev/null
arecord -l 2>/dev/null
wpctl status 2>/dev/null
pactl list short sinks 2>/dev/null
pactl list short sources 2>/dev/null

echo "== iio/input/thermal =="
find /sys/bus/iio/devices -maxdepth 2 -type f \( -name name -o -name "in_*_raw" -o -name "in_*_input" \) -print -exec sh -c "printf %s= \"\$1\"; cat \"\$1\" 2>/dev/null" sh {} \; 2>/dev/null
find /sys/class/input -maxdepth 2 -type f -name name -print -exec cat {} \; 2>/dev/null
find /sys/class/thermal -maxdepth 2 -type f \( -name type -o -name temp -o -name mode \) -print -exec cat {} \; 2>/dev/null

echo "== display/gpu/camera/modem =="
ls -l /dev/dri /dev/video* /dev/media* /dev/wwan* /dev/cdc-wdm* /dev/ccci* 2>/dev/null
find /sys/class/drm -maxdepth 2 -type f \( -name status -o -name modes -o -name enabled \) -print -exec cat {} \; 2>/dev/null
mmcli -L 2>/dev/null

echo "== modules interesting =="
lsmod | grep -Ei "conn|wlan|bt|gps|gnss|snd|mt6369|mt6685|aw882|rt6010|lvts|thermal|panthor|mali|ccci|dpmaif|sensor|scp|imgsensor|cam|v4l2|lm3644"

echo "== dmesg interesting =="
dmesg -T | grep -Ei "error|fail|warn|wlan0|hci0|Bluetooth|conninfra|wmt|gps|gnss|sound|audio|mt6369|aw882|rt6010|thermal|lvts|panthor|mali|ccci|dpmaif|sensor|scp|camera|imgsensor|v4l2|lm3644|usb0|ncm|gadget" | tail -n 700
' > "$outdir/full.txt" 2> "$outdir/ssh.err"

printf '%s\n' "$outdir"
