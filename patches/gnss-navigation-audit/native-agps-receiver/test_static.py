#!/usr/bin/env python3
"""Source-backed receiver contract checks; no emulation or C execution."""
from pathlib import Path
import struct
import sys
import unittest
import capstone
from private_evidence import HERE, load, dynamic_symbols, relative_relocations


class ReceiverEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mnld, cls.lib = load(MNLD, LIB)

    def check_code(self, image, expected):
        for address, instruction in expected.items():
            self.assertEqual(image.instructions(address, 4)[address], instruction, hex(address))

    def test_pin_and_decoder(self):
        self.assertEqual(capstone.__version__, "5.0.6")
        from private_evidence import PinnedImage, MNLD_SHA, LIB_SHA
        with self.assertRaises(ValueError):
            PinnedImage(self.mnld.data, LIB_SHA)
        with self.assertRaises(ValueError):
            PinnedImage(self.lib.data, MNLD_SHA)

    def test_reverse_binding_is_not_forward_binding(self):
        self.assertEqual(self.mnld.read(0xc9e5, 13), b"mtk_agps2mnl\0")
        path = b"/data/agps_supl/agps_to_mnl\0"
        self.assertEqual(self.mnld.read(0x16afc, len(path)), path)
        self.assertEqual(self.mnld.read(0x20a3c, 13), b"mtk_mnl2agps\0")
        self.check_code(self.mnld, {
            0x3b550: ("strb", "wzr, [sp, #2]"),
            0x3b56c: ("stur", "x8, [sp, #3]"),
            0x3b570: ("mov", "w8, #0x6d32"),
            0x3b574: ("movk", "w8, #0x6c6e, lsl #16"),
            0x3b57c: ("stur", "w8, [sp, #0xb]"),
            0x3b5e4: ("mov", "w2, #0xf"),
            0x3b5e8: ("bl", "#0x85370"),
            0x55d70: ("mov", "w0, w21"),
            0x55d74: ("mov", "x1, x26"),
            0x55d78: ("bl", "#0x3a4a0"),
        })
        self.assertEqual(self.mnld.imported_symbol(0x86ae8), (1026, b"bind"))

    def test_receiver_table_and_real_callbacks(self):
        table = struct.unpack("<104H", self.mnld.read(0x22bc0, 208))
        branches = {250: 0x3aca8, 256: 0x3b028, 257: 0x3a614,
                    258: 0x3a954, 259: 0x3a988, 260: 0x3a9bc,
                    261: 0x3a9f0, 262: 0x3b064, 264: 0x3aa24}
        for t, branch in branches.items():
            self.assertEqual(0x3a588 + table[t - 200] * 4, branch)
        rel = relative_relocations(self.mnld)
        callbacks = {0x88560: 0x59290, 0x885a0: 0x599f0, 0x885a8: 0x59b80,
                     0x885b0: 0x59d10, 0x885b8: 0x59ea0, 0x885c0: 0x5a030,
                     0x885c8: 0x5a1c0, 0x885d0: 0x5a350, 0x88608: 0x51390}
        for address, target in callbacks.items():
            self.assertEqual(rel[address], target)
        self.check_code(self.mnld, {
            0x3a51c: ("cmp", "w0, #1"),
            0x3a564: ("sub", "w8, w0, #0xc8"),
            0x3acb8: ("bl", "#0x351c0"),
            0x3acbc: ("ldr", "x8, [x19, #0x58]"),
            0x3b04c: ("mov", "w1, w0"),
            0x3b058: ("add", "x0, x20, x8"),
            0x3b05c: ("blr", "x9"),
            0x3b090: ("mov", "w4, #0x2000"),
            0x3b094: ("bl", "#0x352c0"),
            0x3aa50: ("mov", "w4, #0x10000"),
            0x3aa54: ("bl", "#0x352c0"),
        })

    def test_pmtk_lifetime_and_native_channel(self):
        self.check_code(self.mnld, {
            0x59294: ("b", "#0x64a00"),
            0x64a24: ("mov", "w0, #0x23"),
            0x64a28: ("mov", "x1, x19"),
            0x64a2c: ("mov", "w2, #6"),
            0x64a30: ("mov", "w3, #4"),
            0x64a34: ("bl", "#0x859f0"),
        })
        self.assertEqual(self.mnld.imported_symbol(0x86e28), (1026, b"mtk_agps_set_param"))
        self.assertEqual(self.lib.read(0x4d2f4b + 35 - 26, 1)[0] * 4 + 0x6b1840, 0x6b18c4)
        self.check_code(self.lib, {
            0x6b18c8: ("bl", "#0x6e4960"),
            0x6b18cc: ("add", "w25, w0, #1"),
            0x6b18d4: ("cmp", "w4, #0x101"),
            0x6b192c: ("mov", "w26, #3"),
            0x6b1944: ("strh", "w21, [x0]"),
            0x6b1948: ("strh", "w20, [x0, #2]"),
            0x6b1968: ("bl", "#0x6e48e0"),
            0x6b19b0: ("bl", "#0x651500"),
        })

    def test_all_payload_parameters_and_native_copy(self):
        callbacks = (0x599f0, 0x59b80, 0x59d10, 0x59ea0, 0x5a030, 0x5a1c0, 0x5a350)
        for index, address in enumerate(callbacks):
            self.check_code(self.mnld, {
                address + 0xb4: ("mov", f"w0, #{hex(62 + index)}"),
                address + 0xb8: ("mov", "x1, x20"),
                address + 0xbc: ("mov", "w2, #6"),
                address + 0xc0: ("mov", "w3, #4"),
                address + 0xc4: ("mov", "w4, w19"),
                address + 0xc8: ("bl", "#0x85760"),
            })
        self.check_code(self.mnld, {
            0x51414: ("mov", "w0, #0x76"),
            0x5141c: ("mov", "w2, #6"),
            0x51420: ("mov", "w3, #4"),
            0x51424: ("mov", "w4, w19"),
            0x51428: ("bl", "#0x85760"),
        })
        self.assertEqual(self.mnld.imported_symbol(0x86ce0),
                         (1026, b"mtk_agps_set_param_with_payload_len"))
        self.check_code(self.lib, {
            0x6b15a4: ("sub", "w8, w23, #0x3e"),
            0x6b15a8: ("cmp", "w8, #7"),
            0x6b15d8: ("strh", "w22, [x24]"),
            0x6b15dc: ("strh", "w21, [x24, #2]"),
            0x6b15fc: ("bl", "#0x6e48e0"),
            0x6b1660: ("bl", "#0x651500"),
            0x65153c: ("str", "x19, [x9]"),
            0x6515d0: ("bl", "#0x6e4aa0"),
            0x6b16d8: ("cmp", "w23, #0x76"),
        })
        self.assertEqual(dynamic_symbols(self.lib)["mtk_agps_set_param"], (0x6b17b0, 0x284))
        self.assertEqual(dynamic_symbols(self.lib)["mtk_agps_set_param_with_payload_len"], (0x6b14c4, 0x24c))

    def test_no_unassisted_service_exemption_established(self):
        # Satellite pair consumption alone establishes no bypass of slot6 or
        # frame3/4/5. Keep the parent's explicit source gate, even with mask0.
        gate = (HERE.parent / "b41_native_arguments.c").read_text()
        self.assertIn("missing |= B41_MISSING_SECOND_POLICY | B41_MISSING_AGPS_RECEIVER;", gate)
        self.assertIn("if (arguments->missing_contracts) return -EOPNOTSUPP;",
                      (HERE.parent / "b41_native_receiver_host.c").read_text())
        for file in HERE.glob("b41_*.c"):
            text = file.read_text()
            for forbidden in ("missing_contracts", "property_set", "property_get", "dlopen(",
                              "pthread_cancel", "pthread_kill", "unlink(", "ioctl("):
                self.assertNotIn(forbidden, text)

    def test_two_stage_controller_and_owned_lifetime(self):
        source = (HERE / "b41_agps_receiver.c").read_text()
        prepare = source.split("int b41_agps_receiver_prepare(", 1)[1].split(
            "int b41_agps_receiver_activate(", 1)[0]
        self.assertIn("b41_agps_native_associate", prepare)
        self.assertNotIn("b41_agps_native_admit", prepare)
        self.assertIn("B41_AGPS_RX_PREPARED", prepare)
        self.assertIn("return 1;", prepare)
        run = source.split("static void *run(", 1)[1].split("int b41_agps_receiver_prepare(", 1)[0]
        self.assertIn("{{o->fd[3], POLLIN, 0}", run)
        self.assertLess(run.index("if (!active)"), run.index("receive_one(o)"))
        self.assertIn("SO_PASSCRED", source)
        self.assertIn("peer.pid != o->peer_pid || peer.uid != o->peer_uid", source)
        self.assertIn("MSG_TRUNC | MSG_CTRUNC", source)
        self.assertIn("SCM_RIGHTS", source)
        self.assertIn("(void)close(fd);", source)
        self.assertIn("PTHREAD_CREATE_DETACHED", source)
        self.assertIn("B41_AGPS_RX_QUARANTINED", source)
        native = (HERE / "b41_agps_native.c").read_text()
        self.assertIn("image->base + 0x6b17b0u", native)
        self.assertIn("image->base + 0x6b14c4u", native)
        self.assertIn("record.marker < 0 || record.handle == UINT64_MAX", native)
        self.assertIn("if (offload) return -EOPNOTSUPP;", native)
        runner = (HERE / "run_ci.sh").read_text()
        self.assertIn('"${CI:-}" != true', runner)
        self.assertIn("-fsanitize=address,undefined", runner)
        self.assertIn("timeout 30", runner)
        self.assertIn("--wrap=b41_agps_native_admit", runner)
        fixture = (HERE / "test_receiver.c").read_text()
        for name in ("parked", "failed_activation", "timeout_ownership", "wrong_peer", "rights",
                     "replacement", "association_refused", "native_failure", "unsupported"):
            self.assertIn(f"static void {name}(void)", fixture)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_static.py PINNED_MNLD PINNED_LIBMNL")
    MNLD, LIB = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
