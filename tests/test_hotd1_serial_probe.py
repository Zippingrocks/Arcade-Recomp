"""Original-architecture serial bootstrap synthetic integration tests.

These compiled native tests use only invented instructions and do not embed
any Sega ROM bytes or assume unverified serial status register values.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


class SerialStartupProbeTests(unittest.TestCase):
    def test_serial_tx_opt_in_then_halt_on_unimplemented_status(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("Host C++17 compiler not found")
        program = bytearray(0x200000)
        struct.pack_into("<4I", program, 0, 0, 0xb0, 0, 0x10)
        struct.pack_into("<I", program, 0xb0 + 24, 0x00510400)
        stob = (0x82 << 24) | (17 << 19) | (16 << 14) | (4 << 10)
        ldob = (0x80 << 24) | (18 << 19) | (16 << 14) | (4 << 10)
        # 0x10: lda TX2, g0; lda 0x81, g1; stob g1,(g0);
        # 0x24: lda STATUS,g0; ldob(g0),g2. Status is intentionally unknown.
        opwords = (0x8c803000, 0x01c00014,
                   0x8c883000, 0x81,
                   stob,
                   0x8c803000, 0x01c0001a,
                   ldob, 0xffffffff)
        struct.pack_into("<" + "I" * len(opwords), program, 0x10, *opwords)
        generated, report = emit_cpp(bytes(program), 0x10, 32)
        self.assertEqual(report.translated, 5)
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / "synthetic_maincpu.bin").write_bytes(program)
            (work / "hotd1_i960.cpp").write_text(generated, encoding="utf-8")
            binary = work / "probe"
            compiled = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                 "-I", str(work), "-I", str(ROOT / "runtime"),
                 str(ROOT / "tools/hotd1_strict_boot_probe.cpp"),
                 "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)

            strict = subprocess.run(
                [str(binary), str(work / "synthetic_maincpu.bin"), "10"],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(strict.returncode, 3, strict.stderr)
            self.assertIn("executed=2", strict.stdout)
            self.assertIn("documented_serial_tx=0", strict.stdout)

            serial = subprocess.run(
                [str(binary), str(work / "synthetic_maincpu.bin"),
                 "10", "--serial-tx"],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(serial.returncode, 3, serial.stderr)
            self.assertIn("executed=4", serial.stdout)
            self.assertIn("ip=0x2c", serial.stdout)
            self.assertIn("documented_serial_tx=1", serial.stdout)
            self.assertIn("serial_tx channel=2 byte=0x81 address=0x1c00014",
                          serial.stdout)
            self.assertIn("read8 @0x01c0001a", serial.stderr)


if __name__ == "__main__":
    unittest.main()
