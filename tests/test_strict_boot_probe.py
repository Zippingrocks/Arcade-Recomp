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

    def test_serial_trace_reports_missing_status_without_inventing_zero(self):
        # Entire input is synthetic; observed status is deliberately absent.
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("No C++17 compiler")
        program = bytearray(0x200000)
        struct.pack_into("<4I", program, 0, 0, 0xb0, 0, 0x10)
        struct.pack_into("<I", program, 0xb0 + 24, 0x00510400)
        stob = (0x82 << 24) | (17 << 19) | (16 << 14) | (4 << 10)
        read_status = (0x80 << 24) | (18 << 19) | (16 << 14) | (4 << 10)
        opcodes = (0x8c803000, 0x01c00014, 0x8c883000, 0xff,
                   stob, 0x8c803000, 0x01c0001a, read_status, 0xffffffff)
        struct.pack_into("<" + "I" * len(opcodes), program, 0x10, *opcodes)
        cpp, report = emit_cpp(bytes(program), 0x10, 32)
        self.assertEqual(report.translated, 5)
        with tempfile.TemporaryDirectory(prefix="arcade-strict-serial-trace-") as tmp:
            folder = Path(tmp)
            (folder / "hotd1_i960.cpp").write_text(cpp, encoding="utf-8")
            (folder / "synthetic.bin").write_bytes(program)
            binary = folder / "strict"
            built = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                "-I", str(folder), "-I", str(ROOT / "runtime"),
                str(ROOT / "tools/hotd1_strict_boot_probe.cpp"), "-o", str(binary)],
                capture_output=True, text=True, timeout=45)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([
                str(binary), str(folder / "synthetic.bin"), "10", "--serial-tx"],
                capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 3, run.stdout + run.stderr)
            self.assertIn("executed=4", run.stdout)
            self.assertIn("serial_tx channel=2 byte=0xff", run.stdout)
            self.assertIn("serial_access ordinal=1 direction=write", run.stdout)
            self.assertIn("address=0x1c00014 width=1 completed=yes value=0xff",
                          run.stdout)
            self.assertIn("serial_access ordinal=2 direction=read", run.stdout)
            self.assertIn("address=0x1c0001a width=1 completed=no value=UNOBSERVED",
                          run.stdout)
            self.assertNotIn("completed=no value=0x0", run.stdout)
            self.assertIn("required hardware not implemented", run.stderr)


if __name__ == "__main__":
    unittest.main()
