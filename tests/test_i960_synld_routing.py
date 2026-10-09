"""Compiled Intel 80960KB SYNLD and interrupt-pin routing tests.

All instructions and board data are synthetic, not extracted game content.
Pin routing is tested as a pure CPU register decoder, without simulated
interrupt timing, arcade cabinet I/O or exception delivery.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]
SYNLD = (0x61 << 24) | (17 << 19) | (5 << 7) | 16
IMAGE = struct.pack("<2I", SYNLD, 0xffffffff)


def native(program, harness):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        raise unittest.SkipTest("Need C++17 compiler")
    code, report = emit_cpp(program, 0, 16)
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        source = directory / "test.cpp"
        source.write_text(code + "\n" + harness, encoding="utf-8")
        exe = directory / "test"
        compile_result = subprocess.run(
            [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "runtime"), str(source), "-o", str(exe)],
            capture_output=True, text=True, timeout=50)
        if compile_result.returncode:
            raise AssertionError(compile_result.stderr)
        result = subprocess.run([str(exe)], capture_output=True,
                                text=True, timeout=15)
        if result.returncode:
            raise AssertionError(
                f"Native exit {result.returncode}: {result.stderr}")
    return report


class KBLoadAndRoutingTests(unittest.TestCase):
    def test_original_intel_opcode_decodes_as_synchronous_load(self):
        decoded = decode(IMAGE, 0)
        self.assertTrue(decoded.supported)
        self.assertEqual(decoded.mnemonic, "synld")
        self.assertEqual(decoded.asm(), "synld g0, g1")
        self.assertEqual(decoded.size, 4)

    def test_onchip_icr_read_does_not_need_external_bus(self):
        report = native(IMAGE, r"""
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    cpu.interrupt_control_register = 0x0f0e0d0cu;
    cpu.r[16] = 0xff000007u; // KB forces 4-byte alignment
    cpu.r[17] = 0xdeadbeefu;
    cpu.cc_defined = false;
    if (!step(cpu, bus)) return 1;
    if (cpu.ip != 4 || cpu.r[17] != 0x0f0e0d0cu ||
        cpu.cc != 2 || !cpu.cc_defined) return 2;
    return 0;
}
""")
        self.assertEqual(report.translated, 1)
        self.assertEqual(report.unsupported, (4,))

    def test_plain_memory_sync_read_and_hardware_bad_access(self):
        native(IMAGE, r"""
#include "model2c_bus.hpp"
int main() {
    using namespace arcaderecomp_generated;
    using namespace arcaderecomp_model2c;
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    board.write(0x00510400u, 4, 0x10203040u);
    CPU cpu{};
    cpu.r[16] = 0x00510403u; // aligns down to work-RAM word
    cpu.r[17] = 0u;
    Bus bus = board.callbacks();
    if (!step(cpu, bus) || cpu.ip != 4u ||
        cpu.r[17] != 0x10203040u || cpu.cc != 2) return 1;

    cpu.ip = 0;
    cpu.r[16] = 0x00f80000u; // UNKNOWN Sega board device
    cpu.r[17] = 0x12345678u;
    if (!step(cpu, bus)) return 2; // Bad Access: CC=000; do not CPU-fault
    if (cpu.r[17] != 0x12345678u || cpu.cc != 0 || !cpu.cc_defined) return 3;

    cpu.ip = 0; cpu.r[16] = 0x00e00000u; // CPU wait states, not RAM
    if (!step(cpu, bus) || cpu.cc != 0) return 4;
    return 0;
}
""")

    def test_no_sync_bus_stops_instead_of_async_guess(self):
        native(IMAGE, r"""
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    cpu.r[16] = 0x00510400u;
    cpu.r[17] = 0x12345678u;
    bus.read32 = [](void*, std::uint32_t) -> std::uint32_t {
        return 0xaaaaaaaau;
    }; // Async bus access MUST NOT impersonate a completed SYNLD.
    if (step(cpu, bus) ||
        cpu.stop_code != StopCode::synchronous_device_unimplemented) return 1;
    if (cpu.ip != 0 || cpu.r[17] != 0x12345678u) return 2;
    return 0;
}
""")

    def test_documented_interrupt_pin_mux_and_original_rom_icr(self):
        native(IMAGE, r"""
#include "i960_interrupt_pins.hpp"
using namespace arcaderecomp_generated;
int main() {
    CPU cpu{}; // Intel KB reset ICR=FF000000h
    if (kb_pin_routing(cpu, 0).role != KBPinRole::iac_notification) return 1;
    if (kb_pin_routing(cpu, 1).role != KBPinRole::direct_vector) return 2;
    if (kb_pin_routing(cpu, 2).role != KBPinRole::external_intr) return 3;
    if (kb_pin_routing(cpu, 3).role != KBPinRole::external_inta) return 4;
    cpu.interrupt_control_register = 0x0f0e0d0cu; // Original HOTD1 value
    for (unsigned pin = 0; pin != 4; ++pin) {
        const auto value = kb_pin_routing(cpu, pin);
        if (value.role != KBPinRole::direct_vector ||
            value.vector != 12u + pin) return 5;
    }
    cpu.interrupt_control_register = 0xff000e00u;
    if (kb_pin_routing(cpu, 0).role != KBPinRole::iac_notification ||
        kb_pin_routing(cpu, 1).vector != 0x0eu ||
        kb_pin_routing(cpu, 2).role != KBPinRole::external_intr ||
        kb_pin_routing(cpu, 3).role != KBPinRole::external_inta) return 6;
    bool invalid = false;
    try { (void)kb_pin_routing(cpu, 4u); }
    catch (const std::out_of_range&) { invalid = true; }
    if (!invalid) return 7;
    return 0;
}
""")

if __name__ == "__main__":
    unittest.main()
