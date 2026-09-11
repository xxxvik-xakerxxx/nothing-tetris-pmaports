import unittest
import errno
import os
from unittest.mock import patch
from gps_lifecycle import KernelReader, Lifecycle, ObservationError


def record(sequence, transition, *, link=0, priority=6, level="I", flags="-", timestamp=None):
    old, event, new = transition
    text = (f"GDL-{link}[{level}:4] [gps_dsp_fsm:347]: gps_dsp_fsm: "
            f"old_st={old:4}, evt={event:8}, new_st={new:4}")
    return f"{priority},{sequence},{sequence if timestamp is None else timestamp},{flags};{text}\n".encode()


class Tests(unittest.TestCase):
    def working(self):
        state = Lifecycle()
        for index, transition in enumerate(state.transitions[:3]):
            state.feed(record(index, transition))
        self.assertTrue(state.working)
        return state

    def test_full_order(self):
        state = self.working()
        state.arm_stop()
        self.assertFalse(state.working)
        state.feed(record(3, state.transitions[3]))
        self.assertTrue(state.reset_after_stop)
        state.feed(record(4, state.transitions[4]))
        self.assertEqual(state.phase, 5)

    def test_stale_ready_cannot_start_session(self):
        with self.assertRaises(ObservationError):
            Lifecycle().feed(record(9, Lifecycle.transitions[2]))

    def test_rom_reset_not_ready(self):
        state = Lifecycle()
        for index, transition in enumerate(state.transitions[:2]):
            state.feed(record(index, transition))
        self.assertFalse(state.working)
        with self.assertRaises(ObservationError):
            state.arm_stop()

    def test_reset_before_stop(self):
        state = self.working()
        with self.assertRaises(ObservationError):
            state.feed(record(3, state.transitions[3]))

    def test_missing_reset_before_close(self):
        state = self.working()
        state.arm_stop()
        with self.assertRaises(ObservationError):
            state.feed(record(3, state.transitions[4]))

    def test_sequence_and_time(self):
        for sequence, timestamp in ((2, 3), (0, 3), (1, 0)):
            with self.subTest(sequence=sequence, timestamp=timestamp):
                state = Lifecycle()
                state.feed(record(0, state.transitions[0], timestamp=1))
                with self.assertRaises(ObservationError):
                    state.feed(record(sequence, state.transitions[1], timestamp=timestamp))

    def test_other_link_or_userspace_cannot_advance(self):
        for options in ({"link": 1}, {"priority": 14}):
            state = Lifecycle()
            for index, transition in enumerate(state.transitions):
                state.feed(record(index, transition, **options))
            self.assertEqual(state.phase, 0)

    def test_warning_split_and_unknown(self):
        for options in ({"level": "W"}, {"level": "E"}, {"flags": "c"}):
            with self.assertRaises(ObservationError):
                Lifecycle().feed(record(0, Lifecycle.transitions[0], **options))
        with self.assertRaises(ObservationError):
            Lifecycle().feed(record(0, ("OFF", "FAKE", "ON")))

    def test_failure_is_sticky(self):
        state = Lifecycle()
        with self.assertRaises(ObservationError):
            state.feed(b"invalid")
        with self.assertRaises(ObservationError):
            state.feed(record(0, state.transitions[0]))

    def test_periodic_history_during_download(self):
        state = Lifecycle()
        state.feed(record(0, state.transitions[0]))
        state.feed(record(1, state.transitions[1]))
        history = b"GDL-0[W:2] [gps_dl_hist_rec_rw_do_dump:50]: rd: dp=0, pid=6066, i=0, n=8(1), l=20 12 12 12; 12 12 12 12"
        state.feed(b"5,2,2,-;" + history)
        self.assertEqual(state.phase, 2)
        state.feed(record(3, state.transitions[2]))
        self.assertTrue(state.working)

    def test_history_overflow_is_not_allowed(self):
        state = self.working()
        history = b"5,3,3,-;GDL-0[W:2] [gps_dl_hist_rec_rw_do_dump:50]: rd: dp=0, pid=6066, i=0, n=9(1), l=20 12 12 12; 12 12 12 12"
        with self.assertRaises(ObservationError):
            state.feed(history)

    def test_global_forced_off_is_fatal(self):
        state = self.working()
        with self.assertRaises(ObservationError):
            state.feed(b"4,3,3,-;GDL[W:0] [power:123]: force adie off")

    def test_routine_warning_is_phase_scoped(self):
        text = b"GDL-0[W:0] [gps_each_device_open:159]: major = 503, minor = 0, pid = 123"
        state = Lifecycle()
        state.feed(b"5,0,0,-;" + text)
        self.assertEqual(state.phase, 0)
        state.feed(record(1, state.transitions[0]))
        with self.assertRaises(ObservationError):
            state.feed(b"5,2,2,-;" + text)

    def test_open_failure_is_not_a_routine_warning(self):
        text = b"5,0,0,-;GDL-0[W:0] [gps_each_device_open:159]: major = 503, minor = 0, pid = 123, reopen fail"
        with self.assertRaises(ObservationError):
            Lifecycle().feed(text)

    def test_failed_dma_confirmation_is_not_routine(self):
        state = self.working()
        state.arm_stop()
        state.feed(record(3, state.transitions[3]))
        text = b"5,4,4,-;GDL-0[W:0] [gps_dl_hal_link_confirm_dma_stop:475]: conn_user = 0x1, old_dma_en = 1/1, tx = 1/FAIL, rx = 0/OKAY"
        with self.assertRaises(ObservationError):
            state.feed(text)

    def test_extra_session_is_rejected(self):
        state = self.working()
        state.arm_stop()
        for i in (3, 4):
            state.feed(record(i, state.transitions[i]))
        with self.assertRaises(ObservationError):
            state.feed(record(5, state.transitions[0]))


class ReaderTests(unittest.TestCase):
    def reader(self):
        with patch("gps_lifecycle.os.open", return_value=77) as opened, \
             patch("gps_lifecycle.os.lseek", return_value=0) as seek:
            reader = KernelReader()
            opened.assert_called_once_with("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            seek.assert_called_once_with(77, 0, os.SEEK_END)
            return reader

    def test_constructor_cleanup(self):
        with patch("gps_lifecycle.os.open", return_value=77), \
             patch("gps_lifecycle.os.lseek", side_effect=OSError("seek")), \
             patch("gps_lifecycle.os.close") as close:
            with self.assertRaises(OSError):
                KernelReader()
            close.assert_called_once_with(77)

    def test_ready_requires_drained_log(self):
        reader = self.reader()
        records = [record(i, t) for i, t in enumerate(Lifecycle.transitions[:3])]
        with patch("gps_lifecycle.os.read", side_effect=records + [BlockingIOError()]) as read:
            reader.wait_for_phase(3, 1)
            self.assertEqual(read.call_count, 4)
        self.assertTrue(reader.lifecycle.working)

    def test_error_after_ready_is_not_hidden(self):
        reader = self.reader()
        records = [record(i, t) for i, t in enumerate(Lifecycle.transitions[:3])]
        records.append(record(3, Lifecycle.transitions[3], level="W"))
        with patch("gps_lifecycle.os.read", side_effect=records):
            with self.assertRaises(ObservationError):
                reader.wait_for_phase(3, 1)
        self.assertFalse(reader.lifecycle.working)

    def test_read_failure_or_truncation(self):
        for value in (OSError(errno.EPIPE, "overrun"), b"", b"x" * 8192):
            reader = self.reader()
            with patch("gps_lifecycle.os.read", side_effect=[value]):
                with self.assertRaises(ObservationError):
                    reader.wait_for_phase(3, 1)

    def test_timeout(self):
        reader = self.reader()
        with patch("gps_lifecycle.time.monotonic", side_effect=[0, 0, 0, 2]), \
             patch("gps_lifecycle.os.read", side_effect=BlockingIOError()), \
             patch("gps_lifecycle.select.select"):
            with self.assertRaises(ObservationError):
                reader.wait_for_phase(3, 1)

    def test_close_is_idempotent(self):
        reader = self.reader()
        with patch("gps_lifecycle.os.close") as close:
            reader.close()
            reader.close()
            close.assert_called_once_with(77)

    def test_invalid_bounds(self):
        reader = self.reader()
        for phase, timeout in ((0, 1), (3, 0), (3, 9)):
            with self.assertRaises(ValueError):
                reader.wait_for_phase(phase, timeout)


if __name__ == "__main__":
    unittest.main()
