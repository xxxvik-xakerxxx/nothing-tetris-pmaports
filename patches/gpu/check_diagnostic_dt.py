#!/usr/bin/env python3
"""Reject any diagnostic compiled-DT change beyond the one observer activation."""
import argparse
from pathlib import Path
import subprocess


def read_tree(path):
    tree = {}
    pending = ["/"]
    while pending:
        node = pending.pop()
        properties = subprocess.check_output(["fdtget", "-p", str(path), node], text=True).splitlines()
        tree[node] = {}
        for prop in properties:
            value = subprocess.check_output(["fdtget", "-t", "bx", str(path), node, prop], text=True)
            tree[node][prop] = bytes(int(byte, 16) for byte in value.split())
        children = subprocess.check_output(["fdtget", "-l", str(path), node], text=True).splitlines()
        pending.extend(node.rstrip("/") + "/" + child for child in children)
    return tree


def compatibles(node):
    return node.get("compatible", b"").rstrip(b"\0").split(b"\0")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def validate_trees(normal, diagnostic):
    for tree in (normal, diagnostic):
        identity = compatibles(tree.get("/", {}))
        require(b"nothing,tetris" in identity and b"mediatek,mt6878" in identity,
                "Wrong board compatible; no register access is approved")
    observers = [node for node, props in normal.items()
                 if b"mediatek,mt6319-regulator" in compatibles(props)]
    require(len(observers) == 1, "Expected exactly one described MT6319 observer")
    observer = observers[0]
    require(normal[observer].get("reg") == b"\0\0\0\x06\0\0\0\0",
            "Observer must address SPMI USID 6, not a guessed unit")
    require(normal[observer].get("status") == b"disabled\0", "Normal provider is not disabled")
    require(normal[observer].get("mediatek,observe-vgpu-only") == b"",
            "Normal DT is missing the read-only contract")
    require(diagnostic.get(observer, {}).get("status") == b"okay\0", "Observer was not selected")
    require(diagnostic.get(observer, {}).get("mediatek,observe-vgpu-only") == b"",
            "Diagnostic DT lost the read-only contract")
    require(normal.get(observer + "/regulators/vbuck2", {}).get("status") == b"disabled\0",
            "VBUCK2 child is not disabled")
    srams = [node for node in normal if node.endswith("/regulators/vsram-cpum")]
    require(len(srams) == 1 and normal[srams[0]].get("status") == b"disabled\0",
            "Expected exactly one disabled VSRAM_CPUM child")
    expected = {
        ("/", "model"): b"Nothing CMF Phone 1 (VGPU read-only diagnostic)\0",
        ("/chosen", "tetris,vgpu-observe-diagnostic"): b"",
        (observer, "status"): b"okay\0",
    }
    require(set(normal) == set(diagnostic), "Diagnostic unexpectedly changes DT nodes")
    differences = {}
    for node in normal:
        for prop in normal[node].keys() | diagnostic[node].keys():
            if normal[node].get(prop) != diagnostic[node].get(prop):
                differences[node, prop] = diagnostic[node].get(prop)
    require(differences == expected, "Unexpected DT delta: " + repr(differences))
    return observer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("normal", type=Path)
    parser.add_argument("diagnostic", type=Path)
    args = parser.parse_args()
    observer = validate_trees(read_tree(args.normal), read_tree(args.diagnostic))
    print("Validated one read-only observer activation: " + observer)


if __name__ == "__main__":
    main()
