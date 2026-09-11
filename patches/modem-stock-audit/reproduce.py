#!/usr/bin/env python3
"""Reproduce bounded static evidence; output stays beside this script."""
import argparse
import json
from pathlib import Path
import subprocess

from audit import payload, registry, static_tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="local stock B4.1 lk.img")
    parser.add_argument("--container", default="mt6878-probe-build")
    parser.add_argument("--container-image", default="/tmp/tetris-stock-b41-lk.img")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parent
    local = payload(args.image.read_bytes())
    # Pass only our Python analysis code, not vendor executable code. No
    # container files are created; both image copies are independently hashed.
    base_command = ["docker", "exec", args.container, "python3", "-c",
               (folder / "audit.py").read_text(), args.container_image]
    command = list(base_command)
    for name in ("platform_load_modem", "ccci_lk_tag_info_init", "ccci,modem_info_v2"):
        command += ["--xref", name]
    for address in ("0x19a530", "0x19a528"):
        command += ["--address", address]
    for address in ("0x25358", "0x27d9c", "0x25564", "0x280a0"):
        command += ["--calls-to", address]
    for address in ("0x199910", "0x199bf8", "0x280a0"):
        command += ["--pointers-to", address]
    for window in ("0x16c00:0x98", "0x1bb70:0x64", "0x25358:0x20c",
                   "0x25564:0x190", "0x27d9c:0xb8", "0x27e70:0x108",
                   "0x280a0:0xdc", "0x5aa68:0x88"):
        command += ["--window", window]
    def inspect(arguments):
        completed = subprocess.run(arguments, text=True, capture_output=True)
        if completed.returncode:
            raise SystemExit(completed.stderr)
        return json.loads(completed.stdout)

    result = inspect(command)
    extra = inspect(base_command + ["--xref", "modem_a", "--window", "0x7e14c:0xc8",
                                    "--window", "0x74da0:0x160"])
    result["modem_a"] = extra["modem_a"]
    result["windows"] += extra["windows"]
    result["registry"] = registry(local)
    result["static_tables"] = static_tables(local)
    output = folder / "evidence.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: both input hashes; {result['registry']['count']} registry entries; "
          f"{len(result['windows'])} bounded disassembly windows; {output}")


if __name__ == "__main__":
    main()
