"""Offline extraction of *candidate* TGPx4 upload words from captured CPU writes.

This is not an MB86235 interpreter or an i960 bus implementation. The
input explicitly claims a complete, bounded, filtered write transcript.
Neither its provenance nor the physical meaning of a write is authenticated.
No original Sega data or generated game code is included in this module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

from .tgpx4_program import MAX_DWORDS, UploadError, analyze, pack_candidate

SCHEMA = "model2c-tgpx4-host-writes-v1"
MAX_CAPTURE_BYTES = 4 * 1024 * 1024
FIFO_START, FIFO_END = 0x00884000, 0x00888000
CONTROL_ADDRESS = 0x00980000
HEX32 = re.compile(r"0x[0-9a-fA-F]{1,8}\Z")


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise UploadError("duplicate capture key")
        result[key] = value
    return result


def _u32(value: object) -> int:
    if not isinstance(value, str) or HEX32.fullmatch(value) is None:
        raise UploadError("expected bounded hexadecimal 32-bit value")
    return int(value, 16)


def parse_capture(text: str) -> tuple[dict, list[int]]:
    """Strictly validate one control-bracketed upload *candidate*.

    Capture ordinals must be continuous and the final control deassertion
    must be observed. Other or missing events cannot be silently discarded.
    No accepted-write claim is generated for the project's strict native bus.
    """
    try:
        data = json.loads(text, object_pairs_hook=_unique_keys)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise UploadError("malformed upload capture JSON") from exc
    if type(data) is not dict or set(data) != {
        "schema", "provenance", "source_note", "capture_complete",
        "total_events", "dropped_events", "events"
    }:
        raise UploadError("capture schema fields missing or unexpected")
    if data["schema"] != SCHEMA:
        raise UploadError("wrong capture schema")
    if data["provenance"] not in ("synthetic", "external_capture_unverified"):
        raise UploadError("capture provenance cannot claim arcade verification")
    if type(data["source_note"]) is not str or not (
        1 <= len(data["source_note"].strip()) <= 512
    ):
        raise UploadError("bounded capture source note required")
    if data["capture_complete"] is not True:
        raise UploadError("capture must assert a complete observed window")
    events = data["events"]
    if type(events) is not list or not 4 <= len(events) <= MAX_DWORDS + 2:
        raise UploadError("capture must include both control writes and word pairs")
    if (type(data["total_events"]) is not int or
            data["total_events"] != len(events) or
            type(data["dropped_events"]) is not int or
            data["dropped_events"] != 0):
        raise UploadError("missing, dropped or inconsistent host-write events")
    words = []
    first_control = last_control = None
    for ordinal, event in enumerate(events, 1):
        if type(event) is not dict or set(event) != {
                "ordinal", "direction", "address", "width",
                "completed", "value"}:
            raise UploadError("incorrect host write event shape")
        if (type(event["ordinal"]) is not int or
                event["ordinal"] != ordinal or
                event["direction"] != "write" or
                type(event["width"]) is not int or event["width"] != 4 or
                event["completed"] is not True):
            raise UploadError("noncontiguous, incomplete or non-32bit write")
        address = _u32(event["address"])
        value = _u32(event["value"])
        if ordinal == 1 or ordinal == len(events):
            if address != CONTROL_ADDRESS:
                raise UploadError("capture not enclosed by control register writes")
            if ordinal == 1:
                first_control = value
            else:
                last_control = value
        else:
            if not FIFO_START <= address < FIFO_END or address & 3:
                raise UploadError("unexpected access inside upload window")
            words.append(value)
    # Only the observed high-bit pattern and unchanged lower bits are used.
    # Actual prior control state, reset and chip acceptance remain unknown.
    if not (first_control & 0x80000000) or (last_control & 0x80000000):
        raise UploadError("no observed control-on/control-off write pair")
    if ((first_control ^ last_control) != 0x80000000):
        raise UploadError("control writes changed unsupported bits")
    if len(words) % 2 or not 2 <= len(words) <= MAX_DWORDS:
        raise UploadError("incomplete 64-bit candidate program slots")
    return data, words


def compare_capture(text: str, *, pair_order: str) -> dict:
    """Return metadata only, never dump proprietary candidate instructions."""
    data, words = parse_capture(text)
    raw = b"".join(word.to_bytes(4, "little") for word in words)
    report = analyze(
        raw, expected_dwords=len(words), word_endian="little",
        pair_order=pair_order, provenance=data["provenance"],
        source_note=data["source_note"])
    report.update({
        "source_schema": SCHEMA,
        "source_json_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "capture_write_events": len(words) + 2,
        "control_write_bracket_observed_in_supplied_trace": True,
        "control_initial_state_verified": False,
        "all_cpu_bus_transactions_captured": False,
        "serial_and_geometry_device_behavior_verified": False,
    })
    return report


def _read_bounded(path: Path) -> str:
    with path.open("rb") as stream:
        raw = stream.read(MAX_CAPTURE_BYTES + 1)
    if len(raw) > MAX_CAPTURE_BYTES:
        raise UploadError("host write capture file too large")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UploadError("host write capture is not UTF-8") from exc


def write_metadata(input_path: Path, output: Path, report: dict) -> None:
    if (input_path.resolve() == output.resolve() or
            (output.exists() and input_path.samefile(output))):
        raise UploadError("metadata output aliases the capture evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=output.parent,
            prefix=".tgpx4-capture-", suffix=".tmp", delete=False
        ) as target:
            temp = Path(target.name)
            json.dump(report, target, indent=2, sort_keys=True)
            target.write("\n")
        os.replace(temp, output)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pair-order", required=True,
                        choices=("low-first", "high-first"))
    args = parser.parse_args(argv)
    try:
        if (args.capture.resolve() == args.output.resolve() or
                (args.output.exists() and args.capture.samefile(args.output))):
            raise UploadError("metadata path aliases original capture")
        raw = _read_bounded(args.capture)
        metadata = compare_capture(raw, pair_order=args.pair_order)
        write_metadata(args.capture, args.output, metadata)
    except (OSError, UploadError, ValueError) as exc:
        print("TGPx4 host-write capture refused: " +
              type(exc).__name__, file=sys.stderr)
        return 2
    print("TGPx4 candidate host-write metadata written (unverified)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
