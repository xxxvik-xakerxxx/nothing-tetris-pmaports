#!/bin/sh
# Compile only the actual backend against an already patched/configured CI kernel.
set -eu
if [ "${CI:-}" != true ]; then
    echo "Kernel object compilation is CI-only" >&2
    exit 2
fi
if [ "$#" -ne 2 ]; then
    echo "usage: $0 PATCHED_KERNEL CONFIGURED_ARM64_OUTPUT" >&2
    exit 2
fi
kernel=$(cd "$1" && pwd)
output=$(cd "$2" && pwd)
test -f "$kernel/drivers/soc/mediatek/mt6878-ccci-start.c"
for setting in CONFIG_ARM64=y CONFIG_ARCH_MEDIATEK=y CONFIG_HAVE_ARM_SMCCC=y \
    CONFIG_PM=y CONFIG_REGULATOR=y CONFIG_MTK_SCPSYS_PM_DOMAINS=y \
    CONFIG_OF=y CONFIG_MFD_SYSCON=y CONFIG_MTK_MT6878_CCCI_FIRST_START=m; do
    if ! grep -qx "$setting" "$output/.config"; then
        echo "Compile-only CI configuration missing: $setting" >&2
        exit 1
    fi
done
# Do not change config, package the object, load it, or build a boot artifact.
exec make -C "$kernel" O="$output" ARCH=arm64 W=1 KCFLAGS=-Werror \
    drivers/soc/mediatek/mt6878-ccci-start.o
