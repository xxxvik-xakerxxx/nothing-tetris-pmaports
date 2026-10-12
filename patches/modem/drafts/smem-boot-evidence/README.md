# SMEM boot-evidence decoder draft

Pure decoder for `nothing,modem-smem-boot-evidence`: exactly 336 bytes,
little-endian v1, NS_BL33_BOOT_EVIDENCE scope, NC slot 42 then cache slot 43.
The caller supplies the already validated `tetris_metadata_banks` snapshot
from `../runtime-metadata/metadata_resources.h`; complete reservation base and
capacity must match. Dynamic range sizes must be nonzero, page aligned and
contained, and start at the reservation base as the producer requires.

Success copies a value snapshot with no retained pointers. Consumers must
use it as const evidence. All failures preserve the destination. All three
input/output spans must be disjoint and nonwrapping. Endpoint is start+size,
not last byte; only raw end bit 43 may vary and is preserved in the output.
Enable and every policy word are checked exactly. This is observed BL33 boot
evidence, not firmware authentication, a Linux NS permission grant, mapping,
modem START/READY, transport, or proof of a cold boot.

Source pin: U-Boot `cdd806438d73e2e163fcc9aded557b029816011e`,
`board/mediatek/mt6878/tetris_modem_layout.c` (`tetris_modem_plan_emi`),
`tetris_modem_emi.c` (`tetris_modem_plan_emi_policy`) and `tetris_modem_emi.h`.
Exact SHA256 pins live in `pinned_helpers.py`; extraction rejects any mismatch.
The preloader digest is
`5d2bedd00049fced983d3ae53989616c5c9f46c4eddd32a01a1ad46ff8d2c50f`.
Source checks derive the two policy tables from the pinned shared-AID lists.
CI links the actual decoder body with the actual extracted planner bodies,
not a replacement decoder. The working producer
`../u-boot-mt6878/board/mediatek/mt6878/tetris_modem_smem_evidence.{h,c}`
is inspected read-only and its wire offsets checked separately.
Source checks also reject drift in the current planner bodies relative to the pin.

From the pmaports repository, source-only:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 patches/modem/drafts/smem-boot-evidence/check.py --uboot ../u-boot-mt6878
```

Parent-scheduled CI only (not run locally):

```sh
python3 -B patches/modem/drafts/smem-boot-evidence/check.py --uboot out/uboot --native-ci
```

Fixtures cover relocated reservations and dynamic/full-capacity sizes,
every wire bit and policy group, marker presence/absence, absent/truncated
buffers, reservation/range faults, aliasing, pointer/physical overflow,
aperture endpoints and unchanged output. The native runner
requires both CI=true and GITHUB_ACTIONS=true. It additionally links the real
new U-Boot encoder to this decoder and checks round-trip bytes with relocated
allocations and both endpoint marker variants.
[CI 38218370472](https://github.com/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/runs/38218370472)
passed 12,229 decoder field/range rejections, bounds/aliases, the actual
producer/decoder round-trip under ASan/UBSan and actual ARM64 compilation.
The parent's r181
NC=1204224/cache=39190528 proof with NULL virtuals establishes a metadata
plan only; these totals are not decoder constants or permission evidence.

The isolated AP-only overlay now links this exact decoder and copies the
optional property during serialized plan initialization. Present records must
match the validated reservations and cover both imported plan ranges. An absent
record supports the previous loader; zero-length, malformed, short/long or
incompatible records fail visibly and clear the plan. The node reference is
released on every path, and no DT pointer survives init. Cleanup erases both
plan and evidence. This candidate is not installed/autoloaded and still contains
no SMEM mapping/publication bodies. Native integration and linked-module CI for
this additional consumer are pending; the earlier CI only compiled the decoder.

U-Boot `e2929baa549f54ce5518b2dd84952318ba857fda` passed
[CI 38217024964](https://github.com/xxxvik-xakerxxx/u-boot/actions/runs/38217024964)
and was flashed only to `lk_a`. Linux physically received the 336-byte record:
both reserved banks, endpoints, enables and profile matched the published DT.
This field inspection did not execute the C decoder on the handset. The older
AP-only module also passed import/plan on the new loader with USB/sensors active.
No Linux NS access permission, modem START/READY or SIM operation is inferred.
