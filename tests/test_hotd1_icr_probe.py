"""Synthetic standalone test for isolated original-ICR research harness.

The archive-shaped data is artificially generated here; no Sega game bytes
or user-provided ROMs ever enter repository CI.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


class Hotd1OriginalIcrProbeTests(unittest.TestCase):
    def test_original_icr_probe_runs_on_synthetic_i960_chip(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("C++17 compiler unavailable")
        chip = bytearray(0x200000)
        # Invent an instruction with the published SYNMOV register encoding.
        # The actual original ROM is NOT used in this test.
        synmov = (0x60 << 24) | (21 << 14) | 20
        struct.pack_into("<I", chip, 0x6d4, synmov)
        struct.pack_into("<I", chip, 0x6a8, 0x0f0e0d0c)
        generated, report = emit_cpp(bytes(chip), 0x6d4, 16)
        self.assertEqual(report.translated, 1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / "hotd1_i960.cpp").write_text(generated, encoding="utf-8")
            rom = path / "synthetic_maincpu.bin"
            rom.write_bytes(chip)
            binary = path / "icr_probe"
            compiled = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                "-I", str(path), "-I", str(ROOT / "runtime"),
                str(ROOT / "tools/hotd1_icr_probe.cpp"), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(binary), str(rom)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("NOT FULL ARCADE BOOT", result.stdout)
            self.assertIn("old_icr=0xff000000", result.stdout)
            self.assertIn("new_icr=0xf0e0d0c", result.stdout)
            self.assertIn("next_ip=0x6d8", result.stdout)

            # Refuse a fake input with wrong source word, rather than certify it.
            struct.pack_into("<I", chip, 0x6a8, 0x11223344)
            rom.write_bytes(chip)
            result = subprocess.run([str(binary), str(rom)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("verify this is the original HOTD1", result.stderr)


if __name__ == "__main__":
    unittest.main()
