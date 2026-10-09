"""Compile the strict Model 2C bus and exercise it with fake arcade input.

No commercial ROM data or copied emulator implementations are included.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def native(source, harness):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("Host C++ compiler is required")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        cpp = tmp / "test.cpp"
        cpp.write_text(source + "\n" + harness, encoding="utf-8")
        binary = tmp / "test"
        result = subprocess.run(
            [compiler, "-std=c++17", "-Wall", "-Wextra", "-O2",
             "-I", str(ROOT / "runtime"), str(cpp), "-o", str(binary)],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(f"Native compilation error:\n{result.stderr}")
        result = subprocess.run([str(binary)], capture_output=True,
                                text=True, timeout=15)
        if result.returncode:
            raise AssertionError(f"Native test returned {result.returncode}:\n"
                                 + result.stdout + result.stderr)


class Model2CStrictBusTests(unittest.TestCase):
    def test_address_map_and_unimplemented_io_fail_closed(self):
        native('#include "model2c_bus.hpp"', """
using namespace arcaderecomp_model2c;
int main() {
    std::vector<std::uint8_t> program(StrictBus::kProgramSize, 0);
    program[0] = 0x12; program[1] = 0x34;
    StrictBus board(std::move(program));
    if (board.read(0, 2) != 0x3412u) return 1;
    board.write(0x00510400u, 4u, 0x12345678u);
    if (board.read(0x00510400u, 4u) != 0x12345678u) return 2;
    board.write(0x00510404u, 1u, 0xabu);
    if (board.read(0x00510404u, 1u) != 0xabu) return 3;
    board.write(0x00e00000u, 4u, 0x99887766u);
    if (board.read(0x00e00000u, 4u) != 0x99887766u) return 4;
    if (board.pending_timing_writes() != 1u) return 5;
    if (board.writes().size() != 3u) return 6;

    try { board.read(0x01c00014u, 1u); return 7; }
    catch (const DeviceAccessFault& error) {
        if (error.region != Region::serial_io || error.address != 0x01c00014u)
            return 8;
    }
    try { board.write(0x00000000u, 1u, 42u); return 9; }
    catch (const DeviceAccessFault& error) {
        if (error.region != Region::program_rom) return 10;
    }
    try { board.read(0x00f80000u, 4u); return 11; }
    catch (const DeviceAccessFault& error) {
        if (error.region != Region::unmapped) return 12;
    }
    try { board.read(0x005fffffu, 4u); return 13; }
    catch (const DeviceAccessFault&) {}
    try { board.read(0x02000000u, 4u); return 14; }
    catch (const DeviceAccessFault& error) {
        if (error.region != Region::game_data_rom) return 15;
    }
    return 0;
}
""")

    def test_separate_game_data_windows(self):
        native('#include "model2c_bus.hpp"', """
using namespace arcaderecomp_model2c;
int main() {
    std::vector<std::uint8_t> program(StrictBus::kProgramSize, 0);
    std::vector<std::uint8_t> data(StrictBus::kDataSize, 0);
    data[0] = 0x11u;
    data[0x01000000u] = 0x22u;
    StrictBus board(std::move(program), std::move(data));
    if (board.read(0x02000000u, 1u) != 0x11u) return 1;
    if (board.read(0x06000000u, 1u) != 0x22u) return 2;
    return 0;
}
""")

    def test_generated_native_store_stops_at_serial_io_device(self):
        # Artificial i960 words: lda IO register,g0; stob g1,(g0).
        stob = (0x82 << 24) | (17 << 19) | (16 << 14) | (4 << 10)
        image = struct.pack("<4I", 0x8c803000, 0x01c00014,
                            stob, 0xffffffff)
        code, report = emit_cpp(image, 0, 16)
        self.assertEqual(report.translated, 2)
        native(code, """
#include "model2c_bus.hpp"
int main() {
    using namespace arcaderecomp_generated;
    using namespace arcaderecomp_model2c;
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    CPU cpu{}; Bus callbacks = board.callbacks(); cpu.ip = 0; cpu.r[17] = 0x42;
    if (!step(cpu, callbacks) || cpu.r[16] != 0x01c00014u) return 1;
    try { step(cpu, callbacks); return 2; }
    catch (const DeviceAccessFault& e) {
        if (e.region != Region::serial_io || e.width != 1u || !e.write)
            return 3;
    }
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
