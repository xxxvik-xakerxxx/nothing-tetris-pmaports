#!/bin/sh
# libarchive reads the archive format/compression; never extract onto disk.
set -eu
if [ "$#" -ne 2 ]; then
    echo 'usage: check-initramfs.sh INITRAMFS KERNEL_RELEASE' >&2
    exit 2
fi
archive=$1
release=$2
tar=${BSDTAR:-bsdtar}
test -s "$archive"
names=$("$tar" -tf "$archive")
module="usr/lib/modules/$release/kernel/drivers/usb/gadget/function/usb_f_ncm.ko"
if ! printf '%s\n' "$names" | grep -Fxq "$module"; then
    echo "NCM module missing from initramfs: $module" >&2
    exit 1
fi
deviceinfo=$("$tar" -xOf "$archive" usr/share/deviceinfo/device-nothing-tetris)
if ! printf '%s\n' "$deviceinfo" | grep -Fxq 'deviceinfo_usb_network_function="ncm.usb0"'; then
    echo 'NCM deviceinfo selection missing from initramfs' >&2
    exit 1
fi
echo 'PASS: compressed CPIO contains the NCM module and exact deviceinfo selection'
