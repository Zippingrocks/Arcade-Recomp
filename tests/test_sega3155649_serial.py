"""Synthetic tests for the independently authored Sega 315-5649 serial subset.

All original ROM data stays private; register values used in tests are invented.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def compile_and_run(includes, body):
    cxx = shutil.which("g++") or shutil.which("clang++")
    if not cxx:
        raise unittest.SkipTest("C++17 compiler unavailable")
    with tempfile.TemporaryDirectory() as folder:
        work = Path(folder)
        cpp = work / "sega_io_test.cpp"
        cpp.write_text(includes + "\n" + body, encoding="utf-8")
        exe = work / "io_test"
        build = subprocess.run([
            cxx, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "runtime"), str(cpp), "-o", str(exe)],
            capture_output=True, text=True, timeout=30)
        if build.returncode:
            raise AssertionError(build.stderr)
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
        if run.returncode:
            raise AssertionError(f"Native exit {run.returncode}\n{run.stdout}{run.stderr}")


class Sega3155649Tests(unittest.TestCase):
    def test_serial_register_decode_and_transmission_order(self):
        compile_and_run('#include "sega3155649_serial.hpp"', r"""
#include <cstdint>
#include <vector>
using namespace arcaderecomp_model2c;
int main() {
    IO3155649 device{};
    std::vector<unsigned> outgoing;
    device.set_serial_tx_observer([&](std::uint8_t byte, unsigned channel) {
        outgoing.push_back(channel * 0x100u + byte);
    });
    device.write_bus_byte(0x01c00012u, 0x81u); // TX1
    device.write_bus_byte(0x01c00014u, 0xffu); // TX2
    device.write_bus_byte(0x01c00014u, 0x04u); // TX2, new mux selection
    if (outgoing.size() != 3 || outgoing[0] != 0x181u ||
        outgoing[1] != 0x2ffu || outgoing[2] != 0x204u) return 1;
    if (device.transmissions().size() != 3 ||
        device.transmissions()[0].sequence != 1u ||
        device.transmissions()[2].sequence != 3u) return 2;
    if (device.last_tx(1) != 0x81u || device.last_tx(2) != 0x04u) return 3;
    if (device.transmissions()[2].address != 0x01c00014u) return 4;
    return 0;
}
""")

    def test_no_fabricated_serial_rx_or_status_and_reject_odd_lane(self):
        compile_and_run('#include "model2c_bus.hpp"', r"""
using namespace arcaderecomp_model2c;
int main() {
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    try { board.write(0x01c00014u, 1, 0xffu); return 1; }
    catch (const DeviceAccessFault& e) {
        if (e.region != Region::serial_io) return 2;
    }
    board.enable_partial_serial_io();
    board.write(0x01c00014u, 1, 0xffu);
    if (board.writes().size() != 1u ||
        board.serial_device().last_tx(2u) != 0xffu) return 3;
    try { board.read(0x01c00018u, 1); return 4; }
    catch (const DeviceAccessFault& e) {
        if (e.address != 0x01c00018u || e.write) return 5;
    }
    try { board.read(0x01c0001au, 1); return 6; }
    catch (const DeviceAccessFault&) {} // serial status unimplemented, deliberately
    try { board.write(0x01c00015u, 1, 1); return 7; }
    catch (const DeviceAccessFault&) {} // byte lane not routed to IO chip
    try { board.write(0x01c00014u, 2, 0xff); return 8; }
    catch (const DeviceAccessFault&) {} // unsupported 16-bit device transfer
    try { board.write(0x01c00010u, 1, 0xff); return 9; }
    catch (const DeviceAccessFault&) {} // direction port not implemented
    if (board.writes().size() != 1u ||
        board.serial_device().transmissions().size() != 1u) return 10;
    return 0;
}
""")

    def test_explicit_injected_rx_provider_and_distinct_channels(self):
        compile_and_run('#include "model2c_bus.hpp"', r"""
using namespace arcaderecomp_model2c;
int main() {
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    board.enable_partial_serial_io();
    board.write(0x01c00012u, 1, 0x07u);
    board.write(0x01c00014u, 1, 0x03u);
    unsigned calls = 0;
    board.serial_device().set_serial_rx([&](std::uint8_t selection, unsigned channel) {
        ++calls;
        return static_cast<std::uint8_t>(selection + 0x10u * channel);
    });
    if (board.read(0x01c00016u, 1) != 0x17u) return 1;
    if (board.read(0x01c00018u, 1) != 0x23u) return 2;
    if (calls != 2u) return 3;
    return 0;
}
""")

    def test_translated_i960_serial_transmit_with_unconfigured_receive_halts(self):
        # Artificial executable sequence, NOT taken from HOTD1:
        # lda TX2,g0; lda 0x42,g1; stob g1,(g0);
        # lda RX2,g0; ldob (g0),g2 ; unsupported.
        stob = (0x82 << 24) | (17 << 19) | (16 << 14) | (4 << 10)
        ldob = (0x80 << 24) | (18 << 19) | (16 << 14) | (4 << 10)
        opwords = (0x8c803000, 0x01c00014, 0x8c883000, 0x42,
                   stob, 0x8c803000, 0x01c00018, ldob, 0xffffffff)
        program = struct.pack("<" + "I" * len(opwords), *opwords)
        source, report = emit_cpp(program, 0, max_instructions=32)
        self.assertEqual(report.translated, 5)
        compile_and_run(source + '\n#include "model2c_bus.hpp"', r"""
using namespace arcaderecomp_generated;
using namespace arcaderecomp_model2c;
int main() {
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    board.enable_partial_serial_io();
    CPU cpu{}; Bus bus = board.callbacks();
    for (int i = 0; i < 4; ++i)
        if (!step(cpu, bus)) return 1;
    if (cpu.ip != 28u ||
        board.serial_device().last_tx(2) != 0x42u) return 2;
    try { step(cpu, bus); return 3; }
    catch (const DeviceAccessFault& fault) {
        if (fault.address != 0x01c00018u ||
            fault.region != Region::serial_io || fault.write) return 4;
    }
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
