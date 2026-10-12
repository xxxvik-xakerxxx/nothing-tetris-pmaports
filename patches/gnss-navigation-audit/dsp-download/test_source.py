#!/usr/bin/env python3
"""Read-only exact B4.1 download-boundary evidence; no native execution."""
import hashlib
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_b41_receiver_policy_source import PinnedImage, MNLD_SHA, LIB_SHA

OUTER = HERE.parents[4]
VENDOR = Path(os.environ.get("TETRIS_MODULES_TREE", str(
    OUTER / "upstream/android_kernel_modules_nothing_mt6878"))).expanduser().resolve()
VENDOR_PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
REPO = HERE.parents[2]
PACKAGE = REPO / "pmaports/device/testing/firmware-nothing-tetris/APKBUILD"
FIRMWARE_SHA512 = "94312789dbbb30bff98814fa441e05394e84beee1277cd3bc63d8b5cf35bae93fe844aae8f18d9acb93dc0d36a04df05db180328065a3db095424ec2d20b56cf"


def source(relative):
    return subprocess.check_output([
        "git", "-C", str(VENDOR), "show", f"{VENDOR_PIN}:connectivity/gps/data_link/{relative}"
    ], text=True)


class DownloadEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        commit = subprocess.check_output([
            "git", "-C", str(VENDOR), "rev-parse", "--verify", f"{VENDOR_PIN}^{{commit}}"
        ], text=True).strip()
        if commit != VENDOR_PIN:
            raise ValueError("wrong B4.1 modules git object")
        cls.mnld = PinnedImage(MNLD.read_bytes(), MNLD_SHA)
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)

    def check(self, expectations):
        for address, expected in expectations.items():
            self.assertEqual(self.lib.instructions(address, 4)[address], expected, hex(address))

    def test_wrong_binary_is_refused_before_decoding(self):
        with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
            PinnedImage(self.mnld.data, LIB_SHA)
        with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
            PinnedImage(self.lib.data, MNLD_SHA)

    def test_exact_public_entry_and_actual_record_caller(self):
        sys.path.insert(0, str(HERE.parent / "native-agps-receiver"))
        from private_evidence import dynamic_symbols
        self.assertEqual(dynamic_symbols(self.lib)["mtk_gps_dsp_init"], (0x52f5ec, 0x130))
        self.assertEqual(self.lib.imported_symbol(0x6e9188), (1026, b"mtk_gps_dsp_init"))
        self.assertEqual(struct.unpack("<Q", self.lib.read(0x6e65b8, 8))[0], 0x71f1d0)
        self.check({
            0x52f2b4: ("adrp", "x0, #0x6e6000"),
            0x52f2b8: ("ldr", "x0, [x0, #0x5b8]"),
            0x52f2bc: ("bl", "#0x6e5520"),
            0x52f600: ("mov", "x19, x0"),
            0x52f6a0: ("mov", "x0, x19"),
            0x52f6a4: ("mov", "w1, #1"),
            0x52f6a8: ("bl", "#0x55471c"),
            0x554728: ("bl", "#0x4f3634"),
            0x4f3674: ("bl", "#0x4f0bdc"),
            0x52f6ec: ("bl", "#0x51fec4"),
            0x52f700: ("bl", "#0x52fbb4"),
            0x52f704: ("mov", "w0, #0x12"),
        })

    def test_mvcd_and_cw_selection_are_native_profile_inputs(self):
        for got, target in ((0x6e6660, 0x7178b8), (0x6e6618, 0x717cb0)):
            self.assertEqual(struct.unpack("<Q", self.lib.read(got, 8))[0], target)
        self.check({
            0x4f2244: ("ldrb", "w8, [x8, #0x33e]"),
            0x4f2250: ("cbz", "w8, #0x4f2350"),
            0x4f225c: ("ldrb", "w8, [x8]"),
            0x4f2268: ("sub", "w8, w8, #1"),
            0x4f2270: ("cmp", "w8, #0x3f"),
            0x4f2274: ("mov", "w8, #0x17"),
            0x4f227c: ("cinc", "w2, w8, lo"),
            0x4f2280: ("add", "x4, sp, #0x118"),
            0x4f228c: ("bl", "#0x52e3dc"),
            0x52e444: ("ldr", "w0, [x8, #0x124]"),
            0x52e448: ("and", "w1, w2, #0xff"),
            0x52e44c: ("mov", "x2, x4"),
            0x52e450: ("bl", "#0x6e5200"),
        })

    def test_key_field_consumption_has_no_first_error_barrier(self):
        # Inspect only immutable instruction text; never obtain or print a key.
        post = self.lib.instructions(0x4f2290, 0x4f2318 - 0x4f2290)
        self.assertFalse(any(i[0].startswith("b") or i[0] in ("cbz", "cbnz", "tbz", "tbnz")
                             for i in post.values()))
        self.check({0x4f229c: ("ldr", "w10, [sp, #0x124]"),
                    0x4f230c: ("str", "w10, [sp, #0x10]"),
                    0x4f2318: ("bl", "#0x50c1d8")})
        abi = source("hw/inc/gps_dl_hw_api.h")
        fields = abi.split("struct gps_dl_hw_mvcd_gps_bootup_info {", 1)[1].split("};", 1)[0]
        self.assertEqual([line.strip() for line in fields.splitlines() if line.strip()], [
            "unsigned int code_size;", "unsigned int start_addr;", "unsigned int exec_addr;",
            "unsigned int cipher_key;", "unsigned int frag_num;"
        ])

    def test_bootstrap_tx_requires_real_native_rings(self):
        self.check({
            0x4f2cd4: ("add", "x2, sp, #0x6b0"),
            0x4f2cd8: ("mov", "w0, #8"),
            0x4f2cdc: ("mov", "w1, #0x35"),
            0x4f2ce0: ("mov", "w3, w19"),
            0x4f2ce4: ("bl", "#0x554828"),
            0x5548bc: ("bl", "#0x651e50"),
            0x5548c0: ("cbz", "x0, #0x554930"),
            0x651e54: ("adrp", "x9, #0x6fe000"),
            0x651e58: ("add", "x9, x9, #0xf78"),
            0x651e5c: ("ldr", "x0, [x9, x8, lsl #3]"),
            0x554aa4: ("cmp", "x20, x8"),
            0x554aa8: ("b.ne", "#0x554a84"),
        })

    def test_fragment_submission_and_real_ack_sequence_are_distinct(self):
        self.check({
            0x4f32bc: ("sub", "w3, w8, #1"),
            0x4f32c0: ("mov", "w8, #0x19"),
            0x4f32c4: ("cinc", "w2, w8, lo"),
            0x4f32cc: ("mov", "w0, #1"),
            0x4f32d4: ("bl", "#0x52e3dc"),
            0x52e460: ("and", "w1, w2, #0xff"),
            0x52e464: ("mov", "w2, w3"),
            0x52e468: ("bl", "#0x6e5200"),
            0x4f3378: ("bl", "#0x554748"),
            0x4f33dc: ("and", "w27, w8, #0xffff"),
            0x4f33e4: ("cmp", "w27, w9"),
            0x4f33e8: ("b.ne", "#0x4f3438"),
            0x50a244: ("and", "x10, x10, #0xffffffffffffffdf"),
            0x50a24c: ("ldrh", "w8, [x8, #0xd00]"),
            0x50a250: ("b", "#0x50a280"),
            0x50a284: ("ldr", "x9, [x9, #0x6d0]"),
            0x50a288: ("str", "x8, [x9]"),
        })
        driver = source("linux/gps_each_device.c")
        self.assertIn("GPSDL_IOC_GPS_DSP_MVCD_FRAGEMENT_NO   25", driver)
        self.assertIn("gps_dl_hw_gps_send_dsp_fragement_num((enum gps_dl_link_id_enum)dev->index, 0, (unsigned int)arg)", driver)
        backend = source("hw/gps_dl_hw_atf_mvcd.c")
        self.assertIn("if (fragement_num > GNSS_IMAGE_MAX_FRAGEMENT_NUM)", backend)
        self.assertIn("#define GNSS_IMAGE_MAX_FRAGEMENT_NUM 256", backend)

    def test_kernel_ram_running_is_a_real_separate_event(self):
        fsm = source("hal/gps_dsp_fsm.c")
        active = fsm.split("case GPS_DSP_ST_RESET_DONE:", 2)[2].split("case GPS_DSP_ST_WORKING:", 1)[0]
        self.assertIn("if (GPS_DSP_EVT_RAM_CODE_READY == evt)", active)
        self.assertIn("gps_dsp_state_change_to(GPS_DSP_ST_WORKING, link_id)", active)
        hal = source("hal/gps_dl_hal.c")
        ready = hal.split("if (d2a.flag & GPS_MCUB_D2AF_MASK_DSP_RAMCODE_READY)", 1)[1].split(
            "if (d2a.flag & GPS_MCUB_D2AF_MASK_DSP_REG_READ_READY)", 1)[0]
        self.assertIn("d2a.dat1 == 0xDEAD || d2a.dat1 == 0xBEEF", ready)
        self.assertIn("gps_dsp_fsm(GPS_DSP_EVT_RAM_CODE_READY, link_id)", ready)
        header = source("hal/inc/gps_dsp_fsm.h")
        self.assertIn("GPS_MCUB_D2AF_MASK_DSP_RAMCODE_READY        0x1", header)

    def test_packaged_firmware_is_pinned_but_not_a_proven_wire_payload(self):
        firmware = FIRMWARE.read_bytes()
        self.assertEqual(len(firmware), 523368)
        self.assertEqual(hashlib.sha512(firmware).hexdigest(), FIRMWARE_SHA512)
        declaration = PACKAGE.read_text()
        self.assertIn(FIRMWARE_SHA512 + "  connsys_gnss_mt6878_mt6631.bin", declaration)
        self.assertIn('"$_fwdir/$_name"', declaration)
        self.assertNotIn(b"connsys_gnss", self.lib.data)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: test_source.py PINNED_MNLD PINNED_LIBMNL PACKAGED_GNSS_FIRMWARE")
    MNLD, LIB, FIRMWARE = map(Path, sys.argv[1:])
    unittest.main(argv=[sys.argv[0]])
