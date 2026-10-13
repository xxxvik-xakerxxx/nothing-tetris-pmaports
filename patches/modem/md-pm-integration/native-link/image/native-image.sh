# Source this only in the generated matched candidate APKBUILD.
_prepare_native_start() {
	python3 -B "$srcdir/native-image-prepare.py" \
		--source "$_devmods_dir" --destination "$srcdir/tetris-native-vendor" \
@PATCHES@
}

_build_native_start() {
	[ "$CI" = true ] && [ "$GITHUB_ACTIONS" = true ] && [ "$(uname -s)" = Linux ] ||
		die "native matched candidate build is Linux GitHub CI-only"
	python3 -B "$srcdir/native-image-dt-check.py" \
		--baseline "$builddir/arch/$_carch/boot/dts/mediatek/mt6878-nothing-tetris-native-md-first-off.dtb" \
		--candidate "$builddir/arch/$_carch/boot/dts/mediatek/mt6878-nothing-tetris-native-md-start-candidate.dtb" \
		--report "$srcdir/native-image-dt.json"
	local root="$srcdir/tetris-native-vendor" util modules="$srcdir/tetris-native-modules"
	local symbols flags jobs="${JOBS:-$(nproc)}" component
	util="$root/drivers/misc/mediatek/ccci_util"
	flags="$(_vendor_kcflags) -I$root/include -Werror=implicit-function-declaration"
	flags="$flags -Werror=incompatible-pointer-types -Werror=int-conversion"
	test -s "$builddir/Module.symvers" || die "Missing actual full kernel exports"
	make -j"$jobs" -C "$builddir" M="$util" ARCH="$_carch" LLVM=1 \
		KERNEL_SRC="$builddir" KERNEL_OUT="$builddir" DEVICE_MODULES_PATH="$root" \
		CONFIG_ARM64=y CONFIG_MTK_ECCCI_DRIVER=m CONFIG_MTK_SECURITY_SW_SUPPORT=n \
		CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n CONFIG_MTK_AEE_IPANIC=n \
		KBUILD_EXTRA_SYMBOLS= KBUILD_MODPOST_WARN= KBUILD_MODPOST_NOFINAL= KBUILD_MODPOST_SKIP= \
		KCFLAGS="$flags -I$root/drivers/misc/mediatek/include \
			-DCONFIG_MTK_ECCCI_TETRIS_METADATA_ONLY=1 -DCONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY=1 \
			-DCONFIG_TETRIS_CCCI_SMEM_MAP_ONLY=1 -DCONFIG_TETRIS_CCCI_SMEM_PROVIDER=1 \
			-DCONFIG_MTK_ECCCI_TETRIS_NATIVE_START=1" ccci_util_lib.ko
	# Preserve genuine f25/SCP package dependencies. Never invent their exports.
	symbols="$util/Module.symvers $_devmods_dir/drivers/soc/mediatek/Module.symvers"
	symbols="$symbols $_devmods_dir/drivers/rpmsg/Module.symvers"
	symbols="$symbols $_devmods_dir/drivers/misc/mediatek/scp/rv/Module.symvers"
	for component in $symbols; do
		test -s "$component" || die "Missing actual native package dependency: $component"
	done
	test ! -e "$modules" || die "Native module wrapper is not fresh"
	mkdir "$modules"
	cp "$srcdir/native-image.Kbuild" "$modules/Kbuild"
	for component in eccci ccmni rps; do
		cp -R "$root/drivers/misc/mediatek/$component" "$modules/$component"
	done
	make -j"$jobs" -C "$builddir" M="$modules" ARCH="$_carch" LLVM=1 \
		KERNEL_SRC="$builddir" KERNEL_OUT="$builddir" DEVICE_MODULES_PATH="$root" \
		CONFIG_ARM64=y CONFIG_MTK_ECCCI_DRIVER=m CONFIG_MTK_NET_CCMNI=m CONFIG_MTK_NET_RPS=m \
		CONFIG_DEVICE_MODULES_MEDIATEK_MT6577_AUXADC=m CONFIG_MTK_SECURITY_SW_SUPPORT=n \
		CONFIG_MTK_SEC_MODEM_NVRAM_ANTI_CLONE=n CONFIG_MTK_AEE_IPANIC=n \
		CONFIG_MTK_ECCCI_TETRIS_OWNER=y CONFIG_MTK_ECCCI_TETRIS_NATIVE_START=y \
		KBUILD_EXTRA_SYMBOLS="$symbols" KBUILD_MODPOST_WARN= KBUILD_MODPOST_NOFINAL= KBUILD_MODPOST_SKIP= \
		KCFLAGS="$flags -DCONFIG_MTK_ECCCI_TETRIS_OWNER=1 \
			-DCONFIG_MTK_ECCCI_TETRIS_NATIVE_START=1 -DCONFIG_TETRIS_CCCI_SMEM_CONSUMER=1" modules
	python3 -B "$srcdir/native-image-check.py" --kernel "$builddir" \
		--vendor "$root" --modules "$modules" --shipping-config "$srcdir/native-image-shipping.config" \
		--extra-table "$_devmods_dir/drivers/soc/mediatek/Module.symvers" \
		--extra-table "$_devmods_dir/drivers/rpmsg/Module.symvers" \
		--extra-table "$_devmods_dir/drivers/misc/mediatek/scp/rv/Module.symvers" \
		--report "$srcdir/native-image-module-link.json"
}

_package_native_start() {
	local root="$srcdir/tetris-native-vendor" module
	local destination="$pkgdir/lib/modules/$_release/extra/mediatek-native-modem"
	install -Dm644 "$root/drivers/misc/mediatek/ccci_util/ccci_util_lib.ko" "$destination/ccci_util_lib.ko"
	for module in eccci/ccci_md_all eccci/ccci_auxadc eccci/hif/ccci_ccif \
		eccci/hif/ccci_dpmaif eccci/hif/ccci_cldma eccci/fsm/ccci_fsm_scp ccmni/ccmni rps/rps_perf; do
		install -Dm644 "$srcdir/tetris-native-modules/$module.ko" "$destination/${module##*/}.ko"
	done
	install -Dm644 "$srcdir/native-image-module-link.json" \
		"$pkgdir/usr/share/nothing-tetris/native-start/module-link.json"
	install -Dm644 "$srcdir/native-image-dt.json" "$pkgdir/usr/share/nothing-tetris/native-start/compiled-dt.json"
	install -Dm644 "$srcdir/native-image-modprobe.conf" "$pkgdir/etc/modprobe.d/tetris-native-start.conf"
}
