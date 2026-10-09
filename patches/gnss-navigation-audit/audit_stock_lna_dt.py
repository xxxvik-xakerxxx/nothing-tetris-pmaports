#!/usr/bin/env python3
"""Read-only cached stock DT audit; temporary overlay application, no device IO."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

GPS = "/soc/gps@18c00000"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def table_entries(data):
    if len(data) < 32:
        raise ValueError("truncated Android DT table header")
    magic, total, header, entry_size, count, offset, page, version = struct.unpack_from(">8I", data)
    if (magic != 0xd7b7ab1e or total > len(data) or header < 32 or header > total or
            entry_size < 32 or not 1 <= count <= 32 or offset < header or
            offset + count * entry_size > total or version != 0 or not page):
        raise ValueError("unsupported/malformed Android DT table")
    result, spans = [], []
    for index in range(count):
        entry = struct.unpack_from(">8I", data, offset + index * entry_size)
        size, start = entry[:2]
        if size < 40 or start < offset + count * entry_size or start + size > total:
            raise ValueError("invalid FDT entry bounds")
        if any(start < end and old < start + size for old, end in spans):
            raise ValueError("overlapping FDT entries")
        blob = data[start:start + size]
        if struct.unpack_from(">2I", blob) != (0xd00dfeed, size):
            raise ValueError("FDT magic/size mismatch")
        spans.append((start, start + size))
        result.append((entry, blob))
    return result


def vendor_dtb(image):
    with image.open("rb") as file:
        header = file.read(2128)
        if len(header) != 2128 or header[:8] != b"VNDRBOOT":
            raise ValueError("not a supported vendor_boot image")
        version, page = struct.unpack_from("<2I", header, 8)
        ramdisk = struct.unpack_from("<I", header, 24)[0]
        header_size, size = struct.unpack_from("<2I", header, 2096)
        if (version not in (3, 4) or page < 512 or page & (page - 1) or
                header_size < 2112 or header_size > page or not 0 < size <= 8 * 1024 * 1024):
            raise ValueError("unsupported vendor_boot layout")
        start = page * ((header_size + page - 1) // page + (ramdisk + page - 1) // page)
        file.seek(start)
        blob = file.read(size)
        if len(blob) != size:
            raise ValueError("truncated vendor_boot DT payload")
        return start, blob


def archive_entry(archive, name):
    return subprocess.run(["7zz", "x", "-so", str(archive.resolve()), name],
                          capture_output=True, check=True).stdout


def property_text(path, node, name):
    return subprocess.check_output(["fdtget", "-t", "s", str(path), node, name], text=True).strip()


def inspect(path):
    properties = subprocess.check_output(["fdtget", "-p", str(path), GPS], text=True).splitlines()
    compatible = property_text(path, GPS, "compatible")
    if compatible != "mediatek,mt6878-gps":
        raise ValueError("unexpected GPS owner compatible")
    lna_properties = [name for name in properties if name.startswith("pinctrl-") or "lna" in name.lower()]
    decoded = subprocess.check_output(["dtc", "-q", "-I", "dtb", "-O", "dts", str(path)], text=True)
    markers = [name for name in ("gps_l1_lna", "gps_l5_lna", "gps-l1-lna", "gps-l5-lna")
               if name in decoded]
    return {"gps_node": GPS, "compatible": compatible,
            "status": property_text(path, GPS, "status") if "status" in properties else "absent",
            "gps_lna_or_pinctrl_properties": lna_properties, "lna_state_markers": markers,
            "contains_lna_metadata_candidates": bool(lna_properties or markers)}


def audit(archive, image, cached_dtb):
    offset, payload = vendor_dtb(image)
    if payload != cached_dtb.read_bytes():
        raise ValueError("cached DT payload differs from vendor_boot header extraction")
    archived_image = archive_entry(archive, "vendor_boot.img")
    with image.open("rb") as file:
        image_sha = hashlib.file_digest(file, "sha256").hexdigest()
    if digest(archived_image) != image_sha:
        raise ValueError("extracted vendor_boot differs from cached stock archive entry")
    del archived_image
    bases = table_entries(payload)
    if len(bases) != 1:
        raise ValueError("multiple base DTs require explicit board selection")
    overlays = archive_entry(archive, "dtbo.img")
    entries = table_entries(overlays)
    reports = []
    with tempfile.TemporaryDirectory(prefix="gnss-stock-dt-") as directory:
        root = Path(directory)
        base = root / "base.dtb"
        base.write_bytes(bases[0][1])
        reports.append({"variant": "base", "fdt_sha256": digest(bases[0][1]), **inspect(base)})
        for index, (metadata, blob) in enumerate(entries):
            overlay, merged = root / f"overlay-{index}.dtbo", root / f"merged-{index}.dtb"
            overlay.write_bytes(blob)
            subprocess.run(["fdtoverlay", "-i", str(base), "-o", str(merged), str(overlay)],
                           capture_output=True, check=True)
            reports.append({"variant": f"dtbo-{index}", "entry_id": metadata[2],
                            "entry_revision": metadata[3], "overlay_sha256": digest(blob),
                            "merged_sha256": digest(merged.read_bytes()), **inspect(merged)})
    with archive.open("rb") as file:
        archive_sha = hashlib.file_digest(file, "sha256").hexdigest()
    return {"archive_sha256": archive_sha, "vendor_boot_sha256": image_sha,
            "dt_payload_offset": offset, "dt_payload_sha256": digest(payload),
            "dtbo_image_sha256": digest(overlays), "variants": reports,
            # Finding similarly named metadata must never automatically lift
            # a GPIO-control gate. Actual topology/selection still needs review.
            "gate_0020_lna_control": True,
            "gate_reason": ("Stock metadata candidates require explicit topology review" if
                            any(r["contains_lna_metadata_candidates"] for r in reports) else
                            "No GPS LNA/pinctrl records in base or any independently applied stock DTBO"),
            "limit": "Cached named B4.1 archive, not cryptographic OEM authentication or physical wiring proof. No bootloader DT fixup trace."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--vendor-boot", type=Path, required=True)
    parser.add_argument("--cached-dtb", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.archive, args.vendor_boot, args.cached_dtb), indent=2))
