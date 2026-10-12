# Private Mapped SMEM Profile

Research only: define `CONFIG_TETRIS_CCCI_SMEM_MAP_ONLY=1` together with
`CONFIG_TETRIS_CCCI_SMEM_RESOURCE_ONLY=1` in the isolated AP-only module.
Combining it with INITIAL_READ or omitting RESOURCE_ONLY is a compile error.
There is no shipping configuration, installation or autoload change.

The actual owned importer, planner and transactional mapper are reused. Before
mapping, the sole serialized init rechecks the retained bank snapshot, exact
planner spans, actual held resource handles, both boot records (slots42/43,
initial AID241 RW), range coverage, CONSYS exclusion and actual CurrentEL1.
Matching trustedboot evidence describes inherited initial EL1 policy, not a
fresh NS certificate, immutable policy, modem READY or runtime registration.
No separate permission callback or caller-supplied readiness flag is added.

Both exact spans use the existing `ioremap_wc()` transaction. They are retained
without reading, writing, clearing or retrying SMEM. The new
`tetris_smem_export_mapped_private()` uses the existing copy-layout operation to
copy into private consumer storage before publication. It rejects invalid state,
short/overlapping outputs and owner aliases without changing output. No slot or
legacy util SMEM globals are published. On failure, owner destruction unmaps in
reverse order before releasing claims; the first error reaches module init.
On success, the actual owner, mappings, copied tables and claims remain private
and the module is boot-pinned. This is not an unload/reload interface.

The default metadata, resource-only and single-word initial-read profiles still
exclude the runtime mapper and mapped export at compile time. AP-tag-buffer
copying remains the existing importer operation, separate from SMEM access.
There is no SMC/HVC, START, CCIF, transport or driver-registration integration.

CI runner coverage: 18 profiles/page combinations, 59 real producer/import
scenarios per combination, 40 actual-init postclaim state/evidence/geometry
faults, six malformed held-resource cases, wrong EL, map1/map2, fallible actual
export, reverse unmap/resource release, private-copy isolation and reentry.
Mapping/content boundaries are mocked and sanitized; native C runs only in CI.
Four invalid profile/page combinations must fail actual compilation. The
independent SMEM primitive fixture also exercises mapped-unpublished export.
Exact r181 linking produces `ccci-util-smem-map-only.ko` and the
`map_only_module` manifest alongside the three unchanged profile boundaries.

Native compilation, linkage and physical MAP_ONLY validation remain pending.
The preceding physical initial NC read completed once with zero and stable
USB/sensors/SSH; that is not a MAP_ONLY result or permission/READY certificate.
Parent integration must regenerate the shipping `ccci-owned-metadata.overlay`
from this frozen candidate and update its APK checksum before dispatching CI.
