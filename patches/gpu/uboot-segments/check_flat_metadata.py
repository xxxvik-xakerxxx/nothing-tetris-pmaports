#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Static producer/consumer admission gate; never execute C, git, CI or hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from integrate_flat_metadata import HERE, OWNER, integrate


def require(condition, message):
    if not condition:
        raise ValueError(message)


def code(source):
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)


def compact(source):
    return re.sub(r"\s+", " ", code(source)).strip()


def check_header(header, manifest):
    text = compact(header)
    for name, value in (
        ("TETRIS_FLAT_VERSION", "1U"), ("TETRIS_FLAT_BYTES", "156064U"),
        ("TETRIS_FLAT_ARENA_BYTES", "0x100000U"),
        ("TETRIS_FLAT_ARENA_ALIGN", "0x10000U"),
        ("TETRIS_FLAT_GPR_OFFSET", "0x3fd1cU"),
    ):
        require(f"#define {name} {value}" in text, "wrong bound: " + name)
    for expression in (
        "metadata->handoff_version != TETRIS_FLAT_VERSION",
        "memory->size != TETRIS_FLAT_ARENA_BYTES",
        "memory->base < 0x40000000ULL",
        "memory->base > 0x80000000ULL - TETRIS_FLAT_ARENA_BYTES",
        "(memory->base & (TETRIS_FLAT_ARENA_ALIGN - 1))",
        "metadata->payload_offset || metadata->sram_offset ||",
        "metadata->authenticated_bytes != TETRIS_FLAT_BYTES",
        "metadata->payload_offset > memory->size",
        "metadata->authenticated_bytes > memory->size - metadata->payload_offset",
        "metadata->sram_offset > TETRIS_FLAT_GPR_OFFSET",
        "metadata->authenticated_bytes > TETRIS_FLAT_GPR_OFFSET - metadata->sram_offset",
        "metadata->profile_id < 1 || metadata->profile_id > 2",
        "if (memcmp(metadata->plaintext_sha256, profiles[metadata->profile_id - 1], 32)) return -ENOEXEC;",
        "of_property_count_u32_elems(node, name) != 1",
        "!property || length != 32", "memcpy(value, property, 32)",
        'of_property_count_strings(node, "compatible") != 1',
        '!of_device_is_available(node)',
        '!of_device_is_compatible(node, "nothing,tetris-gpueb-flat-analysis-v1")',
        "bytes != TETRIS_FLAT_BYTES || bytes != metadata->authenticated_bytes",
        "memcmp(digest, metadata->plaintext_sha256, 32) ? -EBADMSG : 0",
    ):
        require(expression in text, "missing admission guard: " + expression)
    profiles = re.search(r"profiles\[2\]\[32\] = \{(.*?)\};", header, re.S)
    require(profiles is not None, "missing reviewed profiles")
    values = bytes(int(item, 16) for item in re.findall(r"0x([0-9a-f]{2})\b", profiles[1]))
    require(values == b"".join(bytes.fromhex(manifest["profiles"][str(i)]) for i in (1, 2)),
            "profile IDs/digests differ from actual producer")
    for field in ("primary_header", "ciphertext", "leaf_certificate", "container"):
        require(f"!memchr_inv(metadata->{field}_sha256, 0, 32)" in text,
                "unvalidated provenance: " + field)
    require("tetris_gpueb_flat_metadata_validate(&metadata, memory); if (ret) return ret; "
            "*result = metadata;" in text, "metadata output must follow validation atomically")
    require(not re.search(r"\b(?:memremap|request_mem_region\w*|readl|writel|ioremap\w*|"
                          r"arm_smccc_smc|enable_irq|rproc_boot|pm_runtime\w*)\s*\(", text),
            "metadata helper must not duplicate ownership or execute hardware")


def check_producer(read, header, manifest):
    sources = {}
    for name, expected in manifest["sources"].items():
        sources[name] = read(name)
        require(hashlib.sha256(sources[name].encode()).hexdigest() == expected,
                "actual producer drift; re-review: " + name)
    publisher = sources["tetris_gpueb_flat_publish.c"]
    for kind, field in re.findall(r'READ_(U32|DIGEST)\("(nothing,[^"]+)",\s*\w+\)', header):
        pattern = (r'fdt_setprop_u32\(fdt, consumer, "' if kind == "U32" else
                   r'fdt_setprop\(fdt, consumer, "') + re.escape(field) + '"'
        require(re.search(pattern, publisher) is not None, "not an actual producer property: " + field)
    consumed = set(re.findall(r'READ_(?:U32|DIGEST)\("(nothing,[^"]+)"', header))
    published = set(re.findall(r'fdt_setprop(?:_u32)?\(fdt, consumer, "(nothing,[^"]+)"', publisher))
    require(consumed == published and len(consumed) == 10, "incomplete producer metadata consumption")
    producer = compact(sources["tetris_gpueb_flat.c"])
    for term in ("image->info.payload_offset = 0;", "image->info.sram_offset = 0;",
                 "image->info.handoff_version = TETRIS_GPUEB_FLAT_HANDOFF_VERSION;",
                 "image->info.profile_id = profile;", "profile = reviewed(metadata.plaintext);"):
        require(term in producer, "producer semantics changed: " + term)


def check_consumer(source):
    text = compact(source)
    ordered = (
        "ret = flat_plain_reservation(node, memory);",
        "ret = tetris_gpueb_flat_metadata_read(pdev->dev.of_node, memory, &metadata);",
        "ret = flat_claim_reserved_ram(analysis, memory);",
        "mapping = memremap(memory->base, size, MEMREMAP_WB);",
        "memcpy(analysis->snapshot, (u8 *)mapping + metadata.payload_offset, size);",
        "memunmap(mapping);",
        "ret = crypto_shash_digest(desc, analysis->snapshot, size, digest);",
        "if (!ret) ret = tetris_gpueb_flat_snapshot_check(&metadata, digest, size);",
        "memzero_explicit(digest, sizeof(digest)); if (ret) goto erase;",
        "analysis->metadata = metadata;",
        "ret = misc_register(&analysis->misc);",
    )
    positions = []
    for term in ordered:
        require(text.count(term) == 1, "missing/duplicate integration: " + term)
        positions.append(text.index(term))
    require(positions == sorted(positions), "admission, ownership or snapshot ordering changed")
    require("&metadata); if (ret) return ret; size = metadata.authenticated_bytes;" in text,
            "metadata rejection must stop before allocation/claim")
    require("ret = flat_claim_reserved_ram(analysis, memory); if (ret) goto release;" in text,
            "ownership failure must stop before mapping")
    require("kvfree_sensitive(analysis->snapshot, size); release:" in text and
            "release_mem_region(analysis->reservation->start, resource_size(analysis->reservation));" in text,
            "snapshot erase and full owned reservation release required on rejection")
    require("const u8 *expected;" not in text, "borrowed DT digest pointer survived")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", type=Path, default=HERE.parents[3] / "u-boot-mt6878")
    parser.add_argument("--consumer", type=Path, help="check an already integrated consumer")
    args = parser.parse_args()
    try:
        manifest = json.loads((HERE / "FLAT-METADATA-PRODUCER.json").read_text())
        header = (HERE / "tetris_gpueb_flat_metadata.h").read_text()
        board = args.tree / manifest["board_directory"]
        check_header(header, manifest)
        check_producer(lambda name: (board / name).read_text(), header, manifest)
        source = (args.consumer.read_text() if args.consumer else
                  integrate((OWNER / "gpueb-flat-analysis.c").read_text(), header))
        require(source.count(header) == 1, "consumer must embed the reviewed metadata helper once")
        check_consumer(source)
    except (OSError, ValueError) as error:
        parser.exit(1, f"GPUEB metadata static gate failed: {error}\n")
    print("Actual v1 producer and existing-owner integration pass static checks; no execution permission")


if __name__ == "__main__":
    main()
