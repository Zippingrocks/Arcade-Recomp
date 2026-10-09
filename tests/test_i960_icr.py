"""Native Intel 80960KB SYNMOV-to-ICR tests using synthetic program bytes.

CPU interrupt-control register behavior is drawn from Intel's 1988 KB
programmer's/hardware designer's manuals, NOT another emulator's source code.
No Sega ROM or game-derived native output is included here.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def fixture(source, harness):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("C++17 compiler unavailable")
    with tempfile.TemporaryDirectory() as root:
        path = Path(root)
        cpp = path / "icr.cpp"
        cpp.write_text(source + "\n" + harness, encoding="utf-8")
        exe = path / "icr"
        compile_result = subprocess.run(
            [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
             "-I", str(ROOT / "runtime"), str(cpp), "-o", str(exe)],
            capture_output=True, text=True, timeout=30)
        if compile_result.returncode:
            raise AssertionError(compile_result.stderr)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise AssertionError(f"native exit {result.returncode}:\n"
                                 + result.stdout + result.stderr)


# Synthetic SYNMOV destination g2, source g3; this is NOT game machine code.
OP = (0x60 << 24) | (19 << 14) | 18
IMAGE = struct.pack("<2I", OP, 0xffffffff)
HEADER = """
#include <cstdint>
#include <stdexcept>
using namespace arcaderecomp_generated;
struct Fixture { std::uint32_t word = 0x0f0e0d0cu; unsigned reads = 0; };
static std::uint32_t rd(void* opaque, std::uint32_t addr) {
    Fixture& m = *static_cast<Fixture*>(opaque);
    if (addr != 0x100u) throw std::out_of_range("unmapped source");
    ++m.reads;
    return m.word;
}
"""


class IntelKBInterruptControlTests(unittest.TestCase):
    def test_initial_icr_and_native_sync_move_to_internal_register(self):
        cpp, report = emit_cpp(IMAGE, 0)
        self.assertEqual(report.translated, 1)
        self.assertEqual(report.unsupported, (4,))
        self.assertIn("sync_move_word", cpp)
        fixture(cpp, HEADER + """
int main() {
    CPU cpu{}; Fixture memory{};
    Bus bus{}; bus.ctx = &memory; bus.read32 = &rd;
    if (!frame_init(cpu, 0x00510400u, 0)) return 1;
    if (cpu.interrupt_control_register != 0xff000000u) return 2;
    cpu.r[18] = 0xff000007u; // Intel forces word alignment down to 0x...004.
    cpu.r[19] = 0x101u;      // Source is also word aligned.
    cpu.cc_defined = false;  // SYNMOV success redefines AC.cc.
    if (!step(cpu, bus)) return 3;
    if (cpu.ip != 4u || cpu.interrupt_control_register != 0x0f0e0d0cu)
        return 4;
    if (cpu.cc != 2 || !cpu.cc_defined || memory.reads != 1u) return 5;
    return 0;
}
""")

    def test_normal_synchronous_io_not_faked_and_cpu_unchanged(self):
        cpp, _ = emit_cpp(IMAGE, 0)
        fixture(cpp, HEADER + """
int main() {
    CPU cpu{}; Fixture memory{};
    Bus bus{}; bus.ctx = &memory; bus.read32 = &rd;
    cpu.r[18] = 0x00f80000u; cpu.r[19] = 0x100u;
    const std::uint32_t before = cpu.interrupt_control_register;
    if (step(cpu, bus) ||
        cpu.stop_code != StopCode::synchronous_device_unimplemented) return 1;
    if (cpu.ip != 0u || cpu.interrupt_control_register != before ||
        memory.reads != 0u) return 2;
    return 0;
}
""")

    def test_missing_source_bus_or_unmapped_read_fails_closed(self):
        cpp, _ = emit_cpp(IMAGE, 0)
        fixture(cpp, HEADER + """
int main() {
    CPU cpu{}; Bus bus{};
    cpu.r[18] = 0xff000004u; cpu.r[19] = 0x100u;
    if (step(cpu, bus) || cpu.stop_code != StopCode::missing_bus) return 1;
    if (cpu.interrupt_control_register != 0xff000000u) return 2;
    Fixture memory{};
    bus.ctx = &memory; bus.read32 = &rd;
    cpu.r[19] = 0x200u;
    try { step(cpu, bus); return 3; }
    catch (const std::out_of_range&) {}
    if (cpu.interrupt_control_register != 0xff000000u ||
        memory.reads != 0u) return 4;
    return 0;
}
""")

    def test_reinitialize_frame_init_restores_initial_icr(self):
        cpp, _ = emit_cpp(IMAGE, 0)
        fixture(cpp, HEADER + """
int main() {
    CPU cpu{};
    if (!frame_init(cpu, 0x00510400u, 0u)) return 1;
    cpu.interrupt_control_register = 0x0f0e0d0cu;
    if (!frame_init(cpu, 0x00510500u, 0u)) return 2;
    if (cpu.interrupt_control_register != 0xff000000u) return 3;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
