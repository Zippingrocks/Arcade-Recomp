"""End-to-end synthetic strict probe must explicitly halt at Sega I/O.

No game ROM bytes or ROM-derived generated files are used or committed.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


class StrictBootProbeTests(unittest.TestCase):
    def test_native_probe_rejects_unimplemented_lightgun_io(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("No C++ compiler")
        program = bytearray(0x200000)
        struct.pack_into("<4I", program, 0, 0, 0xb0, 0, 0x10)
        struct.pack_into("<I", program, 0xb0 + 24, 0x00510400)
        stob = (0x82 << 24) | (17 << 19) | (16 << 14) | (4 << 10)
        struct.pack_into("<4I", program, 0x10,
                         0x8c803000, 0x01c00014, stob, 0xffffffff)
        source, report = emit_cpp(bytes(program), 0x10, 16)
        self.assertEqual(report.translated, 2)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "hotd1_i960.cpp").write_text(source, encoding="utf-8")
            (directory / "synthetic_maincpu.bin").write_bytes(program)
            binary = directory / "strict_probe"
            compile_result = subprocess.run(
                [compiler, "-std=c++17", "-Wall", "-O2",
                 "-I", str(directory), "-I", str(ROOT / "runtime"),
                 str(ROOT / "tools/hotd1_strict_boot_probe.cpp"), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run_result = subprocess.run(
                [str(binary), str(directory / "synthetic_maincpu.bin"), "10"],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(run_result.returncode, 3, run_result.stderr)
            self.assertIn("executed=1", run_result.stdout)
            self.assertIn("ip=0x18", run_result.stdout)
            self.assertIn("Sega 315-5649 I/O", run_result.stderr)
            self.assertIn("required hardware not implemented", run_result.stderr)


if __name__ == "__main__":
    unittest.main()
