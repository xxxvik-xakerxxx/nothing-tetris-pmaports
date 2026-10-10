#!/usr/bin/env python3
"""Read-only exact B4.1 MIPC contract and dependency-closure audit.

No ELF loading/execution. Whole-file pin plus raw opcode pins avoid Capstone
version/display differences. Missing dependency files return2, never readiness.
"""
import argparse
import json
from pathlib import Path
from elftools.common.exceptions import ELFError

from b41_mipc_elf_audit import API, bytes_at, export, read_elf

MIPC_SHA = "aecc344486ef18905eaf7b6ef4f8dcaf266e58b2e87a355cd8d2d7b27ae09d56"
NEEDED = ["libmtkrillog.so", "libtrm.so", "libmtkproperty.so", "libc++.so",
          "libc.so", "libm.so", "libdl.so"]
WORDS = {
    0xf214: "f30302aa",  # retains length pointer x2 in x19
    0xf224: "28380012",  # tag masked to15 bits
    0xf23c: "081040f9",  # hashmap node value allocation
    0xf244: "00110091",  # returns allocation+4 (after TLV header)
    0xf24c: "08054079",  # uint16 length at header+2
    0xf260: "68020079",  # uint16 store through third argument
    0xf6cc: "1f1100f1",  # require4 remaining header bytes
    0xf6d4: "f4064079",  # serialized length
    0xf6dc: "e81a4079",  # zero-length branch reads+12 BEFORE12-byte check!
    0xf700: "e5120091",  # payload begins+4
    0xf70c: "1f0118eb",  # remaining payload compared against length
    0xf710: "6b040054",  # insufficient payload rejects message
    0xf734: "84008052",  # copy4 header bytes
    0xf738: "e603142a",  # and selected payload length to hashmap_add2
    0xf740: "f4270079",  # retained original uint16 length header
    0xe678: "a8021b8b",  # allocate header+payload with aligned key/node
    0xe684: "00c10091",  # plus0x30 node header
    0xe6bc: "991300f9",  # store allocated value pointer node+0x20
    0xe6e4: "2003158b",  # copy payload at value+header_size
    0xe6e8: "e2031baa",  # exact payload length to memcpy
    0xedb4: "000c40f9",  # response hashmap
    0xedb8: "36180094",  # deinit frees hashmap nodes
    0xedc8: "d2170014",  # free response object
    0xe178: "e61a0094",  # free each allocation containing copied TLV
    0x10610: "600200f9", # transfers returned response to caller
    0x10618: "42120094", # no output slot => deinit returned response
    0x10970: "953240f9", # returned response from event+0x60
    0xda90: "901c0094",  # pthread_create
    0xda98: "921c0094",  # pthread_detach (NOT join)
    0xdb04: "831c0014",  # DELETE_THREAD simply frees descriptor
    0x107ac: "55110094", # deinit calls DELETE_THREAD, not pthread_join
}


def contract(image):
    if image["sha256"] != MIPC_SHA or image["dynamic"]["DT_SONAME"] != ["libmipc.so"]:
        raise ValueError("not the exact B4.1 libmipc.so profile")
    if image["dynamic"]["DT_NEEDED"] != NEEDED:
        raise ValueError("dependency profile mismatch")
    for name in API:
        export(image, name)
    for address, opcode in WORDS.items():
        if bytes_at(image, address, 4, executable=True).hex() != opcode:
            raise ValueError(f"opcode mismatch at{address:#x}")
    return {
        "sha256": MIPC_SHA,
        "length_output": {"type": "uint16_t*", "read_pc": "0xf24c", "write_pc": "0xf260"},
        "accessor_guarantees_four_bytes": False,
        "mandatory_host_check": "nonnull pointer AND uint16 length>=4 before copying word",
        "payload_storage": "hashmap_add2 copies header4+payload into one owned allocation; "
                           "get_val_ptr returns allocation+4",
        "borrowed_value_validity": "exclusive response ownership; until mutation/deinit; "
                                   "do not retain pointer after copying",
        "response_transfer": "sync_timeout_with_cause writes returned pointer through x1; "
                             "with NULL x1 it deinitializes response",
        "raw_wire": {"header_bytes": 16, "tlv_header_bytes": 4,
                     "tlv_tag_offset": 0, "tlv_u16_length_offset": 2,
                     "regular_tlv_stride": "(payload_length+11)&~7",
                     "zero_length_record": "special12-byte payload, NOT an ordinary empty value"},
        "vendor_parser_fully_bounds_safe": False,
        "vendor_parser_gap": "0xf6dc reads zero-length record+12 after only a4-byte "
                             "remaining-header check; full payload check occurs later0xf70c/710",
        "deinit_is_rx_join_ack": False,
        "lifecycle_gap": "CREATE_THREAD detaches; DELETE_THREAD only frees descriptor; "
                         "mipc_deinit returning is not an RX join acknowledgement",
        "required_lifecycle": "sole owner dedicated child; no unload/reinit/reuse; "
                              "retain resources until parent observes actual child exit",
        "engine_readiness": False,
    }


def dependency_closure(image, directories, reader=read_elf):
    """Audit exact supplied directories, not guessed Android search order.

    No basename substitution, synthetic system libraries or automatic downloads.
    File presence/export-name resolution is not symbol-version or runtime proof.
    """
    loaded = {"libmipc.so": image}
    missing, ambiguous, rejected = set(), {}, {}
    queue = list(image["dynamic"]["DT_NEEDED"])
    visited = set()
    while queue:
        name = queue.pop(0)
        if name in visited:
            continue
        visited.add(name)
        if name != Path(name).name or name in ("", ".", ".."):
            rejected[name] = "dependency is not a safe basename"
            continue
        if name in loaded:
            continue
        candidates = sorted({(directory / name).resolve() for directory in directories
                             if (directory / name).is_file()})
        if not candidates:
            missing.add(name)
            continue
        if len(candidates) != 1:
            ambiguous[name] = [str(p) for p in candidates]
            continue
        try:
            candidate = reader(candidates[0])
            if candidate["dynamic"]["DT_SONAME"] != [name]:
                raise ValueError("SONAME mismatch/unresolved")
        except (OSError, ValueError, ELFError) as error:
            rejected[name] = str(error)
            continue
        loaded[name] = candidate
        queue.extend(candidate["dynamic"]["DT_NEEDED"])
    exports = {s["name"] for library in loaded.values() for s in library["symbols"]
               if not s["undefined"] and s["binding"] in ("STB_GLOBAL", "STB_WEAK")
               and s["visibility"] in ("STV_DEFAULT", "STV_PROTECTED")}
    unresolved = {name: sorted({s["name"] for s in library["symbols"]
                               if s["undefined"] and s["binding"] != "STB_WEAK"
                               and s["name"] and s["name"] not in exports})
                  for name, library in loaded.items()}
    unresolved = {name: values for name, values in unresolved.items() if values}
    complete = not (missing or ambiguous or rejected or unresolved)
    return {"loaded": {name: {"path": value["path"], "sha256": value["sha256"],
                              "needed": value["dynamic"]["DT_NEEDED"]}
                       for name, value in loaded.items()},
            "missing": sorted(missing), "ambiguous": ambiguous, "rejected": rejected,
            "unresolved_required_symbol_names": unresolved,
            "file_and_symbol_name_closure_complete": complete,
            "symbol_versions_and_runtime_abi_proven": False, "engine_readiness": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("libmipc", type=Path)
    parser.add_argument("--dependency-dir", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        image = read_elf(args.libmipc, MIPC_SHA)
        report = {"contract": contract(image),
                  "dependencies": dependency_closure(image, args.dependency_dir)}
    except (OSError, ValueError, ELFError) as error:
        print(json.dumps({"error": str(error), "engine_readiness": False}, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["dependencies"]["file_and_symbol_name_closure_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
