#!/usr/bin/env python3
"""Read actual ELF/config/export ABI evidence; never execute target code."""
import hashlib
import re
import struct
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def config(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r"CONFIG_([A-Z0-9_]+)=(.*)|# CONFIG_([A-Z0-9_]+) is not set", line)
        if not match:
            continue
        name = match[1] or match[3]
        require(name not in result, "duplicate kernel config: " + name)
        result[name] = match[2] if match[1] else "n"
    require(result, "empty kernel config")
    return result


def security_profile(shipping, candidate):
    # Keep the shipping security/code-generation ABI, including disabled options.
    prefixes = ("CFI", "LTO", "STACKPROTECTOR", "INIT_STACK", "INIT_ON_", "RANDSTRUCT",
                "MODULE_SIG", "MODVERSIONS", "BASIC_MODVERSIONS", "EXTENDED_MODVERSIONS",
                "SECURITY", "LSM", "HARDENED", "STRICT_KERNEL", "STRICT_MODULE", "VMAP_STACK")
    prefixes += ("ARM64_",)
    exact = {"MODULES", "SMP", "ARM64", "FRAME_POINTER", "MODPROBE_PATH",
             "MODULE_ALLOW_MISSING_NAMESPACE_IMPORTS", "MODULE_FORCE_LOAD",
             "MODULE_FORCE_UNLOAD", "TRIM_UNUSED_KSYMS"}
    names = {name for name in shipping.keys() | candidate.keys()
             if name.startswith(prefixes) or name in exact}
    changed = {name: {"shipping": shipping.get(name, "n"), "candidate": candidate.get(name, "n")}
               for name in sorted(names) if shipping.get(name, "n") != candidate.get(name, "n")}
    require(not changed, "shipping security/ABI profile changed: " + repr(changed))
    return {name: candidate.get(name, "n") for name in sorted(names)}


def symvers(text):
    result = {}
    for line in text.splitlines():
        fields = line.split("\t")
        require(len(fields) == 5 and re.fullmatch(r"0x[0-9a-fA-F]{8}", fields[0]),
                "malformed actual Module.symvers row")
        crc, name, owner, export, namespace = fields
        require(name and owner and not re.search(r"\s", name + owner) and
                export in ("EXPORT_SYMBOL", "EXPORT_SYMBOL_GPL"), "invalid export identity")
        require(name not in result, "duplicate export in table: " + name)
        result[name] = {"crc": int(crc, 16), "owner": owner, "export": export, "namespace": namespace}
    require(result, "empty actual export table")
    return result


def export_index(tables):
    result = {}
    for table_name, rows in tables.items():
        for name, row in rows.items():
            require(name not in result, "ambiguous export across genuine tables: " + name)
            result[name] = {**row, "table": table_name}
    return result


def owner_name(path):
    return Path(path).name.replace("-", "_")


def namespace_allowed(namespace, module, imported):
    if not namespace or namespace in imported:
        return True
    if namespace.startswith("module:"):
        # Match d84 modpost's tail-glob semantics, not a general shell glob.
        for pattern in namespace[7:].split(","):
            if pattern.endswith("*") and module.startswith(pattern[:-1]):
                return True
            if module == pattern:
                return True
    return False


def decode_versions(basic, extended_crcs, extended_names, cfg):
    if cfg.get("MODVERSIONS", "n") != "y":
        require(not any((basic, extended_crcs, extended_names)), "version section contradicts MODVERSIONS=n")
        return {}, "disabled_by_inherited_config"
    versions = {}
    if cfg.get("EXTENDED_MODVERSIONS", "n") == "y":
        require(extended_crcs is not None and extended_names is not None and
                len(extended_crcs) % 4 == 0, "missing/misaligned extended CRC sections")
        crcs = list(struct.unpack("<" + "I" * (len(extended_crcs) // 4), extended_crcs))
        names = extended_names.split(b"\0")
        # C concatenated literals retain their final implicit NUL as well.
        require(len(names) in (len(crcs) + 1, len(crcs) + 2) and
                all(part == b"" for part in names[len(crcs):]), "extended CRC/name count differs")
        for raw, crc in zip(names, crcs):
            name = raw.decode("ascii")
            require(name and name not in versions, "empty/duplicate extended version name")
            versions[name] = crc
    else:
        require(not extended_crcs and not extended_names, "unexpected extended CRC sections")
    if cfg.get("BASIC_MODVERSIONS", "n") == "y":
        require(basic is not None and len(basic) % 64 == 0, "missing/misaligned ARM64 basic version section")
        short = {}
        for at in range(0, len(basic), 64):
            crc = struct.unpack_from("<Q", basic, at)[0]
            raw = basic[at + 8:at + 64]
            require(b"\0" in raw and crc <= 0xffffffff, "malformed ARM64 version row")
            name = raw.split(b"\0", 1)[0].decode("ascii")
            require(name and name not in short, "empty/duplicate basic version name")
            short[name] = crc
        if cfg.get("EXTENDED_MODVERSIONS", "n") == "y":
            require(short == {name: crc for name, crc in versions.items() if len(name) < 56},
                    "basic/extended CRCs disagree")
        else:
            versions = short
    else:
        require(not basic, "unexpected basic CRC section")
    require(cfg.get("BASIC_MODVERSIONS") == "y" or cfg.get("EXTENDED_MODVERSIONS") == "y",
            "MODVERSIONS enabled without a supported actual version format")
    return versions, "enforced_by_inherited_config"


def check_linked_type(elf_type, path, cfg=None, module=True):
    expected = "ET_REL"
    if not module:
        # d84 arch/arm64/Makefile: RELOCATABLE=y links -shared -Bsymbolic;
        # scripts/Makefile.vmlinux's objcopy does not change the ELF type.
        # Existing kernel callers omit cfg: use the actual adjacent build config,
        # never infer admission from ET_DYN or fall back to shipping defaults.
        if cfg is None:
            actual = Path(path).parent / ".config"
            require(actual.is_file(), "linked kernel has no actual build config: " + str(actual))
            cfg = config(actual.read_text())
        require(cfg.get("ARM64") == "y" and cfg.get("RELOCATABLE") in ("y", "n"),
                "linked kernel requires explicit ARM64/RELOCATABLE config")
        expected = "ET_DYN" if cfg["RELOCATABLE"] == "y" else "ET_EXEC"
    require(elf_type == expected, "wrong linked ELF type: expected " + expected + ", got " + str(elf_type))


def elf(path, cfg=None, module=True):
    # pyelftools is already used by the repository's genuine ELF evidence reader.
    from elftools.elf.elffile import ELFFile
    with Path(path).open("rb") as stream:
        image = ELFFile(stream)
        require(image.elfclass == 64 and image.little_endian and image["e_machine"] == "EM_AARCH64",
                "not real little-endian ARM64 ELF: " + str(path))
        check_linked_type(image["e_type"], path, cfg, module)
        symbols = image.get_section_by_name(".symtab")
        require(symbols is not None, "linked ELF has no actual symbol table")
        definitions, imports = set(), {}
        for symbol in symbols.iter_symbols():
            if not symbol.name:
                continue
            if symbol["st_shndx"] == "SHN_UNDEF":
                if symbol["st_info"]["bind"] in ("STB_GLOBAL", "STB_WEAK"):
                    imports[symbol.name] = symbol["st_info"]["bind"]
            else:
                definitions.add(symbol.name)
        result = {"machine": "AArch64", "elf_type": image["e_type"],
                  "sha256": sha(path), "definitions": definitions, "imports": imports}
        if not module:
            return result
        info = image.get_section_by_name(".modinfo")
        require(info is not None, "linked module has no .modinfo")
        metadata = {}
        for row in info.data().split(b"\0"):
            if not row:
                continue
            name, sep, value = row.decode().partition("=")
            require(sep, "malformed module metadata")
            metadata.setdefault(name, []).append(value)
        for name in ("name", "vermagic"):
            require(len(metadata.get(name, [])) == 1, "missing/ambiguous module metadata: " + name)
        require(metadata.get("license"), "missing module license metadata")
        def data(name):
            section = image.get_section_by_name(name)
            return section.data() if section is not None else None
        versions, crc_mode = decode_versions(data("__versions"), data("__version_ext_crcs"),
                                            data("__version_ext_names"), cfg)
        result.update(metadata=metadata, versions=versions, crc_mode=crc_mode)
        return result


def closure(module, exports, cfg):
    info = module["metadata"]
    name = info["name"][0]
    # B4.1 ccci_md_all retains GPL declarations from core and platform objects.
    require(info.get("license") and set(info["license"]) == {"GPL"}, "unexpected module license")
    imported_ns = set(info.get("import_ns", []))
    owners, optional = {}, []
    for symbol, binding in sorted(module["imports"].items()):
        row = exports.get(symbol)
        if row is None and binding == "STB_WEAK":
            optional.append(symbol)
            continue
        require(row is not None, "unresolved actual strong import: " + symbol + " in " + name)
        require(owner_name(row["owner"]) != name, "self-exported unresolved import: " + symbol)
        require(namespace_allowed(row["namespace"], name, imported_ns), "missing import namespace: " + symbol)
        owners[symbol] = row
    expected_deps = {owner_name(row["owner"]) for row in owners.values() if row["owner"] != "vmlinux"}
    deps = {entry.replace("-", "_") for value in info.get("depends", []) for entry in value.split(",") if entry}
    require(deps == expected_deps, "actual modinfo dependency closure differs in " + name)
    if cfg.get("MODVERSIONS", "n") == "y":
        expected = set(owners) | {"module_layout"}
        require(set(module["versions"]) == expected, "actual module CRC import inventory differs in " + name)
        for symbol, crc in module["versions"].items():
            require(symbol in exports and crc == exports[symbol]["crc"], "actual CRC mismatch: " + symbol)
    else:
        require(not module["versions"], "fabricated CRC enforcement with MODVERSIONS=n")
        require(all(row["crc"] == 0 for row in owners.values()), "nonzero export CRC contradicts inherited config")
    return {"imports": owners, "optional_unresolved_weak": optional,
            "depends": sorted(deps), "crc_status": module["crc_mode"],
            "crc_count": len(module["versions"]), "runtime_status": "not_loaded_or_executed"}
