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

    def test_overlapping_roms_rejected(self):
        region = dict(self.region)
        region["copies"] = []
        region["loads"] = [spec("a.rom", self.one, "0x0"),
                           spec("b.rom", self.two, "0x0")]
        with self.assertRaisesRegex(RomError, "Overlapping"):
            reconstruct(region, {"a.rom": self.one, "b.rom": self.two})


if __name__ == "__main__":
    unittest.main()
