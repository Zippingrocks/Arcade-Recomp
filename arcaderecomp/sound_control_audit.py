"""Metadata-only candidate audit for the unresolved HOTD sound-control aperture.

An aligned opcode match is not an instruction boundary or proof of execution.
The private CLI authenticates the original sound chip before reconstruction.
No register effects or device acceptance are inferred from these references.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zlib

from .m68k import decode, discover
from .roms import load_layout, reconstruct

BASE = 0x600000
MAX_IMAGE = 0x80000
MAX_MATCHES = 1024
CONTROL_FIRST, CONTROL_LAST = 0x400000, 0x400001
LAYOUT = Path(__file__).resolve().parents[1] / "targets/hotd1/original.json"


def _in_aperture(address: int) -> bool:
    return CONTROL_FIRST <= (address & 0xffffff) <= CONTROL_LAST


def analyze(image: bytes, *, base: int, entry: int, cfg_limit: int = 4096) -> dict:
    """Scan every even offset using only the existing decoder's accepted forms.

    Synthetic inputs are allowed here for ROM-free tests. Only the separate
    authenticated CLI may label an input as the original sound ROM.
    """
    if (not isinstance(image, bytes) or not 2 <= len(image) <= MAX_IMAGE or len(image) & 1
            or type(base) is not int or base < 0 or base & 1 or base + len(image) > 2**32
            or type(entry) is not int or entry & 1 or not base <= entry < base + len(image)):
        raise ValueError("Invalid bounded sound image, base or entry")
    instructions, limited = discover(image, entry, base, cfg_limit)
    graph = {ins.pc: ins for ins in instructions}
    stores, materializations, literals = [], [], []
    for offset in range(0, len(image), 2):
        pc = base + offset
        if offset + 4 <= len(image):
            address = int.from_bytes(image[offset:offset + 4], "big")
            if _in_aperture(address):
                literals.append({"location": pc, "upper_byte_is_zero": address >> 24 == 0,
                                 "bus_address": address & 0xffffff})
                if len(stores) + len(materializations) + len(literals) > MAX_MATCHES:
                    raise ValueError("Candidate limit exceeded; no partial report is valid")
        try:
            ins = decode(image, pc, base)
        except ValueError:
            continue
        if ins.mnemonic == "move":
            width, kind, source, mode, reg, address = ins.operands
            if mode != 7 or reg not in (0, 1):
                continue
            bus_address = address & 0xffffff
            # Include a word starting on the high lane and any explicitly
            # decoded store whose byte span touches either control lane.
            if not any(_in_aperture(bus_address + lane) for lane in range(width)):
                continue
            data = ({"kind": "immediate", "value": source, "value_known": True}
                    if kind == 1 else {"kind": "register", "register": f"d{source}",
                                       "value_known": False})
            stores.append({"pc": pc, "width": width, "bus_address": bus_address,
                           "addressing": "absolute_short" if reg == 0 else "absolute_long",
                           "source": data, "in_supported_static_graph": pc in graph,
                           "instruction_boundary_verified": False,
                           "execution_verified": False, "device_effect_verified": False})
        elif ins.mnemonic == "lea_absolute":
            reg, address = ins.operands
            if _in_aperture(address):
                materializations.append({"pc": pc, "destination": f"a{reg}",
                                         "address_value": address,
                                         "in_supported_static_graph": pc in graph,
                                         "instruction_boundary_verified": False})
        if len(stores) + len(materializations) + len(literals) > MAX_MATCHES:
            raise ValueError("Candidate limit exceeded; no partial report is valid")
    return {
        "schema": "hotdo-sound-control-candidates-v1",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_size": len(image), "base": base, "entry": entry,
        "provenance": "caller-supplied bytes; not authenticated by analyzer",
        "aperture": {"first": CONTROL_FIRST, "last": CONTROL_LAST},
        "scan": {"stride": 2, "examined_offsets": len(image) // 2,
                 "complete_for_declared_patterns": True,
                 "patterns": ["supported absolute MOVE stores", "supported absolute LEA",
                              "aligned 32-bit address values with 24-bit bus masking"],
                 "all_references_recovered": False,
                 "indirect_references_resolved": False,
                 "data_may_match_instruction_patterns": True},
        "static_graph": {"sites": len(graph), "limit": cfg_limit,
                         "limit_reached": limited,
                         "stop_sites": sorted(pc for pc, ins in graph.items()
                                              if ins.mnemonic in ("unsupported", "invalid_fetch")),
                         "models_device_acceptance": False,
                         "proves_execution_or_order": False},
        "store_candidates": stores, "address_materializations": materializations,
        "aligned_address_values": literals,
        "hardware_semantics_verified": False, "runtime_behavior_changed": False,
    }


def authenticate_chip(path: Path) -> tuple[bytes, dict]:
    region = next(r for r in load_layout(LAYOUT)["regions"] if r["name"] == "audiocpu")
    spec = region["loads"][0]
    expected_size = int(spec["size"], 0)
    with path.open("rb") as stream:
        chip = stream.read(expected_size + 1)
    if (len(chip) != expected_size or hashlib.sha1(chip).hexdigest() != spec["sha1"]
            or f"{zlib.crc32(chip) & 0xffffffff:08x}" != spec["crc32"]):
        raise ValueError("Input is not the authenticated original HOTD1 sound chip")
    return reconstruct(region, {spec["file"]: chip}), {
        "file": spec["file"], "sha1": spec["sha1"], "crc32": spec["crc32"]}


def reject_alias(source: Path, output: Path) -> None:
    if (source.resolve() == output.resolve() or
            (output.exists() and source.samefile(output))):
        raise ValueError("Output aliases original sound evidence")


def write_report(source: Path, output: Path, report: dict) -> None:
    reject_alias(source, output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                dir=output.parent, prefix=".sound-control-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, sort_keys=True, indent=2)
            stream.write("\n")
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        reject_alias(args.chip, args.output)
        image, identity = authenticate_chip(args.chip)
        entry = int.from_bytes(image[4:8], "big")
        report = analyze(image, base=BASE, entry=entry)
        report["provenance"] = "authenticated original chip; static candidate evidence only"
        report["chip_identity"] = identity
        write_report(args.chip, args.output, report)
    except (OSError, ValueError) as error:
        print("Sound-control audit refused: " + type(error).__name__, file=sys.stderr)
        return 2
    print(f"Sound-control candidates: {len(report['store_candidates'])} stores; not hardware proof")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
