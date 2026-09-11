import base64
import errno
import os
import unittest
from unittest.mock import Mock, patch

from capture_gps_kmsg import CaptureError, Records, capture


def record(seq, message=b"GDL-0[I:4] state", priority=6):
    return f"{priority},{seq},1234,-;".encode() + message + b"\n"


class Tests(unittest.TestCase):
    def test_raw_and_source_are_preserved(self):
        logs = Records()
        raw = record(10)
        logs.feed(raw, 9000000)
        item = logs.records[0]
        self.assertEqual(base64.b64decode(item["raw_base64"]), raw)
        self.assertEqual((item["source_us"], item["receipt_monotonic_ns"]), (1234, 9000000))

    def test_other_logs_count_for_continuity(self):
        logs = Records()
        logs.feed(record(1, b"unrelated"), 1)
        logs.feed(record(2, priority=14), 2)
        logs.feed(record(3), 3)
        self.assertEqual((logs.scanned, len(logs.records)), (3, 1))
        with self.assertRaises(CaptureError):
            logs.feed(record(5, b"unrelated"), 4)

    def test_duplicate_and_backward_sequence_fail(self):
        for sequence in (1, 2):
            logs = Records()
            logs.feed(record(2), 1)
            with self.assertRaises(CaptureError):
                logs.feed(record(sequence), 2)

    def test_limits_and_bad_headers(self):
        for raw in (b"", b"x" * 8192, b"bad", b"6,x,1,-;GDL-x", record(2**64),
                    record(1, priority=192)):
            with self.subTest(raw=raw[:30]), self.assertRaises(CaptureError):
                Records().feed(raw, 0)
        for logs, message in ((Records(max_records=0), b"GDL-test"),
                              (Records(max_scanned=0), b"other")):
            with self.assertRaises(CaptureError):
                logs.feed(record(1, message), 0)

    def test_duration_rejected_before_open(self):
        with patch("capture_gps_kmsg.os.open") as opened:
            for duration in (0, -1, 121, float("nan"), float("inf")):
                with self.assertRaises(ValueError):
                    capture(duration)
            opened.assert_not_called()

    def test_capture_ready_and_cleanup(self):
        ready = Mock()
        clock = iter((0, 0, 1, 2_000_000_000, 2_000_000_000))
        with patch("capture_gps_kmsg.os.open", return_value=7) as opened, \
             patch("capture_gps_kmsg.os.lseek") as seek, \
             patch("capture_gps_kmsg.os.read", return_value=record(1)), \
             patch("capture_gps_kmsg.os.close") as close, \
             patch("capture_gps_kmsg.time.monotonic_ns", side_effect=lambda: next(clock)):
            result = capture(1, ready)
        self.assertTrue(result["ok"])
        self.assertEqual(result["scanned"], 1)
        opened.assert_called_once_with("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        seek.assert_called_once_with(7, 0, os.SEEK_END)
        ready.assert_called_once()
        close.assert_called_once_with(7)

    def test_overrun_is_failure_and_retains_evidence(self):
        with patch("capture_gps_kmsg.os.open", return_value=7), \
             patch("capture_gps_kmsg.os.lseek"), \
             patch("capture_gps_kmsg.os.read", side_effect=[record(1), OSError(errno.EPIPE, "overrun")]), \
             patch("capture_gps_kmsg.os.close") as close, \
             patch("capture_gps_kmsg.time.monotonic_ns", return_value=0):
            result = capture(1)
        self.assertFalse(result["ok"])
        self.assertIn("overrun", result["error"])
        self.assertEqual(len(result["records"]), 1)
        close.assert_called_once()

    def test_seek_failure_never_announces_ready(self):
        ready = Mock()
        with patch("capture_gps_kmsg.os.open", return_value=7), \
             patch("capture_gps_kmsg.os.lseek", side_effect=OSError("seek failed")), \
             patch("capture_gps_kmsg.os.close") as close:
            result = capture(1, ready)
        self.assertFalse(result["ok"])
        ready.assert_not_called()
        close.assert_called_once()

    def test_quiet_capture_waits_only_until_deadline(self):
        clock = Mock(side_effect=(0, 0, 100000000, 1000000000, 1000000000))
        with patch("capture_gps_kmsg.os.open", return_value=7), \
             patch("capture_gps_kmsg.os.lseek"), \
             patch("capture_gps_kmsg.os.read", side_effect=BlockingIOError()), \
             patch("capture_gps_kmsg.os.close"), \
             patch("capture_gps_kmsg.time.monotonic_ns", clock), \
             patch("capture_gps_kmsg.select.select") as wait:
            result = capture(1)
        self.assertTrue(result["ok"])
        self.assertEqual(result["records"], [])
        wait.assert_called_once_with([7], [], [], 0.9)

    def test_close_error_does_not_hide_read_error(self):
        with patch("capture_gps_kmsg.os.open", return_value=7), \
             patch("capture_gps_kmsg.os.lseek"), \
             patch("capture_gps_kmsg.os.read", side_effect=OSError("read failed")), \
             patch("capture_gps_kmsg.os.close", side_effect=OSError("close failed")), \
             patch("capture_gps_kmsg.time.monotonic_ns", return_value=0):
            result = capture(1)
        self.assertFalse(result["ok"])
        self.assertIn("read failed", result["error"])
        self.assertIn("close failed", result["cleanup_error"])


if __name__ == "__main__":
    unittest.main()
