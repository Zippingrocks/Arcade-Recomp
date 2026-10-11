"""Strict offline staging for candidate Model 2C MB86235/TGPx4 programs.

The i960-side geometry upload is recorded as successive 32-bit words.
Two words can form a candidate 64-bit instruction *container*, but this
module deliberately does not decode, execute, or authenticate any opcode.

Inputs must be externally supplied; no arcade program, generated executable,
or actual Sega capture is bundled. Reports contain hashes/lengths only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

MAX_DWORDS = 16384  # Analysis safety cap, NOT claimed physical program RAM.
SCHEMA = "model2c-tgpx4-program-candidate-v1"
PROVENANCE = ("synthetic", "external_capture_unverified")
WORD_ENDIAN = ("little", "big")
PAIR_ORDER = ("low-first", "high-first")


class UploadError(ValueError):
    """Malformed/incomplete host stream or unsupported evidence claim."""


def pack_candidate(raw: bytes, *, expected_dwords: int,
                   word_endian: str, pair_order: str) -> bytes:
    """Pack explicit host 32-bit writes into candidate little-endian u64 slots.

    This is byte/word staging only. No FPGA, FIFO, CPU or DSP activity is
    inferred. Explicit word byte order and low/high pairing are mandatory
    because neither is established by a supplied original-cabinet trace.
    """
    if type(raw) is not bytes:
        raise UploadError("input must be an immutable byte stream")
    if type(expected_dwords) is not int or not (2 <= expected_dwords <= MAX_DWORDS):
        raise UploadError("expected_dwords outside research safety cap")
    if expected_dwords & 1:
        raise UploadError("unfinished 64-bit slot: odd number of host words")
    if word_endian not in WORD_ENDIAN or pair_order not in PAIR_ORDER:
        raise UploadError("word endian and pair order must be explicitly selected")
    if len(raw) != expected_dwords * 4:
        raise UploadError("host stream length disagrees with explicit expected count")
    output = bytearray(len(raw))
    for offset in range(0, len(raw), 8):
        a = int.from_bytes(raw[offset:offset + 4], word_endian)
        b = int.from_bytes(raw[offset + 4:offset + 8], word_endian)
        low, high = (a, b) if pair_order == "low-first" else (b, a)
        output[offset:offset + 4] = low.to_bytes(4, "little")
        output[offset + 4:offset + 8] = high.to_bytes(4, "little")
    return bytes(output)


def analyze(raw: bytes, *, expected_dwords: int, word_endian: str,
            pair_order: str, provenance: str, source_note: str) -> dict:
    """Return metadata without exposing candidate program words/bytes."""
    if provenance not in PROVENANCE:
        raise UploadError("capture provenance must remain explicitly unverified")
    if (type(source_note) is not str or
            not 1 <= len(source_note.strip()) <= 512):
        raise UploadError("source note required (1..512 characters)")
    candidate = pack_candidate(
        raw, expected_dwords=expected_dwords,
        word_endian=word_endian, pair_order=pair_order)
    return {
        "schema": SCHEMA,
        "provenance": provenance,
        "source_note_sha256": hashlib.sha256(
            source_note.encode("utf-8")).hexdigest(),
        "input_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
        "host_dword_count": expected_dwords,
        "candidate_64bit_slot_count": expected_dwords // 2,
        "word_endian": word_endian,
        "pair_order": pair_order,
        "complete_original_upload_verified": False,
        "original_cabinet_verified": False,
        "mb86235_instruction_decoded": False,
    }


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(MAX_DWORDS * 4 + 1)
    if len(payload) > MAX_DWORDS * 4:
        raise UploadError("capture exceeds bounded research input size")
    return payload


def write_report(source: Path, output: Path, report: dict) -> None:
    """Atomic metadata write; never overwrite or alias input evidence."""
    if (source.resolve() == output.resolve() or
            (output.exists() and source.samefile(output))):
        raise UploadError("metadata destination aliases original capture")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", dir=output.parent, encoding="utf-8",
            prefix=".tgpx4-report-", suffix=".tmp", delete=False
        ) as f:
            temp = Path(f.name)
            json.dump(report, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(temp, output)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path,
                        help="Private contiguous sequence of host 32-bit words")
    parser.add_argument("--output", required=True, type=Path,
                        help="Metadata only, never binary program data")
    parser.add_argument("--expected-dwords", required=True, type=int)
    parser.add_argument("--word-endian", required=True, choices=WORD_ENDIAN)
    parser.add_argument("--pair-order", required=True, choices=PAIR_ORDER)
    parser.add_argument("--provenance", required=True, choices=PROVENANCE)
    parser.add_argument("--source-note", required=True,
                        help="Private provenance description (hashed in report)")
    args = parser.parse_args(argv)
    try:
        # Reject aliases before reading evidence or touching output paths.
        if (args.input.resolve() == args.output.resolve() or
                (args.output.exists() and args.input.samefile(args.output))):
            raise UploadError("output aliases input evidence")
        raw = read_bounded(args.input)
        report = analyze(
            raw, expected_dwords=args.expected_dwords,
            word_endian=args.word_endian, pair_order=args.pair_order,
            provenance=args.provenance, source_note=args.source_note)
        write_report(args.input, args.output, report)
    except (OSError, ValueError) as exc:
        print("TGPx4 staging refused: " + type(exc).__name__, file=sys.stderr)
        return 2
    print("TGPx4 candidate metadata written; opcode and hardware not verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
