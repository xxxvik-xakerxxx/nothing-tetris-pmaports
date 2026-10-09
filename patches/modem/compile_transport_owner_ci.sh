#!/bin/sh
# Disposable CI sources/output only; no module link, packaging or runtime use.
set -eu
if [ "${CI:-}" != true ]; then
    echo "Transport owner compilation is CI-only" >&2
    exit 2
fi
if [ "$#" -ne 3 ]; then
    echo "usage: $0 PATCHED_KERNEL CONFIGURED_ARM64_OUTPUT PATCHED_VENDOR" >&2
    exit 2
fi
kernel=$(cd "$1" && pwd)
output=$(cd "$2" && pwd)
vendor=$(cd "$3" && pwd)
moddir="$vendor/drivers/misc/mediatek/eccci"
test -f "$kernel/include/linux/soc/mediatek/mt6878_ccci_start.h"
test -f "$moddir/fsm/ccci_tetris_owner.c"
test -s "$output/Module.symvers"
for setting in CONFIG_ARM64=y CONFIG_PM=y CONFIG_REGULATOR=y \
    CONFIG_MTK_MT6878_CCCI_FIRST_START=m; do
    if ! grep -qx "$setting" "$output/.config"; then
        echo "Missing compile-only configuration: $setting" >&2
        exit 1
    fi
done
if find "$moddir" -name '*.ko' -print -quit | grep -q .; then
    echo "Use a separate disposable vendor tree without loadable modules" >&2
    exit 1
fi
# Reuse shipping vendor compatibility flags supplied by main; do not weaken them.
# External Kbuild selection does not update generated autoconf, hence the explicit
# C define for the opt-in candidate. Do not put this define in shipping builds.
flags="${TETRIS_VENDOR_KCFLAGS:-} -DCONFIG_MTK_ECCCI_TETRIS_OWNER=1"
flags="$flags -Werror=implicit-function-declaration -Werror=incompatible-pointer-types -Werror=int-conversion"
make -C "$kernel" O="$output" M="$moddir" ARCH=arm64 LLVM=1 \
    KERNEL_SRC="$kernel" KERNEL_OUT="$output" DEVICE_MODULES_PATH="$vendor" \
    CONFIG_ARM64=y CONFIG_MTK_ECCCI_DRIVER=m CONFIG_PAGE_POOL=n \
    CONFIG_MTK_ECCCI_TETRIS_OWNER=y CONFIG_MTK_MT6878_CCCI_FIRST_START=m \
    CONFIG_MTK_SECURITY_SW_SUPPORT=n CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n \
    CONFIG_MTK_AEE_IPANIC=n KCFLAGS="$flags" \
    fsm/ccci_tetris_owner.o hif/ccci_tetris_hif_owned.o \
    fsm/ccci_fsm.o fsm/modem_sys1.o hif/ccci_hif.o \
    hif/ccci_hif_ccif.o hif/ccci_dpmaif_com.o
for object in fsm/ccci_tetris_owner hif/ccci_tetris_hif_owned \
    fsm/ccci_fsm fsm/modem_sys1 hif/ccci_hif hif/ccci_hif_ccif hif/ccci_dpmaif_com; do
    test -s "$moddir/$object.o"
done
if find "$moddir" -name '*.ko' -print -quit | grep -q .; then
    echo "Compile-only target unexpectedly contains loadable modules" >&2
    exit 1
fi
echo "Actual owner/FSM/WDT/CCIF/DPMAIF translation units compiled; no runtime activation"
