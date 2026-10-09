# GPUEB Owner Integration Gate

Status: firmware ingress implemented; authenticated transform, SRAM loading,
physical boot and physical OFF remain unimplemented. No GPUEB/Panthor activation.
`0120` is not a remoteproc owner and must stay inactive until these gates close.

## Verified Inputs

- Device-module source: `ee2be53cb75670b548948636a0db1d1ff112bf12`.
- Vendor-module source: `e96f60dc081ae3525ef43d4bcf0ee5ee97e53835`.
- Private slot A: 2 MiB, SHA256
  `c03136145082bd5e5db13377842d31065d5cf15f8ae0a77c5753f8f5929572d7`.
- Private slot B: 2 MiB, SHA256
  `99c126b901b6b3df06ac39fde283ebd0eff74059d48f500194699fda18b69442`.
- Both slots contain six 512-byte MTK headers, aligned to 16 bytes: RV33,
  cert1, cert2, RV33_xfile, cert1, cert2. The RV33 ciphertext is 156064 bytes;
  the auxiliary payload is 364483 bytes. No extracted bytes are stored here.
- Both certificate pairs verify RSA-2048/PSS-SHA256 with salt 32. Delegated
  leaf keys match signed root metadata. The supplied root SPKI fingerprint
  matches the independently pinned LK root in U-Boot's `tetris_scp_prepare.c`.
- RV33 ciphertext and both component headers match signed metadata digests.
  Wrapped material and a post-transform digest exist for RV33. Its signed
  integer `2.9` is `0x10000`, NOT a proven ATF argument/selector.
- Xfile's certificate/header verify, but its whole-payload digest does not
  match metadata `2.1`. Digest coverage/compression is unresolved. It cannot
  be authenticated as a complete image or treated as ELF yet.

Cryptographic host verification is not an efuse-root/secure-world decision.
The scoped Python CLI requires an independently supplied SPKI pin; it always
reports `boot_permitted: false` and never prints wrapped material.

## SRAM Ownership

Pinned `arch/arm64/boot/dts/mediatek/mt6878.dts` describes these adjacent slices:

| Region | Source Address | Size | Intended Single Owner |
| --- | --- | --- | --- |
| Core SRAM before GPR | 0x13c00000 | 0x3fd1c | Remoteproc loader, after upload layout audit |
| GPR | 0x13c3fd1c | 0x64 | Existing session claim, including GPR13 at +0x34 |
| Mailbox SRAM | 0x13c3fd80 | 0x280 | Mailbox controller |

These addresses are source-validation facts, not a live programming plan.
The complete `gpueb_base` region spans all three: a full 0x40000-byte owner
claim would make the existing GPR and mailbox claims fail with EBUSY. Either
claim only audited disjoint loader slices or introduce one parent controller
with explicit shared APIs. Do not remove resource claims or map the same
physical range independently to hide the conflict. Resource addresses must
come from DT, and overlap/containment must be validated before mapping.

The session owns only the first 0x4000 of no-map GPUEB shared RAM. Vendor logger
allocation would require 0x184000 total, exceeding the observed 0x180000
reservation; no logger may be initialized using that inherited reservation.
No firmware owner may overwrite or free the session block after boot begins.

## Boot And Error Contract

`0123` provides immutable `request_firmware()` staging, bounded parsing and
reference cleanup. It does not authenticate, decrypt, upload, DMA-map, or bind
a device. Its success only means the container layout can be inspected.
Do not wire it to the default ELF loader. The encrypted RV33 prefix is not ELF.

The pinned GPUEB kernel code sets up mailbox/debug/reserved-memory consumers;
it does not provide an audited RV33 firmware boot/reset sequence. The GPUEB
SMC in `gpueb_debug.c` exposes watchdog trigger (operation 0), not firmware
boot. U-Boot's SCP crypto helpers are source-audited for SCP: equivalent MTK
certificates do not prove that their selector or SMC can boot GPUEB. Embedded
LK strings are not proof of the LK load/reset procedure.

The available `/private/tmp/tetris-stock-lkb-first4m.bin` has a first `lk`
payload SHA256 `401d3f39c201967ddc970c58caf546a74922e02ddb63bde043eb73b895eae610`,
not the previously audited stock LK payload. Its untouched `bl2_ext` member is
711336 bytes, SHA256
`170583094d4e4388d8e269cbcc8b14c17df0d4e248dcef57f1d112fba84c004b`.
Read-only disassembly identifies the GPUEB xfile reference at member offset
0x13700, load call 0x13710 to 0x49714 with a 1 MiB destination limit, followed
by an indirect callback at 0x13728. The label is **RV33_A_xfile**, not RV33_A;
this path also references EXPDB and must not be repurposed as processor boot.
These offsets apply only to that member hash. No code/firmware bytes are stored.

Exact selector tracing still needs the legitimate original LK payload SHA256
`431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a` and ATF
payload SHA256 `05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`,
or matching source for the GPUEB load path. SCP's existing ATF trace uses low
selector byte 1; that is not permission to pass signed integer 0x10000, shift
it, or assume GPUEB uses that SCP-specific caller path.

Before a genuine owner calls start/attach:

1. Authenticate firmware and header, validate secure transform policy and
   verify the post-transform digest. Bound actual plaintext segments/entry
   against the audited SRAM partitions, not the ciphertext length.
2. Establish mailbox IRQ/channel ownership before firmware can emit unsolicited
   boot traffic. Current `0120` requests GPUFREQ after `rproc_boot`; boot-channel
   sequencing is therefore still an activation blocker, not proven safe.
3. Retain firmware, device, SRAM, GPR, mailbox and reserved-RAM ownership until
   physical OFF is proven. Source-proven completion/stop acknowledgement and
   exclusion of outstanding DMA are required; logical RPROC_OFFLINE is not enough.
4. Never retry start/power commands after an ambiguous result. Preserve the
   first error and quarantine until a controlled cold reset.

The pinned `rproc_start()` goes directly to unprepare cleanup when `.start()`
returns an error; it does NOT call `.stop()` in this case. `0122` marks boot
attempted before the call and retains every session claim on failure, even
when the core restored OFFLINE and no boot reference was acquired. It never
calls `rproc_shutdown()` without a reference. Successful shutdown still needs
an owner whose `.stop()` honestly guarantees physical OFF; this is unproven.

## Required U-Boot Handoff Evidence

Main owns U-Boot changes. A future versioned handoff must record actual image
identity/slot and authenticated/post-transform digests, true reserved-memory
ranges, and the observed completed GPUEB boot/session epoch. No fixed ready
flag, invented SRAM entry address or copied SCP selector is acceptable.
Kernel attach needs a validated live boot state plus a stale/reset check and
ownership transfer; neither exists merely because GPR13 is nonzero.

The next required source evidence is the matching LK/ATF GPUEB loading and
reset/stop path, including its secure service and plaintext image format.
The legitimate GPU CSF asset is separately `vendor/firmware/mali_csffw.bin`;
it is not supplied by either GPUEB partition and is not cached/validated here.

## CI And Runtime Gates

- Pure Python: `test_gpueb_firmware.py`, `test_gpueb_owner_boundary.py`,
  `test_gpueb_fw_staging.py`; no private assets needed in CI.
- Native CI: `sh patches/gpu/run_gpueb_owner_boundary_ci.sh` and
  `sh patches/gpu/run_gpueb_fw_staging_ci.sh`, with `CI=true`; sanitizer fixtures
  extract the actual production functions. No local native build was run.
- Package order: 0118, 0120, 0122; 0123 is an independent firmware helper.
  Shared APKBUILD/workflow/config edits belong to main. Enable
  `CONFIG_MTK_MT6878_GPUEB_FW=m` only for object smoke with FW_LOADER enabled.
  Compile `drivers/remoteproc/mtk_gpueb_fw.o`; no DT node or service is needed.
- GNU zero-fuzz/no-offset patch application and AArch64 object smoke remain
  required CI gates. The quarantine fixture covers failed partial start in
  both logical OFFLINE and running states, plus failed/still-running shutdown.
- No runtime boot experiment is authorized by these helpers. After authenticated
  transform/load/reset/OFF and mailbox ordering are audited, the first controlled
  boot must test GPUEB ownership alone: no Panthor, rails, or automatic power
  commands; capture epoch/session evidence, keep USB/sensors healthy, and cold
  reset on the first ambiguity. Firmware failure must retain all claims.
