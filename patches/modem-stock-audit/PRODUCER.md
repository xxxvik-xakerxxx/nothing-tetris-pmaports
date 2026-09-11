# Producer candidate: partition/member selection

This follow-up supersedes the earlier uncertainty about `md1img` versus
`modem_a`. Same exact B4.1-labeled LK container/payload hashes as README.md;
no signature/provenance promotion. All addresses here are payload offsets,
with container offset = payload offset + `0x200`.

## Closed lookup boundary

The loader at `0x25564` calls image-table providers in order. `0x25328`,
`0x23b20`, `0x23b28` return null in this exact binary. Getter `0x817f8`
returns the non-null table at **0x1985f8**:

| Entry | Type | Partition base name | Member |
| --- | --- | --- | --- |
| `0x1985f8` | 1 | modem | md1rom |
| `0x198618` | 2 | modem | md1dsp |
| `0x198638` | 4 | modem | md1drdi |
| `0x198658` | 0 | zero terminator | |

The earlier `0xe15e0` table using `md1img` is a fallback bypassed by that
non-null platform provider. There is no need to invent `md1img -> modem_a`
alias registration. This is a platform descriptor override followed by suffix
resolution of **modem**, not an alias between those two strings.

Actual chain: `0x256c4 -> 0x74da0` receives the selected partition/member.
At `0x74e18`, `0x2a3ac` resolves the partition name; `0x74e20 -> 0x67e50`
looks up that resolved name in the registered block-device list by strcmp.
The resolver's A/B path appends the suffix from `0x18cec` using `%s%s`
(`0x2a400..2a41c`), then tests partition existence through `0x2a5b0` at
`0x2a4d8`. For base modem and valid `_a`/`_b`, this produces modem_a/modem_b.
If absent, stock falls back to the unsuffixed base at `0x2a4e0..2a510`.
The native candidate deliberately rejects that fallback and any unknown slot.

`0x18cec` reads boot control through `0x18df8`, checks magic `0x42414342`,
compares the low priority nibbles and returns `_a` on ties, `_b` when B is
higher. On read/magic failure it returns an empty string. This is observed
code, not a validated boot-control reader: CRC, eligibility, retries and
source ownership were not established, and it is NOT copied into the candidate.

The literal `modem_a` xref `0x7e168` is in **set_write_protect** and selects
a range endpoint alongside `dram_para`, passed to `0x2a7c0`. It is not the
loader's alias mechanism. No write-protect operations were run or implemented.

## Authentication order

After locating a member/header, `0x74ed4 -> 0x7e334 -> 0x81dbc` evaluates
the partition authentication policy. Its name lookup uses a 23-entry table
at `0x1988b8`, falling back to entry zero when the name is unknown. The modem
row names only `modem`, not its suffixed forms; default and modem policy words
are both `[1, 2, 1, 3]` in this binary. Runtime lock/security state still
selects policy. Do not interpret this as authorization to disable verification.

For the enforced branch, the bounded disassembly and checked direct edges are:

1. `0x74f0c -> 0x7e33c -> 0x92634`: certificate-chain verification.
   Nonzero at `0x74f10` branches to the Cert Chain Verify Fail path `0x751cc`.
2. `0x74f18 -> 0x7e2e0`: anti-rollback hook (its failure string is ARB Check
   Fail). Nonzero branches at `0x74f1c` to `0x751f8`.
3. `0x74f28 -> 0x7e340 -> 0x92eac`: header authentication. Zero proceeds
   to payload read; nonzero logs Header Auth Fail and calls fatal helper.
4. `0x75030 -> 0x67edc`: payload read into destination; short reads fail.
5. `0x75088 -> 0x7e344 -> 0x93068`: image authentication. Zero branches
   to `0x750cc`; nonzero logs Image Auth Fail and calls fatal helper.
6. `0x750f8 -> 0x7db00`: post-load hook, only after the preceding path.

The non-enforced path differs: certificate parsing at `0x75004 -> 0x7e338
-> 0x92b5c`, then payload read, then image restore at `0x750c4 -> 0x7e348
-> 0x91f9c`. A certificate-parsing error is logged but that branch continues.
The candidate does not expose this path as an authentication bypass.

Confidence is high for these direct calls, branch order and roles supported by
adjacent error strings. Root-key provisioning, certificate formats, crypto and
rollback context ABI, and any secure backend dependencies are not implemented
or proven by this static audit. No vendor code was executed or emulated.

## Implementation delivered

`modem_image.c/.h` are an unwired native C candidate, free of U-Boot globals:

- `tetris_modem_partition`: selects exactly one modem_a/modem_b from a supplied
  validated name inventory and caller-provided slot; rejects missing/duplicate
  matches and invalid slots without changing output. It does not parse raw GPT.
- `tetris_modem_find_member`: walks a caller-owned snapshot of that partition,
  using the MTK magic `0x58881688`, 512-byte header, little-endian size at +4,
  name at +8 and alignment at +0x44. These fields and the skip formula are used
  by stock at `0x74f5c..74fd8`; match handling is `0x75170..751a0`.
- Returns first matching md1rom/md1dsp/md1drdi header/payload offsets and size,
  as the stock search does. It never writes firmware or claims authentication.
  Finding a first match does not prove uniqueness of later members.
- Rejects truncation, invalid alignment, malformed names, exhausted header
  budget and oversize payload. Addition/alignment stay within explicit extents.
  Failures leave both input and output unchanged. Non-MTK container formats,
  including the separate `0xd7b7ab1e` branch in stock, are unsupported and fail.

This closes the deterministic selected-partition/member-location prerequisite
for a native loader. It is not sufficient to boot a modem. No real modem
partition payload was acquired or tested; fixtures are synthetic. Integration
must retain header/certificate bytes and pass the same immutable input through
the authenticated loader before allocating/publishing modem execution state.

## Existing decoder checked

`upstream/u-boot-mt6878`, checkout `5e450af73a5883ef8f1ad1b399849d7f063d43c1`:
`board/mediatek/mt6878/mt6878_tetris.c` already reads versions 1..3, uses
76-byte tag headers for v3, validates required payloads and reserved-memory
ownership. `.github/tests/tetris_ccci_handoff.c:test_valid_v3_descriptor`
exists; the existing complete host suite passed. No CCCI decoder was duplicated.

Important remaining mismatch: both that checkout and inspected `c931695`
require an exactly **32-byte** modem_info_v2 property, while the stock producer
publishes **48 bytes**. Existing v3 tests use a 32-byte descriptor. Adapting
that existing decoder needs a separate exact-48-byte fixture and an explicit
policy for the extra 16 bytes; simply accepting arbitrary trailing bytes is
not part of this producer change.

## Verification and next step

From the workspace root:

```sh
python3 -B worktrees/nothing-tetris-scp-region/patches/modem-stock-audit/producer_audit.py worktrees/hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img
python3 -B worktrees/nothing-tetris-scp-region/patches/modem-stock-audit/test_producer_contract.py worktrees/hardware-integration/local/uboot-c931695-ci34584756418/stock-b41/lk.img
python3 -B worktrees/nothing-tetris-scp-region/patches/modem-stock-audit/test_candidate.py
```

Static checks bind the selected table, 21 direct call edges and four result
branches to the pinned bytes; six mutations must be rejected. Evidence is in
`producer-evidence.json`. The short host C suite passes 23 cases with ASan/UBSan.
The existing U-Boot CCCI suite also passes. No target/kernel build was run.

Next boot-blocking work: provide an authoritative slot/GPT snapshot and exact
selected modem container as offline inputs, validate this locator on their
actual format, then implement or reuse the certificate/ARB/header/image
verification backend with proven key/context ownership. Keep the native loader
disabled until those contracts and memory/reset ownership are established.
No phone/flash/SMC/power/CI/push actions, vendor binary copies, or shared-tree
source modifications were made. Prior SCP files remain untouched.
