"""Compile synthetic i960 byte/shortwidth transfers into native C++.

All test instruction words are artificial; no copyrighted arcade ROM bytes.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def instruction(opcode, register, base=16, disp=0):
    # MEMA base+12bit-offset for nonzero displacement; MEMB mode 4 for (base).
    addressing = ((1 << 13) | disp) if disp else (4 << 10)
    return (opcode << 24) | (register << 19) | (base << 14) | addressing


class WidthTransferTests(unittest.TestCase):
    @staticmethod
    def execute(image, checks):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if compiler is None:
            raise unittest.SkipTest("No host C++ compiler")
        code, report = emit_cpp(image, 0, 48)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "verify.cpp"
            source.write_text(code + "\n" + checks, encoding="utf-8")
            executable = folder / "native_test"
            command = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                       "-I", str(ROOT / "runtime"),
                       str(source), "-o", str(executable)]
            compiling = subprocess.run(command, capture_output=True, text=True,
                                       timeout=30)
            if compiling.returncode:
                raise AssertionError(compiling.stderr)
            result = subprocess.run([str(executable)], capture_output=True,
                                    text=True, timeout=10)
            if result.returncode:
                raise AssertionError(
                    f"Native exit {result.returncode}: {result.stdout}{result.stderr}")
        return report

    def test_byte_and_halfword_load_store_and_signed_extension(self):
        fake = [
            0x8c803000, 0x1000,       # synthetic lda 0x1000, g0
            0x8c883000, 0xdeadbeef,   # synthetic lda constant, g1
            instruction(0x82, 17),    # stob g1, (g0)
            instruction(0x80, 18),    # ldob (g0), g2
            instruction(0xc0, 19),    # ldib (g0), g3
            instruction(0x8a, 17, disp=2),  # stos g1, 2(g0)
            instruction(0x88, 20, disp=2),  # ldos 2(g0), g4
            instruction(0xc8, 21, disp=2),  # ldis 2(g0), g5
            0xffffffff
        ]
        memory = struct.pack("<" + "I" * len(fake), *fake)
        report = self.execute(memory, """
#include <array>
struct RAM {
    std::array<std::uint8_t, 8> bytes{};
    unsigned read8_count = 0, read16_count = 0;
    unsigned write8_count = 0, write16_count = 0;
};
std::uint8_t read8(void* c, std::uint32_t address) {
    RAM& ram = *static_cast<RAM*>(c);
    ++ram.read8_count;
    return ram.bytes.at(address - 0x1000u);
}
std::uint16_t read16(void* c, std::uint32_t address) {
    RAM& ram = *static_cast<RAM*>(c);
    ++ram.read16_count;
    unsigned index = address - 0x1000u;
    return static_cast<std::uint16_t>(ram.bytes.at(index) |
                                     (std::uint16_t(ram.bytes.at(index + 1u)) << 8));
}
void write8(void* c, std::uint32_t address, std::uint8_t value) {
    RAM& ram = *static_cast<RAM*>(c);
    ++ram.write8_count;
    ram.bytes.at(address - 0x1000u) = value;
}
void write16(void* c, std::uint32_t address, std::uint16_t value) {
    RAM& ram = *static_cast<RAM*>(c);
    ++ram.write16_count;
    unsigned index = address - 0x1000u;
    ram.bytes.at(index) = value & 0xffu;
    ram.bytes.at(index + 1u) = value >> 8;
}
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; RAM ram{};
    Bus bus{&ram, nullptr, nullptr, &read8, &write8, &read16, &write16};
    for (int i = 0; i < 8; ++i)
        if (!step(cpu, bus)) return 1;
    if (cpu.r[18] != 0xefu) return 2;        // ldob zero extends
    if (cpu.r[19] != 0xffffffefu) return 3;  // ldib sign extends
    if (cpu.r[20] != 0xbeefu) return 4;      // ldos zero extends
    if (cpu.r[21] != 0xffffbeefu) return 5;  // ldis sign extends
    if (ram.bytes[0] != 0xef || ram.bytes[2] != 0xef ||
        ram.bytes[3] != 0xbe) return 6;
    if (ram.read8_count != 2 || ram.read16_count != 2 ||
        ram.write8_count != 1 || ram.write16_count != 1) return 7;
    return 0;
}
""")
        self.assertEqual(report.translated, 8)
        self.assertIn(40, report.unsupported)

    def test_device_write_fails_closed_if_width_callback_absent(self):
        fake = struct.pack("<4I", 0x8c803000, 0x1000,
                           instruction(0x82, 17), 0xffffffff)
        report = self.execute(fake, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{};
    if (!step(cpu, bus) || cpu.ip != 8u) return 1;
    if (step(cpu, bus)) return 2;
    if (cpu.stop_code != StopCode::missing_bus || cpu.stop_ip != 8u) return 3;
    return 0;
}
""")
        self.assertEqual(report.translated, 2)


if __name__ == "__main__":
    unittest.main()
