# Legacy VMM firmware voter admission sidecar: Untested

The bounded kernel change is an `-EBUSY` admission veto for available
`mediatek,vmm_notifier` and `mediatek,mtk-mmdvfs-v3` nodes. Their B4.1 camera
firmware votes do not need a regulator handle or a `*-supply` property. The
existing rail-property census and exclusive regulator acquisition cannot
exclude these routes. Removing their rail properties must not admit them.

`supplier-admission.patch` inserts `mt6878-vmm-admission.c.inc` into the actual
kernel provider's `scpsys_vmm_prepare()` path. It checks every available node
before the supply-property scan and before allocating the owner, acquiring the
regulator, constructing leaves or publishing the OF provider. Failure releases
the current iterator node and both retained rail references through the existing
error exit. It does not wait for either legacy driver to bind: probe order cannot
establish ownership. All matching notifier nodes are excluded, regardless of
`pd-id`, because the same driver exports `vmm_isp_ctrl_notify()` and can issue
camera votes independently of the per-domain callback.

Apply this optional sidecar **after either** the frozen canonical
`native-provider.patch` or the exact MD composition
`native-provider-after-md.patch`. Their generated kernel include preimages are
identical and checked by digest. The static validator applies the real MD and
camera patches first, then the admission overlay, and compares every resulting
file. The overlay changes only `drivers/pmdomain/mediatek/mt6878-native-vmm.inc`.
The canonical r184 camera artifacts at `cbb777d`, MD artifacts, default-off
Kconfig, board DT, APKBUILD and shared CI helpers remain unchanged. Native
compilation/link and native runtime tests are CI-only and were not run here.

Exact NOS4.1 source: device modules commit
`ee2be53cb75670b548948636a0db1d1ff112bf12`, release
`Tetris-B4.1-260415-1709`:

- `drivers/misc/mediatek/vmm/mtk-vmm-notifier.c:79-90`:
  first genpd/camera users call `mtk_mmdvfs_genpd_notify(VMM_USR_CAM, true)`
  and `mtk_mmdvfs_camera_notify(true)`.
- Same file `:236-237`, `:264-279`, `:339-343`: PRE_ON calls the open path,
  the exported `vmm_isp_ctrl_notify()` also reaches it, and the driver matches
  `mediatek,vmm_notifier`.
- `drivers/soc/mediatek/mtk-mmdvfs-v3.c:240-269`, `:473-510`, `:1877-1881`:
  the camera/genpd routes reach `mmdvfs_vcp_ipi_send()`, update firmware shared
  memory, and the provider matches `mediatek,mtk-mmdvfs-v3`.
- `arch/arm64/boot/dts/mediatek/mt6878.dts:3841-3842` describes that provider.

The vendor wrappers can return zero after discarding an IPI error or when
uninitialized. They authorize neither a successful firmware ownership release
nor a native handoff. The concrete missing activation input remains a matching
firmware/MMUP contract that relinquishes VMM voting with an observable checked
acknowledgment, plus a validated rail voltage/camera rate policy. Absence or
disabled status of these DT nodes proves neither. This veto supplies no READY
flag, firmware command, reset, voltage setting or enable operation.

Static validation, from repository root:

```sh
python3 -B patches/camera-camisp/native-integration/supplier_admission.py
python3 -B patches/camera-camisp/native-integration/test_supplier_admission.py
```

After a reviewed sidecar source change, use `supplier_admission.py --write` to
refresh only its own patch and evidence. Explicit kernel archive/vendor/modules
path options are supported. No prepared-tree mutation, CI dispatch, phone
access, native local compiler, commit or push is part of this tool.
