#!/usr/bin/env python3
"""Static closure for dormant supplier wiring; never compile or access hardware."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import generate
import supplier_wiring as wiring


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resource = load("supplier_resource_check", HERE / "check.py")
TRACE_SHA256 = "1b416b2b9ebbc4a974610d688afdfbdc159cabba3b3f6313223141f389d5eb1d"
require = resource.require


def evidence_contract(data, root=ROOT):
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(digest == TRACE_SHA256, "Frozen supplier ownership trace changed; review source pins")
    require(set(data["parent_input_sha256"]) == set(wiring.PARENT_INPUTS), "Supplier parent input closure")
    for path, digest in data["parent_input_sha256"].items():
        require(hashlib.sha256((root / path).read_bytes()).hexdigest() == digest,
                "Supplier parent input drift: " + path)


def source_contract(files, data):
    resource.evidence_contract(data)
    expected = wiring.outputs(data, generate.fragment, generate.power_fragment)
    require(set(files) == set(expected), "Exact supplier source/patch/plan inventory")
    for name, contents in expected.items():
        require(files[name] == contents, "Generated supplier drift: " + name)
    # These are separately reviewed boundaries, even if source generation changes.
    require(not re.search(r"&disp_iommu\s*\{", files[wiring.RESOURCES]),
            "Do not enroll disabled larbs in live display IOMMU")
    require("&spm" not in files[wiring.POWER] and "-supply" not in files[wiring.POWER],
            "Dormant supplier must not opt into SPM ownership")
    require('status = "disabled";' not in files[wiring.POWER].split("&mm_infra {", 1)[1].split("cam_vcore_pd", 1)[0],
            "Preserve active MM_INFRA")
    require(wiring.MIGRATION not in files[wiring.BOARD], "Boot candidate must exclude blocked migration")
    require('status = "okay";' not in "\n".join(files[name] for name in wiring.DESTINATIONS),
            "No guessed hardware activation")
    plan = json.loads(files["SUPPLIER-STAGING.json"])
    require(plan == wiring.plan(files), "Exact supplier check plan")
    require(not plan["blocked_ownership"]["boot_allowed"], "Ownership target cannot become boot eligible")


def check(root=ROOT, upstream=None, staged=None):
    here = root / "patches/camera-camisp/resources"
    data = json.loads((here / "evidence.json").read_text())
    facts = json.loads((here / "supplier-evidence.json").read_text())
    evidence_contract(facts, root)
    resource.parent_contract(root, data)
    if upstream:
        require(facts == wiring.trace(upstream, root, data), "Supplier git-show/archive provenance drift")
        require(data == generate.trace(upstream), "Pinned rail/graph source drift")
    names = wiring.outputs(data, generate.fragment, generate.power_fragment)
    files = {name: (here / name).read_text() for name in names}
    source_contract(files, data)
    with tempfile.TemporaryDirectory(prefix="camisp-supplier-apply-") as directory:
        tree = Path(directory)
        for name in ("supplier-description.patch", "ownership-description.patch"):
            subprocess.run(["git", "apply", str(here / name)], cwd=tree, check=True, capture_output=True)
        require({str(path.relative_to(tree)) for path in tree.rglob("*") if path.is_file()} ==
                set(wiring.DESTINATIONS.values()), "Additive supplier patch closure")
        for name, destination in wiring.DESTINATIONS.items():
            require((tree / destination).read_bytes() == (here / name).read_bytes(), "Supplier patch bytes: " + name)
    if staged:
        plan = json.loads(files["SUPPLIER-STAGING.json"])
        for source, destination in plan["sources"].items():
            require((staged / destination).read_bytes() == (root / source).read_bytes(), "Supplier staged byte drift")
        header = plan["requires_existing_resource_header"]
        require((staged / generate.DESTINATIONS[Path(header).name]).read_bytes() == (root / header).read_bytes(),
                "Supplier resource header dependency")
    print("PASS: supplier sources, exact patches, pins and blocked ownership plan; no compile/phone access")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-vendor", action="store_true")
    parser.add_argument("--upstream", type=Path, default=ROOT.parent)
    parser.add_argument("--staged-tree", type=Path)
    args = parser.parse_args()
    check(upstream=args.upstream if args.verify_vendor else None, staged=args.staged_tree)
