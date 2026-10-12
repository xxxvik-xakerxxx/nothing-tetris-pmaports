# Exact B4.1 initial NS permissions

The prior decision overstated two requirements: ordinary trusted-bootloader
handoff does not inherently require independent Linux signature verification or
a new NS permission certificate. Keep the real successful loader/BROM/EMI
transaction and its lifetime as the evidence. Do not manufacture a proof from
an initial NC read of zero. This correction does not authorize a physical test.

## Three different zeros

Pinned vendor `ee2be53cb75670b548948636a0db1d1ff112bf12`:

| Object | Zero means | Applicable to slots42/43 handoff? |
| --- | --- | --- |
| Legacy 3-bit APC enum, `include/soc/mediatek/emi.h:11` | `MTK_EMIMPU_NO_PROTECTION=0`; forbidden is 5 | Not the v2 AID cell |
| v2 2-bit AID field, `emi-mpu-test-v2.c:64` | `No`; 1 WO, 2 RO, 3 RW | Yes, query4 packed policy |
| ATF operation2/query2 return | Literal zero from unused/default query; no permission-register read | Cannot interpret as any AP permission |

The matching ATF payload is SHA256
`05a247cb02696ce4fe1982ea00bba81236c352146c307159d3f9e380635ea32e`.
All ATF offsets below exclude its 512-byte container header. Descriptor
`0x58e80` selects BL_EMIMPU `0x82000415/c2000415 -> 0x2f750`.
Operation2 selects `0x2f794 -> 0x2f510`. Query jump table `0x50435` sends
query2 to `0x2f548: mov x0,xzr; ret`, whereas query4 goes to `0x2f558`, then
the real AID reader `0x2f464`. Thus neither a query2 zero nor packed group's
low AID0 zero is a positive AP RW result.

The vendor's `drivers/memory/mediatek/smpu.c:386` explicitly names
`ns_cpu_aid=241`; the preceding/following fields name secure CPU240 and
hypervisor CPU243. The MT6878 DT identifies `nsmpu@10351000`, 63 SRs, 256
AIDs, 32 AIDs per returned group (`mt6878.dts:5214`). This corroborates both
the actual MMIO block and the NS CPU identity; AID0 is not that CPU field.

## Positive RW evidence, not a zero inference

Installed U-Boot `8d2ccc12e7861c5726e9c37a07f62c4ae18db7b5` uses the actual
normal preloader-derived policy in `tetris_modem_plan_emi_policy()`:

| Slot | Source role | RW AIDs | Group7 / NS CPU241 |
| --- | --- | --- | --- |
| 42 | AP/MD NC service memory | 35,38,39,42,43,44,45,47,241 | `0xc00000000`, bits35:34 = 3 = RW |
| 43 | AP/MD cache service memory | 35,40,47,241 | `0xc00000000`, bits35:34 = 3 = RW |

Group index is `241/32=7`; field shift is `2*(241%32)=34`.
Slot42 group1 is `0xcff0f0c0`; slot43 group1 is `0xc00300c0`; groups0 and2..6
are zero. Every one of the eight returned words is checked before programming
and after actual range/enable readback. AID241's nonzero field is positive
initial NS-CPU RW policy evidence. It is not a new custom NS trust class.

The installed final producer verifies the REAL owner's successful loader and
BROM completion, then encodes actual verified replies into the 336-byte
little-endian `nothing,modem-smem-boot-evidence` property. It does not accept an
external success boolean. For record bank0/slot42 and bank1/slot43:

| Field | Wire offset | Meaning |
| --- | --- | --- |
| Reservation base/capacity | record+8/+16 | Actual retained allocation, not a unit-specific constant |
| Programmed start/size | record+24/+32 | Actual service range; can be shorter than the reservation |
| Actual SA/EA/enable | record+40/+48/+56 | Returned range fields and required enable=1 |
| Actual AID group7 | record+120 | NS CPU field at absolute offset200 for42, 328 for43 |

Record base is80 for42 and208 for43. Full group7 equals `0xc00000000`, not a
caller-selected mask. Source `tetris_modem_smem_evidence.c` checks slot, role,
reservation, planner size, range, enable, every policy word and both four-one
BROM replies before copying the encoded value. Missing, inconsistent or failed
reports cannot be treated as a successful trusted boot transaction.

## ATF cells and region lifetime

The real AID reader writes only the AID selector `0x103519bc`, executes DSB,
reads the selected permission word and extracts two bits. It does not commit
permissions. ATF range writer `0x2d61c` writes the SA, EA marker and enable bit:

| Slot | SA / EA register | Enable register / bit | Selected AID241 read field |
| --- | --- | --- | --- |
| 42 | `0x10351148` / `0x1035114c` | `0x103512a8`, bit9 | `0x103519ec`, bits19:18 |
| 43 | `0x10351150` / `0x10351154` | `0x103512a8`, bit10 | `0x103519ec`, bits21:20 |

SA/EA use 4KiB page units relative to `0x40000000`. Raw EA bit31 appears as
bit43 in returned address-shaped data and is masked only as that marker.
The software producer represents the service extent as `[base,base+size)`;
the hardware's exact boundary-match convention has not been independently
proven here, so access must remain within the declared extent and not use its
endpoint/tail. The full 128MiB bank reservation is not wholly covered merely
because it is NOMAP. CONSYS prefix/overlapping slot41 and firmware regions are
separate owners and policies; IRQ/DMA/MMIO access is not granted by slots42/43.

ATF `0x2f618` calls the one-shot admission guard `0x10380`, whose per-slot byte
is at payload `0xf7a25+slot`. That blocks repeat BL range programming through
this path; it is not a hardware policy lock against all secure/kernel writers.
Raw EA's marker is not such a lock either. The record is a boot-time snapshot.
NOMAP/allocation/resource claims preserve Linux memory ownership, not immutable
SMPU permission or exclusion of modem DMA. Query4 readback itself uses selector
writes, so even requesting a current readback is outside this read-only task.

## Trust and remaining dependencies

Under the normal trusted-loader model, a validated installed owner report plus
source-defined AID241 RW, actual enabled ranges and retained allocations is a
defensible initial Linux NS access basis. A separate generic NS certificate is
not required. Independent installed-byte signature verification is a stronger,
different threat model and is not imposed as an adoption prerequisite here.
This is not a claim of enforced verified boot for custom U-Boot or pmOS.

Keep these concrete limits: actual Linux EL/master identity (CPU243 has zero
in these tables), effective overlapping SR/NSR/KP policy, unchanged matching
preloader/ATF, coherency attributes, retained resources and intervening policy
writers. The vendor NS/KP violation code is not a full priority specification.
Current effective rights cannot be refreshed from historical reports alone.
Neither absence of a measured fault nor successful initial NC read proves RW.

EMI access does not solve MD power ownership, first shutdown or execution latch
semantics. Those stay separate from the permission interpretation. Read-only ON
adoption may now use ordinary trusted handoff without inventing certificates;
the exact implementation boundary is in `ON-ADOPTION.md`.

Reproduce the source cells and static ATF decoding with `audit_emi.py --atf
<declared-atf-container>`. It verifies payload SHA and reads/disassembles bytes
only; no instruction is executed, no device is contacted, no SMC is issued and
no private firmware is copied into this directory.
