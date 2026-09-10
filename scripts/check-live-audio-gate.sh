#!/bin/sh
set -eu

host=${1:-172.16.42.1}
user=${2:-user}
password=${3:-147147}
mode=${4:-audit}

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
outdir="$repo_root/local/live-logs/$stamp-$host-audio-gate"
ssh_opts='-o ConnectTimeout=10 -o PreferredAuthentications=keyboard-interactive,password -o KbdInteractiveAuthentication=yes -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

mkdir -p "$outdir"

fail() {
	echo "FAIL: $*" >&2
	echo "logs: $outdir" >&2
	exit 1
}

if ! sshpass -p "$password" ssh $ssh_opts "$user@$host" sh -s -- "$mode" "$password" \
	> "$outdir/audio.txt" 2> "$outdir/ssh.err" <<'EOF'
mode=$1
password=$2

set +e
echo "== identity =="
uname -a
apk info -vv | sort | grep -E "^(device-nothing-tetris|linux-postmarketos-mediatek-mt6878|alsa|pulseaudio|pipewire|wireplumber)"

echo "== hard channels =="
test -d /sys/class/net/usb0 && echo usb0-present || echo usb0-missing
ip -brief addr show usb0 2>/dev/null
systemctl --failed --no-pager

echo "== audio devices =="
cat /proc/asound/cards 2>/dev/null
aplay -l 2>/dev/null
arecord -l 2>/dev/null
pactl list short sinks 2>/dev/null
pactl list short sources 2>/dev/null
wpctl status 2>/dev/null

echo "== audio owners =="
ps -eo pid,user,comm,args | grep -Ei 'pulseaudio|pipewire|wireplumber' | grep -v grep

echo "== greetd dconf =="
printf '%s\n' "$password" | sudo -S stat -c '%F %U %G %a %n' \
	/var/lib/greetd/.config /var/lib/greetd/.config/dconf 2>/dev/null
ps -o pid,user,rss,pcpu,comm,args -C dconf-service 2>/dev/null

if [ "$mode" = lifecycle ]; then
	echo "== playback smoke =="
	timeout 8 speaker-test -D hw:0,6 -c 2 -r 48000 -t sine -f 440 -l 1
	echo "== capture smoke =="
	timeout 8 arecord -D hw:0,13 -f S16_LE -r 48000 -c 2 -d 2 /tmp/nothing-tetris-audio-capture.wav
	wc -c /tmp/nothing-tetris-audio-capture.wav
	rm -f /tmp/nothing-tetris-audio-capture.wav
fi

echo "== audio dmesg =="
dmesg -T | grep -Ei 'audio|snd|mt6369|mt6685|aw882|pulse|pipewire|BUG:|WARNING:|Oops:|Kernel panic' | tail -n 400
EOF
then
	fail "audio gate SSH command failed"
fi

grep -q '^usb0-present$' "$outdir/audio.txt" ||
	fail "USB disappeared during audio gate"
grep -q 'mt6878-mt6369' "$outdir/audio.txt" ||
	fail "MT6878 sound card is missing"
grep -q '^directory greetd greetd 700 /var/lib/greetd/.config/dconf$' "$outdir/audio.txt" ||
	fail "greetd dconf directory is missing"
if awk '/== audio owners ==/ { in_owners = 1; next } /== greetd dconf ==/ { in_owners = 0 } in_owners && $2 == "greetd" && $4 ~ /pulseaudio/ { found = 1 } END { exit found ? 0 : 1 }' "$outdir/audio.txt"; then
	fail "greetd owns a PulseAudio process"
fi
if grep -Eiq 'BUG:|Oops:|Kernel panic' "$outdir/audio.txt"; then
	fail "kernel fatal pattern present in audio log"
fi
if [ "$mode" = lifecycle ]; then
	grep -q '^== playback smoke ==$' "$outdir/audio.txt" ||
		fail "playback smoke did not run"
	awk '/== capture smoke ==/ { capture = 1; next } capture && /nothing-tetris-audio-capture.wav/ { if ($1 > 4096) ok = 1 } END { exit ok ? 0 : 1 }' "$outdir/audio.txt" ||
		fail "capture smoke did not produce audio data"
fi

printf 'PASS: audio gate %s\nlogs: %s\n' "$mode" "$outdir"
