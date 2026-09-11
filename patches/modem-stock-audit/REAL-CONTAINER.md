# Real B4.1 modem container and conservative stock48 decoder candidate

## Actual input and locator result

The entire existing `Tetris_B4.1-260415-1709-image-firmware.7z` was hashed
before extraction and matched
`2336875d0b1e7364f87690701706e0d8cd7149bcf8f05c6d295f6082cf949811`.
Only member `modem.img` was extracted to this folder's ignored `local/`.
`bsdtar` listed the archive but failed extraction with Truncated 7-Zip file
body; its partial output was deleted. Installed `7zz` extracted successfully.

The real modem container is **90,214,400 bytes**, SHA-256
`b15207a948125439a5957224d65774d9d44c558c6eb285372a520b27b8d7d6c5`.
This establishes local archive consistency, not signature validation, SKU
portability, installed firmware identity, or any active-slot match.

The existing `modem_image.c` needed **no algorithm change**. The new bounded
C harness maps the container read-only, caps it at 512 MiB and searches at most
128 headers. It runs our locator under ASan/UBSan, never vendor instructions.

| Member | Header offset | Payload offset | Payload bytes |
| --- | ---: | ---: | ---: |
| md1rom | 0 | 512 | 55,396,432 |
| md1drdi | 55,400,768 | 55,401,280 | 8,483,520 |
| md1dsp | 63,888,576 | 63,889,088 | 5,767,168 |

All three calls succeeded. All three calls with their payload extent shortened
by one byte failed with `-EMSGSIZE` (Darwin numeric value -40), leaving the
output unchanged. Whole-container SHA-256 was identical before and after.
Per-member hashes are recorded in `modem-real-result.json`.

An independent bounded header walk finds **23 headers**, all with alignment
16. ROM is followed by `cert1md` and `cert2`; DRDI precedes DSP and each is
followed by `cert1` and `cert2`. Debug/filter members follow the executable
members. The header walk ends at 90,213,936, leaving 464 bytes outside the
walk; those bytes were not interpreted as a firmware member. This confirms
that a fixed ROM/DSP/DRDI physical order would be wrong. The locator correctly
skips certificate and other members by their declared aligned sizes.

This is not certificate-chain validation: names alone do not establish that
certificate contents match their preceding image. A subsequent authenticated
loader must keep the headers and certificate records from the same immutable
selected container; passing only the three payload spans would lose inputs
needed by the stock authentication path.

## Exact 48-byte descriptor boundary

Pinned LK payload SHA and offsets remain those in README.md. Directly observed:

- `0x28130..0x28138` publishes state address plus **0x30 bytes** as the
  `ccci,modem_info_v2` property through the raw-copy property helper.
- Initializer `0x27df8` clears state bytes `0x18..0x27`; `0x27dfc` clears
  `0x28..0x2b`. Thus **12 of the extra 16 bytes**, at `0x20..0x2b`, are
  explicitly initialized to zero along with the prefix load/error state.
- Bytes `0x2c..0x2f` are not written by that initializer. Four bytes of
  structure alignment padding is plausible, but is not established as a
  portable ABI by the inspected machine code. No nonzero field meanings or
  complete indirect-writer/lifetime proof has been recovered for the tail.

Consequently the tail is **not claimed semantically decoded**. The candidate
`ccci-stock48.patch` supports the defensible zero-tail subset: accept exactly
48 bytes only with version 3 and all 16 extension bytes zero. Reject every
nonzero extension byte before mapping tag memory. The existing 32-byte path,
prefix errors, tag validation and memory ownership checks remain intact.
Some otherwise usable firmware handoffs with nonzero padding/extension state
may be conservatively rejected; do not loosen this gate without evidence.

The patch targets existing U-Boot `c931695bb963efaa0dfdf928ea475440581838b4`;
it adds no second decoder and is **not applied to the shared U-Boot checkout**.
The scratch test reproduces the baseline's BAD_DESCRIPTOR_SIZE on an exact
48-byte synthetic descriptor, applies the patch, then proves the positive
zero-tail v3 case and 52 negative length/version/tail/prefix cases. Both the
before and after runs also pass the full existing CCCI host suite. ASan/UBSan
are enabled. No live 48-byte property or tag buffer was captured in this task.

The test explicitly prevents parent-repository discovery during scratch patch
application and checks that the source changed; initial testing exposed Git
silently skipping paths inside a nested scratch directory. This was fixed in
the harness, not mistaken for a decoder algorithm failure.

## Reproduction

From `worktrees/nothing-tetris-scp-region`:

```sh
python3 -B patches/modem-stock-audit/extract_modem.py ../nothing-tetris-scp-thermal/local/stock-b41/Tetris_B4.1-260415-1709-image-firmware.7z
python3 -B patches/modem-stock-audit/probe_real.py
python3 -B patches/modem-stock-audit/test_stock48.py ../../upstream/u-boot-mt6878
```

Extraction rejects an archive hash mismatch before creating output; repeats
compare the extracted member to any existing modem.img and refuse a differing
replacement. Only metadata, scripts, tests and the candidate patch are tracked.
`local/` excludes modem.img and temporary host executables/source copies.

## Remaining modem boot blocker

The selected-image locator now works on this real archive input. Modem producer
readiness is **not established**: authentication/anti-rollback context, trusted
active-slot provenance, reserved-memory lifetime and reset/power ownership
remain unresolved. The decoder patch removes only a length mismatch for the
strict zero-tail subset; it does not manufacture a valid handoff or start a
modem. No phone, power, SMC, flashing, new OTA, target/full build, CI or push.
