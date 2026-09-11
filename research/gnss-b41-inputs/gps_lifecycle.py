"""Read-only observation for one fresh, externally controlled GNSS session.

Open before the sole owner opens gpsdl0. This is a diagnostic log contract,
not a stable driver API or proof that the radio has obtained a position.
"""
import os
import re
import select
import time


class ObservationError(RuntimeError):
    pass


class Lifecycle:
    transitions = (
        ("OFF", "FUNC_ON", "ON"),
        ("ON", "RST_DONE", "RST"),
        ("RST", "RAM_OKAY", "WORK"),
        ("WORK", "RST_DONE", "RST"),
        ("RST", "FUNC_OFF", "OFF"),
    )
    pattern = re.compile(
        r"GDL-0\[I:4\] \[gps_dsp_fsm:[0-9]+\]: gps_dsp_fsm: "
        r"old_st=([A-Z_]+) *, evt=([A-Z_]+) *, new_st=([A-Z_]+) *"
    )
    # The vendor logs these normal lifecycle operations at warning level.
    routine_warnings = (
        (0, 0, "gps_each_device_open", r"major = [0-9]+, minor = 0, pid = [0-9]+"),
        (0, 1, "gps_dl_hal_link_power_ctrl",
         r"op = 1, conn_okay = 1/1/0x0, gps_common = 0, L1 = 0, L5 = 0, cfg = 1/0x[0-9a-f]+"),
        (2, 1, "gps_dl_link_open_ack", "user still online, try to change to opened"),
        (4, 0, "gps_each_device_release", r"major = [0-9]+, minor = 0, pid = [0-9]+"),
        (4, 0, "gps_dl_hal_link_confirm_dma_stop",
         r"conn_user = 0x1, old_dma_en = 1/1, tx = 0/OKAY, rx = 0/OKAY"),
        (4, 1, "gps_dl_hal_link_power_ctrl",
         r"op = 0, conn_okay = 1/1/0x0, gps_common = 1, L1 = 1, L5 = 0, cfg = 0/0x[0-9a-f]+"),
    )
    history_pattern = re.compile(
        r"GDL-0\[W:2\] \[gps_dl_hist_rec_rw_do_dump:[0-9]+\]: "
        r"(?:rd|wr): dp=[0-9]+, pid=[0-9]+, i=[0-9]+, n=[0-8]\([0-9]+\), "
        r"l=[0-9]+ [0-9]+ [0-9]+ [0-9]+; [0-9]+ [0-9]+ [0-9]+ [0-9]+"
    )

    def __init__(self):
        self.sequence = None
        self.timestamp = None
        self.phase = 0
        self.stop_armed = False
        self.failed = False

    @property
    def working(self):
        return not self.failed and self.phase == 3 and not self.stop_armed

    @property
    def reset_after_stop(self):
        return not self.failed and self.phase == 4

    def reject(self, reason):
        self.failed = True
        raise ObservationError(reason)

    def arm_stop(self):
        if not self.working:
            self.reject("stop requires a fresh observed WORKING state")
        self.stop_armed = True

    def feed(self, record):
        if self.failed:
            raise ObservationError("observation already invalid")
        try:
            header, message = record.split(b";", 1)
            fields = header.split(b",")
            if len(fields) != 4 or not all(x.isdigit() for x in fields[:3]):
                raise ValueError("invalid header")
            priority, sequence, timestamp = map(int, fields[:3])
            if priority > 191 or sequence >= 2**64 or timestamp >= 2**64:
                raise ValueError("out of range")
            message = message.split(b"\n", 1)[0].decode("ascii")
        except (ValueError, UnicodeDecodeError):
            self.reject("malformed kernel record")
        if self.sequence is not None and sequence != self.sequence + 1:
            self.reject("lost, duplicated or reordered kernel records")
        if self.timestamp is not None and timestamp < self.timestamp:
            self.reject("kernel timestamp moved backwards")
        self.sequence, self.timestamp = sequence, timestamp
        if priority >> 3:
            return  # User-facility messages are not driver evidence.
        if any(text in message for text in (
            "force adie off", "trigger connsys reset", "Kernel panic", "Oops:", "BUG:",
        )):
            self.reject("kernel fault or forced connectivity recovery")
        if not message.startswith("GDL-0["):
            return
        if fields[3] != b"-":
            self.reject("split GNSS record cannot establish a transition")
        if 2 <= self.phase <= 5 and self.history_pattern.fullmatch(message):
            return
        for phase, module, function, body in self.routine_warnings:
            if self.phase == phase and re.fullmatch(
                rf"GDL-0\[W:{module}\] \[{function}:[0-9]+\]: {body}", message
            ):
                return
        if message.startswith(("GDL-0[E:", "GDL-0[W:")):
            self.reject("primary GNSS warning or error")
        if "gps_dsp_fsm" not in message:
            return
        match = self.pattern.fullmatch(message)
        if not match or self.phase >= len(self.transitions):
            self.reject("unexpected GNSS state record")
        if match.groups() != self.transitions[self.phase]:
            self.reject("unexpected GNSS lifecycle transition")
        if self.phase == 3 and not self.stop_armed:
            self.reject("DSP reset before the controlled stop request")
        self.phase += 1


class KernelReader:
    """Independent kmsg cursor at the current end; no clear or log writes."""

    def __init__(self):
        self.fd = os.open("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            os.lseek(self.fd, 0, os.SEEK_END)
        except BaseException:
            os.close(self.fd)
            raise
        self.lifecycle = Lifecycle()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def wait_for_phase(self, phase, timeout):
        if phase not in (3, 4, 5) or not 0 < timeout <= 8:
            raise ValueError("invalid observation bound")
        deadline = time.monotonic() + timeout
        count = 0
        while time.monotonic() < deadline:
            try:
                record = os.read(self.fd, 8192)
            except BlockingIOError:
                if self.lifecycle.phase == phase:
                    return
                select.select([self.fd], [], [], max(0, deadline - time.monotonic()))
                continue
            except OSError:
                self.lifecycle.reject("kernel log read failed or overran")
            if not record or len(record) == 8192 or count >= 4096:
                self.lifecycle.reject("kernel observation budget exceeded")
            self.lifecycle.feed(record)
            count += 1
        self.lifecycle.reject("GNSS lifecycle observation timed out")
