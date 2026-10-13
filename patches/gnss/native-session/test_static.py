#!/usr/bin/env python3
"""Pinned source and patch checks only. Never execute vendor/native instructions."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest

import generate as g

AUDIT = g.HERE.parents[1] / "gnss-navigation-audit"
sys.path.insert(0, str(AUDIT))
from test_b41_receiver_policy_source import PinnedImage, LIB_SHA


class SessionSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = g.baseline()
        cls.fixed = {path: g.transform(path, text) for path, text in cls.original.items()}
        cls.manifest = json.loads((g.HERE / "STAGING.json").read_text())
        cls.lib = PinnedImage(Path(os.environ.get("TETRIS_B41_LIBMNL",
            "/private/tmp/tetris-b41-providers-ci38048111345/vendor/lib64/mt6878/libmnl.so")).read_bytes(), LIB_SHA)

    def test_exact_pin_stack_and_patch(self):
        self.assertEqual(self.manifest["connectivity_commit"], g.PIN)
        self.assertEqual({path: hashlib.sha512(text.encode()).hexdigest()
                          for path, text in self.original.items()}, self.manifest["baseline_sha512"])
        self.assertEqual(hashlib.sha512(g.PATCH.read_bytes()).hexdigest(), self.manifest["patch_sha512"])
        self.assertEqual(g.generate(self.original), g.PATCH.read_text())
        for path, digest in self.manifest["frozen_api_sha256"].items():
            self.assertEqual(hashlib.sha256((g.HERE / path).read_bytes()).hexdigest(), digest)

    def test_patch_check_and_application_are_exact(self):
        with tempfile.TemporaryDirectory(prefix="session-apply-", dir=g.HERE) as directory:
            for path, text in self.original.items():
                if not text:
                    continue
                target = Path(directory) / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text)
            for check in (True, False):
                g.write.checked(["git", "apply", "--whitespace=error"] +
                                (["--check"] if check else []) + [str(g.PATCH)], directory)
            for path, expected in self.fixed.items():
                self.assertEqual((Path(directory) / path).read_text(), expected)

    def test_snapshot_only_real_open_device_and_locked_link_reads(self):
        body = g.write.function_span(self.fixed[g.DEVICE], "gps_each_device_session_snapshot").text(self.fixed[g.DEVICE])
        for evidence in ("READ_ONCE(dev->is_open)", "gps_dl_link_get(id)",
                         "READ_ONCE(link->session_id)", "READ_ONCE(link->state_for_user)",
                         "before = gps_dsp_state_snapshot(id)", "return -ENOTCONN;", "return -EAGAIN;"):
            self.assertIn(evidence, body)
        self.assertEqual(body.count("copy_to_user("), 1)
        self.assertLess(body.index("gps_each_link_spin_lock_take("), body.index("READ_ONCE(link->session_id)"))
        self.assertLess(body.index("READ_ONCE(link->state_for_user)"), body.index("gps_each_link_spin_lock_give("))
        for forbidden in ("copy_from_user", "gps_dsp_fsm(", "gps_dl_hw_", "power_ctrl", "reset(", "SMC", "cipher_key"):
            self.assertNotIn(forbidden, body)

    def test_reader_is_read_once_without_changing_old_fsm(self):
        old = self.original[g.FSM]
        new = self.fixed[g.FSM]
        restored = new.replace('#include <linux/compiler.h>\n', '', 1).replace(g.DSP_READER, '', 1)
        self.assertEqual(restored, old)
        self.assertIn("return READ_ONCE(g_gps_dsp_state[link_id]);", g.DSP_READER)

    def test_existing_ioctls_and_old_uapi_remain_unchanged(self):
        old, new = self.original[g.DEVICE], self.fixed[g.DEVICE]
        before = g.write.function_span(old, "gps_each_device_ioctl_inner").text(old)
        after = g.write.function_span(new, "gps_each_device_ioctl_inner").text(new)
        added = "\tcase GPSDL_V051_IOC_SESSION_SNAPSHOT:\n\t\treturn gps_each_device_session_snapshot(dev, arg);\n"
        self.assertEqual(after.replace(added, "", 1), before)
        self.assertIn("#define GPSDL_IOC_TRIGGER_ASSERT       12", old)
        self.assertNotRegex(old, r"#define GPSDL_IOC_\w+\s+31\b")
        self.assertNotIn("linux/inc/uapi/gpsdl_v051.h\n", g.PATCH.read_text())
        header = (g.HERE / "gpsdl_v051_session.h").read_text()
        fields = re.findall(r"gpsdl_session_u32 (\w+)(?:\[(\d+)\])?;", header)
        self.assertEqual(sum(int(count) if count else 1 for _, count in fields), 8)
        self.assertEqual(self.fixed[g.UAPI], header)

    def test_no_default_package_activation(self):
        apk = (g.write.PACKAGE / "APKBUILD").read_text()
        self.assertNotIn(g.PATCH.name, apk)
        self.assertIs(self.manifest["shipping_activation"], False)
        self.assertIs(self.manifest["firmware_writes_added_by_patch"], False)

    def test_plain_integer_legacy_abi_and_compat_entry_are_preserved(self):
        old, new = self.original[g.DEVICE], self.fixed[g.DEVICE]
        for name, value in (("CO_CLOCK_FLAG", 11), ("GPS_HW_SUSPEND", 18),
                            ("GPS_DSP_MVCD_FRAGEMENT_NO", 25),
                            ("GET_PLATFORM_CLOCK_FREQ", 30)):
            pattern = r"#define GPSDL_IOC_" + name + r"\s+" + str(value) + r"\b"
            self.assertRegex(old, pattern)
            self.assertRegex(new, pattern)
        alias = r"#define GPSDL_IOC_GPS_GET_DSP_BOOTUP_INFO\s+GPSDL_V051_IOC_GET_DSP_BOOTUP_INFO\b"
        self.assertRegex(old, alias)
        self.assertRegex(new, alias)
        patch = next(g.write.PACKAGE.glob("1003-*.patch.vendor")).read_text()
        self.assertRegex(patch, r"\+#define GPSDL_V051_IOC_GET_DSP_BOOTUP_INFO\s+23U\b")
        for name in ("gps_each_device_unlocked_ioctl", "gps_each_device_compat_ioctl"):
            self.assertEqual(g.write.function_span(old, name).text(old),
                             g.write.function_span(new, name).text(new))
        self.assertIn("gps_each_device_ioctl_inner(filp, cmd, arg, true)", new)
        self.assertRegex((g.HERE / "gpsdl_v051_session.h").read_text(),
                         r"#define GPSDL_V051_IOC_SESSION_SNAPSHOT\s+31U\b")

    def test_common_sources_do_not_make_v050_and_v051_backends_interchangeable(self):
        for platform in ("v050", "v051"):
            root = g.BASE + "plat/" + platform + "/"
            for directory in ("linux", "hal", "link"):
                self.assertEqual(g.write.source(root + directory).strip().rstrip("/"),
                                 "../../" + directory)
            kbuild = g.write.source(root + "Kbuild")
            self.assertIn("GPS_PLATFORM := " + platform, kbuild)
            self.assertIn("linux/gps_each_device.o", kbuild)
            self.assertIn("hal/gps_dsp_fsm.o", kbuild)
            config = g.write.source(root + "inc/gps_dl_config.h")
            self.assertIn("#define GPS_DL_GET_PLATFORM_CLOCK_FREQ (" +
                          ("1" if platform == "v051" else "0") + ")", config)
            if platform == "v051":
                self.assertIn("hw/gps_dl_hw_atf_mvcd.o", kbuild)
                self.assertIn("linux/gps_dl_linux_clock_mng.o", kbuild)
            else:
                self.assertNotIn("hw/gps_dl_hw_atf_mvcd.o", kbuild)
                self.assertNotIn("linux/gps_dl_linux_clock_mng.o", kbuild)
        source = g.write.source(g.BASE + "hw/gps_dl_hw_gps.c")
        body = g.write.function_span(source, "gps_dl_hw_gps_get_bootup_info").text(source)
        self.assertIn("return false;", body)

    def test_native_owner_retains_fd_and_actual_session_id(self):
        source = (g.HERE / "session.c").read_text()
        for evidence in ("GPSDL_V051_IOC_SESSION_SNAPSHOT", "result.session_id != owner->session_id",
                         "st.st_ino != owner->inode", "now >= owner->deadline_ns", "now < owner->last_ns",
                         "owner->latest.dsp_state == DSP_WORKING", "owner->stage = B41_SESSION_WORKING;"):
            self.assertIn(evidence, source)
        for forbidden in ("open(", "close(", "dup(", "CLOCK_REALTIME", "dmesg", "private_clock",
                          "ioctl(owner->fd, 12", "ioctl(owner->fd, 13", "ioctl(owner->fd, 19"):
            self.assertNotIn(forbidden, source)
        self.assertIn("if (owner->stage == B41_SESSION_FAILED) return owner->first_error;", source)

    def test_readonly_routes_cannot_emit_stop(self):
        source = (g.HERE / "session.c").read_text()
        readonly = source[:source.index("int b41_session_stop_begin(")]
        self.assertNotIn("write(", readonly)
        self.assertNotIn("18UL", readonly)
        cli = (g.HERE / "session-tool.c").read_text()
        default = cli[cli.index("if (!wait && !stop) {"):cli.index("} else {", cli.index("if (!wait && !stop) {"))]
        self.assertIn("b41_session_snapshot(", default)
        self.assertNotIn("stop_begin", default)
        self.assertIn("if (!status && stop) status = b41_session_stop_begin(&owner);", cli)

    def test_normal_stop_requires_actual_reset_before_one_hwstop(self):
        source = (g.HERE / "session.c").read_text()
        stop = source[source.index("int b41_session_stop_step("):]
        self.assertEqual(stop.count("18UL, 0UL"), 1)
        self.assertLess(stop.index("owner->latest.dsp_state != DSP_RESET_DONE"), stop.index("18UL, 0UL"))
        self.assertLess(stop.index("owner->stage = B41_SESSION_WAIT_HWSTOP;"), stop.index("18UL, 0UL"))
        self.assertIn("owner->latest.link_state == LINK_SUSPENDED && owner->latest.dsp_state == DSP_HW_STOP", stop)
        fsm = self.original[g.FSM]
        close = fsm.split("if (GPS_DSP_EVT_FUNC_OFF == evt)", 1)[1].split("if (GPS_DSP_EVT_CTRL_TIMER_EXPIRE", 1)[0]
        self.assertIn("GPS_DSP_ST_RESET_DONE == last_state", close)
        self.assertIn("GPS_DSP_ST_HW_STOP_MODE == last_state", close)
        self.assertNotIn("GPS_DSP_ST_WORKING == last_state", close)

    def test_exact_stop_opcode_payload_and_checksum_from_immutable_instructions(self):
        for address, size, expected in (
            (0x5328b0, 0x18, "e571c133471f77cb26ba3ebdc81897891e7a73d612fd1c308a8ee33822f6774b"),
            (0x50bbe4, 0x17c, "63f0b71128d0f944002c4658b55d13e10547e5446b226f9dbcdb753517a24251"),
            (0x50bd60, 0x1b8, "321ffe3035d7700bd041d6b2cb52177fd13d81497d990dfcd2bba56e29b3bc60"),
            (0x554ae8, 0xe8, "2f294f5b4bf0cf1d7fa0b4968ba8c1d1bfe553f83468f9cb98efeee26403f167"),
        ):
            self.assertEqual(hashlib.sha256(self.lib.read(address, size)).hexdigest(), expected)
        instructions = self.lib.instructions(0x5328b0, 0x18)
        self.assertEqual(instructions[0x5328b0], ("mov", "w0, #5"))
        self.assertEqual(instructions[0x5328b8], ("mov", "w2, #1"))
        self.assertEqual(instructions[0x5328bc], ("mov", "w3, #4"))
        words = self.lib.instructions(0x50bc98, 0x28)
        self.assertEqual(words[0x50bc9c], ("lsr", "w14, w13, #8"))
        sender = self.lib.instructions(0x50be54, 0x1c)
        self.assertEqual(sender[0x50be54], ("mov", "w1, #-0x200"))
        frame = bytes([0xaa, 0xf0, 6, 0, 5, 0xfe, 4, 0, 0x0d, 1, 0xaa, 0x0f])
        self.assertEqual(int.from_bytes(frame[8:10], "little"), sum(frame[2:8]))
        self.assertIn("0x05, 0xfe, 0x04, 0x00, 0x0d, 0x01", (g.HERE / "session.c").read_text())

    def test_kernel_normal_dpstop_chain_and_enum_values(self):
        link = g.write.source(g.write.LINK)
        events = g.write.source(g.BASE + "link/gps_dl_link_event_proc.c")
        self.assertIn("close_or_suspend_op == GDL_DPSTOP || close_or_suspend_op == GDL_CLKEXT", link)
        active = events.split("case GPS_DL_EVT_LINK_ENTER_DPSTOP:", 1)[1].split("case GPS_DL_EVT_LINK_DSP_ROM_READY_TIMEOUT", 1)[0]
        self.assertLess(active.index("gps_dl_hal_link_power_ctrl(link_id, GPS_DL_HAL_ENTER_DPSTOP)"),
                        active.index("gps_dsp_fsm(GPS_DSP_EVT_HW_STOP_REQ, link_id)"))
        self.assertIn("GPS_DSP_ST_RESET_DONE != dsp_state", active)
        self.assertIn("gps_dl_link_close_ack(link_id, true, true)", active)
        # Stock ignores the HAL return here. FSM STOP is not proof of physical
        # power acknowledgement; preserve that residual rather than certify it.
        self.assertIn("\n\t\tgps_dl_hal_link_power_ctrl(link_id, GPS_DL_HAL_ENTER_DPSTOP);", active)
        self.assertRegex(self.original[g.FSM_H], r"GPS_DSP_ST_WORKING,\s*/\* 3 \*/")
        self.assertRegex(self.original[g.FSM_H], r"GPS_DSP_ST_HW_STOP_MODE,\s*/\* 5 \*/")
        enum = g.write.read.declaration(g.write.source(g.BASE + "inc/gps_each_link.h"), "enum", "gps_each_link_state_enum")
        names = re.findall(r"^\s*(LINK_\w+)\s*[,}]", g.write.read.mask_c(enum), re.M)
        self.assertEqual(names[3], "LINK_OPENED")
        self.assertEqual(names[9], "LINK_SUSPENDED")

    def test_native_fixtures_remain_ci_only_and_have_no_device_access(self):
        runner = (g.HERE / "run.py").read_text()
        self.assertIn('os.environ.get("CI") == "true"', runner)
        self.assertIn('os.environ.get("GITHUB_ACTIONS") == "true"', runner)
        self.assertIn('"-fsanitize=address,undefined"', runner)
        self.assertIn('"-DSESSION_CLI_GUARD"', runner)
        fixture = (g.HERE / "test_session.c").read_text()
        for evidence in ("stop_calls == previous_stops + 1", "owner.stage == B41_SESSION_STOPPED",
                         "query_error = EFAULT", "actual.session_id++", "tick = 1000", "tick = 9",
                         "write_error = EINTR", "stop_error = EBUSY", "actual.abi_version++", "actual.link_id = 1"):
            self.assertIn(evidence, fixture)

    def test_navigation_start_counterexample_is_repeated_stop_not_start(self):
        for address, size, expected in (
            (0x530c80, 0x10, "75e48245e89bf2c76113e85fe7e691ee4f30d11f7785821512f18554e8be5a1f"),
            (0x4fa630, 0x40, "627fd6d7a6b9399967db9c0039914553f1d0db279b8c8951548a7600a5d29f2e"),
        ):
            self.assertEqual(hashlib.sha256(self.lib.read(address, size)).hexdigest(), expected)
        commands = self.lib.instructions(0x4fa630, 0x40)
        for call, value in ((0x4fa650, 0x4fa64c), (0x4fa664, 0x4fa660)):
            self.assertEqual(commands[value], ("mov", "w3, #4"))
            self.assertEqual(commands[call], ("bl", "#0x50bbe4"))

    def test_post_init_configuration_and_host_initialization_are_separate(self):
        for address, size, expected in (
            (0x52f334, 0x60, "b4544525b2e439a380935f75629314a262b1d7603b393a4320b0ea73d414adb9"),
            (0x5c6644, 0x78, "4accfa99597d4af5a736ba41e4888c2388a86ea2c1aaf94851413a7e59e4f27b"),
            (0x51e57c, 0x38, "d39148e3d665185b419c6ab269bfda852058262f0605e12a1087f87638132ce6"),
        ):
            self.assertEqual(hashlib.sha256(self.lib.read(address, size)).hexdigest(), expected)
        self.assertEqual(self.lib.read(0x9e20, 8), bytes.fromhex("0300000001000000"))
        config = self.lib.instructions(0x5c6644, 0x78)
        self.assertEqual(config[0x5c665c], ("mov", "w9, #0x32"))
        self.assertEqual(config[0x5c6690], ("bl", "#0x699c50"))
        initializer = self.lib.instructions(0x51e57c, 0x38)
        self.assertEqual(initializer[0x51e57c], ("mov", "w0, #0x1c"))
        self.assertEqual(initializer[0x51e584], ("mov", "w2, wzr"))
        self.assertEqual(initializer[0x51e5ac], ("mov", "w3, #0x29"))
        # These constants are real, but emitting them alone is not a proven
        # standalone INIT recipe. No native INIT sender is manufactured here.
        source = (g.HERE / "session.c").read_text()
        self.assertNotIn("0x1c, 0xfe", source)
        self.assertNotIn("0x29, 0x00", source)

    def test_output_requires_host_processing_not_raw_uart_position_cast(self):
        for address, size, expected in (
            (0x533674, 0x90, "5ba07e910aa23a0e59b4794a9daa8c621de4577f155608e0c989c55c9151dc4e"),
            (0x534c84, 0x10, "7450686f20f4aad8dab2168ae56b31939d2d7d3a76680b954fcda5ee34e2a395"),
            (0x50e2bc, 0x50, "04b5bae2c00463f6f7be0c4e6a5ad91f9f4d99120c940167b1001876eea1b93a"),
            (0x554d3c, 0x68, "68fd1a47165bbeef6b2431b743d140de32d028486a247c94d1a997f31d381929"),
        ):
            self.assertEqual(hashlib.sha256(self.lib.read(address, size)).hexdigest(), expected)
        output = self.lib.instructions(0x534c84, 0x10)
        self.assertEqual(output[0x534c88], ("cbz", "w0, #0x534ccc"))
        getter = self.lib.instructions(0x50e2bc, 0x50)
        self.assertEqual(getter[0x50e2f8], ("mov", "w2, #0xc60"))
        wire = self.lib.instructions(0x554d3c, 0x68)
        self.assertEqual(wire[0x554d8c], ("bl", "#0x509830"))

    def test_no_rtc_or_implicit_time_seed(self):
        source = (g.HERE / "session.c").read_text() + (g.HERE / "session-tool.c").read_text()
        for forbidden in ("CLOCK_REALTIME", "gettimeofday(", "time(NULL)", "clock_settime(",
                          "RTC_RD_TIME", "adjtimex(", "timedatectl", "NTP", "utc_seed_valid"):
            self.assertNotIn(forbidden, source)
        self.assertIn("CLOCK_MONOTONIC", source)


if __name__ == "__main__":
    unittest.main()
