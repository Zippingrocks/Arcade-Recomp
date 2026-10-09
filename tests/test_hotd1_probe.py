"""Integration test: native bootstrap probe with GENERATED SYNTHETIC program."""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp


ROOT = Path(__file__).resolve().parents[1]


class BootProbeTests(unittest.TestCase):
    def test_probe_builds_and_uses_shadow_bus_on_fake_rom(self):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            raise unittest.SkipTest("C++ compiler not installed")
        # Fake i960 reset record, then a 3-op native memory-write program.
        store = (0x92 << 24) | (17 << 19) | (16 << 14) | (4 << 10)
        memory = struct.pack("<9I", 0, 0xb0, 0, 0x10,
                             0x8c803000, 0x00200000,  # lda 0x200000,g0
                             0x8c883000, 0x42,        # lda 0x42,g1
                             store) + struct.pack("<I", 0xffffffff)
        # Synthetic PRCB lives at 0xb0 with initial FP stored at PRCB+24.
        memory = bytearray(memory.ljust(0xd0, b"\x00"))
        struct.pack_into("<I", memory, 0xb0 + 24, 0x00510400)
        memory = bytes(memory)
        source, report = emit_cpp(memory, 0x10)
        self.assertEqual(report.translated, 3)
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "hotd1_i960.cpp").write_text(source, encoding="utf-8")
            (directory / "fake_maincpu.bin").write_bytes(memory)
            binary = directory / "probe"
            compiling = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall",
                "-I", str(directory), "-I", str(ROOT / "runtime"),
                str(ROOT / "tools/hotd1_boot_probe.cpp"), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiling.returncode, 0, compiling.stderr)
            running = subprocess.run([
                str(binary), str(directory / "fake_maincpu.bin"), "3"],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(running.returncode, 0, running.stderr)
            self.assertIn("steps_executed=3", running.stdout)
            self.assertIn("shadow_bus_writes=1", running.stdout)
            self.assertIn("stop_ip=0x24", running.stdout)
            self.assertIn("limit_reached=true", running.stdout)


if __name__ == "__main__":
    unittest.main()
