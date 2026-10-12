"""Bounded proof of the HOTD sound startup ``ErrorSet`` state partition.

This proves a property of an authenticated instruction sequence, not the
power-on value of sound RAM.  Unknown bytes stay unknown; the report describes
all possible inputs and the finite architectural states they can produce.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .m68k import decode
from .sound_control_audit import authenticate_chip, write_report

ROM_BASE = 0x600000
START = 0x600172
CONVERGENCE = 0x600194
MAX_IMAGE = 0x80000
FIRST_ADDRESS, SECOND_ADDRESS, SAVED_ADDRESS = 0x0C08, 0x0C0C, 0x0C04
FIRST_SIGNATURE, SECOND_SIGNATURE = 0x4572726F, 0x72536574


def _instruction(image: bytes, pc: int, base: int):
    try:
        return decode(image, pc, base)
    except ValueError as error:
        raise ValueError("Startup signature sequence is truncated") from error


def analyze(image: bytes, *, base: int = ROM_BASE) -> dict:
    """Verify the exact semantic sequence and return its exhaustive partition."""
    if (not isinstance(image, bytes) or not 2 <= len(image) <= MAX_IMAGE or len(image) & 1
            or type(base) is not int or base < 0 or base & 1
            or base + len(image) > 2**32 or not base <= START
            or CONVERGENCE > base + len(image)):
        raise ValueError("Invalid bounded sound image or base")

    expected = (
        (0x600172, "clr_d", (4, 4), 0x600174),
        (0x600174, "cmpi", (4, FIRST_SIGNATURE, 7, 0, FIRST_ADDRESS), 0x60017C),
        (0x60017C, "bcc", (6,), 0x60017E, 0x60018C),
        (0x60017E, "cmpi", (4, SECOND_SIGNATURE, 7, 0, SECOND_ADDRESS), 0x600186),
        (0x600186, "bcc", (6,), 0x600188, 0x60018C),
        (0x600188, "move_memory_to_d", (1, 7, 0, SAVED_ADDRESS, 4), 0x60018C),
        (0x60018C, "lea_absolute", (0, 0), 0x600190),
        (0x600190, "move", (2, 1, 3, 0, 6, 0), CONVERGENCE),
    )
    verified = []
    for row in expected:
        pc, mnemonic, operands, next_pc, *target = row
        ins = _instruction(image, pc, base)
        if (ins.mnemonic != mnemonic or ins.operands != operands or ins.next_pc != next_pc
                or (target and ins.target != target[0])):
            raise ValueError(f"Unexpected instruction semantics at 0x{pc:08x}")
        verified.append({"pc": pc, "mnemonic": mnemonic, "next_pc": next_pc,
                         **({"target": target[0]} if target else {})})

    first_mismatch = (2**32 - 1) * 2**40
    second_mismatch = (2**32 - 1) * 2**8
    exact_marker = 2**8
    if first_mismatch + second_mismatch + exact_marker != 2**72:
        raise AssertionError("Partition arithmetic is not exhaustive")

    return {
        "schema": "hotdo-sound-startup-signature-proof-v1",
        "image_sha256": hashlib.sha256(image).hexdigest(),
        "image_size": len(image),
        "provenance": "caller-supplied bytes; not authenticated by analyzer",
        "verified_instruction_semantics": verified,
        "input_domain": {
            "bits": 72,
            "bytes": [SAVED_ADDRESS, *range(FIRST_ADDRESS, SECOND_ADDRESS + 4)],
            "possible_assignments": str(2**72),
            "initial_values_established": False,
        },
        "partition": [
            {"case": "first_longword_mismatch", "assignments": str(first_mismatch),
             "d4_at_convergence": 0},
            {"case": "first_match_second_longword_mismatch", "assignments": str(second_mismatch),
             "d4_at_convergence": 0},
            {"case": "exact_ErrorSet_marker", "assignments": str(exact_marker),
             "d4_at_convergence": "zero-extended byte at 0x0c04 (all 256 values)"},
        ],
        "convergence": {
            "pc": CONVERGENCE,
            "architectural_state_classes": 257,
            "d4_fully_known_in_every_class": True,
            "nzvc": 0,
            "x": "preserved from entry in every class",
            "other_entry_state_differences_introduced": False,
            "sound_ram_writes_before_convergence": 0,
        },
        "proof_scope": {
            "partition_is_exhaustive": True,
            "branch_condition": "BNE after exact 32-bit CMPI",
            "mismatch_compare_flags_are_overwritten": True,
            "power_on_ram_values_proven": False,
            "reset_wiring_proven": False,
            "hardware_execution_proven": False,
            "safe_to_replace_unknown_ram_with_zero": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        image, identity = authenticate_chip(args.chip)
        report = analyze(image)
        report["provenance"] = "authenticated original HOTD1 sound chip; bounded software proof"
        report["chip_identity"] = identity
        write_report(args.chip, args.output, report)
    except (OSError, ValueError) as error:
        print("Sound startup signature proof refused: " + type(error).__name__, file=sys.stderr)
        return 2
    print("Sound startup signature partition: 2^72 inputs -> 257 architectural classes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
