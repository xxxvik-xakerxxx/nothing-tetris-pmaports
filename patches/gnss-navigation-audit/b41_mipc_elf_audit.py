#!/usr/bin/env python3
"""Read-only B4.1 MIPC ELF evidence extraction; never loads/executes libraries.

Exit0 means ELF compatibility evidence collected, NOT a verified tag/lifetime
contract. Exit2 means a missing asset/structural dependency. Bounds, C types and
ownership cannot be certified from exported names and remain explicit unknowns.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile
from elftools.common.exceptions import ELFError

MNLD_SHA = "285e11f27be29430580d1759b9ed60f21923c4ed7d77c1aba7f6a413faac2e83"
MNL_SHA = "3b3501d46031fb22cf399f3495211a3d2202acd04df489fa827e383852ceff90"
API = ("SETCOM", "mipc_msg_set_timeout_once", "mipc_init", "mipc_msg_init",
       "mipc_msg_sync_timeout_with_cause", "mipc_msg_get_val_ptr",
       "mipc_msg_deinit", "mipc_deinit")


def read_elf(path, expected_sha=None):
    # Hash and parse the same immutable bytes, including in-place replacement.
    with path.open("rb") as stream:
        raw = stream.read()
        digest = hashlib.sha256(raw).hexdigest()
        if expected_sha is not None and digest != expected_sha:
            raise ValueError(f"SHA256 mismatch: {path}")
        elf = ELFFile(io.BytesIO(raw))
        if elf.elfclass != 64 or not elf.little_endian or \
                elf["e_machine"] != "EM_AARCH64" or elf["e_type"] != "ET_DYN":
            raise ValueError(f"not little-endian ARM64 ET_DYN: {path}")
        dynamic = elf.get_section_by_name(".dynamic")
        symbols = elf.get_section_by_name(".dynsym")
        if dynamic is None or symbols is None:
            raise ValueError(f"missing dynamic sections: {path}")
        tags = {"DT_NEEDED": [], "DT_SONAME": [], "DT_RPATH": [], "DT_RUNPATH": []}
        fields = {"DT_NEEDED": "needed", "DT_SONAME": "soname",
                  "DT_RPATH": "rpath", "DT_RUNPATH": "runpath"}
        for tag in dynamic.iter_tags():
            if tag.entry.d_tag in fields:
                tags[tag.entry.d_tag].append(getattr(tag, fields[tag.entry.d_tag]))
        syms = [{"name": s.name, "address": s["st_value"], "size": s["st_size"],
                 "type": s["st_info"]["type"], "binding": s["st_info"]["bind"],
                 "visibility": s["st_other"]["visibility"],
                 "undefined": s["st_shndx"] == "SHN_UNDEF"}
                for s in symbols.iter_symbols()]
        segments = [{"address": s["p_vaddr"], "flags": s["p_flags"], "data": s.data()}
                    for s in elf.iter_segments() if s["p_type"] == "PT_LOAD"]
    return {"path": str(path.resolve()), "sha256": digest, "dynamic": tags,
            "symbols": syms, "segments": segments}


def bytes_at(image, address, size, executable=False):
    if size < 0:
        raise ValueError("negative extent")
    for segment in image["segments"]:
        start, data = segment["address"], segment["data"]
        if start <= address and address + size <= start + len(data) and \
                (not executable or segment["flags"] & 1):
            return data[address - start:address - start + size]
    raise ValueError(f"unbacked/non-executable extent: {address:#x}+{size:#x}")


def export(image, name):
    candidates = [s for s in image["symbols"] if s["name"] == name and
                  not s["undefined"] and s["type"] == "STT_FUNC" and
                  s["binding"] in ("STB_GLOBAL", "STB_WEAK") and
                  s["visibility"] in ("STV_DEFAULT", "STV_PROTECTED")]
    if len(candidates) != 1:
        raise ValueError(f"missing/ambiguous callable export: {name}")
    symbol = candidates[0]
    if symbol["size"] == 0 or symbol["address"] % 4 or symbol["size"] % 4:
        raise ValueError(f"unresolved ARM64 function extent: {name}")
    bytes_at(image, symbol["address"], symbol["size"], executable=True)
    return symbol


def disassembly(image, address, size):
    # Bounded evidence, not a claimed complete CFG or type/length proof.
    code = bytes_at(image, address, min(size, 1024), executable=True)
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    result = [{"address": hex(i.address), "mnemonic": i.mnemonic, "operands": i.op_str}
              for i in md.disasm(code, address)]
    return {"instructions": result, "truncated": size > len(code),
            "decoded_bytes": len(result) * 4, "requested_bytes": len(code)}


def audit(mnld, mnl, mipc=None):
    imports = {s["name"] for s in mnld["symbols"] if s["undefined"] and
               s["type"] == "STT_FUNC"}
    if not set(API).issubset(imports):
        raise ValueError("mnld MIPC imports differ from recovered consumer ABI")
    if mnld["dynamic"]["DT_NEEDED"].count("libmipc.so") != 1:
        raise ValueError("mnld libmipc.so dependency mismatch")
    if any("mipc" in n.lower() for n in mnl["dynamic"]["DT_NEEDED"]):
        raise ValueError("unexpected libMNL MIPC dependency")
    report = {
        "mnld_sha256": mnld["sha256"], "libmnl_sha256": mnl["sha256"],
        "mnld_needed": mnld["dynamic"]["DT_NEEDED"],
        "mipc_needed_literal": "libmipc.so",
        "encoded_directory_prefix": None,
        "mnld_search_paths": {k: mnld["dynamic"][k] for k in ("DT_RPATH", "DT_RUNPATH")},
        "library_prefix_note": "DT_NEEDED encodes basename only; /vendor/lib64 versus "
                               "/vendor/lib64/mt6878 requires loader/extraction evidence",
        "engine_readiness": False,
        "contract": {
            "tag_word_required_readable_bytes": 4,
            "tag_extent_at_least_4_proven": False,
            "third_accessor_argument": "NULL in mnld; not proven to be a length output",
            "value_lifetime_until_response_deinit_proven": False,
            "sync_response_ownership_proven": False,
            "raw_wire_framing_proven": False,
            "source_c_signatures_proven": False,
            "consumer_machine_abi": {
                "SETCOM": "x0: endpoint C string; return ignored",
                "mipc_msg_set_timeout_once": "w0:10000/5000; return ignored",
                "mipc_init": "x0:gnss C string; w0 zero accepted",
                "mipc_msg_init": "w0:141,w1:1; x0 request pointer",
                "mipc_msg_sync_timeout_with_cause": "x0 request,x1 response-pointer storage; w0 zero accepted",
                "mipc_msg_get_val_ptr": "x0 response,w1 tag(0/257/258/259),x2 NULL; x0 borrowed pointer read by ldr w",
                "mipc_msg_deinit": "x0 response then request; return ignored",
                "mipc_deinit": "no supplied arguments; return ignored",
            },
        },
        "consumer_evidence": [disassembly(mnld, lo, hi - lo) for lo, hi in
                              ((0x7f4a4, 0x7f5a0), (0x7f610, 0x7f680),
                               (0x7f6a4, 0x7f6b8), (0x7f6e8, 0x7f798))],
    }
    if mipc is None:
        report["structural_status"] = "missing libmipc asset"
        return report, 2
    if Path(mipc["path"]).name != "libmipc.so":
        raise ValueError("future asset basename must be libmipc.so")
    if mipc["dynamic"]["DT_SONAME"] != ["libmipc.so"]:
        raise ValueError("libmipc SONAME mismatch or unresolved")
    exports = [export(mipc, name) for name in API]
    report["libmipc"] = {"path": mipc["path"], "sha256": mipc["sha256"],
                         "dynamic": mipc["dynamic"],
                         "undefined_symbols": sorted({s["name"] for s in mipc["symbols"]
                                                       if s["undefined"] and s["name"]}),
                         "exports": [{**s, "evidence": disassembly(mipc, s["address"], s["size"])}
                                     for s in exports]}
    report["structural_status"] = "compatible ELF exports; semantic contract unresolved"
    return report, 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mnld", type=Path, required=True)
    parser.add_argument("--libmnl", type=Path, required=True)
    parser.add_argument("--libmipc", type=Path)
    parser.add_argument("--libmipc-sha256", help="independent CI manifest pin, never inferred")
    args = parser.parse_args()
    if bool(args.libmipc) != bool(args.libmipc_sha256):
        parser.error("future libmipc asset and independent SHA256 pin must be supplied together")
    if args.libmipc_sha256 and (len(args.libmipc_sha256) != 64 or
                              any(c not in "0123456789abcdef" for c in args.libmipc_sha256)):
        parser.error("SHA256 pin must be64 lowercase hexadecimal digits")
    try:
        report, status = audit(read_elf(args.mnld, MNLD_SHA), read_elf(args.libmnl, MNL_SHA),
                               read_elf(args.libmipc, args.libmipc_sha256) if args.libmipc else None)
    except (OSError, ValueError, ELFError) as error:
        print(json.dumps({"structural_status": "rejected", "error": str(error),
                          "engine_readiness": False}, sort_keys=True))
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
