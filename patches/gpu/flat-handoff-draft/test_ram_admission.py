#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Source-only gates, including pinned Linux API semantics. No C execution."""
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LINUX_REV = "d84b264a54a37611f2f46bc19363cb9b41606205"
KERNEL = Path(os.environ.get("TETRIS_KERNEL_TREE", ROOT.parent / f"linux-{LINUX_REV}"))
SOURCE = (HERE / "gpueb-flat-analysis.c").read_text()
TOKENS = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:(?:\\.)|[^\'\\])*\'', re.S)


def without_comments(source):
    return TOKENS.sub(lambda m: "" if m[0].startswith(("/*", "//")) else m[0], source)


def function(source, name):
    text = without_comments(source)
    match = re.search(r"\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", text)
    if not match:
        raise AssertionError(f"missing function {name}")
    start = match.end()
    depth = 1
    # Mask strings so braces in a literal cannot change function boundaries.
    masked = TOKENS.sub(lambda m: " " * len(m[0]), text)
    for end in range(start, len(text)):
        depth += (masked[end] == "{") - (masked[end] == "}")
        if not depth:
            return text[start:end]
    raise AssertionError(f"unclosed function {name}")


def compact(text):
    return re.sub(r"\s+", " ", text).strip()


class RamAdmission(unittest.TestCase):
    def terms(self, body, *terms):
        normalized = compact(body)
        for term in terms:
            self.assertIn(compact(term), normalized)

    def test_catalogue_requires_plain_exact_producer_node(self):
        body = function(SOURCE, "flat_plain_reservation")
        self.terms(body, '!memory || memory->ops',
                   '!of_device_is_available(node)',
                   '!of_find_property(node, "no-map", &length) || length',
                   'of_find_property(node, "compatible", NULL)',
                   'of_find_property(node, "reusable", NULL)',
                   'of_n_addr_cells(node) != 2 || of_n_size_cells(node) != 2',
                   '!of_find_property(node, "reg", &length) || length != 16',
                   'of_find_node_by_path("/reserved-memory")',
                   'node->parent == parent',
                   'of_n_addr_cells(parent) == 2 && of_n_size_cells(parent) == 2',
                   'of_find_property(parent, "ranges", &length) && !length',
                   'resource.start == memory->base',
                   'resource_size(&resource) == memory->size', 'of_node_put(parent)')
        probe = function(SOURCE, "flat_probe")
        self.assertLess(probe.index("flat_plain_reservation("), probe.index("of_node_put(node)"))
        self.assertLess(probe.index("flat_plain_reservation("), probe.index("flat_claim_reserved_ram("))

    def test_gap_free_top_level_resource_coverage(self):
        body = function(SOURCE, "flat_reserved_resource")
        self.terms(body, 'resource->flags != IORESOURCE_MEM',
                   'resource->desc != IORES_DESC_NONE',
                   'resource->parent != &iomem_resource',
                   'resource->start != check->cursor',
                   'resource->end < resource->start',
                   'resource->end >= check->end', 'return -ENXIO;',
                   'check->cursor = resource->end + 1;')
        self.assertNotIn("resource->name", body)
        self.assertNotIn("resource->child", body)
        body = function(SOURCE, "flat_normal_reserved_ram")
        self.terms(body, '.cursor = memory->base', '.end = memory->base + memory->size',
                   'memory->base, check.end - 1, &check, flat_reserved_resource',
                   'if (ret || check.cursor != check.end)', 'return ret ? ret : -ENXIO;')

    def test_whole_reservation_is_dram_and_retained_nomap(self):
        body = function(SOURCE, "flat_normal_reserved_ram")
        self.terms(body, '(memory->base | memory->size) & (PAGE_SIZE - 1)',
                   'for_each_node_by_type(node, "memory")',
                   'resource.start <= memory->base && resource.end >= check.end - 1',
                   'IORESOURCE_SYSTEM_RAM, IORES_DESC_NONE) != REGION_DISJOINT',
                   'address = memory->base; address < check.end; address += PAGE_SIZE',
                   '(phys_addr_t)pfn != address >> PAGE_SHIFT || pfn_is_map_memory(pfn)')
        self.assertLess(body.index("check.cursor != check.end"), body.index("pfn_is_map_memory("))
        self.assertNotRegex(without_comments(SOURCE), r"\bmemblock_\w+\s*\(")

    def test_full_exclusive_claim_and_nested_container_rejection(self):
        body = function(SOURCE, "flat_claim_reserved_ram")
        self.terms(body, 'request_mem_region_exclusive(memory->base, memory->size, "gpueb-flat-analysis")',
                   'if (!claim) return -EBUSY;', 'analysis->reservation = claim;',
                   'claim->start != memory->base',
                   'resource_size(claim) != memory->size || claim->child',
                   'claim->flags != (IORESOURCE_MEM | IORESOURCE_BUSY | IORESOURCE_EXCLUSIVE)',
                   'claim->desc != IORES_DESC_NONE || !parent',
                   'parent->parent != &iomem_resource || parent->flags != IORESOURCE_MEM',
                   'parent->desc != IORES_DESC_NONE || !parent->name',
                   'strcmp(parent->name, "reserved")',
                   'parent->start > claim->start || parent->end < claim->end')
        self.assertLess(body.index("analysis->reservation = claim"), body.index("claim->start !="))
        self.assertEqual(body.count("flat_normal_reserved_ram(memory)"), 2)
        self.assertLess(body.index("flat_normal_reserved_ram(memory)"), body.index("request_mem_region_exclusive("))
        self.assertGreater(body.rindex("flat_normal_reserved_ram(memory)"), body.index("parent->start >"))
        self.assertNotRegex(without_comments(SOURCE), r"\bdevm_\w+\s*\(")

    def test_claim_failure_never_reaches_mapping(self):
        body = function(SOURCE, "flat_probe")
        self.terms(body, 'ret = flat_claim_reserved_ram(analysis, memory); if (ret) goto release;')
        self.assertLess(body.index("flat_claim_reserved_ram("), body.index("memremap("))
        self.assertEqual(body.count("memremap("), 1)
        self.assertEqual(body.count("memunmap("), 1)
        self.assertLess(body.index("memunmap(mapping)"), body.index("crypto_alloc_shash("))

    def test_all_post_claim_failures_erase_then_release(self):
        body = function(SOURCE, "flat_probe")
        self.terms(body, 'if (!analysis->snapshot) { ret = -ENOMEM; goto release; }',
                   'if (!mapping) { ret = -ENOMEM; goto erase; }',
                   'if (IS_ERR(hash)) { ret = PTR_ERR(hash); goto erase; }',
                   'if (!desc) { crypto_free_shash(hash); ret = -ENOMEM; goto erase; }',
                   'memzero_explicit(digest, sizeof(digest)); if (ret) goto erase;',
                   'ret = misc_register(&analysis->misc); if (ret) goto erase;')
        tail = body.split("erase:", 1)[1]
        self.terms(tail, 'kvfree_sensitive(analysis->snapshot, size);',
                   'release: if (analysis->reservation)',
                   'release_mem_region(analysis->reservation->start, resource_size(analysis->reservation));',
                   'kfree(analysis); return ret;')
        self.assertLess(tail.index("kvfree_sensitive("), tail.index("release_mem_region("))
        self.assertLess(tail.index("release_mem_region("), tail.index("kfree(analysis)"))
        self.assertEqual(body.count("release_mem_region("), 1)

    def test_success_keeps_exclusive_boot_owner(self):
        body = function(SOURCE, "flat_probe")
        success = body.split("platform_set_drvdata(pdev, analysis);", 1)[1].split("erase:", 1)[0]
        self.assertEqual(compact(success), "return 0;")
        body = function(SOURCE, "flat_bound_probe")
        self.terms(body, 'if (!try_module_get(THIS_MODULE)) return -ENODEV;',
                   'ret = flat_probe(pdev); if (ret) module_put(THIS_MODULE);')
        self.assertNotRegex(without_comments(SOURCE), r"\.remove(?:_new)?\s*=|\.shutdown\s*=")
        self.assertIn(".suppress_bind_attrs = true", SOURCE)

    def test_read_and_authentication_surface_stays_bounded(self):
        self.terms(function(SOURCE, "flat_read"), 'if (!capable(CAP_SYS_RAWIO)) return -EPERM;',
                   'analysis->snapshot, analysis->size')
        body = function(SOURCE, "flat_probe")
        self.terms(body, 'memory->size != 0x100000', 'memory->base & 0xffff',
                   'memory->base > 0x80000000ULL - memory->size',
                   'size != 156064 || size > memory->size',
                   '!expected || length != sizeof(digest)',
                   'memremap(memory->base, size, MEMREMAP_WB)',
                   'crypto_shash_digest(desc, analysis->snapshot, size, digest)',
                   'if (!ret && memcmp(digest, expected, sizeof(digest))) ret = -EBADMSG;',
                   'analysis->misc.mode = 0600;')
        self.assertLess(body.index("memcmp(digest, expected"), body.index("misc_register("))
        self.assertNotRegex(without_comments(SOURCE),
                            r"\b(?:readl|writel|ioremap\w*|arm_smccc_smc|rproc_boot|request_firmware)\s*\(")

    def test_pinned_failed_init_catalogue_and_pfn_lifetime(self):
        rmem = (KERNEL / "drivers/of/of_reserved_mem.c").read_text()
        self.terms(function(rmem, "fdt_init_reserved_mem_node"),
                   'if (err != 0 && err != -ENOENT)',
                   'if (nomap) memblock_clear_nomap(rmem->base, rmem->size);')
        saved = function(rmem, "fdt_reserved_mem_save_node")
        self.assertLess(saved.index("fdt_init_reserved_mem_node(rmem)"), saved.index("reserved_mem_count++"))
        self.assertIn("return &reserved_mem[i];", function(rmem, "of_reserved_mem_lookup"))
        init = (KERNEL / "arch/arm64/mm/init.c").read_text()
        self.assertIn("return memblock_is_map_memory(addr);", function(init, "pfn_is_map_memory"))
        self.assertIn("EXPORT_SYMBOL(pfn_is_map_memory);", init)
        self.assertIn("select ARCH_KEEP_MEMBLOCK", (KERNEL / "arch/arm64/Kconfig").read_text())

    def test_pinned_walker_omits_names_and_children(self):
        resources = (KERNEL / "kernel/resource.c").read_text()
        body = function(resources, "find_next_iomem_res")
        copied = body.split("*res = (struct resource)", 1)[1].split("};", 1)[0]
        self.terms(copied, '.start = max(start, p->start)', '.end = min(end, p->end)',
                   '.flags = p->flags', '.desc = p->desc', '.parent = p->parent')
        self.assertNotIn(".name", copied)
        self.assertNotIn(".child", copied)
        self.assertIn("EXPORT_SYMBOL_GPL(walk_iomem_res_desc);", resources)
        self.terms(function(resources, "__walk_iomem_res_desc"), 'if (ret) break;', 'start = res.end + 1;')
        setup = (KERNEL / "arch/arm64/kernel/setup.c").read_text()
        self.terms(function(setup, "request_standard_resources"),
                   'if (memblock_is_nomap(region))', 'res->name = "reserved";',
                   'res->flags = IORESOURCE_MEM;', 'insert_resource(&iomem_resource, res);')

    def test_pinned_claim_descends_nonbusy_and_excludes_conflicts(self):
        resources = (KERNEL / "kernel/resource.c").read_text()
        body = function(resources, "__request_region_locked")
        self.terms(body, 'res->start = start;', 'res->end = start + n - 1;',
                   'res->flags |= IORESOURCE_BUSY | flags;', 'res->desc = parent->desc;',
                   'conflict = __request_resource(parent, res);',
                   'if (!(conflict->flags & IORESOURCE_BUSY)) { parent = conflict; continue; }',
                   'return -EBUSY;')
        self.assertIn('EXPORT_SYMBOL(__request_region);', resources)
        self.assertIn('EXPORT_SYMBOL(__release_region);', resources)
        header = (KERNEL / "include/linux/ioport.h").read_text()
        macro = header.split('#define request_mem_region_exclusive(start,n,name)', 1)[1].split('#define', 1)[0]
        self.terms(macro, '__request_region(&iomem_resource, (start), (n), (name), IORESOURCE_EXCLUSIVE)')

    def test_safe_producer_chain_is_unchanged(self):
        producer = (HERE / "tetris_gpueb_flat.c").read_text()
        ordered = ['ret = tetris_gpueb_authenticate(', 'if (!reviewed(metadata.plaintext))',
                   'ret = lmb_alloc_mem(', 'ret = tetris_scp_crypto_check_image(',
                   'memcpy(image->mapping,', 'ret = tetris_scp_crypto_decrypt(', '*result = image;']
        positions = [producer.index(term) for term in ordered]
        self.assertEqual(positions, sorted(positions))
        publication = (HERE / "tetris_gpueb_flat_publish.c").read_text()
        self.assertIn('fdt_setprop(fdt, node, "no-map", NULL, 0)', publication)
        self.assertNotIn('fdt_setprop_string(fdt, node, "compatible"', publication)
        self.assertNotIn('"reusable"', publication)
        hook = (HERE / "tetris_gpueb_flat_hook.c").read_text()
        self.assertLess(hook.index("tetris_gpueb_flat_retain("), hook.index("tetris_gpueb_flat_publish("))

    def test_generator_is_deterministic_and_embeds_authoritative_source(self):
        spec = importlib.util.spec_from_file_location("flat_consumer_generator", HERE / "generate_consumer_patch.py")
        generator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generator)
        patch = generator.render(SOURCE)
        self.assertEqual(patch, generator.render(SOURCE))
        added = patch.split("+++ b/drivers/misc/gpueb-flat-analysis.c\n", 1)[1]
        header, *lines = added.splitlines()
        self.assertEqual(header, f"@@ -0,0 +1,{len(SOURCE.splitlines())} @@")
        self.assertTrue(all(line.startswith("+") for line in lines))
        self.assertEqual("\n".join(line[1:] for line in lines) + "\n", SOURCE)
        shipping = ROOT / "pmaports/device/testing/linux-postmarketos-mediatek-mt6878/0120-misc-tetris-gpueb-authenticated-ram-analysis.patch"
        self.assertEqual(patch.split("diff --git a/drivers/misc/gpueb-flat-analysis.c", 1)[0],
                         shipping.read_text().split("diff --git a/drivers/misc/gpueb-flat-analysis.c", 1)[0])
        for invalid in ("", "int missing_newline;"):
            with self.assertRaises(ValueError):
                generator.render(invalid)

    def test_snapshot_covers_admission_source_and_source_only_tests(self):
        entries = dict(line.split("  ", 1)[::-1] for line in
                       (HERE / "SNAPSHOT.sha256").read_text().splitlines())
        for name in ("gpueb-flat-analysis.c", "generate_consumer_patch.py", "test_ram_admission.py"):
            self.assertIn(name, entries)
        for name, digest in entries.items():
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), digest, name)


if __name__ == "__main__":
    unittest.main()
