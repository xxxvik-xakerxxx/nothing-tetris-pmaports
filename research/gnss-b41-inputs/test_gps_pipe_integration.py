"""Actual C probe/Python supervisor pipes; GPS syscalls and logs substituted."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from gps_lifecycle import Lifecycle, ObservationError
from supervise_gps_download import run_reviewed_probe


class RecordedReader:
    def __init__(self, fail=None):
        self.lifecycle = Lifecycle()
        self.fail = fail
        self.closed = False

    def wait_for_phase(self, phase, timeout):
        if phase == self.fail:
            self.lifecycle.reject("synthetic missing hardware transition")
        while self.lifecycle.phase < phase:
            index = self.lifecycle.phase
            old, event, new = self.lifecycle.transitions[index]
            message = (f"6,{index},{index},-;GDL-0[I:4] [gps_dsp_fsm:347]: "
                       f"gps_dsp_fsm: old_st={old:4}, evt={event:8}, new_st={new:4}\n")
            self.lifecycle.feed(message.encode())

    def close(self):
        self.closed = True


class PipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[2]
        cls.temp = tempfile.TemporaryDirectory(prefix="gps-pipe-test-")
        cls.binary = str(Path(cls.temp.name) / "probe-without-hardware")
        try:
            subprocess.run([
                os.environ.get("HOSTCC", "cc"), "-std=c11", "-O2", "-Wall",
                "-Wextra", "-Werror", "-DBINFO_PIPE_TEST",
                "-I" + os.environ.get("GPSDL_UAPI_INCLUDE", str(
                    root / "pmaports/device/testing/device-nothing-tetris")),
                str(Path(__file__).with_name("test-binfo-io.c")), "-o", cls.binary,
            ], check=True)
        except BaseException:
            cls.temp.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_case(self, fail=None, scenario="normal"):
        reader = RecordedReader(fail)
        children = []
        real_popen = subprocess.Popen

        def start(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        with patch("supervise_gps_download.KernelReader", return_value=reader), \
             patch("supervise_gps_download.subprocess.Popen", side_effect=start), \
             patch.dict(os.environ, {"BINFO_PIPE_SCENARIO": scenario}):
            try:
                run_reviewed_probe(self.binary, "template.bin")
                error = None
            except ObservationError as caught:
                error = caught
        self.assertTrue(reader.closed)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll(), "child must be reaped")
        self.assertTrue(children[0].stdin.closed and children[0].stdout.closed)
        return reader, error

    def test_full_exchange(self):
        reader, error = self.run_case()
        self.assertIsNone(error)
        self.assertEqual(reader.lifecycle.phase, 5)

    def test_no_readiness(self):
        reader, error = self.run_case(fail=3)
        self.assertIsNotNone(error)
        self.assertFalse(reader.lifecycle.stop_armed)

    def test_no_reset(self):
        reader, error = self.run_case(fail=4)
        self.assertIsNotNone(error)
        self.assertEqual(reader.lifecycle.phase, 3)

    def test_no_off(self):
        self.assertIsNotNone(self.run_case(fail=5)[1])

    def test_short_device_stop_write(self):
        reader, error = self.run_case(scenario="short-stop")
        self.assertIsNotNone(error)
        self.assertEqual(reader.lifecycle.phase, 3)


if __name__ == "__main__":
    unittest.main()
