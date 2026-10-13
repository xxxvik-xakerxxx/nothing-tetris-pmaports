#!/usr/bin/env python3
"""Immutable B4.1 producer/override evidence; no instruction execution."""
import hashlib
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import unittest

import capstone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA

ROOT = HERE.parents[3]
VENDOR = Path(os.environ.get("TETRIS_MODULES_TREE",
    str(ROOT.parents[0] / "android_kernel_modules_nothing_mt6878")))
PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"


class SelectorSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if capstone.__version__ != "5.0.6":
            raise ValueError("expected offline Capstone 5.0.6")
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def check(self, expected, image=None):
        image = image or self.lib
        for address, instruction in expected.items():
            self.assertEqual(image.instructions(address, 4)[address], instruction, hex(address))

    def test_complete_producer_slices(self):
        for start, end, digest in (
            (0x5ccaa0, 0x5cccf8, "cb2009bb21edd3f0620bc76e79037504c7ac01880c112b0c7268f8c9fe51f0e7"),
            (0x52ea3c, 0x52eca4, "7f824c238d271571325111ae642428441bbe15d6f28f90f4997fbe9a284aa52c"),
            (0x4fcb78, 0x4fcd68, "8202234e8e3637e5246672e7d11b542fbe79eb5144f8bc87bdf5dfc4d99d125d"),
            (0x52ba90, 0x52bb74, "717a6cfb7d5a975af4d21c178953c0de8cdfec67154b2c032cb40820946b84f8"),
            (0x51b488, 0x51b5e0, "179a204a3337ee5b088becd5f47ac6b8bce03c1c7581374e67d0c76c437c20b3"),
        ):
            self.assertEqual(hashlib.sha256(self.lib.read(start, end-start)).hexdigest(), digest)
        with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
            PinnedImage(self.mnld.data, LIB_SHA)

    def test_capability_destination_is_configured_chip_not_adie(self):
        self.assertEqual(self.mnld.imported_symbol(0x86d38),
                         (1026, b"mtk_gps_get_chipset_capability_v2"))
        # These pointers are zero in the file; R_AARCH64_RELATIVE supplies them.
        offset = struct.unpack_from("<Q", self.mnld.data, 40)[0]
        size, count = struct.unpack_from("<HH", self.mnld.data, 58)
        sections = [struct.unpack_from("<II4QII2Q", self.mnld.data, offset+i*size)
                    for i in range(count)]
        relocations = {
            address: (info, addend)
            for section in sections if section[1] == 4
            for address, info, addend in
            (struct.unpack_from("<QQq", self.mnld.data, entry)
             for entry in range(section[4], section[4]+section[5], section[9]))
        }
        self.assertEqual(relocations[0x887a0], (1027, 0xde230))
        self.assertEqual(relocations[0x887a8], (1027, 0xde2f0))
        self.check({
            0x579e0: ("adr", "x21, #0x887a0"),
            0x579e4: ("mov", "w1, #0xd0"),
            0x579e8: ("mov", "x0, x21"),
            0x579ec: ("bl", "#0x85810"),
            0x63368: ("ldp", "w19, w8, [x8]"),
            0x6336c: ("str", "w19, [x9, #8]"),
        }, self.mnld)
        self.check({
            0x51b4b8: ("ldp", "x20, x21, [x0]"),
            0x51b578: ("ldr", "x1, [x24, #8]"),
            0x51b57c: ("mov", "w2, w23"),
            0x51b580: ("mov", "x0, x21"),
            0x51b584: ("bl", "#0x6e48e0"),
        })
        self.assertEqual(0xde2f0 + 0x14, 0xde304)
        for address in (0x6ed7d0, 0x6ed960, 0x6edaf0):
            self.assertEqual(struct.unpack("<II", self.lib.read(address+0x14, 8)),
                             (0xffff6878, 0x370))
        self.assertEqual([struct.unpack("<I", self.lib.read(address+8, 4))[0]
                          for address in (0x6ed7d0, 0x6ed960, 0x6edaf0)], [6, 10, 10])

    def test_profile_table_complete_first_match_and_default(self):
        table = [struct.unpack("<II", self.lib.read(0x6ee1a8 + i*8, 8)) for i in range(50)]
        self.assertEqual(len(table), 50)
        self.assertEqual(table[0], (5, 0xffff6878))
        self.assertEqual(table[32:34], [(1, 0xfffe6735), (1, 0xffff6580)])
        self.assertEqual(table[34:], [(0, 0)] * 16)
        self.check({
            0x52ea3c: ("ldr", "w9, [x24, #0x30]"),
            0x52ea54: ("ldr", "w11, [x11, #4]"),
            0x52ea5c: ("b.eq", "#0x52ea74"),
            0x52ea64: ("cmp", "x8, #0x190"),
            0x52ea6c: ("mov", "w8, #1"),
            0x52ea74: ("ldr", "w8, [x10, x8]"),
            0x52ea80: ("strb", "w8, [x26]"),
        })

    def test_mode_jump_tables_and_all_fixed_assignments(self):
        self.assertEqual(list(self.lib.read(0x4ce116, 12)),
                         [0, 11, 31, 105, 11, 0, 40, 0, 0, 0, 46, 69])
        self.assertEqual(list(self.lib.read(0x4ce122, 10)),
                         [84, 0, 8, 77, 90, 93, 81, 96, 99, 102])
        # Second dispatch entries consume these defaults and leaf assignments.
        self.check({
            0x5ccb3c: ("mov", "w22, #3"),
            0x5ccb40: ("mov", "w21, #3"),
            0x5ccb54: ("mov", "w21, #6"),
            0x5ccb58: ("mov", "w22, #0x31"),
            0x5ccb78: ("mov", "w21, #7"),
            0x5ccb7c: ("mov", "w22, #0x33"),
            0x5ccc88: ("mov", "w0, #3"),
            0x5ccc8c: ("mov", "w21, #5"),
            0x5ccc90: ("mov", "w22, #1"),
            0x5ccc98: ("mov", "w0, #6"),
            0x5ccc9c: ("mov", "w21, #0x17"),
            0x5ccca0: ("mov", "w22, #0x3f"),
            0x5cccbc: ("mov", "w21, #0x17"),
            0x5cccc0: ("mov", "w22, #0x30"),
            0x5ccccc: ("mov", "w22, #2"),
            0x5cccd8: ("mov", "w22, #0xd"),
            0x5ccce4: ("mov", "w22, #0xf"),
            0x5cccf0: ("mov", "w22, #0xc"),
            0x5ccca4: ("strb", "w22, [x20]"),
            0x5ccca8: ("strb", "w21, [x19]"),
        })

    def test_mode10_and_11_need_actual_secondary_predicate(self):
        self.check({
            0x5ccbac: ("b.lo", "#0x5ccc80"),
            0x5ccbb0: ("bl", "#0x508d0c"),
            0x5ccbd8: ("ldr", "w8, [x8, #0x30]"),
            0x5ccbdc: ("mov", "w9, #-0x9877"),
            0x5ccbe8: ("mov", "w0, #0xa"),
            0x5ccbec: ("mov", "w21, #0x27"),
            0x5ccbf0: ("mov", "w22, #0x7f"),
            0x5ccc08: ("b.ls", "#0x5ccc80"),
            0x5ccc0c: ("bl", "#0x508d0c"),
            0x5ccc50: ("tst", "w10, w8"),
            0x5ccc58: ("csel", "w22, w22, w9, ne"),
            0x5ccc5c: ("csel", "w21, w21, w8, ne"),
            0x5211bc: ("bl", "#0x6e4a80"),
            0x5211c8: ("cmp", "x0, #4"),
            0x5211d0: ("cmn", "w8, #1"),
        })

    def test_initializer_has_later_owner_overrides(self):
        self.check({
            0x52eab8: ("bl", "#0x6e4b80"),
            0x52ead8: ("and", "w9, w9, #2"),
            0x52eadc: ("strb", "w9, [x10]"),
            0x52eb00: ("cmp", "w9, #1"),
            0x52eb34: ("strb", "w9, [x21]"),
            0x52eb38: ("str", "w10, [x24, #0x38]"),
            0x52eb4c: ("cmp", "w9, #1"),
            0x52eb5c: ("strb", "w9, [x21]"),
            0x52eb88: ("cbz", "w11, #0x52eba4"),
            0x52eb9c: ("strb", "w11, [x21]"),
        })
        # Identical GOT offsets on DIFFERENT pages must never be conflated.
        self.assertEqual(struct.unpack("<Q", self.lib.read(0x6e7650, 8))[0], 0x89cd24)
        self.assertEqual(struct.unpack("<Q", self.lib.read(0x6e6650, 8))[0], 0x717cb7)
        self.assertNotEqual(self.lib.read(0x6e7650, 8), self.lib.read(0x6e6650, 8))

    def test_policy_clock3_is_engine_private_not_ioctl11(self):
        self.check({
            0x4fcc10: ("b.ne", "#0x4fcc84"),
            0x4fcc24: ("ldr", "w8, [x19, #0x64]"),
            0x4fcc38: ("strb", "w8, [x26]"),
            0x4fcc40: ("bl", "#0x660f9c"),
            0x4fcc78: ("ldr", "w0, [x19, #0x64]"),
            0x4fcc7c: ("bl", "#0x665158"),
        })

    def test_initial_override_producers_are_retained_inputs_and_queued_messages(self):
        self.check({
            0x52b984: ("ldrb", "w11, [x22, #0x50]"),
            0x52b99c: ("str", "w11, [x10]"),
            0x52be28: ("mov", "w1, #9"),
            0x52be30: ("bl", "#0x6e5200"),
            0x52be38: ("and", "w9, w0, #0x3000000"),
            0x52be50: ("strb", "w9, [x8]"),
            0x532004: ("ldrb", "w8, [x24, #0x14]"),
            0x532020: ("strb", "w8, [x9]"),
            0x532024: ("ldrb", "w8, [x24, #0x16]"),
            0x532034: ("strb", "w8, [x10]"),
            0x532230: ("ldrh", "w8, [x24, #0x16]"),
            0x53224c: ("strb", "w8, [x9]"),
        })
        offset = self.lib.read(0x4c4acd + 0x45, 1)[0]
        self.assertEqual(0x52bbe4 + 4*offset, 0x52bd84)
        self.check({0x52bd84: ("mov", "w8, #0x370"),
                    0x52bd88: ("b", "#0x52befc")})

    def test_secure_default_is_capability_mask_with_policy_override(self):
        entry = self.lib.read(0x4ce055 + 0xb3 - 1, 1)[0]
        self.assertEqual(0x5cc594 + 4*entry, 0x5cc8fc)
        self.check({
            0x5cc904: ("ldr", "w8, [x8, #0x28]"),
            0x5cc908: ("and", "w8, w8, #0xffffff0"),
            0x5cc90c: ("cmp", "w8, #0x30f"),
            0x5cc910: ("cset", "w0, hi"),
            0x4fd178: ("mov", "w0, #0xb3"),
            0x4fd194: ("strb", "w0, [x19, #0x33e]"),
            0x4fcd54: ("tbnz", "w8, #7, #0x4fcd68"),
            0x4fcd64: ("strb", "w0, [x22, #0x33e]"),
            0x4ff350: ("strb", "w10, [x8, #0x33e]"),
        })
        self.assertEqual(int((0x370 & 0x0ffffff0) > 0x30f), 1)

    def test_dsp_selector_is_context5c_not_nvm_profile33(self):
        self.check({
            0x52ee74: ("ldrb", "w9, [x24, #0x5c]"),
            0x52ee88: ("and", "w9, w9, #0x3f"),
            0x52eea0: ("strb", "w9, [x11]"),
            0x4f2268: ("sub", "w8, w8, #1"),
        })

    def test_6878_download_branch_does_not_change_requested_fields(self):
        offset = struct.unpack("<H", self.lib.read(0xaada + 2*0x45, 2))[0]
        self.assertEqual(0x4f0fdc + 4*offset, 0x4f151c)
        self.check({
            0x4f0bfc: ("mov", "w19, w1"),
            0x4f151c: ("and", "w9, w19, #0xff"),
            0x4f154c: ("strb", "w9, [x20]"),
            0x4f1ac4: ("strb", "w10, [x9]"),
            0x4f1f44: ("strb", "wzr, [x20]"),
        })
        self.assertEqual(struct.unpack("<Q", self.lib.read(0x6e6640, 8))[0], 0x717cb2)
        self.assertEqual(struct.unpack("<Q", self.lib.read(0x6e6648, 8))[0], 0x717cb1)
        self.check({0x4f283c: ("mov", "w9, #0x27"),
                    0x4f2844: ("strb", "w9, [x8]")})

    def test_auxiliary_word_is_ioctl29_zero_buffer_and_error_not_success(self):
        self.check({
            0x52b66c: ("str", "xzr, [sp, #0x18]"),
            0x52b6b4: ("str", "wzr, [x24]"),
            0x52bb14: ("ldr", "w0, [x25, #0x124]"),
            0x52bb18: ("add", "x2, sp, #0x18"),
            0x52bb1c: ("mov", "w1, #0x1d"),
            0x52bb20: ("bl", "#0x6e5200"),
            0x52bb24: ("ldr", "w8, [sp, #0x18]"),
            0x52bb2c: ("str", "w8, [x24]"),
        })
        code = subprocess.check_output([
            "git", "-C", str(VENDOR), "show",
            PIN + ":connectivity/gps/data_link/linux/gps_each_device.c"
        ])
        self.assertEqual(hashlib.sha256(code).hexdigest(),
                         "e340d2c61fb306b15d9edd0b828f6f613169c3f28c7c96ea59e1d754503e17c5")
        self.assertIn(b"#if 0\n#define GPSDL_IOC_GPS_EAP_SAP_TIMESYNC 29\n#endif", code)
        self.assertIn(b"default:\n\t\tretval = -EFAULT;", code)

    def test_native_acquisition_has_no_generic_setter_or_execution(self):
        source = (HERE / "selectors.c").read_text().split("static void write16", 1)[0]
        self.assertIn("b41_capability_branch_read(image, chip, adie, hw, sw", source)
        self.assertIn("result.capability.capability + 0x14", source)
        self.assertIn("result.capability.capability + 8", source)
        self.assertIn("result.capabilities & UINT32_C(0x0ffffff0)", source)
        self.assertIn("i < 50", source)
        self.assertIn("target != image->base + bindings[i].target", source)
        self.assertIn("if (memcmp(&first, &second, sizeof(first))) return -EAGAIN;", source)
        for forbidden in ("dlopen(", "ioctl(", "open(", "ready", "final_proven", "getenv("):
            self.assertNotIn(forbidden, source)

    def test_nominal_is_explicit_native_policy_with_actual_fe_marker(self):
        full_code = (HERE / "selectors.c").read_text()
        code = full_code[full_code.index("int b41_native_l1_nominal_build("):
                         full_code.index("static int overlaps(")]
        self.assertIn("if (clock11 < 0) return clock11;", code)
        self.assertIn("if (clock30 < 0) return clock30;", code)
        self.assertIn("clock11 != 0x21 || clock30 != 0", code)
        self.assertIn("b41_bootstrap_mode_build(3, chip->context_chip_30", code)
        self.assertIn("result.inputs.private_clock = NULL;", code)
        self.assertIn("b41_mvcd_clock_synthesize(result.inputs.context_hz_18, mode, &clock)", code)
        self.assertIn("result.fields.synthesis_and_profile[30] = 1;", code)
        self.assertIn("result.inputs.context_mode_13 = first->bytes[0x13];", code)
        self.assertIn("result.inputs.secondary_fd_6edeec = -1;", code)
        for forbidden in ("b41_bootstrap_observe(", "b41_mvcd_bootstrap_fields_build(",
                          "private_word(", "frequency_1670", "adjustment_1668", "ioctl(", "dlopen("):
            self.assertNotIn(forbidden, code)
        self.check({0x4f20ac: ("cmp", "w8, #0xfe"),
                    0x4f20b4: ("cset", "w8, eq"),
                    0x5ccc88: ("mov", "w0, #3"),
                    0x5ccc8c: ("mov", "w21, #5"),
                    0x5ccc90: ("mov", "w22, #1"),
                    0x4f2134: ("mov", "w1, wzr")})

    def test_nominal_uses_exact_26m_reference_row_not_calibration(self):
        row = self.lib.read(0x27934 + 5*72, 64)
        words = struct.unpack("<16I", row)
        expected = [(word >> 8) & 0xff if 5 <= i <= 8 else word & 0xffff
                    for i, word in enumerate(words)]
        code = (HERE / "selectors.c").read_text()
        array = re.search(r"static const uint16_t profile\[16\] = \{([^}]+)\}", code)
        self.assertIsNotNone(array)
        values = [int(item.strip()) for item in array.group(1).split(",") if item.strip()]
        self.assertEqual(values, expected)
        self.assertEqual(hashlib.sha256(self.lib.read(0x27934, 720)).hexdigest(),
                         "ec85c275d49568c182872ba5d4f51f04f47bc815b126ed0eaa1b77b5b9c08290")

    def test_nominal_query_and_fixture_keep_real_session_boundaries(self):
        code = (HERE / "selectors.c").read_text()
        for check in ("query->session != session", "query->gps0_fd != session->gps0_fd",
                      "session->fields != &policy->inputs", "query->command != 23",
                      "if (query->status < 0) return query->status;",
                      "info->frag_num-1u > 256u", "forget(temporary, sizeof(temporary));"):
            self.assertIn(check, code)
        fixture = (HERE / "test_selectors.c").read_text()
        for evidence in ("B41_MVCD_FIELDS_MISSING", "query.status = -EFAULT",
                         "query.status = 18", "query.command = 24", "info.frag_num = 258",
                         "first->unresolved_bytes = 99",
                         "B41_BOOTSTRAP_OVERLAP", "synthesis[14]"):
            self.assertIn(evidence, fixture)

    def test_native_identity_is_revision_independent_without_fake_queries(self):
        self.assertEqual(hashlib.sha256(self.lib.read(0x51b31c, 0x16c)).hexdigest(),
                         "498b730f15817c17497917596190fdc1adf0eca4ad054ed7830272eb02ee0259")
        self.check({0x51b3b8: ("cbnz", "w9, #0x51b3d8"),
                    0x51b3c0: ("cbnz", "w10, #0x51b3d8"),
                    0x51b3c4: ("b", "#0x51b400"),
                    0x51b414: ("mov", "w24, #1")})
        code = (HERE / "selectors.c").read_text()
        identity = code[code.index("int b41_native_l1_identity_select("):
                        code.index("int b41_native_l1_nominal_build(")]
        self.assertIn("hardware_chip != 0x6878u", identity)
        self.assertIn("case 0x6631u: result.navigation_mode_base = 6;", identity)
        self.assertIn("case 0x6637u: case 0x6686u: result.navigation_mode_base = 10;", identity)
        self.assertIn("result.context_chip_30 = UINT32_C(0xffff6878);", identity)
        self.assertIn("result.capabilities = 0x370;", identity)
        for forbidden in ("ioctl(", "b41_capability_branch_read(", "dlopen(", "hw, sw"):
            self.assertNotIn(forbidden, identity)
        for key, name in ((0x6ed710, b"0x6631\0"), (0x6ed8a0, b"0x6637\0"),
                          (0x6eda30, b"0x6686\0")):
            self.assertEqual(self.lib.read(key, 7), b"0x6878\0")
            self.assertEqual(self.lib.read(key+0x5c, 7), name)

    def test_conninfra_queries_use_return_values_and_actual_gps_selector(self):
        code = subprocess.check_output(["git", "-C", str(VENDOR), "show",
            PIN + ":connectivity/conninfra/adaptor/conninfra_dev.c"])
        self.assertEqual(hashlib.sha256(code).hexdigest(),
                         "9b971702e10ceb844310c68d0639114c86f41c9a7ed21d36ccccb5181ddf87ed")
        self.assertIn(b"retval = conn_adaptor_get_chipid();", code)
        self.assertIn(b"retval = conn_adaptor_detect_adie_chipid(arg);", code)
        self.assertIn(b'"WIFI", "BT", "GPS", "FM"', code)
        self.assertEqual((2 << 30) | (4 << 16) | (0xc2 << 8), 0x8004c200)
        runner = (HERE / "selectors.c").read_text().split("#ifdef B41_NATIVE_L1_RUNNER", 1)[1]
        self.assertIn("scalar_query(conn_fd, 0x8004c200UL, 0UL)", runner)
        self.assertIn("scalar_query(conn_fd, 0x8004c203UL, 2UL)", runner)
        for command in (6, 7, 8):
            self.assertNotRegex(runner, rf"(?:ioctl|scalar_query)\(gps_fd, {command}UL")

    def test_runner_reads_only_public_nv_ranges_and_one_attempt(self):
        runner = (HERE / "selectors.c").read_text().split("#ifdef B41_NATIVE_L1_RUNNER", 1)[1]
        self.assertIn("st.st_size != 54", runner)
        self.assertIn("pread(fd, &name_first, 1, 0)", runner)
        self.assertIn("pread(fd, numeric, sizeof(numeric), 24)", runner)
        self.assertEqual(runner.count("pread("), 2)
        self.assertEqual(runner.count('open("/dev/gpsdl0"'), 1)
        self.assertIn("O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW", runner)
        self.assertIn("aux_status != -EFAULT || auxiliary", runner)
        self.assertIn("lna_status != -EFAULT || lna", runner)
        self.assertIn("b41_native_l1_download_linux_begin(&owner", runner)
        self.assertIn("b41_download_linux_step(&owner)", runner)
        self.assertNotIn("cipher_key", runner)
        self.assertNotIn("dlopen(", runner)
        self.check({0x62bcc: ("stp", "w9, wzr, [sp, #0x90]"),
                    0x63454: ("add", "x2, sp, #0x94"),
                    0x63458: ("mov", "w1, #0x10"),
                    0x6348c: ("ldr", "w9, [sp, #0x94]")}, self.mnld)

    def test_callable_native_adapter_reuses_bounded_download_controller(self):
        code = (HERE / "selectors.c").read_text()
        begin = code[code.index("int b41_native_l1_download_linux_begin("):
                     code.index("#ifdef B41_NATIVE_L1_RUNNER")]
        self.assertEqual(begin.count("ioctl("), 1)
        self.assertIn("ioctl(session->gps0_fd, 23UL, &info)", begin)
        self.assertIn("b41_native_l1_download_begin(owner, policy, session", begin)
        self.assertNotIn("b41_mvcd_bootstrap_fields_build(", begin)
        self.assertIn("forget((uint8_t *)&info, sizeof(info));", begin)
        fixture = (HERE / "test_selectors.c").read_text()
        self.assertIn("metadata_calls == 1", fixture)
        self.assertIn("metadata_calls == 2", fixture)
        self.assertIn("action.command == 25 && action.argument == 0", fixture)
        self.assertIn("owner.stage == B41_DOWNLOAD_ACKS_COMPLETE", fixture)
        ci = (HERE / "run-ci.sh").read_text()
        self.assertIn("aarch64*)", ci)
        self.assertNotIn("aarch64*musl*", ci)
        self.assertIn("'#include <features.h>'", ci)
        self.assertIn('"$compiler" -std=c11 -dM -E -x c -', ci)
        self.assertIn("__GLIBC__([[:space:]]|$)", ci)
        self.assertLess(ci.index("__GLIBC__"), ci.index('"$compiler" -std=c11 -static'))
        self.assertIn("-static -DB41_NATIVE_L1_RUNNER", ci)
        self.assertIn("Machine:.*AArch64", ci)
        self.assertIn("NEEDED", ci)

    def test_cli_help_and_rejections_cannot_acquire_devices(self):
        runner = (HERE / "selectors.c").read_text().split("#ifdef B41_NATIVE_L1_RUNNER", 1)[1]
        main = runner[runner.index("int main("):]
        self.assertIn('argc == 2 && !strcmp(argv[1], "--help")', main)
        self.assertIn("argc < 2 || argc > 3 || !argv[1][0] || argv[1][0] == '-'", main)
        self.assertIn('strspn(argv[2], "0123456789") != strlen(argv[2])', main)
        self.assertLess(main.index("timeout_ms < 1 || timeout_ms > 30000"),
                        main.index("status = native_now(&now)"))
        ci = (HERE / "run-ci.sh").read_text()
        self.assertIn("-DB41_NATIVE_L1_CLI_FIXTURE", ci)
        self.assertIn("-Wl,--wrap=open -Wl,--wrap=ioctl", ci)
        self.assertIn('"$result" -eq 2', ci)
        self.assertIn("expect_usage_rejection --help 1", ci)
        self.assertIn("expect_usage_rejection --unknown", ci)
        fixture = (HERE / "test_selectors.c").read_text()
        acquisition_guard = fixture.split("#ifdef B41_NATIVE_L1_CLI_FIXTURE", 1)[1].split("#else", 1)[0]
        self.assertIn("int __wrap_open(", acquisition_guard)
        self.assertIn("int __wrap_ioctl(", acquisition_guard)
        self.assertEqual(acquisition_guard.count("_Exit(99);"), 2)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_selectors_source.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
