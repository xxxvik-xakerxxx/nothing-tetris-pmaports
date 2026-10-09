#!/usr/bin/env python3
"""Validate the compiled single-experiment modem preflight DTB pair."""
import argparse
from pathlib import Path
import re
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


def compatible(props):
    return props.get("compatible", b"").rstrip(b"\0").split(b"\0")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def cells(data):
    require(len(data) % 4 == 0, "Malformed DT cells")
    return [int.from_bytes(data[i:i + 4], "big") for i in range(0, len(data), 4)]


def phandle_owners(tree):
    owners = {}
    for path, node in tree.items():
        handles = [cells(node[prop]) for prop in ("phandle", "linux,phandle") if prop in node]
        if not handles:
            continue
        require(all(len(value) == 1 for value in handles), "Malformed phandle: " + path)
        require(all(value == handles[0] for value in handles), "Conflicting phandle aliases: " + path)
        handle = handles[0][0]
        require(handle not in (0, 0xffffffff) and handle not in owners, "Invalid/duplicate phandle")
        owners[handle] = path
    return owners


def reference_value(tree, owners, prop, data):
    """Compare typed DT references by node path, never by incidental integers."""
    arrays = {
        "clocks": "#clock-cells", "resets": "#reset-cells",
        "power-domains": "#power-domain-cells", "iommus": "#iommu-cells",
        "phys": "#phy-cells", "io-channels": "#io-channel-cells",
        "interrupts-extended": "#interrupt-cells",
        "performance-domains": "#performance-domain-cells",
        "thermal-sensors": "#thermal-sensor-cells", "sound-dai": "#sound-dai-cells",
    }
    plain = {"access-controllers", "affinity", "cpu", "cpus", "cpu-idle-states",
             "interrupt-parent", "memory-region", "remote-endpoint", "nvmem-cells",
             "nvmem", "monitored-battery", "power-supplies", "apmixedsys", "infracfg",
             "topckgen", "hw-voter-regmap", "hwid-node", "mediatek,codec",
             "mediatek,ipm", "mediatek,platform", "mediatek,hardware-voter",
             "mediatek,infracfg", "mediatek,larbs", "mediatek,smi",
             "mediatek,main-pmic", "mediatek,secondary-pmic"}
    if prop.endswith("-gpios") or prop in {"gpio", "gpios"} or prop in {
            "focaltech,dvdd-gpio", "focaltech,irq-gpio", "focaltech,reset-gpio"}:
        args_property = "#gpio-cells"
    else:
        args_property = arrays.get(prop)
    fixed_args = {"gpio-ranges": 3, "mediatek,syscon-wakeup": 2}
    is_plain = prop in plain or prop.endswith("-supply") or re.fullmatch(r"pinctrl-\d+", prop)
    if not (args_property or is_plain or prop in fixed_args):
        return data
    values = cells(data)
    result = []
    index = 0
    while index < len(values):
        handle = values[index]
        require(handle in owners, "Unresolved typed reference: " + prop)
        path = owners[handle]
        count = fixed_args.get(prop, 0)
        if args_property:
            descriptor = tree[path].get(args_property)
            # The pinned vendor USB PHY uses phy-cells instead of #phy-cells.
            if descriptor is None and args_property == "#phy-cells":
                descriptor = tree[path].get("phy-cells")
            require(descriptor is not None, "Missing provider cells: " + path + "/" + args_property)
            widths = cells(descriptor)
            require(len(widths) == 1 and widths[0] <= 16, "Invalid provider cells: " + path)
            count = widths[0]
        require(index + count < len(values), "Truncated typed reference: " + prop)
        result.append((path, tuple(values[index + 1:index + 1 + count])))
        index += 1 + count
    return tuple(result)


def check_native_baseline(normal, off):
    """Permit only the exact two disabled fixture nodes, preserving shipping DT."""
    require(set(normal) <= set(off), "OFF baseline removes shipping nodes")
    require({b"nothing,tetris", b"mediatek,mt6878"} <= set(compatible(normal.get("/", {}))),
            "Wrong shipping device compatible")
    spms = [path for path, props in normal.items()
            if b"mediatek,mt6878-scpsys" in compatible(props)]
    require(len(spms) == 1, "Expected one existing SPM syscon")
    spm = spms[0]
    observer = spm + "/modem-preflight"
    nemi = spm.rsplit("/", 1)[0] + "/syscon@10270000"
    require(set(off) - set(normal) == {observer, nemi}, "Unexpected OFF baseline node additions")
    owners = phandle_owners(off)
    normal_owners = phandle_owners(normal)
    require(set(normal_owners.values()) == set(owners.values()) & set(normal),
            "OFF baseline changes existing phandle ownership")
    for path, props in normal.items():
        require(off[path].keys() == props.keys(), "OFF baseline changes property inventory: " + path)
        for prop, value in props.items():
            if prop in ("phandle", "linux,phandle"):
                continue
            require(reference_value(normal, normal_owners, prop, value) ==
                    reference_value(off, owners, prop, off[path][prop]),
                    "OFF baseline changes existing properties: " + path + "/" + prop)
    references = cells(off[observer].get("access-controllers", b""))
    require(len(references) == 2 and references[0] != references[1], "Malformed IFR/NEMI references")
    require(all(ref in owners for ref in references), "Unresolved OFF access-controller phandle")
    ifr = owners[references[0]]
    require(ifr in normal and owners[references[1]] == nemi, "Access controllers do not resolve to existing IFR/new NEMI")
    require(compatible(normal[ifr]) == [b"mediatek,mt6878-infracfg-ao", b"syscon"], "Wrong existing IFR syscon")
    require(cells(normal[ifr].get("reg", b"")) == [0x10001000, 0x1000], "Wrong existing IFR resource")
    require({b"mediatek,mt6878-scpsys", b"syscon", b"simple-mfd"} <= set(compatible(normal[spm])),
            "Wrong SPM parent binding")
    require(cells(normal[spm].get("reg", b"")) == [0x1c001000, 0x1000], "Wrong existing SPM resource")
    expected = {
        observer: {"compatible": b"mediatek,mt6878-modem-preflight\0",
                   "access-controllers": off[observer]["access-controllers"], "status": b"disabled\0"},
        nemi: {"compatible": b"mediatek,mt6878-nemicfg_ao_mem_reg_bus\0syscon\0",
               "reg": (0x10270000).to_bytes(4, "big") + (0x1000).to_bytes(4, "big"),
               "status": b"disabled\0"},
    }
    for path, props in expected.items():
        actual = {prop: value for prop, value in off[path].items() if prop not in ("phandle", "linux,phandle")}
        require(actual == props, "Unexpected disabled fixture properties: " + path)
    return observer


def validate_trees(baseline, diagnostic):
    require(set(baseline) == set(diagnostic), "Diagnostic changes node inventory")
    observers = [path for path, props in baseline.items()
                 if b"mediatek,mt6878-modem-preflight" in compatible(props)]
    require(len(observers) == 1, "Expected exactly one read-only modem observer")
    observer = observers[0]
    parent = observer.rsplit("/", 1)[0]
    for tree in (baseline, diagnostic):
        require({b"nothing,tetris", b"mediatek,mt6878"} <= set(compatible(tree.get("/", {}))),
                "Wrong device compatible")
        props = tree[observer]
        require(compatible(props) == [b"mediatek,mt6878-modem-preflight"], "Wrong observer driver")
        require(not any(path.startswith(observer + "/") for path in tree), "Observer has domain children")
        require(not ({"power-domains", "#power-domain-cells", "clocks", "resets", "hwlocks"} & props.keys()),
                "Observer requests managed resources")
        require({b"mediatek,mt6878-scpsys", b"syscon", b"simple-mfd"} <=
                set(compatible(tree[parent])), "Observer is not directly under the SPM syscon")
        require(cells(tree[parent].get("reg", b"")) == [0x1c001000, 0x1000], "Wrong SPM resource")
        refs = cells(props.get("access-controllers", b""))
        require(len(refs) == 2 and refs[0] != refs[1], "Expected distinct IFR/NEMI phandles")
        owners = phandle_owners(tree)
        require(all(ref in owners for ref in refs), "Unresolved access-controller phandle")
        resource_paths = [parent] + [owners[ref] for ref in refs]
        for path, start, expected_compatible in zip(resource_paths,
                [0x1c001000, 0x10001000, 0x10270000],
                [b"mediatek,mt6878-scpsys", b"mediatek,mt6878-infracfg-ao",
                 b"mediatek,mt6878-nemicfg_ao_mem_reg_bus"]):
            node = tree[path]
            require(cells(node.get("reg", b"")) == [start, 0x1000], "Wrong diagnostic resource: " + path)
            require({expected_compatible, b"syscon"} <= set(compatible(node)), "Wrong syscon: " + path)
            require(not ({"clocks", "resets", "hwlocks"} & node.keys()), "Syscon may mutate managed resources")
        require(tree[resource_paths[2]].get("status") == b"disabled\0", "NEMICFG device was enabled")
        require("tetris,vgpu-observe-diagnostic" not in tree.get("/chosen", {}), "GPU experiment combined")
        for path, node in tree.items():
            compatibles = compatible(node)
            require(b"mediatek,mt6878-modem-power-controller" not in compatibles,
                    "Modem power-provider fixture must not be present")
            if (b"mediatek,mt6319-regulator" in compatibles or
                    b"mediatek,mt6878-mfg-power-controller" in compatibles or
                    b"mediatek,mddriver" in compatibles or path.endswith("/regulators/vsram-cpum") or
                    path.endswith("/gpu@13000000") or
                    any(value.startswith(b"arm,mali") for value in compatibles)):
                require(node.get("status") == b"disabled\0", "Another hardware experiment enabled: " + path)
    require(baseline[observer].get("status") == b"disabled\0", "Baseline observer is not disabled")
    require(diagnostic[observer].get("status") == b"okay\0", "Diagnostic observer is not enabled")
    require("tetris,modem-preflight-diagnostic" not in baseline.get("/chosen", {}), "Baseline is diagnostic")
    expected = {
        ("/", "model"): b"Nothing CMF Phone 1 (modem read-only preflight)\0",
        ("/chosen", "tetris,modem-preflight-diagnostic"): b"",
        (observer, "status"): b"okay\0",
    }
    delta = {(node, prop): diagnostic[node].get(prop)
             for node in baseline for prop in baseline[node].keys() | diagnostic[node].keys()
             if baseline[node].get(prop) != diagnostic[node].get(prop)}
    require(delta == expected, "Unexpected compiled DT delta: " + repr(delta))
    return observer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("diagnostic", type=Path)
    parser.add_argument("--normal", type=Path, help="shipping native DTB; mandatory for FIT repackaging")
    args = parser.parse_args()
    baseline = read_tree(args.baseline)
    if args.normal:
        check_native_baseline(read_tree(args.normal), baseline)
    observer = validate_trees(baseline, read_tree(args.diagnostic))
    print("Validated single read-only modem experiment: " + observer)


if __name__ == "__main__":
    main()
