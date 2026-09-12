# SCP DRAM recovery candidate

Status: host validation passes; SCP/sensors remain Broken and runtime disabled.

## Provenance and scope

- Authoritative integration baseline: `aecf4f44f4170952709a7dd514538f0d75b55e22`.
- Working tree: `nothing-tetris-scp-region`, initially clean at `60dc957`.
- Existing `0093` matches the integration baseline byte-for-byte.
- Vendor sources read with `git show` at Nothing OS 4.1 commit
  `ee2be53cb75670b548948636a0db1d1ff112bf12`; the older checkout is not used.
- Read the integration SCP bring-up contract, the porting validation gates,
  and `local/agent-results/scp-uboot-next/BLOCKED_NEXT_GATE.md`. No separately
  named region handoff report was found in the workspace or temporary files.
- Existing integration changes and concurrent work are preserved. No APKBUILD,
  existing documentation, configuration, DT, autoload or service files changed.

## Concrete defect and change

In vendor `scp_helper.c`, `scp_recovery_init()` maps
`ROUNDUP(ap_dram_size, 1024) * 4` when `(int)ap_dram_size > 0`, independently
of the DT `scp_dram_region` flag. Patch `0093` validates only the single,
unrounded range and only when that flag is one. Thus a malformed handoff can
pass validation but produce an overflowing backup mapping, or bypass the
DRAM validation altogether with the flag off.

Candidate `0094` validates every advertised DRAM range and checks rounding,
multiplication and the physical end in the same 32-bit arithmetic used by
the consumer. An entirely absent range is allowed only when not required by
DT. Failure returns `-EINVAL` through the existing `0093` early error path.

The candidate is intentionally NOT referenced by APKBUILD. Integrators must
review and wire it after `0093` in a separate packaging change. Do not cherry-
pick the entire older worktree history into the authoritative baseline.

## Reproduction

From this worktree:

```sh
python3 scripts/check-scp-region-host.py ../../upstream/android_kernel_device_modules_6.1_nothing_mt6878
```

The harness extracts pinned vendor files into temporary storage, applies all
files in `0036`, `0041`, `0093`, then the candidate with `git apply --check`.
It compiles the actual region validator and exact vendor structure using
the host C compiler, warnings as errors and UBSan. No full kernel build,
network access or device operation occurs. `CC` can select another compiler.

Results: baseline 18 cases / 10 failures; candidate 18 cases / 0 failures.
Fixtures cover absent/required DRAM, zero endpoints, alignment boundaries,
rounding/multiplication/address overflow, the signed-size boundary and the
DT-flag bypass. They also check that the input structure is not mutated.
All fixture addresses are synthetic and are not production carveout values.

## Limits and next gate

This validates arithmetic only. It does not prove reserved-memory ownership,
active-slot selection, image authentication, ABI lifetime, regdump mapping,
successful ioremap or error-path teardown. No target kernel compilation or
live test was performed. SCP DVFS and autoload remain disabled.

Next source boundary: tie the complete recovery span to an authoritative
loader/reserved-memory contract once that contract is available. Structural
validation alone must not grant permission to map an arbitrary valid address.

Next minimal live gate, after the missing boot metadata ABI and a reviewed
observation-only bootloader artifact are available: one cold observation boot
that records active slot, authenticated image identity, preserved LK carveouts
and region-info agreement without starting, stopping or resetting SCP. Record
artifact identities and USB NCM/SSH baseline before/after; stop on the first
mismatch or USB regression. No DVFS/module activation follows this host result.
