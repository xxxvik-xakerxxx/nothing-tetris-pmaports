#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Validate and optionally stage the real prepared kernel's stream owner in CI."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import check
import generate as gen


def ci_only():
    if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("prepared stream-owner application is CI-only")


def verify_prepared(kernel, base):
    hashes = {}
    for path in gen.INPUTS:
        data = (kernel / path).read_bytes()
        if data != base[path].encode():
            raise ValueError("prepared source differs from exact packaged baseline: " + path)
        hashes[path] = gen.sha(data)
    return hashes


def apply(kernel, base, output, patch):
    hashes = verify_prepared(kernel, base)
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=kernel, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=kernel, check=True)
    for path in gen.TARGETS:
        if (kernel / path).read_bytes() != output[path].encode():
            raise ValueError("prepared stream payload differs: " + path)
    return hashes


def main():
    # Refuse the mutating mode before parsing, subprocesses or filesystem writes.
    if "--ci-apply" in sys.argv[1:]:
        ci_only()
    parser = argparse.ArgumentParser(description=__doc__)
    gen.arguments(parser, explicit=True)
    parser.add_argument("--prepared-kernel", type=Path, required=True)
    parser.add_argument("--ci-apply", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.ci_apply and not args.report:
        parser.error("--ci-apply requires a fresh --report directory")
    base, output, _, evidence, _ = check.check(args.kernel_archive, args.device_repo, args.modules_repo)
    kernel = args.prepared_kernel.resolve()
    before = verify_prepared(kernel, base)
    patch = gen.HERE / "stream-owner.patch"
    if not args.ci_apply:
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=kernel, check=True)
        print("PASS: actual prepared source hashes and stream patch applicability; no prepared-tree changes")
        return
    report = args.report.resolve()
    if report == kernel or kernel in report.parents or report in kernel.parents:
        raise ValueError("report must be outside prepared kernel")
    report.mkdir(parents=True, exist_ok=False)
    manifest = {"status": "started", "scope": "source staging only; no compile, config rewrite, DT or hardware",
                "kernel_commit": gen.KERNEL, "device_modules_commit": gen.DEVICE, "modules_commit": gen.MODULES,
                "prepared_baseline_sha256": before, "patch_sha256": gen.sha(patch.read_bytes()),
                "evidence_sha256": gen.sha((gen.HERE / "evidence.json").read_bytes()),
                "object": gen.DRIVER.removesuffix(".c") + ".o", "compile_selector": "CONFIG_VIDEO_IMX882_TETRIS=y",
                "shipping_selector": "CONFIG_VIDEO_IMX882_TETRIS=n", "security_profile": "unchanged; no .config edits"}
    manifest_path = report / "STAGE-MANIFEST.json"
    try:
        apply(kernel, base, output, patch)
        manifest.update(status="staged", staged_sha256=evidence["payload_sha256"])
        print("PASS: actual prepared stream driver/binding/Kconfig staged; compilation still required")
    except Exception as error:
        manifest.update(status="failed", error=str(error))
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
