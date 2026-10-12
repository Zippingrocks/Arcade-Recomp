"""ROM reconstruction tests use synthetic bytes; no proprietary game data."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
import zlib

from arcaderecomp.roms import load_layout, reconstruct, select_regions, verify, RomError


ROOT = Path(__file__).resolve().parents[1]


def spec(name, raw, offset, group=2, stride=4, swap16=False):
    return {"file": name, "size": len(raw), "offset": offset,
            "sha1": hashlib.sha1(raw).hexdigest(),
            "crc32": f"{zlib.crc32(raw) & 0xffffffff:08x}",
            "group": group, "stride": stride, "swap16": swap16}


class ManifestTests(unittest.TestCase):
    def test_target_is_original_not_revision_a(self):
        original = load_layout(ROOT / "targets/hotd1/original.json")
        revision_a = load_layout(ROOT / "targets/hotd1/rev_a.json")
        self.assertEqual(original["rom_set"], "hotdo")
        self.assertEqual(original["role"], "primary")
        self.assertEqual(revision_a["rom_set"], "hotd")
        originals = {item["file"]: item for region in original["regions"]
                     for item in region["loads"]}
        later = {item["file"]: item for region in revision_a["regions"]
                 for item in region["loads"]}
        self.assertEqual(len(originals), 29)
        self.assertEqual(originals["epr-19696.15"]["crc32"], "03da5623")
        self.assertEqual(originals["epr-19697.16"]["crc32"], "a9722d87")
        self.assertNotIn("epr-19696a.15", originals)
        self.assertNotIn("epr-19697a.16", originals)
        self.assertIn("epr-19696a.15", later)
        self.assertIn("epr-19697a.16", later)
        self.assertEqual(originals["epr-19694.13"], later["epr-19694.13"])

    def test_invalid_region_rejected(self):
        layout = load_layout(ROOT / "targets/hotd1/original.json")
        with self.assertRaises(RomError):
            select_regions(layout, ["does_not_exist"])


class SyntheticRomTests(unittest.TestCase):
    def setUp(self):
        self.one = bytes([0x10, 0x11, 0x12, 0x13])
        self.two = bytes([0x20, 0x21, 0x22, 0x23])
        self.region = {
            "name": "maincpu", "size": "0x10",
            "loads": [spec("chip_a.rom", self.one, "0x0"),
                      spec("chip_b.rom", self.two, "0x2")],
            "copies": [{"source": "0x0", "target": "0x8", "size": "0x8"}]
        }

    def test_exact_hashes_and_lanes(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "original.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("hotdo/chip_a.rom", self.one)
                z.writestr("hotdo/chip_b.rom", self.two)
            result, data = verify([archive], [self.region])
            self.assertTrue(result["ok"])
            self.assertEqual(result["matched"], 2)
            expected = bytes([0x10, 0x11, 0x20, 0x21, 0x12, 0x13, 0x22, 0x23])
            self.assertEqual(reconstruct(self.region, data), expected + expected)

    def test_different_revision_must_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "wrong-revision.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("chip_a.rom", b"xxxx")
                z.writestr("chip_b.rom", self.two)
            result, _ = verify([archive], [self.region])
            self.assertFalse(result["ok"])
            self.assertEqual(result["unmatched"], ["chip_a.rom"])

    def test_split_parent_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            child = Path(folder) / "child.zip"
            parent = Path(folder) / "parent.zip"
            with zipfile.ZipFile(child, "w") as z:
                z.writestr("chip_a.rom", self.one)
            with zipfile.ZipFile(parent, "w") as z:
                z.writestr("chip_b.rom", self.two)
            result, _ = verify([child, parent], [self.region])
            self.assertTrue(result["ok"])

    def test_word_swap(self):
        raw = b"\x01\x02\x03\x04"
        region = {"name": "sound", "size": "0x4",
                  "loads": [spec("sound.rom", raw, "0x0", 1, 1, True)]}
        self.assertEqual(reconstruct(region, {"sound.rom": raw}), b"\x02\x01\x04\x03")

    def test_word_swap_rejects_odd_sized_input(self):
        raw = b"\x01\x02\x03"
        region = {"name": "sound", "size": "0x3",
                  "loads": [spec("sound.rom", raw, "0x0", 1, 1, True)]}
        with self.assertRaisesRegex(RomError, "even-sized"):
            reconstruct(region, {"sound.rom": raw})

    def test_overlapping_roms_rejected(self):
        region = dict(self.region)
        region["copies"] = []
        region["loads"] = [spec("a.rom", self.one, "0x0"),
                           spec("b.rom", self.two, "0x0")]
        with self.assertRaisesRegex(RomError, "Overlapping"):
            reconstruct(region, {"a.rom": self.one, "b.rom": self.two})

    def test_every_wiring_shape_matches_independent_byte_oracle(self):
        # Cover all admitted group/stride pairs, including a last byte exactly
        # at the region boundary and gaps whose fill must remain unchanged.
        for stride in range(1, 33):
            for group in range(1, stride + 1):
                for swap in (False, True):
                    with self.subTest(group=group, stride=stride, swap=swap):
                        raw = bytes((i * 71 + 13) % 256 for i in range(group * 6))
                        offset = 3
                        size = offset + stride * 5 + group
                        chip = spec("chip", raw, offset, group, stride, swap)
                        region = {"size": size, "loads": [chip]}
                        expected = bytearray(size)
                        for i in range(len(raw)):
                            source = i ^ 1 if swap else i
                            expected[offset + (i // group) * stride + i % group] = raw[source]
                        self.assertEqual(reconstruct(region, {"chip": raw}), bytes(expected))
                        self.assertEqual(chip["offset"], offset)

    def test_load_bounds_empty_and_invalid_wiring_are_rejected(self):
        for raw, offset, group, stride in (
                (b"abcd", -1, 1, 1), (b"abcd", -4, 2, 4),
                (b"abcd", 8, 1, 1), (b"abcd", 5, 1, 1),
                (b"abcd", 3, 2, 4), (b"", 0, 1, 1),
                (b"abc", 0, 2, 4), (b"abcd", 0, 0, 4),
                (b"abcd", 0, 3, 2), (b"abcd", 0, 1, 33)):
            with self.subTest(raw=raw, offset=offset, group=group, stride=stride):
                region = {"size": 8, "loads": [spec("chip", raw, offset, group, stride)]}
                with self.assertRaises(RomError):
                    reconstruct(region, {"chip": raw})

    def test_zero_valued_chips_still_occupy_all_loaded_lanes(self):
        for group, stride in ((1, 1), (2, 2), (2, 4), (3, 8)):
            for overlap in (0, group - 1, stride, stride + group - 1):
                with self.subTest(group=group, stride=stride, overlap=overlap):
                    raw = bytes(group * 2)
                    region = {"size": 32, "loads": [
                        spec("a", raw, 0, group, stride),
                        spec("b", b"x", overlap, 1, 1)]}
                    with self.assertRaisesRegex(RomError, "Overlapping ROM chips"):
                        reconstruct(region, {"a": raw, "b": b"x"})

    def test_mirror_boundaries_holes_and_overlap_are_rejected(self):
        for src, dst, length in (
                (-1, 8, 4), (0, -1, 4), (0, 8, -1), (0, 8, 0),
                (0, 13, 4), (14, 8, 4), (1, 8, 4), (8, 12, 4),
                (0, 0, 4), (0, 2, 4)):
            with self.subTest(src=src, dst=dst, length=length):
                region = {"size": 16, "loads": [spec("a", b"\0" * 4, 0, 1, 1)],
                          "copies": [{"source": src, "target": dst, "size": length}]}
                with self.assertRaises(RomError):
                    reconstruct(region, {"a": b"\0" * 4})

    def test_mirrors_can_chain_and_end_at_exact_region_boundary(self):
        region = {"size": 12, "loads": [spec("a", b"\0abc", 0, 2, 2)],
                  "copies": [{"source": 0, "target": 4, "size": 4},
                             {"source": 4, "target": 8, "size": 4}]}
        self.assertEqual(reconstruct(region, {"a": b"\0abc"}), b"\0abc" * 3)

    def test_contiguous_and_interleaved_chips_fill_each_others_gaps(self):
        region = {"size": 8, "loads": [spec("a", b"abcd", 0, 2, 4),
                                        spec("b", b"12", 2, 2, 2),
                                        spec("c", b"34", 6, 1, 1)]}
        self.assertEqual(reconstruct(region, {"a": b"abcd", "b": b"12", "c": b"34"}),
                         b"ab12cd34")


if __name__ == "__main__":
    unittest.main()
