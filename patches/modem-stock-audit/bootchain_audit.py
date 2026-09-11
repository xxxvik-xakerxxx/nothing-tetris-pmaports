#!/usr/bin/env python3
"""Hash-pinned static bootchain evidence; no vendor instruction execution."""
import argparse
import json
from pathlib import Path
import subprocess

from audit import payload

WINDOWS = (
    "0xc020:0x60", "0xf5f0:0x40", "0xfe80:0x40",
    "0x10380:0xc", "0x188f0:0x74", "0x1868c:0x40",
    "0xe460:0x54", "0xe744:0xc", "0x10420:0x60",
    "0x10628:0x48", "0x28118:0x24",
)
EXPECTED = {
    "0x00c038": "mov w2, #8",
    "0x00f618": "mov x26, x1",
    "0x00f61c": "mov x19, x0",
    "0x00feac": "movk w1, #0xc200, lsl #16",
    "0x00febc": "bl #0x188f0",
    "0x010380": "mov x4, #1",
    "0x010384": "smc #0",
    "0x018960": "bl #0x1868c",
    "0x018690": "mov x0, x1",
    "0x018694": "mov x1, x2",
    "0x018698": "mov x2, x3",
    "0x0186c8": "br x4",
    "0x00e4b0": "cbz w10, #0xe744",
    "0x00e74c": "bl #0x68bf0",
    "0x01047c": "bl #0xf5f0",
}


def check(result):
    instructions = {}
    for window in result["windows"]:
        if len(window["instructions"]) * 4 != window["size"]:
            raise ValueError("incomplete bounded disassembly")
        for line in window["instructions"]:
            address, instruction = line.split(": ", 1)
            instructions[address] = instruction.strip()
    for address, instruction in EXPECTED.items():
        if instructions.get(address) != instruction:
            raise ValueError(f"changed bootchain instruction {address}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    payload(args.image.read_bytes())
    folder = Path(__file__).resolve().parent
    command = ["docker", "exec", "mt6878-probe-build", "python3", "-c",
               (folder / "audit.py").read_text(), "/tmp/tetris-stock-b41-lk.img"]
    result = None
    for start in range(0, len(WINDOWS), 8):
        bounded = command.copy()
        for window in WINDOWS[start:start + 8]:
            bounded += ["--window", window]
        decoded = json.loads(subprocess.check_output(bounded, text=True))
        if result is None:
            result = decoded
        else:
            result["windows"] += decoded["windows"]
    check(result)
    # Every pinned edge/argument has a negative test, not only a happy path.
    import copy
    for address in EXPECTED:
        changed = copy.deepcopy(result)
        for window in changed["windows"]:
            window["instructions"] = [
                line.split(": ")[0] + ": nop" if line.startswith(address + ":")
                else line for line in window["instructions"]]
        try:
            check(changed)
        except ValueError:
            continue
        raise AssertionError(f"accepted mutation at {address}")
    result["checked_instructions"] = len(EXPECTED)
    result["negative_mutations"] = len(EXPECTED)
    (folder / "bootchain-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"PASS: two input hashes, {len(WINDOWS)} bounded windows, "
          f"{len(EXPECTED)} instruction checks and negative mutations")


if __name__ == "__main__":
    main()
