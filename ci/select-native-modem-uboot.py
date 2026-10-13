#!/usr/bin/env python3
"""Retain the exact successful, paired loader with diagnostic install artifacts."""
import hashlib
import io
import json
import os
from pathlib import Path
import struct
from urllib.request import Request, urlopen
import zipfile

RUN = 38325598818
COMMIT = "322cf227f2ea26a7e319d20e3ce0321db8a38f15"
REPO = "xxxvik-xakerxxx/u-boot"
PROFILE = {
    "commit": COMMIT,
    "modem_startup_off": "disabled",
    "modem_brom_only": "cold-one-attempt-owned-metadata-linux-md-disabled",
    "modem_metadata": "owned-64k-nomap-after-brom-linux-md-disabled",
    "scp_secure": "slot-a-diagnostic",
    "scp_tcm": "reset-held",
    "scp_prepare": "slot-a-diagnostic",
    "gpueb_flat_retention": "disabled",
    "gpueb_transform": "disabled",
}


def read(url, token, limit):
    request = Request(url, headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("paired loader response exceeds bound")
    return data


def checked_image(archive):
    with zipfile.ZipFile(io.BytesIO(archive)) as source:
        for name in ("BUILD-MANIFEST", "SHA256SUMS", "u-boot-tetris-lk.img"):
            entries = [i for i in source.infolist() if i.filename == name]
            if len(entries) != 1 or entries[0].is_dir() or entries[0].file_size > 16 * 1024 * 1024:
                raise ValueError("invalid paired loader member: " + name)
        manifest = dict(line.split("=", 1) for line in source.read("BUILD-MANIFEST").decode().splitlines())
        if any(manifest.get(name) != value for name, value in PROFILE.items()):
            raise ValueError("paired loader profile/source mismatch")
        sums = dict((line.split()[1], line.split()[0]) for line in source.read("SHA256SUMS").decode().splitlines())
        image = source.read("u-boot-tetris-lk.img")
        digest = hashlib.sha256(image).hexdigest()
        if digest != sums.get("u-boot-tetris-lk.img") or not 3 * 1024 * 1024 <= len(image) <= 16 * 1024 * 1024:
            raise ValueError("paired LK image identity/size mismatch")
        magic, payload_size = struct.unpack_from("<II", image)
        if magic != 0x58881688 or payload_size % 16 or not 0 < payload_size < len(image):
            raise ValueError("paired LK payload header mismatch")
        return image, digest, manifest


def main():
    if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("paired loader selection is GitHub CI-only")
    token = os.environ["GH_TOKEN"]
    api = "https://api.github.com/repos/" + REPO + "/actions/runs/" + str(RUN)
    run = json.loads(read(api, token, 1024 * 1024))
    if run["head_sha"] != COMMIT or run["status"] != "completed" or run["conclusion"] != "success":
        raise ValueError("paired loader build did not complete successfully at the frozen source")
    artifacts = json.loads(read(api + "/artifacts", token, 1024 * 1024))["artifacts"]
    matches = [a for a in artifacts if a["name"] == "mt6878-tetris-u-boot" and not a["expired"]]
    if len(matches) != 1 or matches[0]["size_in_bytes"] > 50 * 1024 * 1024:
        raise ValueError("paired loader artifact missing/ambiguous/oversized")
    artifact = matches[0]
    image, digest, manifest = checked_image(read(artifact["archive_download_url"], token, 50 * 1024 * 1024))
    output = Path("/work/out")
    output.mkdir(parents=True, exist_ok=True)
    (output / "u-boot-tetris-lk.img").write_bytes(image)
    (output / "native-modem-uboot.json").write_text(json.dumps(dict(
        run=RUN, artifact=artifact["id"], sha256=digest, manifest=manifest), indent=2) + "\n")
    with Path(os.environ["GITHUB_ENV"]).open("a") as env:
        env.write("TETRIS_UBOOT_COMMIT=" + COMMIT + "\nTETRIS_UBOOT_SHA256=" + digest + "\n")
    print("Retained successful paired U-Boot", COMMIT, digest)


if __name__ == "__main__":
    main()
