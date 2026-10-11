"""ROM-free tests for strict CPU-side serial access capture comparison.

Synthetic examples resemble the 315-5649 aperture but are not original
cabinet observations. Never treat a missing RX/status read as observed zero.
"""
import json
import os
from pathlib import Path
import tempfile
import unittest

from arcaderecomp.serial_access_compare import (
    Access, TraceError, SCHEMA, compare, main, parse_capture, parse_native,
    write_report,
)

NATIVE = """\
executed=1910
serial_access ordinal=1 direction=write address=0x1c00014 width=1 completed=yes value=0xff
serial_access ordinal=2 direction=write address=0x1c00012 width=1 completed=yes value=0x1
serial_access ordinal=3 direction=read address=0x1c0001a width=1 completed=no value=UNOBSERVED
required hardware not implemented
"""


def capture(read_complete=False, read_value=None, provenance="synthetic"):
    return {
        "schema": SCHEMA,
        "provenance": provenance,
        "source_note": "Explicit synthetic CPU bus access fixture",
        "events": [
            {"ordinal": 1, "direction": "write", "address": "0x01c00014",
             "width": 1, "completed": True, "value": "0xff"},
            {"ordinal": 2, "direction": "write", "address": "0x01c00012",
             "width": 1, "completed": True, "value": "0x01"},
            {"ordinal": 3, "direction": "read", "address": "0x01c0001a",
             "width": 1, "completed": read_complete, "value": read_value},
        ],
    }


class SerialAccessComparisonTests(unittest.TestCase):
    def parsed(self, obj):
        return parse_capture(json.dumps(obj))[1]

    def test_missing_status_is_not_a_real_zero(self):
        native = parse_native(NATIVE)
        observed = self.parsed(capture())
        report = compare(native, observed, "synthetic")
        self.assertEqual(report["verdict"], "insufficient_evidence")
        self.assertEqual(report["counts"]["matched"], 2)
        self.assertEqual(report["differences"][0]["reason"],
                         "both_reads_unobserved")
        self.assertFalse(report["arcade_hardware_verified"])

        external = capture(True, "0x00", "external_capture_unverified")
        report = compare(native, self.parsed(external),
                         "external_capture_unverified")
        self.assertEqual(report["verdict"], "implementation_gap")
        self.assertEqual(report["differences"][0]["reason"],
                         "native_read_not_implemented")
        self.assertNotIn("0x00", json.dumps(report))
        self.assertFalse(report["arcade_hardware_verified"])

    def test_a_synthetic_ready_byte_does_not_invent_native_read(self):
        result = compare(parse_native(NATIVE),
                         self.parsed(capture(True, "0x0c")),
                         "synthetic")
        self.assertEqual(result["verdict"], "implementation_gap")
        self.assertFalse(result["arcade_hardware_verified"])

    def test_known_real_zero_matches_only_if_both_sources_observed(self):
        source = NATIVE.replace(
            "completed=no value=UNOBSERVED", "completed=yes value=0x0")
        result = compare(parse_native(source),
                         self.parsed(capture(True, "0x00")),
                         "external_capture_unverified")
        self.assertEqual(result["verdict"], "matches_supplied_observations")
        self.assertEqual(result["counts"]["matched"], 3)
        self.assertFalse(result["arcade_hardware_verified"])

    def test_read_byte_and_outgoing_tx_mismatch(self):
        src = NATIVE.replace(
            "completed=no value=UNOBSERVED", "completed=yes value=0x10")
        result = compare(parse_native(src),
                         self.parsed(capture(True, "0x00")), "synthetic")
        self.assertEqual(result["verdict"], "diverged")
        self.assertEqual(result["differences"][0]["reason"],
                         "observed_read_value_mismatch")
        bad = capture()
        bad["events"][0]["value"] = "0x00"
        result = compare(parse_native(NATIVE), self.parsed(bad), "synthetic")
        self.assertEqual(result["verdict"], "diverged")
        self.assertEqual(result["differences"][0]["reason"],
                         "outgoing_byte_mismatch")

    def test_identity_order_length_and_completion_mismatches(self):
        bad = capture()
        bad["events"][1]["address"] = "0x01c00016"
        result = compare(parse_native(NATIVE), self.parsed(bad), "synthetic")
        self.assertEqual(result["verdict"], "diverged")
        self.assertEqual(result["differences"][0]["reason"],
                         "transaction_identity_mismatch")
        bad = capture()
        bad["events"].pop()
        result = compare(parse_native(NATIVE), self.parsed(bad), "synthetic")
        self.assertEqual(result["verdict"], "diverged")
        self.assertEqual(result["differences"][0]["reason"],
                         "trace_length_mismatch")
        bad = capture()
        bad["events"][1]["completed"] = False
        result = compare(parse_native(NATIVE), self.parsed(bad), "synthetic")
        self.assertEqual(result["verdict"], "diverged")
        self.assertEqual(result["differences"][0]["reason"],
                         "native_accepted_external_refused")

    def test_native_unimplemented_write_and_incomplete_capture(self):
        source = NATIVE.replace(
            "completed=yes value=0xff", "completed=no value=0xff")
        result = compare(parse_native(source),
                         self.parsed(capture()), "synthetic")
        self.assertEqual(result["verdict"], "implementation_gap")
        self.assertEqual(result["differences"][0]["reason"],
                         "native_write_not_implemented")
        source = NATIVE.replace(
            "completed=no value=UNOBSERVED", "completed=yes value=0x0")
        result = compare(parse_native(source),
                         self.parsed(capture()), "synthetic")
        self.assertEqual(result["verdict"], "insufficient_evidence")
        self.assertEqual(result["differences"][0]["reason"],
                         "external_read_unobserved")

    def test_reject_fake_value_unknown_bit_ranges_and_bad_ordinals(self):
        for bad in (
            NATIVE.replace("UNOBSERVED", "0x0"),
            NATIVE.replace("ordinal=2", "ordinal=7"),
            NATIVE.replace("width=1", "width=8"),
            NATIVE.replace("address=0x1c0001a", "address=0x0"),
            NATIVE.replace("value=UNOBSERVED", "value=NULL"),
        ):
            with self.subTest(input=bad[-85:]):
                with self.assertRaises(TraceError):
                    parse_native(bad)
        for mutation in (
            ("value", "0x100"),
            ("value", 0),
            ("ordinal", True),
            ("ordinal", 4),
            ("width", 0),
            ("completed", 1),
            ("address", "0xdeadbeef"),
        ):
            obj = capture(True, "0x00")
            obj["events"][2][mutation[0]] = mutation[1]
            with self.subTest(mutation=mutation):
                with self.assertRaises(TraceError):
                    self.parsed(obj)
        bad = capture(True, None)
        with self.assertRaises(TraceError):
            self.parsed(bad)

    def test_capture_requires_explicit_provenance_and_unique_keys(self):
        for prov in ("verified_on_cabinet", "authentic", None, ""):
            obj = capture(provenance=prov)
            with self.assertRaises(TraceError):
                self.parsed(obj)
        obj = capture()
        del obj["source_note"]
        with self.assertRaises(TraceError):
            self.parsed(obj)
        with self.assertRaises(TraceError):
            parse_capture('{"schema":"x","schema":"y"}')
        with self.assertRaises(TraceError):
            parse_native("executed=10\n")

    def test_cli_reports_metadata_only_and_distinct_exit_codes(self):
        with tempfile.TemporaryDirectory(prefix="arcade-serial-compare-") as tmp:
            root = Path(tmp)
            native = root / "native.log"
            observed = root / "capture.json"
            report = root / "result.json"
            native.write_text(NATIVE)
            observed.write_text(json.dumps(capture(True, "0x0c")))
            arguments = ["--native-log", str(native), "--observed-json",
                         str(observed), "--output", str(report)]
            self.assertEqual(main(arguments), 4)  # not a fake match
            result = json.loads(report.read_text())
            self.assertEqual(result["verdict"], "implementation_gap")
            self.assertIn("capture_sha256", result)
            self.assertIn("native_log_sha256", result)
            self.assertNotIn("0x0c", report.read_text())
            observed.write_text(json.dumps(capture()))
            self.assertEqual(main(arguments), 4)
            obj = capture()
            obj["events"][0]["value"] = "0x00"
            observed.write_text(json.dumps(obj))
            self.assertEqual(main(arguments), 3)

    def test_native_bounded_capture_summary_rejects_evidence_loss(self):
        native = NATIVE + (
            "serial_trace_summary total=3 retained=3 dropped=0 "
            "truncated=no limit=4096\n")
        self.assertEqual(parse_native(native), parse_native(NATIVE))
        summary = ("serial_trace_summary total=6 retained=3 dropped=3 "
                   "truncated=yes limit=3\n")
        with self.assertRaisesRegex(TraceError, "truncated native"):
            parse_native(NATIVE + summary)
        with tempfile.TemporaryDirectory(prefix="arcade-trace-loss-") as d:
            root = Path(d)
            source = root / "native.log"
            comparison = root / "observed.json"
            output = root / "report.json"
            source.write_text(NATIVE + summary)
            comparison.write_text(json.dumps(capture()))
            self.assertEqual(main(["--native-log", str(source),
                                   "--observed-json", str(comparison),
                                   "--output", str(output)]), 2)
            self.assertFalse(output.exists())

    def test_capture_summary_must_agree_with_observed_prefix(self):
        suffixes = (
            "serial_trace_summary total=3 retained=2 dropped=1 truncated=yes limit=3\n",
            "serial_trace_summary total=3 retained=3 dropped=0 truncated=yes limit=3\n",
            "serial_trace_summary total=3 retained=3 dropped=0 truncated=no limit=2\n",
            "serial_trace_summary total=4 retained=3 dropped=0 truncated=no limit=3\n",
            "serial_trace_summary total=3 retained=3 dropped=0 truncated=no limit=3\n"
            "serial_trace_summary total=3 retained=3 dropped=0 truncated=no limit=3\n",
            "serial_trace_summary total=3 retained=3 dropped=0 truncated=no limit=3\n"
            "serial_access ordinal=4 direction=read address=0x1c0001a width=1 completed=no value=UNOBSERVED\n",
            "serial_trace_summary total=-3 retained=3 dropped=0 truncated=no limit=3\n",
        )
        for summary in suffixes:
            with self.subTest(summary=summary[:95]):
                with self.assertRaises(TraceError):
                    parse_native(NATIVE + summary)

    def test_atomic_report_cannot_overwrite_input_or_hardlink(self):
        with tempfile.TemporaryDirectory(prefix="arcade-serial-safe-") as tmp:
            root = Path(tmp)
            native = root / "native.log"
            observed = root / "capture.json"
            native.write_text(NATIVE)
            observed.write_text(json.dumps(capture()))
            link = root / "hard.json"
            symlink = root / "sym.json"
            os.link(observed, link)
            symlink.symlink_to(native)
            for target in (native, observed, link, symlink):
                with self.subTest(destination=target.name):
                    with self.assertRaises(TraceError):
                        write_report((native, observed), target, {"safe": True})
                    self.assertEqual(native.read_text(), NATIVE)
                    self.assertEqual(json.loads(observed.read_text()), capture())
                    self.assertEqual(main(["--native-log", str(native),
                        "--observed-json", str(observed),
                        "--output", str(target)]), 2)
            output = root / "results.json"
            write_report((native, observed), output, {"safe": True})
            self.assertEqual(json.loads(output.read_text()), {"safe": True})
            self.assertFalse(any(p.name.startswith(".serial-compare-")
                                 for p in root.iterdir()))


if __name__ == "__main__":
    unittest.main()
