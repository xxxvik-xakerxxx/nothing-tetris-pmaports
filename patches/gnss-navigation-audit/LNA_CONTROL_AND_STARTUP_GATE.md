# LNA control restriction and startup query contract

## Control candidate

`0003-gps-refuse-unproven-lna-control.patch` is regenerated with balanced U3
context against modules e96f60dc081ae3525ef43d4bcf0ee5ee97e53835 plus frozen0002.
Apply after metadata1006, including the package1002..1005 compatibility stack.
Main can package it as1007. All four power-helper calls (on, wake, sleep, off)
reach the replaced helper. Enable, DSP handover and disable are all refused;
none can select a pin or request a GPIO. Even populated/stale globals, successful
metadata queries, manual DT states, removal or reprobe cannot authorize control.
The void ABI is retained, with a once-only refusal warning, not a success result.

Full v051 Kbuild links this platform helper and no gps_stp LNA object. The only
pinctrl selection in pinned data_link/gps_mcudl is the removed call. Separate
gps_stp code still contains an LNA selector and is outside this build/profile;
this is not a universal gate for every vendor GPS module. No A-die RF/secure
operations are modified or claimed harmless by this narrowly scoped patch.

Main must remove0020's unproven GPS pinctrl/pio additions. This helper cannot
prevent pinctrl core from applying a separately injected default state at probe.
The cached stock DT evidence is in STOCK_LNA_DT_PROVENANCE.md. Metadata0002 is
read-only description, never board authorization or external-LNA wiring proof.

Run `test_lna_control_gate.py` locally without native builds. CI runs
`sh run_lna_control_gate_ci.sh` with injectable TETRIS_MODULES_TREE and
TETRIS_DEVICE_MODULES_TREE. It extracts the actual stacked helper, then tests
all link/on/force combinations with NULL/populated/error pointers across
synthetic lifecycle states. Native ASAN/UBSAN compile/run remains a CI gate.

## Startup correction

The previous isolated ioctl16 slice correctly showed that a failing ioctl copies
the previous stack output, but did not recover its earlier initialization.
Pinned mnld62bcc does `stp w9,wzr,[sp,#0x90]`: sp+94 is initialized0. The
unconditional query at6345c and copy at63498 therefore retain0 when the pinned
disabled kernel case returns EFAULT without touching the output. No conditional
external-LNA flag bypasses the mnld query in the recovered producer block.

This does NOT mean the field is unused. libMNL init copies first0x70 at52e718..73c;
primary DSP startup52f2bc -> mtk_gps_dsp_init52f5ec ->55471c ->4f3634 ->4f0bdc.
The config pointer survives asx26. Config+30 is chip identity; the real family
table at6ee1a8 maps0xffff6878 to5. Consumer4f29e0..4f2a48 reads config+54 for
MT6878 and stores its lowbyte in startup payload sp+712, with mode10. Only older
profiles have the recovered literal72 alternative. They are NOT MT6878 defaults.
There is no proof here that payload0 means a physical GPIO0 or no external LNA.

New b41_lna_query_plan.* separates:

- successful ioctl16 metadata (original query provenance);
- exact pinned disabled-case EFAULT, untouched zero output (OEM retained-zero);
- reviewed0002 absent-state ENODATA, untouched zero output (same initialized-value
  contract, an explicit port policy extension, NOT an OEM-successful query);
- every other error, unexpected positive status, modified error output or
  unresolved driver profile (reject, stop before21).

Callers select profiles from verified artifact/driver identity, never a manual
DT property. EBUSY ownership conflict and ENODEV owner loss always reject.
The snapshot does not set B41_FIRST_LNA_QUERY for retained-zero. Its builder
bridge assigns distinct provenance0x80, not B41_FIRST_LNA_RESULT, and leaves
remaining unknown fields/XML/host-services/stop/transport gates intact. It does
not register callbacks, load firmware, call an engine or authorize RF execution.
Main should coordinate replacing the frozen fail-first collector only after
review and CI. The frozen original builder/collector/tests are unchanged.
The frozen builder intentionally returns1 (partial) today, so the bridge retains
that status. If the builder later gains a complete result, recompute completeness
after assigning retained-zero provenance; do not reuse a pre-bridge partial
status. First-config completion will still not establish engine readiness.

Offline pinned binary regression: `test_b41_lna_profile.py MNLD LIBMNL` executes
only bounded initialization/query/consumer slices with synthetic memory and
mocked ioctl/logger. No phone, real syscall, native ELF execution or engine init.
CI standalone: `sh run_lna_query_plan_ci.sh`. Bionic standalone fixture can link
b41_first_config.c + b41_lna_query_plan.c + test_b41_lna_query_plan.c using main's
existing Bionic compiler/runner, without shared CI edits here.

## Next gate

Before any GNSS runtime, main must verify packaged1007 applies after1006/metadata
and that final compiled DT has no injected LNA state/default GPIO143/144.
Run both new native fixtures in CI and compile the touched vendor translation
unit. Resolve remaining first/second config and mandatory host services, descriptor
ownership and bounded stop before native init. Retained-zero removes an artificial
successful-ioctl16 requirement, not those startup gates or the navigation fix test.
