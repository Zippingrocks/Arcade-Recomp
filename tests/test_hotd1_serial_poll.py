"""Compiled native i960 polling and explicit serial-ready fixture.

The test reflects generic architecture documentation, not any copyrighted
Sega executable bytes. The 315-5649 status fixture is deliberately synthetic;
it is NOT evidence of actual Model 2C serial clock or input timing.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


class NativeSerialReadyPollTests(unittest.TestCase):
    def test_compiled_poll_waits_for_explicit_ready_status(self):
        cxx = shutil.which("g++") or shutil.which("clang++")
        if not cxx:
            raise unittest.SkipTest("C++17 compiler unavailable")
        # Synthetic sequence:
        #  0x00: lda 0x01c00000,g0
        #  0x08: mov 12,g1
        #  0x0c: ldob 0x1a(g0),g2
        #  0x10: and g1,g2,g2
        #  0x14: cmpi g1,g2
        #  0x18: be +8   (exit at 0x20)
        #  0x1c: b -16  (poll 0x0c)
        #  0x20: ret (not executed in this test)
        mov = (0x5c << 24) | (17 << 19) | (0xc << 7) | (1 << 11) | 12
        ldob = (0x80 << 24) | (18 << 19) | (16 << 14) | (1 << 13) | 0x1a
        and_op = (0x58 << 24) | (18 << 19) | (18 << 14) | (1 << 7) | 17
        cmpi = (0x5a << 24) | (18 << 14) | (1 << 7) | 17
        words = [0x8c803000, 0x01c00000, mov, ldob, and_op, cmpi,
                 0x12000008, 0x08fffff0, 0x0a000000]
        translated, report = emit_cpp(
            struct.pack("<" + "I" * len(words), *words), 0, 64)
        self.assertEqual(report.translated, 8)
        main = r"""
#include "model2c_bus.hpp"
using namespace arcaderecomp_generated;
using namespace arcaderecomp_model2c;
int main() {
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    board.enable_partial_serial_io();
    unsigned sample_count = 0;
    board.serial_device().set_serial_status_source([&]() -> std::uint8_t {
        ++sample_count;
        return sample_count >= 3u ? 0x0cu : 0x08u; // explicit fake test sequence
    });
    CPU cpu{};
    cpu.ip = 0;
    Bus bus = board.callbacks();
    unsigned steps = 0;
    while (steps < 32u && cpu.ip != 0x20u) {
        if (!step(cpu, bus)) return 1;
        ++steps;
    }
    if (cpu.ip != 0x20u || sample_count != 3u ||
        cpu.cc != 2 || cpu.r[18] != 12u) return 2;
    if (board.serial_device().transmissions().size() != 0) return 3;
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            file = tmp / "test.cpp"
            file.write_text(translated + "\n" + main, encoding="utf-8")
            binary = tmp / "test"
            compiled = subprocess.run(
                [cxx, "-std=c++17", "-O2", "-Wall", "-Wextra",
                 "-I", str(ROOT / "runtime"), str(file), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(binary)], capture_output=True,
                                      text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stderr)


if __name__ == "__main__":
    unittest.main()
