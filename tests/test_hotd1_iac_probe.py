"""Compile the isolated IAC diagnostic with synthetic instructions, no game assets."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


class IsolatedIacProbeTests(unittest.TestCase):
    def test_original_style_reinit_in_isolated_synthetic_chip(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("C++17 compiler is required")
        chip = bytearray(0x200000)
        # Synthetic isolated code with g0=destination and g1=source.
        instruction = (0x60 << 24) | (17 << 14) | (2 << 7) | 16
        struct.pack_into("<I", chip, 0x6a0, instruction)
        struct.pack_into("<4I", chip, 0x560, 0x93000000, 0, 0x00510e00, 0x6b0)
        code, report = emit_cpp(bytes(chip), 0x6a0, 16)
        self.assertEqual(report.translated, 1)
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "synthetic_maincpu.bin").write_bytes(chip)
            (work / "hotd1_i960.cpp").write_text(code)
            exe = work / "probe"
            compile_command = [
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                "-I", str(work), "-I", str(ROOT / "runtime"),
                str(ROOT / "tools/hotd1_iac_probe.cpp"), "-o", str(exe)
            ]
            result = subprocess.run(compile_command, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(exe), str(work / "synthetic_maincpu.bin")],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ISOLATED ORIGINAL I960 INSTRUCTION, NOT AN ARCADE BOOT",
                          result.stdout)
            self.assertIn("pending_message=0x93000000", result.stdout)
            self.assertIn("prcb=0x510e00 requested_next_ip=0x6b0", result.stdout)


if __name__ == "__main__":
    unittest.main()
