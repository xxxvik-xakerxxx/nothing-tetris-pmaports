#!/usr/bin/env python3
"""No device I/O: pinned-source checks and real observer with a ring model.

The ring model covers sequential non-cont printk records only. It is NOT an
execution of Linux atomics, interrupt wakeups, console code or a running kernel.
"""
import collections
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
VENDOR = ROOT / "upstream/android_kernel_modules_nothing_mt6878"
PIN = "e96f60dc081ae3525ef43d4bcf0ee5ee97e53835"
FSM = "connectivity/gps/data_link/hal/gps_dsp_fsm.c"
KERNEL = ROOT / "upstream/linux-d84b264a54a37611f2f46bc19363cb9b41606205/kernel/printk"
OBSERVER = ROOT / "worktrees/gnss-userspace-bridge/research/gnss-b41-inputs/gps_lifecycle.py"
OBSERVER_SHA = "52d18c1e7751c247da07d1252de55d10bc099df86bd9ebb466bc817a111c908e"


def source(path):
    return subprocess.check_output(["git", "-C", str(VENDOR), "show", f"{PIN}:{path}"], text=True)


def observer():
    data = OBSERVER.read_bytes()
    if hashlib.sha256(data).hexdigest() != OBSERVER_SHA:
        raise ValueError("observer changed; re-audit before updating pin")
    module = types.ModuleType("pinned_gps_lifecycle")
    exec(compile(data, str(OBSERVER), "exec"), module.__dict__)
    return module


def check_hunk_position(original, diff):
    """Reject relocation independently of BSD/GNU patch diagnostics."""
    lines = diff.splitlines()
    hunks = [i for i, line in enumerate(lines) if line.startswith("@@ ")]
    if len(hunks) != 1:
        raise AssertionError("expected exactly one FSM hunk")
    index = hunks[0]
    match = re.fullmatch(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@.*", lines[index])
    if not match:
        raise AssertionError("invalid hunk header")
    old_start, old_count, new_start, new_count = map(int, match.groups())
    body = lines[index + 1:]
    before = [line[1:] for line in body if line.startswith((" ", "-"))]
    after = [line[1:] for line in body if line.startswith((" ", "+"))]
    if (old_count != len(before) or new_count != len(after) or
            old_start != new_start or old_start < 1 or
            original.splitlines()[old_start - 1:old_start - 1 + old_count] != before):
        raise AssertionError("hunk requires offset or has incorrect counts")


def check_patch_diagnostics(stdout, stderr):
    diagnostics = stdout + "\n" + stderr
    if re.search(r"offset|fuzz", diagnostics, re.IGNORECASE):
        raise AssertionError(diagnostics)


class Ring:
    """Model the three Descriptor Finalization rules in printk_ringbuffer.c."""
    def __init__(self):
        self.ready = collections.deque()
        self.pending = None
        self.seq = 0
        self.now = 0.0

    def printk(self, message, priority=6):
        if self.pending is not None:
            self.ready.append(self.pending)  # New reservation finalizes predecessor.
            self.pending = None
        record = (f"{priority},{self.seq},{int(self.now * 1000000)},-;".encode()
                  + message.rstrip("\n").encode() + b"\n")
        self.seq += 1
        if message.endswith("\n"):
            self.ready.append(record)
        else:
            self.pending = record

    def read(self, fd, size):
        if not self.ready:
            raise BlockingIOError()
        return self.ready.popleft()

    def select(self, reads, writes, errors, timeout):
        self.now += timeout
        return [], [], []


class FinalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = observer()
        cls.original = source(FSM)
        cls.diff = (HERE / "0001-gps-finalize-fsm-log-records.patch").read_text()
        check_hunk_position(cls.original, cls.diff)
        with tempfile.TemporaryDirectory(prefix="camera-agent-fsm-", dir="/tmp") as temp:
            dest = Path(temp) / FSM
            dest.parent.mkdir(parents=True)
            dest.write_text(cls.original)
            result = subprocess.run(
                ["patch", "--batch", "--fuzz=0", "-p1", "-i",
                 str(HERE / "0001-gps-finalize-fsm-log-records.patch")],
                cwd=temp, text=True, capture_output=True, check=True,
                env={**os.environ, "LC_ALL": "C"},
            )
            check_patch_diagnostics(result.stdout, result.stderr)
            cls.fixed = dest.read_text()

    def test_original_wrong_header_rejected_without_patch_warning(self):
        wrong = self.diff.replace("@@ -340,12 +340,12 @@", "@@ -339,12 +339,12 @@")
        self.assertNotEqual(wrong, self.diff)
        with self.assertRaisesRegex(AssertionError, "offset"):
            check_hunk_position(self.original, wrong)

    def test_offset_and_fuzz_diagnostics_rejected_on_both_streams(self):
        for message in ("Hunk #1 succeeded at 340 (offset 1 line).",
                        "Hunk #1 succeeded with fuzz 1.", "OFFSET 1"):
            for stdout, stderr in ((message, ""), ("", message)):
                with self.subTest(stdout=stdout, stderr=stderr):
                    with self.assertRaises(AssertionError):
                        check_patch_diagnostics(stdout, stderr)

    def test_patch_only_adds_two_newlines(self):
        old = self.original.splitlines()
        new = self.fixed.splitlines()
        self.assertEqual(len(old), len(new))
        changes = [(a, b) for a, b in zip(old, new) if a != b]
        self.assertEqual(len(changes), 2)
        for a, b in changes:
            self.assertIn("GDL_LOGX", a)
            self.assertIn("gps_dsp_fsm:", a)
            self.assertEqual(b, a.replace('\",', '\\n\",'))

    def test_linux_source_contract(self):
        printk = (KERNEL / "printk.c").read_text()
        ring = (KERNEL / "printk_ringbuffer.c").read_text()
        self.assertEqual(hashlib.sha256(printk.encode()).hexdigest(),
                         "d60698367c6548c4734c0862de22b583f5474add040a654815d89ada649a5ab1")
        self.assertEqual(hashlib.sha256(ring.encode()).hexdigest(),
                         "96840b39053bd9b4c7f0349528dd63a5ad8864a19e35671cf52bb8b474b66814")
        self.assertIn("text[text_len - 1] == '\\n'", printk)
        self.assertRegex(printk, r"if \(!\(flags & LOG_NEWLINE\)\)\s+prb_commit\(&e\);\s+else\s+prb_final_commit\(&e\);")
        self.assertIn("data is not yet available to readers until it is finalized", ring)
        self.assertIn("that previous record is automatically", ring)
        self.assertIn("desc_read_finalized_seq(desc_ring, id, seq", ring)
        self.assertIn("d_state == desc_committed ||", ring)
        self.assertIn("_prb_commit(e, desc_committed);", ring)
        self.assertIn("if (head_id != e->id)", ring)
        self.assertIn("_prb_commit(e, desc_finalized);", ring)
        self.assertIn("ret = -EAGAIN;", printk[printk.index("static ssize_t devkmsg_read"):])

    def fixture(self, phase, fixed):
        ring = Ring()
        reader = self.mod.KernelReader.__new__(self.mod.KernelReader)
        reader.fd = 123  # Never opened or used for a real syscall.
        reader.lifecycle = self.mod.Lifecycle()
        reader.lifecycle.phase = phase - 1
        reader.lifecycle.stop_armed = phase == 4
        fmt = re.search(r'GDL_LOGXI_STA\(link_id, "([^"]+)"', self.fixed if fixed else self.original)[1]
        fmt = fmt.replace(r"\n", "\n")
        body = fmt % reader.lifecycle.transitions[phase - 1]
        ring.printk("GDL-0[I:4] [gps_dsp_fsm:347]: " + body)
        return ring, reader

    def wait(self, ring, reader, phase):
        with patch.object(self.mod.os, "read", ring.read), \
             patch.object(self.mod.select, "select", ring.select), \
             patch.object(self.mod.time, "monotonic", lambda: ring.now):
            reader.wait_for_phase(phase, 8)

    def test_original_quiet_ring_times_out_after_hardware_transition(self):
        ring, reader = self.fixture(4, False)
        with self.assertRaisesRegex(self.mod.ObservationError, "timed out"):
            self.wait(ring, reader, 4)
        self.assertEqual(ring.now, 8)
        self.assertEqual(reader.lifecycle.phase, 3)
        self.assertIsNotNone(ring.pending)

    def test_original_unrelated_printk_releases_old_source_timestamp(self):
        ring, reader = self.fixture(4, False)
        ring.now = 6.6
        ring.printk("unrelated kernel activity\n")
        self.assertEqual(ring.ready[0].split(b";", 1)[0], b"6,0,0,-")
        self.wait(ring, reader, 4)
        self.assertTrue(reader.lifecycle.reset_after_stop)
        self.assertEqual(reader.lifecycle.timestamp, 6600000)
        self.assertEqual(ring.now, 6.6)

    def test_fixed_all_waited_phases_visible_without_next_printk(self):
        for phase in (3, 4, 5):
            with self.subTest(phase=phase):
                ring, reader = self.fixture(phase, True)
                self.wait(ring, reader, phase)
                self.assertEqual(reader.lifecycle.phase, phase)
                self.assertEqual(ring.now, 0)
                self.assertIsNone(ring.pending)

    def test_fixed_does_not_allow_unarmed_reset(self):
        ring, reader = self.fixture(4, True)
        reader.lifecycle.stop_armed = False
        with self.assertRaisesRegex(self.mod.ObservationError, "before the controlled stop"):
            self.wait(ring, reader, 4)

    def test_fixed_abnormal_remains_error(self):
        ring, reader = self.fixture(4, True)
        ring.ready.clear()
        ring.seq = 0
        fmt = re.search(r'GDL_LOGXW_STA\(link_id, "(gps_dsp_fsm:[^"]+)"', self.fixed)[1]
        ring.printk("GDL-0[W:4] [gps_dsp_fsm:343]: " +
                    fmt.replace(r"\n", "\n") % ("WORK", "HW_STOP", "STOP", 1), 5)
        with self.assertRaisesRegex(self.mod.ObservationError, "warning or error"):
            self.wait(ring, reader, 4)


if __name__ == "__main__":
    unittest.main()
