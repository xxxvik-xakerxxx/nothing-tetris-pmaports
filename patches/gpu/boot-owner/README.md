# Reset-held primary installation

Status: source-tested staging patch, not installed, compiled or hardware-tested
in this task. No existing owner, package, workflow or U-Boot file is modified.
`owner-join.patch` adds concrete operations to the existing owners rather than
introducing another resource owner or an activation permission flag.

## Initialization contract

The actual authenticated slot-A container matches the observed profile-1
156064-byte snapshot SHA256 in `SOURCE-PINS.json`. Its reset vector jumps to
0xac. On the selected cold caller path, it fills BSS [0x1b538,0x2619c) with
zero (44132 bytes) and stack [0x18c00,0x197f0) with 0xabababab. Both ranges
are inside the signed primary. Caller dominance assumes intervening callees
return; the RV33 words at 0x1eb0..0x1ebc remain opaque.

The signed LK clears the whole 256 KiB SRAM bank after reset assertion. This
initialization is distinct from its subsequent 258744-byte copy. Reproducing
the extra [156064,258744) source interval is not a requirement of this new
diagnostic or a justified executable-image rule. A future start must resolve
its actual initialized consumers rather than upload an unauthenticated tail.
Runtime pointer stores name workspaces at 0x3f2b8 and 0x3f6b8; they do not
establish an initial executable tail. No full boot proof follows from BSS alone.

## Three different DRAM contracts

| Input | Pinned LK producer | Known contract | Remaining boundary |
| --- | --- | --- | --- |
| GPR0 | 0x1ee38 stores low32 of 1 MiB staging PA | Reader/copy use mapped staging +24; GPR0 names the allocation base | No first-24-byte content producer/consumer contract; LK frees staging after wait/error |
| GPR6 | 0x1ee20/0x1ee44 store separate MPU allocation PA >>12 | 6 MiB, 64 KiB alignment, selected below 2 GiB; region 12 protection request | Protection result is unchecked; table contents/secure semantics remain unresolved |
| Linux shared DRAM | 0x29754..0x298a0 publishes gpueb_mem_addr/size | Separate 1.5 MiB allocation, 64 KiB alignment; region 31 request | NOS table totals 0x184000, exceeding stock allocation by 0x4000 |

The primary reads GPR6 at 0x100b8 and passes its value with size argument
4 MiB to 0xfe94. Two RV33 words at 0xfe9a/0xfec2 and downstream callees are
opaque; this is not proof that the whole 6 MiB allocation can be replaced by
zeros. In particular, GPR6 is not the Linux shared-memory allocation. The
kernel explicitly zeros its first 16 KiB GPUFREQ shared area, separately from
MPU-table construction. These facts are checked against exact NOS B4.1 Git
objects, the signed LK and matching signed-container plaintext identity.

## Concrete owner join

After parent applies the staged delta, the new callable path is:

`mt6878_gpueb_sram_install_retained(sram, reset, input)` -> canonical
`tetris_gpueb_flat_use_primary()` -> existing
`mt6878_gpueb_reset_primary_transaction()` -> private sole-SRAM installer.

The canonical loan checks the actual bound diagnostic driver and its existing
claimed, verified snapshot. It rejects profile 2: equal length does not prove
equal startup layout. The snapshot is borrowed synchronously and never becomes
a physical-address, arbitrary-tail or caller authentication interface.

The reset transaction requires the matching actual SRAM/parent, sealed dispatch
owner, existing eleven channel pins, disabled owned IRQ and an in-use runtime-PM
reference. It drains the threaded IRQ, quarantines before reset MMIO, records
the reset write before issuing it, and checks the actual zero latch. The sole
SRAM object then clears its already-owned bank, copies exactly 156064 signed
bytes at offset zero and reads back every word, including the initialized tail.
No GPR0/GPR6, entry marker, doorbell, IRQ enable or reset release is programmed.

Success means reset-held clear/copy/readback only. It deliberately retains
quarantine, the full SRAM claim and original reset/dispatch PM/module pins.
Readback failure latches the first error. Existing destruction refuses after
the reset write, even on success; no reset echo, IRQ drain or SMC zero becomes
physical OFF. This is not a remoteproc .start/.stop or a ready GPU session.
All original owner helpers remain unchanged. Lock order is input device,
reset scope, SRAM; callbacks must not acquire the input device lock while an
installation caller drains them. Parent must serialize handle destruction.

The delta is uninstalled staging. Parent integration must regenerate 0120 and
refresh its canonical/snapshot/package pins, link all three actual owners and
extend CI fault fixtures for the new path. Existing legacy host fixtures do
not exercise these kernel-only additions. Require ARM64 compilation/modpost
and failures before reset, reset-readback failure, full-bank readback mismatch,
unknown profile, owner mismatch and retained-resource destruction in CI before
any separately authorized diagnostic boot. No local C build was performed.
Parent also needs the real power/RPC access prerequisite for its board profile:
LK writes MFG-RPC 0x13f91030 = 0x10f00 before reset/clear. This delta introduces
no second RPC owner or claim that a runtime-PM usage count proves that state.

The next start transition belongs inside this same owner boundary, after the
GPR0/GPR6/shared-DRAM contracts are resolved. It must integrate the real IRQ
activation and session response owner; the old independent-GPR session patch
cannot be bolted on beside this whole-bank owner. No stock overread or fake OFF
is required as a substitute for those dependencies.

## Reproduce

From the repository root, using the already authenticated private inputs:

```sh
export PYTHONPATH=/private/tmp/tetris-gpu-offline-capstone-20261012
python3 -B patches/gpu/boot-owner/test_boot.py \
  --snapshot /private/tmp/tetris-gpueb-signed-39116740.bin \
  --lk '../../worktrees/hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img' \
  --gpueb /private/tmp/tetris-gpueb-stock-20261009-e6f6/gpueb_a.img \
  --device-tree ../android_kernel_device_modules_6.1_nothing_mt6878 \
  --module-tree ../android_kernel_modules_nothing_mt6878 \
  --linux-tree /private/tmp/tetris-gpu-canonical-linux.git -v
python3 -B patches/gpu/boot-owner/generate_join_patch.py
patch --dry-run --batch --fuzz=0 -p1 -i patches/gpu/boot-owner/owner-join.patch
```

`audit_boot.py` accepts the same six input/source options and emits metadata
only. It verifies root/delegation/signatures, signed header/ciphertext and the
matching signed plaintext identity without transforming or executing firmware.
Tests cover real input identity, instruction mutations, the DRAM distinctions,
bounded loan/installation guards, owner helper preservation, and deterministic
patch application to the actual pinned consumer/owner sources. These are static
checks, not C execution, malformed-DT runtime faults or hardware validation.
