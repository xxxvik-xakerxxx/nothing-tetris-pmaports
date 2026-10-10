#!/usr/bin/env python3
"""ARM64 ELF version-aware dependency audit; no library loading or execution."""
import hashlib
import io
from elftools.elf.elffile import ELFFile


def decode(raw, path):
    elf = ELFFile(io.BytesIO(raw))
    if elf.elfclass != 64 or not elf.little_endian or elf["e_machine"] != "EM_AARCH64" \
            or elf["e_type"] != "ET_DYN":
        raise ValueError("provider must be little-endian ARM64 ET_DYN")
    dynamic = elf.get_section_by_name(".dynamic")
    dynsym = elf.get_section_by_name(".dynsym")
    if dynamic is None or dynsym is None:
        raise ValueError("missing dynamic symbol metadata")
    needed, sonames = [], []
    for tag in dynamic.iter_tags():
        if tag.entry.d_tag == "DT_NEEDED":
            needed.append(tag.needed)
        elif tag.entry.d_tag == "DT_SONAME":
            sonames.append(tag.soname)
    if len(sonames) != 1:
        raise ValueError("single SONAME required (linker64 legitimately supplies ld-android.so)")
    version_map = {}
    requirements = elf.get_section_by_name(".gnu.version_r")
    if requirements:
        for requirement, auxiliaries in requirements.iter_versions():
            for aux in auxiliaries:
                index = aux["vna_other"] & 0x7fff
                if index in version_map:
                    raise ValueError("duplicate version index")
                version_map[index] = {"name": aux.name, "provider": requirement.name,
                                      "hash": aux["vna_hash"]}
    definitions = elf.get_section_by_name(".gnu.version_d")
    if definitions:
        for definition, auxiliaries in definitions.iter_versions():
            names = [aux.name for aux in auxiliaries]
            index = definition["vd_ndx"] & 0x7fff
            if not names or index in version_map:
                raise ValueError("invalid version definition")
            version_map[index] = {"name": names[0], "provider": sonames[0],
                                  "hash": definition["vd_hash"]}
    versions = elf.get_section_by_name(".gnu.version")
    symbols = []
    for index, symbol in enumerate(dynsym.iter_symbols()):
        if not symbol.name:
            continue
        raw_index = versions.get_symbol(index)["ndx"] if versions else "VER_NDX_GLOBAL"
        numeric = raw_index if isinstance(raw_index, int) else \
            {"VER_NDX_LOCAL": 0, "VER_NDX_GLOBAL": 1}[raw_index]
        ver_index = numeric & 0x7fff
        if ver_index > 1 and ver_index not in version_map:
            raise ValueError("unresolved symbol version index")
        # Index1 is VER_NDX_GLOBAL even when a base VERDEF names the SONAME.
        # Treating base index1 as a named version fabricates loader failures.
        version = version_map.get(ver_index) if ver_index > 1 else None
        symbols.append({"name": symbol.name, "undefined": symbol["st_shndx"] == "SHN_UNDEF",
                        "type": symbol["st_info"]["type"], "binding": symbol["st_info"]["bind"],
                        "visibility": symbol["st_other"]["visibility"], "version": version,
                        "hidden_version": bool(numeric & 0x8000), "local_version": ver_index == 0})
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "soname": sonames[0], "needed": needed, "symbols": symbols}


def matches(request, symbol, provider):
    if symbol["undefined"] or symbol["name"] != request["name"] or symbol["local_version"] \
            or symbol["binding"] not in ("STB_GLOBAL", "STB_WEAK") \
            or symbol["visibility"] not in ("STV_DEFAULT", "STV_PROTECTED"):
        return False
    # ARM64 GNU IFUNC has ELF type10, rendered STT_LOOS by pyelftools. Bionic
    # libc's memcpy/strcmp/etc legitimately provide function imports this way.
    callable_types = ("STT_FUNC", "STT_GNU_IFUNC", "STT_LOOS")
    if request["type"] != "STT_NOTYPE" and symbol["type"] != request["type"] and not \
            (request["type"] == "STT_FUNC" and symbol["type"] in callable_types):
        return False
    version = request["version"]
    if version:
        return provider == version["provider"] and symbol["version"] is not None \
            and symbol["version"]["name"] == version["name"] \
            and symbol["version"].get("hash") == version.get("hash")
    return not symbol["hidden_version"]


def resolve(images, root="libmipc.so"):
    queue, visited, missing, errors, bindings, weak = [root], set(), set(), [], [], []
    while queue:
        name = queue.pop(0)
        if name in visited:
            continue
        visited.add(name)
        if name not in images:
            missing.add(name)
            continue
        queue.extend(images[name]["needed"])
    reachable = {name: images[name] for name in visited if name in images}
    for name, image in reachable.items():
        for request in image["symbols"]:
            if not request["undefined"] or request["local_version"]:
                continue
            providers = [provider for provider, candidate in reachable.items()
                         if any(matches(request, symbol, provider) for symbol in candidate["symbols"])]
            if not providers:
                item = {"consumer": name, "symbol": request["name"], "version": request["version"]}
                (weak if request["binding"] == "STB_WEAK" else errors).append(item)
            else:
                bindings.append({"consumer": name, "symbol": request["name"],
                                 "version": request["version"], "providers": sorted(providers)})
    # Runtime dlsym targets are not undefined symbols; check their actual owner.
    trm = reachable.get("libtrm.so")
    for name in ("libtrm_init", "libtrm_deinit", "libtrm_reset", "libtrm_power_off_md",
                 "libtrm_power_on_md", "libtrm_md_event_register"):
        request = {"name": name, "type": "STT_FUNC", "version": None}
        if trm and not any(matches(request, symbol, "libtrm.so") for symbol in trm["symbols"]):
            errors.append({"consumer": "libmipc.so dlopen/dlsym", "symbol": name, "version": None})
    return {"providers": {name: {k: image[k] for k in ("path", "sha256", "needed")}
                          for name, image in sorted(reachable.items())},
            "missing_libraries": sorted(missing), "unresolved_required_symbols": errors,
            "unresolved_weak_symbols": weak, "resolved_versioned_bindings": bindings,
            "versioned_symbol_closure_complete": not (missing or errors),
            "runtime_namespace_and_services_proven": False, "engine_readiness": False}
