"""Build an explicitly fictional HOTD1 serial/IAC experiment with fake CPU ROM."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


class ExperimentalFixtureSmokeTests(unittest.TestCase):
    def test_fixture_is_separately_labeled_and_not_release_runtime(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("Host C++17 compiler missing")
        toy = bytearray(0x200000)
        struct.pack_into("<4I", toy, 0, 0, 0xb0, 0, 0x10)
        struct.pack_into("<I", toy, 0xb0 + 24, 0x00510400)
        struct.pack_into("<I", toy, 0x10, 0xffffffff)
        source, report = emit_cpp(bytes(toy), 0x10, 16,
                                  additional_entries=(0x40,))
        self.assertEqual(report.translated, 0)
        with tempfile.TemporaryDirectory() as path:
            work = Path(path)
            (work / "hotd1_i960.cpp").write_text(source, encoding="utf-8")
            (work / "synthetic_maincpu.bin").write_bytes(toy)
            binary = work / "fake_serial_probe"
            built = subprocess.run(
                [compiler, "-std=c++17", "-Wall", "-Wextra", "-O2",
                 "-I", str(work), "-I", str(ROOT / "runtime"),
                 str(ROOT / "tools/experimental/hotd1_fake_serial_reinit.cpp"),
                 "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary),
                                  str(work / "synthetic_maincpu.bin")],
                                 capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 4, run.stdout + run.stderr)
            self.assertIn("ARTIFICIAL SERIAL RESPONSE", run.stderr)
            self.assertIn("reinit_count=0", run.stdout)


if __name__ == "__main__":
    unittest.main()
