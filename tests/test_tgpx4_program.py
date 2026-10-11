"""ROM-free Model 2C MB86235 program upload-staging safety tests."""
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

from arcaderecomp.tgpx4_program import (
    MAX_DWORDS, SCHEMA, UploadError, analyze, main,
    pack_candidate, read_bounded, write_report,
)


def fixture():
    return struct.pack("<4I", 0x11223344, 0xaabbccdd,
                       0x01020304, 0x55667788)


def settings():
    return dict(expected_dwords=4, word_endian="little",
                pair_order="low-first")


def info():
    return dict(settings(), provenance="synthetic",
                source_note="Synthetic 32-bit host-write fixture, not hardware")


class TGPx4ProgramTests(unittest.TestCase):
    def test_exact_low_and_high_packing_two_slots(self):
        original = fixture()
        assembled = pack_candidate(original, **settings())
        self.assertEqual(assembled, struct.pack(
            "<2Q", 0xaabbccdd11223344, 0x5566778801020304))
        self.assertEqual(len(assembled), len(original))
        self.assertEqual(pack_candidate(original, **settings()), assembled)

    def test_explicit_high_first_changes_candidate_not_capture(self):
        original = fixture()
        high_first = pack_candidate(original, expected_dwords=4,
                                    word_endian="little",
                                    pair_order="high-first")
        self.assertEqual(high_first, struct.pack(
            "<2Q", 0x11223344aabbccdd, 0x0102030455667788))
        self.assertNotEqual(high_first, pack_candidate(original, **settings()))
        self.assertEqual(original, fixture())

    def test_endian_is_explicit_and_not_host_dependent(self):
        raw = struct.pack(">2I", 0x11223344, 0xaabbccdd)
        image = pack_candidate(raw, expected_dwords=2,
                               word_endian="big", pair_order="low-first")
        self.assertEqual(image, struct.pack("<Q", 0xaabbccdd11223344))
        wrong = pack_candidate(raw, expected_dwords=2,
                               word_endian="little", pair_order="low-first")
        self.assertNotEqual(image, wrong)

    def test_refuse_missing_half_odd_count_trailing_bytes_and_wrong_count(self):
        original = fixture()
        cases = [
            (original[:12], 3),
            (original[:12], 4),
            (original + b"\0", 4),
            (original[:8], 4),
            (original, 6),
            (original, 0),
            (original, MAX_DWORDS + 2),
            (original, True),
        ]
        for raw, count in cases:
            with self.subTest(size=len(raw), count=count):
                with self.assertRaises(UploadError):
                    pack_candidate(raw, expected_dwords=count,
                                   word_endian="little",
                                   pair_order="low-first")

    def test_refuse_implicit_word_order_wrong_type_and_unverified_claim(self):
        for extra in ({"word_endian": "auto"},
                      {"word_endian": "native"},
                      {"pair_order": "auto"},
                      {"pair_order": "little"},
                      {"pair_order": None}):
            kwargs = dict(settings(), **extra) if not (
                set(settings()) & set(extra)) else {**settings(), **extra}
            with self.subTest(extra=extra):
                with self.assertRaises(UploadError):
                    pack_candidate(fixture(), **kwargs)
        for raw in (bytearray(fixture()), list(fixture()), memoryview(fixture())):
            with self.assertRaises(UploadError):
                pack_candidate(raw, **settings())
        for provenance in ("cabinet_verified", "", None, "real_hardware"):
            with self.assertRaises(UploadError):
                analyze(fixture(), **settings(), provenance=provenance,
                        source_note="synthetic")
        for note in ("", " ", "X" * 513, None):
            with self.assertRaises(UploadError):
                analyze(fixture(), **settings(), provenance="synthetic",
                        source_note=note)

    def test_report_only_contains_hashes_counts_and_unverified_flags(self):
        raw = fixture()
        result = analyze(raw, **info())
        candidate = pack_candidate(raw, **settings())
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["host_dword_count"], 4)
        self.assertEqual(result["candidate_64bit_slot_count"], 2)
        self.assertEqual(result["input_sha256"],
                         hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["candidate_sha256"],
                         hashlib.sha256(candidate).hexdigest())
        self.assertFalse(result["complete_original_upload_verified"])
        self.assertFalse(result["original_cabinet_verified"])
        self.assertFalse(result["mb86235_instruction_decoded"])
        text = json.dumps(result)
        for word in ("11223344", "aabbccdd", "01020304", "55667788",
                     "Synthetic 32-bit"):
            self.assertNotIn(word, text)

    def test_cli_requires_count_writes_metadata_and_refuses_truncation(self):
        with tempfile.TemporaryDirectory(prefix="arcade-tgpx4-") as directory:
            root = Path(directory)
            source = root / "input.bin"
            dest = root / "metadata.json"
            source.write_bytes(fixture())
            args = ["--input", str(source), "--output", str(dest),
                    "--expected-dwords", "4", "--word-endian", "little",
                    "--pair-order", "low-first", "--provenance", "synthetic",
                    "--source-note", "Synthetic fixture only"]
            self.assertEqual(main(args), 0)
            result = json.loads(dest.read_text())
            self.assertEqual(result["host_dword_count"], 4)
            self.assertNotIn("11223344", dest.read_text())
            dest.unlink()
            source.write_bytes(fixture()[:-4])
            self.assertEqual(main(args), 2)
            self.assertFalse(dest.exists())

    def test_never_overwrite_original_capture_or_aliases(self):
        with tempfile.TemporaryDirectory(prefix="arcade-tgpx4-safe-") as d:
            root = Path(d)
            source = root / "original.bin"
            source.write_bytes(fixture())
            hard = root / "hard.bin"
            sym = root / "link.bin"
            os.link(source, hard)
            sym.symlink_to(source)
            report = analyze(fixture(), **info())
            for output in (source, hard, sym):
                with self.subTest(output=output.name):
                    with self.assertRaises(UploadError):
                        write_report(source, output, report)
                    self.assertEqual(source.read_bytes(), fixture())
            output = root / "safe.json"
            write_report(source, output, report)
            self.assertEqual(json.loads(output.read_text()), report)
            self.assertFalse(any(
                p.name.startswith(".tgpx4-report-") for p in root.iterdir()))

    def test_input_size_cap_does_not_infer_hardware_capacity(self):
        with tempfile.TemporaryDirectory(prefix="arcade-tgpx4-max-") as d:
            path = Path(d) / "stream.bin"
            path.write_bytes(bytes(MAX_DWORDS * 4))
            self.assertEqual(len(read_bounded(path)), MAX_DWORDS * 4)
            path.write_bytes(bytes(MAX_DWORDS * 4 + 1))
            with self.assertRaises(UploadError):
                read_bounded(path)


if __name__ == "__main__":
    unittest.main()
