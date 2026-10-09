"""Compile native Intel 80960KB 0x93 reinitialization on synthetic memory.

This tests what ArcadeRecomp IMPLEMENTS, not full original-arcade fidelity.
All opcode streams and PRCB data in this file are artificial.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]
SYNMOVQ = (0x60 << 24) | (17 << 14) | (2 << 7) | 16
MOV3_G0 = (0x5c << 24) | (16 << 19) | (0xc << 7) | (1 << 11) | 3

MEMORY = r"""
#include <cstdint>
#include <unordered_map>
#include <stdexcept>
using namespace arcaderecomp_generated;
struct TestMem {
    std::unordered_map<std::uint32_t, std::uint32_t> words;
    unsigned reads = 0;
};
static std::uint32_t read32(void* context, std::uint32_t address) {
    auto& mem = *static_cast<TestMem*>(context);
    ++mem.reads;
    return mem.words.at(address);
}
static TestMem make_mem() {
    TestMem mem{};
    mem.words[0x100] = 0x93000000u;
    mem.words[0x104] = 0x00000000u;
    mem.words[0x108] = 0x00510e00u;
    mem.words[0x10c] = 0x00000040u;
    mem.words[0x00510e04u] = 0x0000000cu;
    mem.words[0x00510e14u] = 0x00510800u;
    mem.words[0x00510e18u] = 0x00510400u;
    // Original HOTD1 has 0x1ff at PRCB+32, unlike Intel's published
    // generic example; don't reject a verified arcade control block.
    mem.words[0x00510e20u] = 0x000001ffu;
    mem.words[0x00510e24u] = 0x0000027fu;
    mem.words[0x00510e28u] = 0x00000210u;
    mem.words[0x00510e2cu] = 0u;
    return mem;
}
"""


def run_cpp(stream, body, entries=(0x40,)):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("C++17 compiler unavailable")
    source, report = emit_cpp(stream, 0, 64,
                              additional_entries=entries)
    with tempfile.TemporaryDirectory() as work:
        path = Path(work)
        cpp = path / "native.cpp"
        cpp.write_text(source + "\n" + MEMORY + body, encoding="utf-8")
        executable = path / "native"
        built = subprocess.run(
            [compiler, "-std=c++17", "-Wall", "-Wextra", "-O2",
             "-I", str(ROOT / "runtime"), str(cpp), "-o", str(executable)],
            capture_output=True, text=True, timeout=30)
        if built.returncode:
            raise AssertionError(built.stderr)
        executed = subprocess.run([str(executable)], capture_output=True,
                                  text=True, timeout=10)
        if executed.returncode:
            raise AssertionError(
                f"Native exit {executed.returncode}: {executed.stdout}{executed.stderr}"
            )
    return report


def stream(second_entry=MOV3_G0):
    data = bytearray(b"\xff" * 0x60)
    struct.pack_into("<I", data, 0, SYNMOVQ)
    struct.pack_into("<I", data, 0x40, second_entry)
    return bytes(data)


class ProcessorReinitializationTests(unittest.TestCase):
    def test_opt_in_reloads_prcb_and_enters_new_native_entry(self):
        report = run_cpp(stream(), r"""
int main() {
    TestMem memory = make_mem();
    CPU cpu{};
    Bus bus{}; bus.ctx = &memory; bus.read32 = &read32;
    if (!frame_init(cpu, 0x00510200u, 0u)) return 1;
    // Create a current local procedure frame that the IAC should retire.
    cpu.saved_valid[0] = true;
    cpu.saved_fp[0] = 0x00510200u;
    cpu.frame_depth = 1;
    cpu.r[0] = 0x00510200u;
    cpu.r[31] = 0x00510240u;
    cpu.r[16] = 0xff000010u;
    cpu.r[17] = 0x100u;
    cpu.allow_iac_93_reinitialize = true;

    if (!step(cpu, bus)) return 2;
    if (cpu.ip != 0x40u || cpu.r[31] != 0x00510400u ||
        cpu.r[1] != 0x00510440u || cpu.frame_depth != 0u ||
        cpu.saved_valid[0]) return 3;
    if (!cpu.prcb_loaded || cpu.prcb_address != 0x00510e00u ||
        cpu.sat_address != 0 ||
        cpu.interrupt_table_address != 0x00510800u ||
        cpu.interrupt_stack_address != 0x00510400u ||
        cpu.fault_table_address != 0x210u) return 4;
    if (cpu.process_controls != 0x001f2002u ||
        cpu.trace_controls != 0u || cpu.cc_defined ||
        cpu.pending_iac_valid || cpu.reinitialize_count != 1u) return 5;
    if (memory.reads != 11u || cpu.stop_code != StopCode::none) return 6;
    if (!step(cpu, bus) || cpu.r[16] != 3u || cpu.ip != 0x44u) return 7;
    return 0;
}
""")
        self.assertEqual(report.translated, 2)

    def test_default_strict_mode_still_stops_before_reinit(self):
        run_cpp(stream(), r"""
int main() {
    TestMem memory = make_mem();
    CPU cpu{};
    Bus bus{}; bus.ctx = &memory; bus.read32 = &read32;
    cpu.r[16] = 0xff000010u; cpu.r[17] = 0x100u;
    if (step(cpu, bus)) return 1;
    if (!cpu.pending_iac_valid ||
        cpu.stop_code != StopCode::iac_reinitialize_pending ||
        cpu.ip != 0 || cpu.reinitialize_count != 0 ||
        cpu.prcb_loaded) return 2;
    if (memory.reads != 4) return 3; // No PRCB read without opt-in
    return 0;
}
""")

    def test_bad_prcb_rejected_without_partial_cpu_commit(self):
        run_cpp(stream(), r"""
int main() {
    TestMem memory = make_mem();
    memory.words[0x00510e18u] = 0x00510401u; // broken KB frame alignment
    CPU cpu{}; Bus bus{}; bus.ctx = &memory; bus.read32 = &read32;
    cpu.ip = 0; cpu.r[16] = 0xff000010u; cpu.r[17] = 0x100u;
    cpu.allow_iac_93_reinitialize = true;
    if (step(cpu, bus) || cpu.stop_code != StopCode::iac_invalid_prcb)
        return 1;
    if (cpu.ip != 0 || cpu.reinitialize_count != 0 ||
        cpu.prcb_loaded || !cpu.pending_iac_valid ||
        cpu.r[31] != 0u) return 2;
    return 0;
}
""")

    def test_unmapped_prcb_does_not_mutate_cpu_before_fault(self):
        run_cpp(stream(), r"""
int main() {
    TestMem memory = make_mem();
    memory.words.erase(0x00510e14u); // missing interrupt-table location
    CPU cpu{}; Bus bus{}; bus.ctx = &memory; bus.read32 = &read32;
    cpu.r[16] = 0xff000010u; cpu.r[17] = 0x100u;
    cpu.allow_iac_93_reinitialize = true;
    try { step(cpu, bus); return 1; }
    catch (const std::out_of_range&) {}
    if (cpu.reinitialize_count != 0u || cpu.prcb_loaded ||
        cpu.ip != 0u || !cpu.pending_iac_valid) return 2;
    return 0;
}
""")

    def test_uninitialized_comparison_prevents_fake_post_reset_branch(self):
        # At 0x40, branch on equality without a fresh comparison.
        run_cpp(stream(second_entry=0x12000008), r"""
int main() {
    TestMem memory = make_mem();
    CPU cpu{}; Bus bus{}; bus.ctx = &memory; bus.read32 = &read32;
    cpu.r[16] = 0xff000010u; cpu.r[17] = 0x100u;
    cpu.allow_iac_93_reinitialize = true;
    if (!step(cpu, bus) || cpu.ip != 0x40u) return 1;
    if (step(cpu, bus) ||
        cpu.stop_code != StopCode::undefined_condition_code ||
        cpu.stop_ip != 0x40u) return 2;
    return 0;
}
""")

    def test_extra_entry_produces_post_reinit_aot_code(self):
        report = run_cpp(stream(), r"""
int main() { return 0; }
""")
        # AOT CFG also records the two sentinel invalid words that terminate
        # each artificial entry stream. They are never executed in the test.
        self.assertEqual(report.discovered, 4)
        self.assertEqual(report.translated, 2)
        self.assertEqual(report.unsupported, (4, 0x44))


if __name__ == "__main__":
    unittest.main()
