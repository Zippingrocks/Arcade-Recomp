"""Compare strict native 315-5649 CPU bus accesses with external observations.

This is a comparison boundary, NOT a serial chip emulator, timing oracle or
cabinet authenticity certificate. It never fills unknown native read values.
An external capture must describe *CPU-side* accesses in transaction order,
not raw RS-422 wire frames (see arcaderecomp.serial_wire for that format).

Result JSON contains hashes and discrepancy metadata, NOT observed RX bytes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

SCHEMA = "model2c-cpu-serial-capture-v1"
SUMMARY_RE = re.compile(
    r"^serial_trace_summary total=([0-9]+) retained=([0-9]+)"
    r" dropped=([0-9]+) truncated=(yes|no) limit=([0-9]+)$"
)
NATIVE_RE = re.compile(
    r"^serial_access ordinal=([0-9]+) direction=(read|write)"
    r" address=0x([0-9a-fA-F]+) width=([0-9]+)"
    r" completed=(yes|no) value=(0x[0-9a-fA-F]+|UNOBSERVED)$"
)
MAX_FILE_SIZE = 4 * 1024 * 1024
MAX_EVENTS = 100000
BASE = 0x01C00000
APERTURE = 0x20


class TraceError(ValueError):
    """Invalid input, not a reported original-hardware discrepancy."""


@dataclass(frozen=True)
class Access:
    ordinal: int
    direction: str
    address: int
    width: int
    completed: bool
    value: int | None


def _read_limited(path: Path) -> bytes:
    with path.open("rb") as reader:
        data = reader.read(MAX_FILE_SIZE + 1)
    if len(data) > MAX_FILE_SIZE:
        raise TraceError("trace file exceeds the documented 4 MiB limit")
    return data


def _validate_access(event: Access) -> None:
    if isinstance(event.ordinal, bool) or event.ordinal < 1:
        raise TraceError("invalid transaction ordinal")
    if event.direction not in ("read", "write"):
        raise TraceError("invalid direction")
    if not BASE <= event.address < BASE + APERTURE:
        raise TraceError("address outside the 315-5649 CPU aperture")
    if event.width not in (1, 2, 4):
        raise TraceError("unsupported CPU transaction width")
    if not isinstance(event.completed, bool):
        raise TraceError("completion must be explicitly boolean")
    if event.value is None:
        if event.direction == "write" or event.completed:
            raise TraceError("a completed access or attempted write needs a value")
    elif (isinstance(event.value, bool) or event.value < 0 or
          event.value >= (1 << (8 * event.width)) or
          (event.direction == "read" and not event.completed)):
        raise TraceError("invalid or invented access value")


def _sequence(events: list[Access]) -> list[Access]:
    if not events or len(events) > MAX_EVENTS:
        raise TraceError("trace requires 1..100000 ordered events")
    for i, event in enumerate(events, 1):
        _validate_access(event)
        if event.ordinal != i:
            raise TraceError("ordinals must start at 1 and increase without gaps")
    return events


def parse_native(text: str) -> list[Access]:
    """Read strict_boot_probe diagnostic lines, retaining unknown reads."""
    found: list[Access] = []
    summary: tuple[int, int, int, str, int] | None = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("serial_trace_summary"):
            match = SUMMARY_RE.fullmatch(line)
            if match is None or summary is not None:
                raise TraceError("malformed or duplicated serial trace summary")
            total, retained, dropped, truncated, limit = match.groups()
            summary = (int(total), int(retained), int(dropped), truncated, int(limit))
            continue
        if not line.startswith("serial_access"):
            continue
        if summary is not None:
            raise TraceError("serial access after final trace summary")
        match = NATIVE_RE.fullmatch(line)
        if not match:
            raise TraceError("malformed native serial_access diagnostic")
        ordinal, direction, address, width, completed, value = match.groups()
        found.append(Access(
            int(ordinal), direction, int(address, 16), int(width),
            completed == "yes",
            None if value == "UNOBSERVED" else int(value, 16)
        ))
        if len(found) > MAX_EVENTS:
            raise TraceError("too many native observations")
    entries = _sequence(found)
    # The strict native probe ALWAYS emits a bounded-capture summary.
    # A missing footer may mean the file ended before lost accesses were
    # reported. Never compare a seemingly contiguous but incomplete prefix.
    if summary is None:
        raise TraceError("native serial trace summary required (possibly truncated log)")
    total, retained, dropped, truncated, limit = summary
    if (retained != len(entries) or retained > limit or
            total != retained + dropped or
            (truncated == "yes") != (dropped > 0)):
        raise TraceError("serial trace summary disagrees with captured events")
    if dropped != 0:
        raise TraceError("truncated native serial trace is not comparable")
    return entries


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for k, v in pairs:
        if k in result:
            raise TraceError("duplicate JSON key")
        result[k] = v
    return result


def _hex_byte(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", value):
        raise TraceError("observation value must be a hexadecimal string or null")
    return int(value, 16)


def parse_capture(text: str) -> tuple[str, list[Access]]:
    """Parse explicit independent CPU-side observation metadata.

    The provenance label is an assertion about the INPUT'S origin, never a
    hardware-verified result. A synthetic trace cannot impersonate a real
    capture by supplying ready/status bytes.
    """
    try:
        root = json.loads(text, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TraceError("invalid capture JSON") from exc
    if not isinstance(root, dict) or set(root) != {
            "schema", "provenance", "source_note", "events"}:
        raise TraceError("capture must use the exact schema fields")
    if root["schema"] != SCHEMA:
        raise TraceError("unsupported observation schema")
    provenance = root["provenance"]
    if provenance not in ("synthetic", "external_capture_unverified"):
        raise TraceError("capture provenance must remain explicitly unverified")
    note = root["source_note"]
    if not isinstance(note, str) or not (1 <= len(note.strip()) <= 512):
        raise TraceError("a bounded nonempty capture source note is required")
    items = root["events"]
    if not isinstance(items, list) or not (1 <= len(items) <= MAX_EVENTS):
        raise TraceError("invalid event list length")
    events = []
    for row in items:
        if not isinstance(row, dict) or set(row) != {
                "ordinal", "direction", "address", "width", "completed", "value"}:
            raise TraceError("event must declare all required access fields")
        ordinal, address, width = row["ordinal"], row["address"], row["width"]
        if (type(ordinal) is not int or type(width) is not int or
                not isinstance(address, str) or
                not re.fullmatch(r"0x[0-9a-fA-F]+", address)):
            raise TraceError("invalid transaction index, width or address")
        direction = row["direction"]
        if not isinstance(direction, str):
            raise TraceError("direction must be a string")
        value = _hex_byte(row["value"])
        events.append(Access(ordinal, direction, int(address, 16), width,
                             row["completed"], value))
    return provenance, _sequence(events)


def compare(native: list[Access], observed: list[Access],
            provenance: str) -> dict:
    """Classify discrepancies; never count an unobserved read as zero."""
    _sequence(native)
    _sequence(observed)
    if provenance not in ("synthetic", "external_capture_unverified"):
        raise TraceError("capture provenance is untrusted")
    counts = {"matched": 0, "implementation_gaps": 0,
              "insufficient_evidence": 0, "divergences": 0}
    differences = []
    for index in range(max(len(native), len(observed))):
        number = index + 1
        n = native[index] if index < len(native) else None
        o = observed[index] if index < len(observed) else None
        reason = None
        if n is None or o is None:
            reason = "trace_length_mismatch"
        elif (n.ordinal, n.direction, n.address, n.width) != (
                o.ordinal, o.direction, o.address, o.width):
            reason = "transaction_identity_mismatch"
        elif n.direction == "write":
            if n.value != o.value:
                reason = "outgoing_byte_mismatch"
            elif n.completed and not o.completed:
                reason = "native_accepted_external_refused"
            elif not n.completed and o.completed:
                reason = "native_write_not_implemented"
            elif not n.completed:
                reason = "both_refused_write"
        elif n.completed and o.completed:
            if n.value != o.value:
                reason = "observed_read_value_mismatch"
        elif n.completed and not o.completed:
            reason = "external_read_unobserved"
        elif not n.completed and o.completed:
            reason = "native_read_not_implemented"
        else:
            reason = "both_reads_unobserved"
        if reason is None:
            counts["matched"] += 1
        else:
            if reason in ("native_write_not_implemented",
                          "native_read_not_implemented"):
                category = "implementation_gaps"
            elif reason in ("both_reads_unobserved", "both_refused_write",
                            "external_read_unobserved"):
                category = "insufficient_evidence"
            else:
                category = "divergences"
            counts[category] += 1
            differences.append({
                "ordinal": number,
                "reason": reason,
                "address": f"0x{(n or o).address:08x}"
            })
    if counts["divergences"]:
        verdict = "diverged"
    elif counts["implementation_gaps"]:
        # A proven missing native bus implementation is actionable even
        # when another event lacks enough evidence to be compared.
        verdict = "implementation_gap"
    elif counts["insufficient_evidence"]:
        verdict = "insufficient_evidence"
    else:
        verdict = "matches_supplied_observations"
    return {"schema": "model2c-serial-access-comparison-v1",
            "verdict": verdict, "provenance": provenance,
            "arcade_hardware_verified": False,
            "native_events": len(native), "observation_events": len(observed),
            "counts": counts, "differences": differences}


def write_report(inputs: tuple[Path, Path], output: Path, report: dict) -> None:
    # Never truncate a supplied capture, including via symlink or hardlink.
    for source in inputs:
        if source.resolve() == output.resolve() or (
                output.exists() and source.samefile(output)):
            raise TraceError("report path aliases a trace input")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                dir=output.parent, prefix=".serial-compare-", suffix=".tmp",
                delete=False) as stream:
            temp = Path(stream.name)
            stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
        os.replace(temp, output)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-log", required=True, type=Path)
    parser.add_argument("--observed-json", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        sources = (args.native_log, args.observed_json)
        for source in sources:
            if source.resolve() == args.output.resolve() or (
                    args.output.exists() and source.samefile(args.output)):
                raise TraceError("report path aliases a trace input")
        native_bytes, capture_bytes = map(_read_limited, sources)
        native = parse_native(native_bytes.decode("utf-8"))
        provenance, observed = parse_capture(capture_bytes.decode("utf-8"))
        result = compare(native, observed, provenance)
        result["native_log_sha256"] = hashlib.sha256(native_bytes).hexdigest()
        result["capture_sha256"] = hashlib.sha256(capture_bytes).hexdigest()
        write_report(sources, args.output, result)
    except (OSError, ValueError, UnicodeError) as exc:
        print("serial comparison refused: " + type(exc).__name__, file=sys.stderr)
        return 2
    print("Serial comparison: " + result["verdict"])
    return (3 if result["verdict"] == "diverged" else
            4 if result["verdict"] != "matches_supplied_observations" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
