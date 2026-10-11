"""ROM-free strict TGPx4 host-write observation/packing tests."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from arcaderecomp.tgpx4_host_trace import (
    SCHEMA, UploadError, compare_capture, main, parse_capture,
    write_metadata,
)


def capture():
    writes = [
        (0x00980000, 0x80000000),
        (0x00884000, 0x11223344),
        (0x00884004, 0x55667788),
        (0x00980000, 0),
    ]
    return {
        "schema": SCHEMA,
        "provenance": "synthetic",
        "source_note": "ROM-free synthetic test, not original board data",
        "capture_complete": True,
        "total_events": len(writes),
        "dropped_events": 0,
        "events": [
            {"ordinal": i, "direction": "write", "address": f"0x{addr:08x}",
             "width": 4, "completed": True, "value": f"0x{value:08x}"}
            for i, (addr, value) in enumerate(writes, 1)
        ]
    }


class HostTraceTests(unittest.TestCase):
    def test_observed_control_bracket_and_two_fifo_writes(self):
        source = json.dumps(capture())
        data, words = parse_capture(source)
        self.assertEqual(words, [0x11223344, 0x55667788])
        self.assertEqual(data["total_events"], 4)
        result = compare_capture(source, pair_order="low-first")
        raw = struct.pack("<2I", *words)
        self.assertEqual(result["input_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["candidate_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(result["control_write_bracket_observed_in_supplied_trace"])
        self.assertFalse(result["control_initial_state_verified"])
        self.assertFalse(result["complete_original_upload_verified"])
        self.assertFalse(result["original_cabinet_verified"])
        self.assertFalse(result["mb86235_instruction_decoded"])
        self.assertNotIn("11223344", json.dumps(result))
        self.assertNotIn("synthetic test, not", json.dumps(result))

    def test_reverse_pair_is_explicit_hypothesis(self):
        text = json.dumps(capture())
        a = compare_capture(text, pair_order="low-first")
        b = compare_capture(text, pair_order="high-first")
        self.assertNotEqual(a["candidate_sha256"], b["candidate_sha256"])
        self.assertEqual(a["input_sha256"], b["input_sha256"])
        self.assertEqual(a["host_dword_count"], 2)

    def test_refuse_incomplete_capture_missing_control_and_loss(self):
        original = capture()
        variants = []
        for key, value in (("capture_complete", False), ("total_events", 3),
                           ("dropped_events", 1), ("provenance", "verified"),
                           ("source_note", "")):
            v = copy.deepcopy(original)
            v[key] = value
            variants.append(v)
        for index in (0, -1):
            v = copy.deepcopy(original)
            v["events"].pop(index)
            v["total_events"] -= 1
            variants.append(v)
        for v in variants:
            with self.subTest(v=v):
                with self.assertRaises(UploadError):
                    parse_capture(json.dumps(v))

    def test_refuse_gaps_wrong_port_width_incomplete_and_side_effects(self):
        original = capture()
        for i, key, value in (
            (0, "address", "0x00884000"),
            (3, "address", "0x00884000"),
            (0, "value", "0x00000000"),
            (3, "value", "0x80000000"),
            (3, "value", "0x00000001"),
            (1, "address", "0x00880000"),
            (2, "address", "0x00888000"),
            (2, "address", "0x00884001"),
            (2, "width", 1),
            (2, "direction", "read"),
            (2, "completed", False),
            (2, "ordinal", 4),
            (2, "value", "0x100000000"),
        ):
            v = copy.deepcopy(original)
            v["events"][i][key] = value
            with self.subTest(i=i, key=key, value=value):
                with self.assertRaises(UploadError):
                    parse_capture(json.dumps(v))

    def test_reject_duplicate_keys_extra_keys_and_trailing_instructions(self):
        with self.assertRaises(UploadError):
            parse_capture('{"schema":"x","schema":"y"}')
        v = capture()
        v["unknown"] = True
        with self.assertRaises(UploadError):
            parse_capture(json.dumps(v))
        v = capture()
        v["events"][1]["extra"] = "ignored?"
        with self.assertRaises(UploadError):
            parse_capture(json.dumps(v))
        v = capture()
        v["events"].insert(-1, dict(v["events"][2]))
        for i, event in enumerate(v["events"], 1):
            event["ordinal"] = i
        v["total_events"] = len(v["events"])
        with self.assertRaises(UploadError):
            parse_capture(json.dumps(v))  # odd FIFO dword count

    def test_cli_metadata_is_atomic_and_never_overwrites_evidence(self):
        with tempfile.TemporaryDirectory(prefix="arcade-tgpx4-trace-") as d:
            folder = Path(d)
            source = folder / "capture.json"
            target = folder / "metadata.json"
            source.write_text(json.dumps(capture()))
            args = ["--capture", str(source), "--output", str(target),
                    "--pair-order", "low-first"]
            self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(target.read_text())["host_dword_count"], 2)
            self.assertNotIn("11223344", target.read_text())
            hard = folder / "hard.json"
            sym = folder / "sym.json"
            os.link(source, hard)
            sym.symlink_to(source)
            report = json.loads(target.read_text())
            for path in (source, hard, sym):
                with self.subTest(path=path.name):
                    with self.assertRaises(UploadError):
                        write_metadata(source, path, report)
                    self.assertEqual(main(["--capture", str(source), "--output",
                        str(path), "--pair-order", "low-first"]), 2)
                    self.assertEqual(json.loads(source.read_text()), capture())
            target.unlink()
            v = capture()
            v["events"][-1]["completed"] = False
            source.write_text(json.dumps(v))
            self.assertEqual(main(args), 2)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
