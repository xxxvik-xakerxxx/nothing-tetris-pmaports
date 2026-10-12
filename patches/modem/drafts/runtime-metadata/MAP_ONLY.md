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

[CI38245658821](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38245658821)
passed the native fixtures, actual ARM64 objects and strict original-r181 link.
The ARM64 gate checks `ioremap_prot`, the pinned architecture's actual expansion
of `ioremap_wc`, rather than expecting the mock's literal function name.
Module SHA256: `cdb2841bfd0bfb0baf0933ae6e0c189ad8d75abcd393f77f9334b43392711eb2`.
On fresh r181 boot `7d4b87cb-bd4e-412e-a7ea-b54eb9729c34`, with U-Boot8d2ccc12,
one insmod at uptime229.86s returned0 and logged retained private mappings.
Both exact iomem claims and module reference1 remained held. USB/sensors/SSH
stayed active; there was no reboot, failed unit or new abort/Oops.
The same boot later registered gpsdl0/1 through the explicit GNSS transport
service without opening either link. No memory access, runtime transport,
modem READY or SIM/call result is inferred. Three-start/lifecycle validation
and the actual CCCI consumer integration remain.
