#!/usr/bin/env python3
"""Pinned offline secure L1 sequence evidence; never execute vendor code."""
import hashlib
from pathlib import Path
import struct
import subprocess
import sys
import unittest

import capstone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from test_b41_receiver_policy_source import PinnedImage, LIB_SHA
from test_source import source, VENDOR, VENDOR_PIN

REPO = HERE.parents[2]
PACKAGE = REPO / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
READ_PATCH = "1008-vendor-gnss-bound-data-link-read.patch.vendor"
READ_PATCH_SHA = "5ecf24e445441eae599f1ca7d75e9f76c87967d14edc08cffd88a434a2ff14e5"
ROUTINES = (
    (0x4f0bdc, 0x4f3634, "559fc7a71f7be281bf79877e50dd3907f84bf7d4d185671c17471315989169af"),
    (0x52e3dc, 0x52e480, "7cc700f48da362fb998027bb0a72cf31b9564c654d9806cd490ad99fc70bdabb"),
    (0x509830, 0x50acc8, "9c6760cd19c9923aef5b102aa886e65acf0361264e1ee633d6c939c7cef0633a"),
    (0x554828, 0x554aec, "d10beb55cf93ba411ab3deace29bf7649e15f699449ad4167c7be15b481dc06b"),
)
SOURCE_SHA = {
    "linux/gps_each_device.c": "e340d2c61fb306b15d9edd0b828f6f613169c3f28c7c96ea59e1d754503e17c5",
    "gps_each_link.c": "456c64ff0d17c230c409fb3272a89c5dffb4de0e25bb41f6cdef7f4baece796e",
    "link/gps_dl_link_sync.c": "c34b718ed48d07daeedc09586c1f5fa7d2b8abcc718e99647af93bfc33025f88",
    "hw/gps_dl_hw_atf_mvcd.c": "09b860755b033961fe120f35bd6c5686ed4da1c7f625d1f41ad3044032db423f",
    "hw/inc/gps_dl_hw_atf.h": "77eb468a2ff1df84d4ed95795a47c5fa928195df5cf58ba8489bbbab4d3e5729",
    "hal/gps_dl_hal.c": "8e9de5f75d14dc3ac9ecf44b9a6021353dd16dbe4b72c7a9050b73097166ae9d",
    "hal/gps_dsp_fsm.c": "a1a1221a44cde42196808c24cebbe1ba949d46699b7b443563db3652c96b1b17",
    "hal/inc/gps_dsp_fsm.h": "b29f772db37cd26f20f439a2e53e511572c7feb98c2e778b97f666fe1e5a363e",
    "lib/inc/gps_dl_time_tick.h": "bcc6aeef11168ef8b733b06fc2a2fe2efc8b71bcbb61e515a574012364fdedb9",
}


class DownloadSequenceEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if capstone.__version__ != "5.0.6":
            raise ValueError("expected offline Capstone 5.0.6")
        commit = subprocess.check_output([
            "git", "-C", str(VENDOR), "rev-parse", "--verify", f"{VENDOR_PIN}^{{commit}}"
        ], text=True).strip()
        if commit != "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835":
            raise ValueError("wrong B4.1 source object")
        cls.lib = PinnedImage(LIB.read_bytes(), LIB_SHA)
        cls.sources = {path: source(path) for path in SOURCE_SHA}
        for path, digest in SOURCE_SHA.items():
            if hashlib.sha256(cls.sources[path].encode()).hexdigest() != digest:
                raise ValueError(f"wrong pinned source: {path}")

    def check(self, expected):
        for address, instruction in expected.items():
            self.assertEqual(self.lib.instructions(address, 4)[address], instruction, hex(address))

    def table_target(self, table, origin, command, minimum):
        offset = struct.unpack("<H", self.lib.read(table + 2 * (command - minimum), 2))[0]
        return origin + 4 * offset

    def test_complete_elf_and_routine_pins(self):
        with self.assertRaisesRegex(ValueError, "wrong B4.1 SHA256"):
            PinnedImage(b"not the pinned vendor ELF", LIB_SHA)
        for start, end, digest in ROUTINES:
            self.assertEqual(hashlib.sha256(self.lib.read(start, end - start)).hexdigest(), digest)

    def test_count_and_sequence_have_separate_producers(self):
        # ATF count is u16 in a u32 field; stock retains its upper half too.
        self.assertIn("bootup_info->frag_num = (unsigned int)(res.a1 & 0x000000000000FFFF);",
                      self.sources["hw/gps_dl_hw_atf_mvcd.c"])
        self.check({
            0x4f22c4: ("ldrb", "w12, [sp, #0x128]"),
            0x4f22d0: ("ldrb", "w11, [sp, #0x129]"),
            0x4f22d4: ("ldrh", "w25, [sp, #0x12a]"),
            0x4f22d8: ("strb", "w12, [sp, #0xec]"),
            0x4f22e8: ("strb", "w11, [sp, #0xe8]"),
            0x4f2ab0: ("lsl", "w8, w25, #0x10"),
            0x4f2ab4: ("str", "w8, [sp, #0x98]"),
            0x4f2b58: ("mov", "w11, wzr"),
            0x4f263c: ("strb", "wzr, [sp, #0xe4]"),
            0x4f2640: ("strb", "wzr, [sp, #0xe0]"),
        })

    def test_bootstrap_zero_ack_precedes_first_sequence_increment(self):
        self.check({
            0x4f2cd4: ("add", "x2, sp, #0x6b0"),
            0x4f2cd8: ("mov", "w0, #8"),
            0x4f2cdc: ("mov", "w1, #0x35"),
            0x4f2ce4: ("bl", "#0x554828"),
            0x4f2da8: ("bl", "#0x554748"),
            0x4f2dd4: ("tbnz", "w8, #0xf, #0x4f2d70"),
            0x4f2ddc: ("ldr", "x8, [x8, #0x6d0]"),
            0x4f2dec: ("ldr", "x8, [x8]"),
            0x4f2df0: ("ldrb", "w9, [sp, #0xe4]"),
            0x4f2df4: ("ldrb", "w10, [sp, #0xe0]"),
            0x4f2df8: ("mov", "x11, x26"),
            0x4f2dfc: ("bfi", "w9, w11, #0x10, #0x10"),
            0x4f2e00: ("and", "w6, w8, #0xffff"),
            0x4f2e04: ("bfi", "w9, w10, #8, #8"),
            0x4f2e08: ("cmp", "w6, w9"),
            0x4f2e0c: ("b.ne", "#0x4f2e6c"),
            0x4f2e10: ("lsl", "w25, w11, #0x10"),
            0x4f2e3c: ("ldrb", "w8, [sp, #0xe4]"),
            0x4f2e40: ("ldrb", "w9, [sp, #0xe0]"),
            0x4f2e44: ("orr", "w8, w25, w8"),
            0x4f2e48: ("orr", "w8, w8, w9, lsl #8"),
            0x4f2e4c: ("add", "w8, w8, #1"),
            0x4f2e50: ("lsr", "w9, w8, #8"),
            0x4f2e54: ("lsr", "w11, w8, #0x10"),
            0x4f2e58: ("strb", "w8, [sp, #0xe4]"),
            0x4f2e5c: ("strb", "w9, [sp, #0xe0]"),
            0x4f2e60: ("b", "#0x4f2f34"),
            0x4f2f4c: ("cbz", "w8, #0x4f2c58"),
        })

    def test_bootstrap_auxiliary_word_does_not_supply_fragment_count_or_success(self):
        self.assertEqual(struct.unpack("<Q", self.lib.read(0x6e6638, 8))[0], 0x717cf0)
        self.check({
            0x509fcc: ("add", "x8, x8, #0x233"),
            0x509fd4: ("ldrh", "w8, [x8]"),
            0x509fdc: ("ldr", "x9, [x9, #0x638]"),
            0x509fe0: ("str", "x8, [x9]"),
            0x4f0e0c: ("ldr", "x8, [x8, #0x638]"),
            0x4f0e14: ("str", "xzr, [x8]"),
            0x4f22c4: ("ldrb", "w12, [sp, #0x128]"),
            0x4f22d0: ("ldrb", "w11, [sp, #0x129]"),
            0x4f22d8: ("strb", "w12, [sp, #0xec]"),
            0x4f22e8: ("strb", "w11, [sp, #0xe8]"),
        })
        producer = self.lib.instructions(0x4f0bdc, 0x4f3634 - 0x4f0bdc)
        self.assertEqual([a for a, (m, o) in producer.items()
                          if m == "ldr" and "#0x638]" in o], [0x4f0e0c])
        wait = self.lib.instructions(0x4f2dac, 0x4f2e64 - 0x4f2dac)
        self.assertFalse(any("#0x638]" in o for _, o in wait.values()))

    def test_secure_branch_has_no_userspace_fragment_trigger_frame(self):
        # The complete producer has two bootstrap calls and one embedded call.
        producer = self.lib.instructions(0x4f0bdc, 0x4f3634 - 0x4f0bdc)
        self.assertEqual([a for a, ins in producer.items() if ins == ("bl", "#0x554828")],
                         [0x4f2c84, 0x4f2ce4, 0x4f32ec])
        self.check({
            0x4f3148: ("ldr", "x10, [x10, #0x660]"),
            0x4f314c: ("ldrb", "w10, [x10, #0x33e]"),
            0x4f3158: ("cbz", "w10, #0x4f3164"),
            0x4f315c: ("mov", "w27, wzr"),
            0x4f3160: ("b", "#0x4f325c"),
            0x4f326c: ("ldr", "x9, [sp, #0xb0]"),
            0x4f3270: ("ldr", "x8, [x9]"),
            0x4f3274: ("orr", "x8, x8, #0x20"),
            0x4f3278: ("str", "x8, [x9]"),
            0x4f3284: ("ldrb", "w8, [x8, #0x33e]"),
            0x4f328c: ("cbz", "w8, #0x4f32dc"),
            0x4f32d4: ("bl", "#0x52e3dc"),
            0x4f32d8: ("b", "#0x4f32f0"),
            0x4f32dc: ("add", "x2, sp, #0x134"),
            0x4f32e0: ("mov", "w0, #0xc"),
            0x4f32e4: ("ldr", "w1, [sp, #0x9c]"),
            0x4f32ec: ("bl", "#0x554828"),
        })
        self.assertEqual(struct.unpack("<Q", self.lib.read(0x6e6660, 8))[0], 0x7178b8)

    def test_fragment_argument_is_current_sequence_minus_one_not_count_minus_one(self):
        self.check({
            0x4f3290: ("ldrb", "w8, [sp, #0xe0]"),
            0x4f329c: ("ldrb", "w9, [x9]"),
            0x4f32a0: ("ldrb", "w10, [sp, #0xe4]"),
            0x4f32a4: ("lsl", "w8, w8, #8"),
            0x4f32a8: ("sub", "w9, w9, #1"),
            0x4f32ac: ("bfi", "w8, w12, #0x10, #0x10"),
            0x4f32b0: ("and", "w9, w9, #0xff"),
            0x4f32b4: ("orr", "w8, w10, w8"),
            0x4f32b8: ("cmp", "w9, #0x3f"),
            0x4f32bc: ("sub", "w3, w8, #1"),
            0x4f32c0: ("mov", "w8, #0x19"),
            0x4f32c4: ("cinc", "w2, w8, lo"),
            0x4f32cc: ("mov", "w0, #1"),
            0x4f32d0: ("mov", "w1, w19"),
            0x52e414: ("and", "w8, w1, #0xff"),
            0x52e418: ("cmp", "w8, #1"),
            0x52e41c: ("b.eq", "#0x52e458"),
            0x52e45c: ("ldr", "w0, [x8, #0x124]"),
            0x52e460: ("and", "w1, w2, #0xff"),
            0x52e464: ("mov", "w2, w3"),
            0x52e468: ("bl", "#0x6e5200"),
            0x52e46c: ("cmp", "w0, #0"),
            0x52e470: ("cset", "w8, ne"),
            0x52e474: ("lsl", "w0, w8, #1"),
            0x6e5204: ("ldr", "x17, [x16, #0xff8]"),
        })
        self.assertEqual(self.lib.imported_symbol(0x6e8ff8), (1026, b"ioctl"))

    def test_ack_dispatch_is_32_for_every_secure_fragment_including_last(self):
        for command, copy, completion in ((0x31, 0x509984, 0x509f98),
                                           (0x32, 0x509f20, 0x50a228),
                                           (0x33, 0x509984, 0x50a254)):
            self.assertEqual(self.table_target(0x4c3e36, 0x509894, command, 0x29), 0x509eec)
            self.assertEqual(self.table_target(0x4c3f08, 0x509970, command, 0x14), copy)
            self.assertEqual(self.table_target(0x4c4024, 0x509900, command, 0x14), completion)
        self.check({
            0x509f2c: ("mov", "w24, #2"),
            0x509fb4: ("and", "x10, x10, #0xffffffffffff7fff"),
            0x50a244: ("and", "x10, x10, #0xffffffffffffffdf"),
            0x50a24c: ("ldrh", "w8, [x8, #0xd00]"),
            0x50a250: ("b", "#0x50a280"),
            0x50a270: ("and", "x10, x10, #0xffffffffffffbfff"),
            0x50a284: ("ldr", "x9, [x9, #0x6d0]"),
            0x50a288: ("str", "x8, [x9]"),
            0x4f3378: ("bl", "#0x554748"),
            0x4f33a4: ("tbnz", "w8, #5, #0x4f3340"),
            0x4f33ac: ("ldr", "x8, [x8, #0x6d0]"),
            0x4f33dc: ("and", "w27, w8, #0xffff"),
            0x4f33e4: ("cmp", "w27, w9"),
            0x4f33e8: ("b.ne", "#0x4f3438"),
        })
        self.assertEqual(struct.unpack("<Q", self.lib.read(0x6e66d0, 8))[0], 0x7178a0)

    def test_only_matched_ack_advances_and_stock_retry_reuses_sequence(self):
        self.check({
            0x4f32fc: ("cbnz", "w0, #0x4f30b0"),
            0x4f30d0: ("mov", "w27, #0xffff"),
            0x4f30dc: ("cmp", "w24, w8"),
            0x4f30e0: ("b.hs", "#0x4f34f4"),
            0x4f33ec: ("lsl", "w28, w11, #0x10"),
            0x4f3410: ("ldrb", "w8, [sp, #0xe4]"),
            0x4f3414: ("ldrb", "w9, [sp, #0xe0]"),
            0x4f3418: ("orr", "w8, w28, w8"),
            0x4f341c: ("orr", "w8, w8, w9, lsl #8"),
            0x4f3420: ("add", "w8, w8, #1"),
            0x4f3424: ("lsr", "w9, w8, #8"),
            0x4f3428: ("lsr", "w25, w8, #0x10"),
            0x4f342c: ("strb", "w8, [sp, #0xe4]"),
            0x4f3430: ("strb", "w9, [sp, #0xe0]"),
            0x4f3434: ("b", "#0x4f347c"),
            0x4f3448: ("add", "w24, w24, #1"),
            0x4f347c: ("ldr", "w8, [sp, #0xbc]"),
            0x4f3484: ("b.hs", "#0x4f30d4"),
            0x4f3490: ("mov", "x12, x25"),
            0x4f3494: ("bfi", "w8, w12, #0x10, #0x10"),
            0x4f3498: ("bfi", "w8, w9, #8, #8"),
            0x4f349c: ("cmp", "w8, w26"),
            0x4f34a0: ("b.eq", "#0x4f326c"),
            0x4f34a4: ("b", "#0x4f30d8"),
        })
        mismatch = self.lib.instructions(0x4f3438, 0x4f347c - 0x4f3438)
        self.assertFalse(any(m.startswith("str") and ("#0xe4]" in o or "#0xe0]" in o)
                             for m, o in mismatch.values()))

    def test_termination_is_sequence_greater_than_count_without_final_wire_request(self):
        self.check({
            0x4f30ec: ("and", "x10, x12, #0xffff"),
            0x4f30f0: ("ldrb", "w11, [sp, #0xec]"),
            0x4f30f4: ("lsl", "x24, x10, #0x10"),
            0x4f30f8: ("ldrb", "w10, [sp, #0xe8]"),
            0x4f30fc: ("orr", "w5, w24, w8"),
            0x4f3100: ("bfi", "w5, w9, #8, #8"),
            0x4f3104: ("ldr", "w8, [sp, #0x98]"),
            0x4f3108: ("orr", "w8, w8, w11"),
            0x4f310c: ("orr", "w8, w8, w10, lsl #8"),
            0x4f3110: ("cmp", "w5, #0"),
            0x4f3114: ("ccmp", "w5, w8, #2, ne"),
            0x4f3118: ("b.hi", "#0x4f34a8"),
            0x4f34c4: ("strb", "wzr, [x8]"),
            0x4f34f0: ("b", "#0x4f0d94"),
            0x4f0e00: ("mov", "w0, #0x10"),
            0x4f0e04: ("b", "#0x4f3560"),
            0x4f358c: ("ret", ""),
        })
        terminal = self.lib.instructions(0x4f34a8, 0x4f34f4 - 0x4f34a8)
        self.assertEqual([(a, ins) for a, ins in terminal.items() if ins[0] == "bl"], [
            (0x4f34c8, ("bl", "#0x507e4c")), (0x4f34e8, ("bl", "#0x50c1d8"))])
        epilogue = self.lib.instructions(0x4f0d94, 0x4f0e08 - 0x4f0d94)
        self.assertEqual([ins for ins in epilogue.values() if ins[0] == "bl"],
                         [("bl", "#0x508d0c"), ("bl", "#0x4f0554")])

    def test_kernel_integer_submission_and_secure_return_are_not_ack(self):
        driver = self.sources["linux/gps_each_device.c"]
        for command, number, cw in (("GPS_DSP_MVCD_FRAGEMENT_NO", 25, 0),
                                     ("GPS_CWDSP_MVCD_FRAGEMENT_NO", 26, 1)):
            self.assertRegex(driver, rf"#define GPSDL_IOC_{command}\s+{number}\b")
            block = driver.split(f"case GPSDL_IOC_{command}:", 1)[1].split("break;\n", 2)
            block = "break;\n".join(block[:2])
            self.assertIn("if (!dev->is_open)", block)
            self.assertIn(f"dev->index, {cw}, (unsigned int)arg)", block)
            self.assertIn("retval = 0;", block)
            self.assertIn("retval = -EFAULT;", block)
            self.assertNotIn("copy_from_user", block)
        backend = self.sources["hw/gps_dl_hw_atf_mvcd.c"].split(
            "bool gps_dl_hw_gps_send_dsp_fragement_num", 1)[1]
        self.assertIn("#define GNSS_IMAGE_MAX_FRAGEMENT_NUM 256",
                      self.sources["hw/gps_dl_hw_atf_mvcd.c"])
        self.assertIn("if (fragement_num > GNSS_IMAGE_MAX_FRAGEMENT_NUM)", backend)
        self.assertIn("dsp_type = GPS_DL_MVCD_DSP_L1;", backend)
        self.assertIn("dsp_type = GPS_DL_MVCD_DSP_L1_CW;", backend)
        self.assertIn("SMC_GPS_MVCD_SEND_DSP_FRAGEMENT,\n"
                      "\t\t\tdsp_type, fragement_num, 0, 0, 0, 0, &res);", backend)
        self.assertIn("if (res.a1 == 1)", backend)
        self.assertNotIn("gps_dsp_fsm(", backend)
        self.assertIn("SMC_GPS_MVCD_SEND_DSP_FRAGEMENT = 0x20,",
                      self.sources["hw/inc/gps_dl_hw_atf.h"])

    def test_kernel_ready_is_separate_mcub_event_with_exception_filter(self):
        hal = self.sources["hal/gps_dl_hal.c"]
        ready = hal.split("if (d2a.flag & GPS_MCUB_D2AF_MASK_DSP_RAMCODE_READY)", 1)[1].split(
            "if (d2a.flag & GPS_MCUB_D2AF_MASK_DSP_REG_READ_READY)", 1)[0]
        self.assertIn("d2a.dat1 == 0xDEAD || d2a.dat1 == 0xBEEF", ready)
        self.assertLess(ready.index("continue;"), ready.index("gps_dsp_fsm("))
        self.assertIn("GPS_DSP_ST_WORKING == gps_dsp_state_get(link_id)", ready)
        self.assertIn("gps_dsp_fsm(GPS_DSP_EVT_RAM_CODE_READY, link_id);", ready)
        self.assertIn("GPS_MCUB_D2AF_MASK_DSP_RAMCODE_READY        0x1",
                      self.sources["hal/inc/gps_dsp_fsm.h"])
        fsm = self.sources["hal/gps_dsp_fsm.c"]
        active = fsm.split("case GPS_DSP_ST_RESET_DONE:", 2)[2].split("case GPS_DSP_ST_WORKING:", 1)[0]
        self.assertIn("if (GPS_DSP_EVT_RAM_CODE_READY == evt)", active)
        self.assertIn("gps_dsp_state_change_to(GPS_DSP_ST_WORKING, link_id);", active)

    def test_stock_transport_has_no_nonblocking_write_or_poll_contract(self):
        driver = self.sources["linux/gps_each_device.c"]
        write = driver.split("static ssize_t gps_each_device_write", 1)[1].split("#if 0", 1)[0]
        self.assertNotIn("O_NONBLOCK", write)
        self.assertIn("gps_each_link_write(link_id, &dev->o_buf[0], copy_size)", write)
        fops = driver.split("static const struct file_operations gps_each_device_fops = {", 1)[1].split("};", 1)[0]
        self.assertNotRegex(fops, r"\.poll\s*=")
        link = self.sources["gps_each_link.c"]
        write = link.split("int gps_each_link_write(", 1)[1].split("int gps_each_link_read(", 1)[0]
        self.assertIn("gps_each_link_write_with_opt(link_id, buf, len, true)", write)
        self.assertIn("gps_dl_link_wait_on(&p->waitables[GPS_DL_WAIT_WRITE], &sigval)", write)
        self.assertIn("link_id, GPS_DL_RW_NO_TIMEOUT, false)", write)
        self.assertIn("#define GPS_DL_RW_NO_TIMEOUT (-1)", self.sources["lib/inc/gps_dl_time_tick.h"])
        self.assertIn("wait_event_interruptible(p->wq, p->fired)",
                      self.sources["link/gps_dl_link_sync.c"])

    def test_package_1008_is_the_existing_nonblocking_read_boundary(self):
        patch = (PACKAGE / READ_PATCH).read_bytes()
        self.assertEqual(hashlib.sha256(patch).hexdigest(), READ_PATCH_SHA)
        text = patch.decode()
        self.assertIn("+\tif (filp->f_flags & O_NONBLOCK)", text)
        self.assertIn("+\t\t\t&dev->i_buf[0], count, 0, NULL);", text)
        self.assertIn("+\t\t\tif (timeout_usec == 0)\n+\t\t\t\treturn -EAGAIN;", text)
        added = "\n".join(line[1:] for line in text.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        self.assertNotIn(".poll", added)
        self.assertNotIn("gps_each_device_write", added)
        package = (PACKAGE / "APKBUILD").read_text()
        self.assertIn(READ_PATCH, package)
        self.assertIn('< "$srcdir"/' + READ_PATCH, package)
        self.assertIn(hashlib.sha512(patch).hexdigest() + "  " + READ_PATCH, package)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_download_sequence_source.py PINNED_LIBMNL")
    LIB = Path(sys.argv[1])
    unittest.main(argv=[sys.argv[0]])
