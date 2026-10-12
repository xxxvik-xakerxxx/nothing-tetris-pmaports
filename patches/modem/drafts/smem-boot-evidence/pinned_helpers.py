#!/usr/bin/env python3
"""Read-only, hash-checked extraction of the real U-Boot planner bodies."""
import hashlib
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
PIN = "cdd806438d73e2e163fcc9aded557b029816011e"
BOARD = "board/mediatek/mt6878/"
PINS = {
    "tetris_modem_layout.c": "0402ae516ef572b79d14d97256a14cfdfa166f5274bd36a2bb2509b53e1a6bf5",
    "tetris_modem_emi.c": "c055ac548b11aa22411b0d3e736ecce3458ba1e103357bdc2c1e1f34e64dddce",
    "tetris_modem_emi.h": "63de7e86df4b641c2f382834ed8f62a11d4a1dd41b94756ab60972061a9498de",
}


def sources(uboot):
    result = {}
    for name, digest in PINS.items():
        raw = subprocess.check_output(["git", "-C", str(uboot), "show", PIN + ":" + BOARD + name])
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("pinned source mismatch: " + name)
        result[name] = raw.decode("ascii")
    return result


def function(source, name):
    start = source.index("int " + name + "(")
    opening = source.index("{", start)
    # Ignore braces inside C comments and literals while bounding one body.
    tokens = re.finditer(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]',
                         source[opening:], re.S)
    depth = 0
    for token in tokens:
        if token.group() == "{":
            depth += 1
        elif token.group() == "}":
            depth -= 1
            if depth == 0:
                return source[start:opening + token.end()]
    raise ValueError("unterminated pinned helper: " + name)


def shared_policies(source):
    body = function(source, "tetris_modem_plan_emi_policy")
    initializer = re.search(r'shared_aids\[3\]\[9\]\s*=\s*\{(.*?)\n\s*\};', body, re.S)
    if not initializer:
        raise ValueError("unrecognized pinned policy initializer")
    rows = [list(map(int, re.findall(r'\d+', row)))
            for row in re.findall(r'\{([^{}]*)\}', initializer[1])]
    if len(rows) != 3 or any(len(row) > 9 for row in rows):
        raise ValueError("unexpected policy dimensions")
    result = []
    for row in rows[1:]:
        words = [0] * 8
        for aid in row:
            if not aid:
                break
            if aid >= 256:
                raise ValueError("unexpected AID")
            words[aid // 32] |= 3 << (2 * (aid % 32))
        result.append(words)
    return result


def oracle_c(src):
    return '''/* Actual helpers extracted from hash-checked pinned U-Boot. */
#include <errno.h>
#include <string.h>
#include "oracle.h"
''' + function(src["tetris_modem_layout.c"], "tetris_modem_plan_emi") + "\n" + function(
        src["tetris_modem_emi.c"], "tetris_modem_plan_emi_policy") + "\n"
