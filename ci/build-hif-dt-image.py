#!/usr/bin/env python3
"""CI-only HIF DT image on the exact installed r182 kernel/initramfs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = 11751726266
ZIP_SHA256 = "1ca7f7ca96d7a7290bdec94b19caeb5917b97508d640c49fa136617c4b130a3e"
BASELINE = "75a510f072239825b9de7e620205a513568cce6e"
INPUT_HASHES = {
    "boot_image.itb": "a4e5cad84cc5815113c76ff1e96009bb556a005a30e00aeda3270845b45ee144",
    "nothing-tetris-boot.img": "92b0aadba9aed22c1872f1828a48daf8d4b2ccc77e1ad32056913ed1dd314ae9",
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build(dtbs, output):
    if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("native DT/FIT packaging is GitHub CI-only")
    token = os.environ.get("GH_TOKEN")
    if not token:
        raise ValueError("missing read-only artifact token")
    for name in ("mt6878-nothing-tetris-native.dtb", "mt6878-nothing-tetris-ccci-hif-resources.dtb"):
        if not (dtbs / name).is_file() or not (dtbs / name).stat().st_size:
            raise ValueError("missing checked DT input: " + name)
    work = ROOT / "out/hif-r182-inputs"
    work.mkdir(parents=True, exist_ok=False)
    archive = work / "r182-images.zip"
    subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error",
                    "--header", "Authorization: Bearer " + token, "--output", str(archive),
                    f"https://api.github.com/repos/xxxvik-xakerxxx/nothing-tetris-pmaports/actions/artifacts/{ARTIFACT}/zip"],
                   check=True)
    if digest(archive) != ZIP_SHA256:
        raise ValueError("original r182 install ZIP identity changed")
    with zipfile.ZipFile(archive) as source:
        metadata = dict(line.split("=", 1) for line in source.read("BUILD-MANIFEST").decode().splitlines())
        if metadata.get("github_sha") != BASELINE or metadata.get("kernel_release") != "6.18.0":
            raise ValueError("not the original installed r182 source/kernel")
        for name, expected in INPUT_HASHES.items():
            info = source.getinfo(name)
            if info.is_dir() or info.file_size <= 0 or info.file_size > 536870912:
                raise ValueError("invalid original boot input")
            with source.open(info) as src, (work / name).open("xb") as dest:
                for block in iter(lambda: src.read(1024 * 1024), b""):
                    dest.write(block)
            if digest(work / name) != expected:
                raise ValueError("original boot member mismatch: " + name)
    archive.unlink()
    sys.path.insert(0, str(ROOT / "patches/gpu"))
    import build_diagnostic_boot as builder
    args = argparse.Namespace(mode="ccci-hif-resources", normal_fit=work / "boot_image.itb",
        boot_image=work / "nothing-tetris-boot.img", require_boot_image=True,
        normal_dtb=dtbs / "mt6878-nothing-tetris-native.dtb",
        diagnostic_dtb=dtbs / "mt6878-nothing-tetris-ccci-hif-resources.dtb",
        baseline_dtb=None, its=ROOT / "pmaports/device/testing/device-nothing-tetris/boot_image.its",
        output_dir=output)
    result = builder.build(args)
    result.update(source_commit=os.environ["GITHUB_SHA"], baseline_source=BASELINE,
                  baseline_artifact_id=ARTIFACT, baseline_zip_sha256=ZIP_SHA256,
                  scope="HIF resource binding DT; unchanged r182 kernel/initramfs; no modem START")
    (output / "diagnostic-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtbs", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    build(args.dtbs.resolve(), args.output.resolve())
