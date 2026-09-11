#!/usr/bin/env python3
"""Short host C test only. No target build, device or vendor execution."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

folder = Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix="scp-agent-modem-host-") as tmp:
    executable = Path(tmp) / "test"
    subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
        "-std=c11", "-Wall", "-Wextra", "-Werror", "-O1",
        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
        str(folder / "modem_image.c"), str(folder / "test_modem_image.c"),
        "-o", str(executable)], check=True)
    subprocess.run([str(executable)], check=True)
