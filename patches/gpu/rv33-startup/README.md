# Authenticated RV33 Startup Layout

Status: partial static proof, not permission to upload or start GPUEB.
The private 156064-byte snapshot was captured on r181 through the root-only
ordinary-DRAM analysis driver. Its signed plaintext digest is
`9628a446c2453664eebb7ce0f5b6d9db51d677d6c1db3c4ac1449f4cfaad86d7`.
Neither firmware bytes nor extracted unique data are included here.

The audit requires that exact snapshot, matching B4.1 LK payload digest
`431e0551382e21f4edfb8ff3ca05cd67b177d40b1a51f9e863965eea58f8b94a`,
and Capstone 5.0.6. It performs bounded static disassembly, never emulation or
firmware execution. RV32 branch/JAL immediates from this decoder are relative
to the instruction address; regression tests cover positive and negative targets.

Established local semantics:

- Entry jumps to `0xac`; startup selects its path using GPR words at `0x3fd78`
  and `0x3fd20`.
- The cold caller reaches a zero-fill of `[0x1b538, 0x2619c)` and a stack fill
  of `[0x18c00, 0x197f0)`. Both lie inside the signed snapshot. Caller dominance
  assumes every callee returns to its link address; opaque callees prevent a
  whole-startup proof.
- LK clears 256 KiB and copies 258744 bytes. Its extra source interval
  `[0x261a0, 0x3f2b8)` is not the demonstrated BSS range.
- An alternate helper reads the full 256 KiB SRAM window. Later pointer stores
  name `0x3f2b8` and `0x3f6b8`; these observations do not identify the initial
  source of the extra LK copy bytes or prove that they are required payload.
- Undecoded RV33/vendor instructions remain opaque. Opcode resemblance to a
  different RISC-V vendor extension is not an instruction-set identity check.

Run with externally retained private inputs:

```sh
python3 -B patches/gpu/rv33-startup/test_startup.py --snapshot /private/path/primary.bin --lk /private/path/lk.img
python3 -B patches/gpu/rv33-startup/audit_startup.py --snapshot /private/path/primary.bin --lk /private/path/lk.img --output /private/path/report.json
```

The snapshot must be a private regular file, not a symlink. Reports are written
atomically with mode 0600 and contain bounds/hashes/results, never raw firmware.
Identity, decode-boundary, control-flow, range, mutation and failure-output tests
must pass. Next: identify the LK source-tail producer and transitive startup
memory requirements, then integrate upload with actual power/reset/OFF/IRQ
ownership. No renderer, render node, GPU readiness or lifecycle is claimed.
