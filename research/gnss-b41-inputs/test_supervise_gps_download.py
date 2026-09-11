import subprocess
import unittest
from unittest.mock import Mock, patch

from gps_lifecycle import ObservationError
from supervise_gps_download import run_reviewed_probe, supervise


class Tests(unittest.TestCase):
    def exercise(self, *, failed_phase=None, output=None, short=False, status=0):
        reader, process = Mock(), Mock()
        process.stdout.fileno.return_value = 9
        process.stdin.fileno.return_value = 10
        process.wait.return_value = status
        output = output if output is not None else b"DOWNLOAD_COMPLETE\nSTOP_WRITTEN\nCLOSED\n"
        pending = list(bytes([x]) for x in output) + [b""]
        history = []

        def phase(value, timeout):
            self.assertTrue(0 < timeout <= 8)
            history.append(value)
            if value == failed_phase:
                raise ObservationError("bad state")

        def write(fd, token):
            self.assertEqual(fd, 10)
            history.append(token)
            return 1 if short else len(token)

        reader.wait_for_phase.side_effect = phase
        reader.lifecycle.arm_stop.side_effect = lambda: history.append("armed")
        with patch("supervise_gps_download.os.read", side_effect=pending), \
             patch("supervise_gps_download.os.write", side_effect=write), \
             patch("supervise_gps_download.select.select", return_value=([9], [], [])):
            try:
                supervise(reader, process)
                error = None
            except ObservationError as caught:
                error = caught
        return history, error

    def test_success_order(self):
        history, error = self.exercise()
        self.assertIsNone(error)
        self.assertEqual(history, [3, "armed", b"W\n", 4, b"R\n", 5])

    def test_bad_readiness_never_sends_stop(self):
        history, error = self.exercise(failed_phase=3)
        self.assertIsNotNone(error)
        self.assertEqual(history, [3])

    def test_bad_reset_never_authorizes_close(self):
        history, error = self.exercise(failed_phase=4)
        self.assertIsNotNone(error)
        self.assertNotIn(b"R\n", history)

    def test_bad_close_is_failure(self):
        self.assertIsNotNone(self.exercise(failed_phase=5)[1])

    def test_child_failure(self):
        self.assertIsNotNone(self.exercise(status=1)[1])

    def test_bad_protocol(self):
        for value in (b"", b"STOP_WRITTEN\n", b"x" * 65, b"DOWNLOAD_COMPLETE\n"):
            with self.subTest(value=value):
                self.assertIsNotNone(self.exercise(output=value)[1])

    def test_short_token(self):
        history, error = self.exercise(short=True)
        self.assertIsNotNone(error)
        self.assertEqual(history, [3, "armed", b"W\n"])

    def test_cleanup_after_observer_failure(self):
        reader, process = Mock(), Mock()
        process.poll.return_value = None
        with patch("supervise_gps_download.KernelReader", return_value=reader), \
             patch("supervise_gps_download.subprocess.Popen", return_value=process) as start, \
             patch("supervise_gps_download.supervise", side_effect=ObservationError("failure")):
            with self.assertRaises(ObservationError):
                run_reviewed_probe("/reviewed/probe", "/reviewed/template")
        self.assertEqual(start.call_args.args[0], [
            "/reviewed/probe", "--experimental-supervised-download", "/reviewed/template"])
        process.terminate.assert_called_once()
        process.kill.assert_not_called()
        reader.close.assert_called_once()
        process.stdin.close.assert_called_once()
        process.stdout.close.assert_called_once()

    def test_stuck_child_requires_recovery(self):
        reader, process = Mock(), Mock()
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired("probe", 1)
        with patch("supervise_gps_download.KernelReader", return_value=reader), \
             patch("supervise_gps_download.subprocess.Popen", return_value=process), \
             patch("supervise_gps_download.supervise", side_effect=ObservationError("failure")):
            with self.assertRaisesRegex(ObservationError, "stuck in kernel"):
                run_reviewed_probe("/reviewed/probe", "/reviewed/template")
        process.kill.assert_called_once()
        reader.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
