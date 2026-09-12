#!/usr/bin/env python3
import importlib.util
import errno
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from unittest.mock import Mock

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "measurement", Path(__file__).resolve().parents[1] / "scripts/measure-drm-sequence.py")
measurement = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measurement)
dpms_spec = importlib.util.spec_from_file_location(
    "dpms", Path(__file__).resolve().parents[1] / "scripts/check-live-display-dpms.py")
dpms = importlib.util.module_from_spec(dpms_spec)
dpms_spec.loader.exec_module(dpms)


class SequenceTests(unittest.TestCase):
    def test_modes(self):
        for hz in (60, 120):
            result = measurement.summarize((1, 10), (1_000_000_001, 10 + hz), hz)
            self.assertEqual(result["sequence_hz"], hz)

    def test_event(self):
        data = measurement.EVENT.pack(3, 32, 1, 100, 42)
        self.assertEqual(measurement.decode_event(data, 1), (100, 42))
        for invalid in (data[:-1], data + b"x",
                        measurement.EVENT.pack(2, 32, 1, 100, 42),
                        measurement.EVENT.pack(3, 31, 1, 100, 42),
                        measurement.EVENT.pack(3, 32, 2, 100, 42),
                        measurement.EVENT.pack(3, 32, 1, 0, 42)):
            with self.assertRaises(ValueError):
                measurement.decode_event(invalid, 1)

    def test_discontinuities(self):
        for last in ((99, 130), (100, 130), (200, 129), (200, 5)):
            with self.assertRaises(ValueError):
                measurement.summarize((100, 10), last, 120)

    def test_timeout(self):
        with patch.object(measurement.select, "select", return_value=([], [], [])):
            with self.assertRaises(TimeoutError):
                measurement.receive(5, 1, measurement.time.monotonic() + 1)

    def test_first_error_closes_without_retry(self):
        with patch.object(measurement.os, "open", return_value=5), \
             patch.object(measurement.os, "close") as close, \
             patch.object(measurement, "queue", side_effect=OSError("EINVAL")) as queue:
            with self.assertRaises(OSError):
                measurement.measure("fixture", 59, 120, 5)
            self.assertEqual(queue.call_count, 1)
            close.assert_called_once_with(5)


class TransitionTests(unittest.TestCase):
    def test_einval_is_observed_not_other_errors(self):
        with patch.object(dpms.fcntl, "ioctl", side_effect=OSError(errno.EINVAL, "inactive")):
            self.assertIsNone(dpms.get_sequence(5, 59))
        with patch.object(dpms.fcntl, "ioctl", side_effect=OSError(errno.EIO, "fault")):
            with self.assertRaises(OSError):
                dpms.get_sequence(5, 59)

    def test_on_waits_for_vblank_not_only_connector(self):
        connector = Mock()
        connector.read_text.return_value = "enabled\n"
        with patch.object(dpms, "get_sequence", side_effect=[None, {"active": True}]), \
             patch.object(dpms.time, "sleep"):
            result = dpms.wait_transition(5, 59, connector, True, 3)
        self.assertEqual(result["samples"], 2)
        self.assertEqual(result["get_sequence_einval"], 1)

    def test_off_requires_disabled_connector(self):
        connector = Mock()
        connector.read_text.side_effect = ["enabled", "disabled"]
        with patch.object(dpms, "get_sequence", return_value=None), \
             patch.object(dpms.time, "sleep"):
            result = dpms.wait_transition(5, 59, connector, False, 3)
        self.assertEqual(result["samples"], 2)

    def test_never_ready_is_failure(self):
        connector = Mock()
        connector.read_text.return_value = "enabled"
        with patch.object(dpms, "get_sequence", return_value=None):
            with self.assertRaises(TimeoutError):
                dpms.wait_transition(5, 59, connector, True, 0)


if __name__ == "__main__":
    unittest.main()
