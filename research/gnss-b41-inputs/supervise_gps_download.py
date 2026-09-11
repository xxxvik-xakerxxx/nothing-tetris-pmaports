"""Uninstalled experimental supervisor; no CLI or automatic device startup."""
import os
import select
import subprocess
import time

from gps_lifecycle import KernelReader, ObservationError


def supervise(reader, process, timeout=8):
    """Observe one child; caller owns failure cleanup and post-test USB checks."""
    if not 0 < timeout <= 8:
        raise ValueError("invalid total deadline")
    deadline = time.monotonic() + timeout

    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise ObservationError("supervised download deadline expired")
        return value

    def expect(line):
        output = bytearray()
        while not output.endswith(b"\n"):
            fd = process.stdout.fileno()
            ready, _, _ = select.select([fd], [], [], remaining())
            if not ready:
                raise ObservationError("probe event timed out")
            byte = os.read(fd, 1)
            if not byte or len(output) >= 64:
                raise ObservationError("probe event missing or oversized")
            output.extend(byte)
        if output != line:
            raise ObservationError("unexpected probe event")

    def allow(token):
        remaining()
        if os.write(process.stdin.fileno(), token) != len(token):
            raise ObservationError("short supervisor token write")

    expect(b"DOWNLOAD_COMPLETE\n")
    reader.wait_for_phase(3, remaining())
    reader.lifecycle.arm_stop()
    allow(b"W\n")
    expect(b"STOP_WRITTEN\n")
    reader.wait_for_phase(4, remaining())
    allow(b"R\n")
    expect(b"CLOSED\n")
    reader.wait_for_phase(5, remaining())
    if process.wait(timeout=remaining()) != 0:
        raise ObservationError("probe failed after closing")
    if os.read(process.stdout.fileno(), 1):
        raise ObservationError("unexpected trailing probe output")


def run_reviewed_probe(executable, template):
    """Caller must validate hashes/profile, sole ownership and reboot recovery.

    This function opens a GPS device through its child. It is deliberately
    not called at import time and is not a service or a command-line entry.
    """
    reader = KernelReader()
    process = None
    try:
        process = subprocess.Popen(
            [executable, "--experimental-supervised-download", template],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0,
        )
        supervise(reader, process)
    except BaseException:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired as error:
                    raise ObservationError(
                        "probe stuck in kernel; recover phone, do not reload module"
                    ) from error
        raise
    finally:
        if process is not None:
            process.stdin.close()
            process.stdout.close()
        reader.close()
