#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
config="$repo_root/pmaports/device/testing/linux-postmarketos-mediatek-mt6878/config-postmarketos-mediatek-mt6878.aarch64"
overlay="${1:-$repo_root/local/config-overlays/mt6878-tetris-first-pass.config}"
tmp="$config.tmp"

if [ ! -f "$config" ]; then
	echo "Kernel config not found: $config" >&2
	exit 1
fi

if [ ! -f "$overlay" ]; then
	echo "Overlay not found: $overlay" >&2
	exit 1
fi

cp "$config" "$tmp"

while IFS= read -r line; do
	case "$line" in
		''|'#'*) continue ;;
	esac

	symbol=${line%%=*}
	value=${line#*=}

	case "$value" in
		y|m)
			if grep -q "^$symbol=" "$tmp"; then
				sed -i.bak "s/^$symbol=.*/$symbol=$value/" "$tmp"
			elif grep -q "^# $symbol is not set" "$tmp"; then
				sed -i.bak "s/^# $symbol is not set/$symbol=$value/" "$tmp"
			else
				printf "%s=%s\n" "$symbol" "$value" >> "$tmp"
			fi
			rm -f "$tmp.bak"
			;;
		n)
			if grep -q "^$symbol=" "$tmp"; then
				sed -i.bak "s/^$symbol=.*/# $symbol is not set/" "$tmp"
			elif ! grep -q "^# $symbol is not set" "$tmp"; then
				printf "# %s is not set\n" "$symbol" >> "$tmp"
			fi
			rm -f "$tmp.bak"
			;;
		*)
			echo "Unsupported config value in overlay: $line" >&2
			rm -f "$tmp"
			exit 1
			;;
	esac
done < "$overlay"

mv "$tmp" "$config"
echo "Applied $overlay to $config"
