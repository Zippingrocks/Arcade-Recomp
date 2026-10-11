"""ROM-free safety and mathematical assertions for private original-site FP audit."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = ROOT / "tools" / "experimental" / "hotdo_fp_arithmetic_probe.py"
MODULE = runpy.run_path(str(PROBE_PATH))


def bits(x):
    return struct.unpack("<I", struct.pack("<f", float(x)))[0]


class OriginalFPArithmeticProbeTests(unittest.TestCase):
    def test_known_real32_multiply_divide_and_failure_classes(self):
        oracle = MODULE["oracle"]
        a, b = bits(-4), bits(2)
        self.assertEqual(oracle("mulr", a, b), (0, bits(-8)))
        self.assertEqual(oracle("divr", a, b), (0, bits(-0.5)))
        self.assertEqual(oracle("divr", bits(0), bits(1)), (3, 0))
        self.assertEqual(oracle("divr", bits(1), bits(3)), (0, bits(3)))
        self.assertEqual(oracle("divr", bits(3), bits(1))[0], 1)
        self.assertEqual(oracle("mulr", bits(-0.0), bits(2)), (0, bits(-0.0)))
        self.assertEqual(oracle("mulr", 0x7f800000, bits(2))[0], 2)
        self.assertEqual(oracle("divr", bits(2), 0x7fc00001)[0], 2)
        self.assertEqual(oracle("mulr", 0x00800000, bits(0.5))[0], 2)

    def test_verifier_rejects_wrong_digest_and_size_before_compilation(self):
        verify = MODULE["verify"]
        with self.assertRaisesRegex(ValueError, "not authenticated original"):
            verify(b"\0" * 0x200000, ["g++"])
        with self.assertRaisesRegex(ValueError, "not authenticated original"):
            verify(b"", ["g++"])

    def test_verifier_rejects_unexpected_original_opcode_without_native_build(self):
        # Synthetic all-zero image with an intentionally mock-valid digest:
        # tests exact original instruction matching, no actual ROM required.
        synthetic = b"\0" * 0x200000
        globals_ = MODULE["verify"].__globals__
        with patch.dict(globals_, {"ORIGINAL_SHA": hashlib.sha256(synthetic).hexdigest()}):
            with self.assertRaisesRegex(ValueError, "original floating-point instruction"):
                MODULE["verify"](synthetic, ["g++"])

    def test_report_aliasing_atomic_write_and_no_code_leakage(self):
        write = MODULE["write_metadata"]
        with tempfile.TemporaryDirectory(prefix="arcade-private-fp-audit-") as d:
            folder = Path(d)
            original = folder / "rom.bin"
            original.write_bytes(b"private-original-must-not-be-modified")
            hard = folder / "same-inode.json"
            link = folder / "same-target.json"
            os.link(original, hard)
            link.symlink_to(original)
            for dest in (original, hard, link):
                with self.subTest(dest=dest.name):
                    with self.assertRaisesRegex(ValueError, "aliases"):
                        write(original, dest, {"fake": True})
                    self.assertEqual(original.read_bytes(),
                                     b"private-original-must-not-be-modified")
            target = folder / "report.json"
            metadata = {"synthetic_cpu_state": True,
                        "continuous_original_boot": False,
                        "original_bytes_or_generated_game_code_exported": False}
            write(original, target, metadata)
            self.assertEqual(json.loads(target.read_text()), metadata)
            self.assertEqual(original.read_bytes(),
                             b"private-original-must-not-be-modified")
            self.assertEqual(set(x.name for x in folder.iterdir()),
                             {"rom.bin", "same-inode.json", "same-target.json",
                              "report.json"})


if __name__ == "__main__":
    unittest.main()
