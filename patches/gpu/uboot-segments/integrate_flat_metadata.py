#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render a metadata-admitted existing consumer or full package patch to stdout."""
import argparse
from difflib import unified_diff
import hashlib
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
OWNER = HERE.parent / "flat-handoff-draft"
BASE_SHA256 = "90659a3481c240f58673cd769d44245fb2814dcb61ac8ffce371311c5359ea86"


def integrate(source, header):
    if hashlib.sha256(source.encode()).hexdigest() != BASE_SHA256:
        raise ValueError("existing consumer changed; reconcile instead of duplicating admission")
    if not header or not header.endswith("\n"):
        raise ValueError("metadata header must be nonempty and newline terminated")
    replacements = (
        ("#include <asm/page.h>\n", "#include <asm/page.h>\n\n" + header),
        ("\tu32 size;\n};", "\tu32 size;\n\tstruct tetris_gpueb_flat_metadata metadata;\n};"),
        ("\tconst u8 *expected;", "\tstruct tetris_gpueb_flat_metadata metadata;"),
        ("\tint length, ret;\n\n\tif (of_property_count_u32_elems",
         "\tint ret;\n\n\tif (of_property_count_u32_elems"),
        ("\tif (memory->size != 0x100000 || !memory->base ||\n"
         "\t    memory->base & 0xffff || memory->base > 0x80000000ULL - memory->size)\n"
         "\t\treturn -EINVAL;\n"
         "\tif (of_property_read_u32(pdev->dev.of_node, \"nothing,authenticated-bytes\", &size) ||\n"
         "\t    size != 156064 || size > memory->size)\n"
         "\t\treturn -EINVAL;\n"
         "\texpected = of_get_property(pdev->dev.of_node, \"nothing,plaintext-sha256\", &length);\n"
         "\tif (!expected || length != sizeof(digest))\n"
         "\t\treturn -EINVAL;",
         "\tret = tetris_gpueb_flat_metadata_read(pdev->dev.of_node, memory, &metadata);\n"
         "\tif (ret)\n\t\treturn ret;\n\tsize = metadata.authenticated_bytes;"),
        ("\tmemcpy(analysis->snapshot, mapping, size);",
         "\tmemcpy(analysis->snapshot, (u8 *)mapping + metadata.payload_offset, size);"),
        ("\tif (!ret && memcmp(digest, expected, sizeof(digest)))\n\t\tret = -EBADMSG;",
         "\tif (!ret)\n\t\tret = tetris_gpueb_flat_snapshot_check(&metadata, digest, size);"),
        ("\tanalysis->size = size;", "\tanalysis->metadata = metadata;\n\tanalysis->size = size;"),
    )
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError("ambiguous integration anchor: " + old.splitlines()[0])
        source = source.replace(old, new, 1)
    return source


def render_patch(source):
    spec = importlib.util.spec_from_file_location("existing_flat_generator",
                                                OWNER / "generate_consumer_patch.py")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    return generator.render(source)


def render_delta(original, source):
    target = "patches/gpu/flat-handoff-draft/gpueb-flat-analysis.c"
    return "".join(unified_diff(original.splitlines(keepends=True),
                                source.splitlines(keepends=True),
                                fromfile="a/" + target, tofile="b/" + target))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("source", "patch", "delta"), default="source")
    args = parser.parse_args()
    try:
        original = (OWNER / "gpueb-flat-analysis.c").read_text()
        source = integrate(original,
                           (HERE / "tetris_gpueb_flat_metadata.h").read_text())
        if args.format == "delta":
            result = render_delta(original, source)
        else:
            result = source if args.format == "source" else render_patch(source)
    except (OSError, ValueError) as error:
        parser.exit(1, f"GPUEB metadata integration failed: {error}\n")
    sys.stdout.write(result)


if __name__ == "__main__":
    main()
