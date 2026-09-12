#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the pinned sensor-list predicate without a build or device access."""

import argparse
import ast
from itertools import product
from pathlib import Path
import re
import subprocess
import tempfile


COMMIT = "ee2be53cb75670b548948636a0db1d1ff112bf12"
SOURCE = "drivers/misc/mediatek/sensor/2.0/sensorhub/sensor_list.c"
FIELDS = ("sequence", "sensor_type", "command")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def predicate(source):
    matches = re.findall(r"if \((rx_notify\.sequence.*?notify\.command)\) \{"
                         r'\s*pr_err\("reply fail\\n"\);'
                         r"\s*spin_unlock_irqrestore\(&rx_notify_lock, flags\);"
                         r"\s*return -EREMOTEIO;\s*\}"
                         r"\s*write_position = rx_notify\.value\[0\];", source, re.S)
    require(len(matches) == 1, "reply/error/position boundary changed")
    expression = matches[0]
    for field in FIELDS:
        term = f"rx_notify.{field} != notify.{field}"
        require(expression.count(term) == 1, f"comparison changed: {field}")
        expression = expression.replace(term, field)
    expression = expression.replace("&&", " and ").replace("||", " or ")
    tree = ast.parse(" ".join(expression.split()), mode="eval").body

    def evaluate(node, differences):
        if isinstance(node, ast.Name) and node.id in FIELDS:
            return differences[FIELDS.index(node.id)]
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            values = [evaluate(value, differences) for value in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        raise RuntimeError("unsupported predicate syntax")

    return lambda differences: evaluate(tree, differences)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vendor_repo", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    candidate = root / "patches/sensors/0001-sensor-list-reject-mismatched-reply.patch.vendor"
    original = subprocess.check_output(
        ["git", "-C", str(args.vendor_repo), "show", f"{COMMIT}:{SOURCE}"], text=True)
    kernel = root / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878"
    require(f'_devmods_commit="{COMMIT}"' in (kernel / "APKBUILD").read_text(),
            "package vendor pin changed")
    for path in kernel.glob("*.patch*"):
        require(f"+++ b/{SOURCE}".encode() not in path.read_bytes(),
                f"existing patch now changes sensor_list.c: {path.name}")

    with tempfile.TemporaryDirectory(prefix="sensor-list-reply-") as temporary:
        scratch = Path(temporary)
        target = scratch / SOURCE
        target.parent.mkdir(parents=True)
        target.write_text(original)
        for options in (("--check",), ()):
            subprocess.run(["git", "apply", *options, str(candidate)], cwd=scratch, check=True)
        patched = target.read_text()

    before, after = predicate(original), predicate(patched)
    cases = list(product((False, True), repeat=3))
    require(sum(before(case) != any(case) for case in cases) == 6,
            "baseline did not reproduce six incorrectly accepted mismatch combinations")
    require(all(after(case) == any(case) for case in cases), "candidate correlation failure")
    for sent in range(256):
        for received in range(256):
            mismatch = (sent != received, False, False)
            require(not before(mismatch), "baseline stale-LIST behavior changed")
            require(after(mismatch) == (sent != received), "sequence correlation failure")
    # The two one-operator mutations must both be caught by the truth table.
    for replacement in (0, 1):
        mutant = patched.split(" ||", 2)
        require(len(mutant) == 3, "unexpected candidate operator layout")
        text = mutant[0] + (" &&" if replacement == 0 else " ||") + mutant[1]
        text += (" &&" if replacement == 1 else " ||") + mutant[2]
        reject = predicate(text)
        require(any(reject(case) != any(case) for case in cases), "mutation escaped")
    print(f"PASS: patch application against {COMMIT}")
    print("PASS: 8 correlation combinations; baseline 6 failures, candidate 0")
    print("PASS: 65536 sequence pairs (including 255/0); both operator mutations rejected")
    print("LIMIT: Boolean source predicate only; no C build, firmware, IRQ or live tests")


if __name__ == "__main__":
    main()
