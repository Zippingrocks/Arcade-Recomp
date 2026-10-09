"""Synthetic native 80960KB SYNMOVQ / IAC tests. No copyrighted game bytes."""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def run_native(words, harness):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("C++17 compiler unavailable")
    source, report = emit_cpp(struct.pack("<" + "I" * len(words), *words), 0, 32)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)
        (path / "test.cpp").write_text(source + "\n" + harness, encoding="utf-8")
        exe = path / "native"
        compiled = subprocess.run([
            compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
            "-I", str(ROOT / "runtime"), str(path / "test.cpp"), "-o", str(exe)
        ], capture_output=True, text=True, timeout=30)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        tested = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10)
        if tested.returncode:
            raise AssertionError(f"exit {tested.returncode}: {tested.stdout}{tested.stderr}")
    return report


PRELUDE = """
#include <cstdint>
#include <stdexcept>
#include <array>
using namespace arcaderecomp_generated;
struct Memory {
    std::array<std::uint32_t, 4> data{};
    std::uint32_t base = 0x00000100u;
    unsigned reads = 0;
};
static std::uint32_t rd(void* p, std::uint32_t address) {
    Memory& m = *static_cast<Memory*>(p);
    if (address < m.base || address >= m.base + 16 || (address & 3u))
        throw std::runtime_error("unmapped SYNMOVQ read");
    ++m.reads;
    return m.data[(address - m.base) >> 2];
}
"""


class SynmovqTests(unittest.TestCase):
    def test_reinitialize_iac_captured_with_real_field_order(self):
        # Artificial opcode: SYNMOVQ g2,g3; original HOTD1 opcode not included.
        word = (0x60 << 24) | (19 << 14) | (2 << 7) | 18
        report = run_native([word, 0xffffffff], PRELUDE + """
int main() {
    CPU cpu{}; Memory m{{0x93000000u, 0u, 0x00510e00u, 0x000006b0u}};
    Bus bus{}; bus.ctx = &m; bus.read32 = &rd;
    cpu.ip = 0; cpu.r[18] = 0xff000017u; // forced quad alignment
    cpu.r[19] = 0x00000109u;             // source aligned down to 0x100
    if (step(cpu, bus)) return 1;         // no fabricated reinitialize success
    if (cpu.stop_code != StopCode::iac_reinitialize_pending ||
        !cpu.pending_iac_valid) return 2;
    if (cpu.pending_iac[0] != 0x93000000u || cpu.pending_iac[1] != 0 ||
        cpu.pending_iac[2] != 0x00510e00u || cpu.pending_iac[3] != 0x6b0u)
        return 3;
    if (cpu.ip != 0 || m.reads != 4) return 4;
    return 0;
}
""")
        self.assertEqual(report.translated, 1)
        self.assertEqual(report.unsupported, (4,))

    def test_other_iac_type_does_not_fake_success(self):
        word = (0x60 << 24) | (19 << 14) | (2 << 7) | 18
        run_native([word, 0xffffffff], PRELUDE + """
int main() {
    CPU cpu{}; Memory m{{0x8f000000u, 0u, 0u, 0u}};
    Bus bus{}; bus.ctx = &m; bus.read32 = &rd;
    cpu.r[18] = 0xff000010u; cpu.r[19] = 0x100u;
    if (step(cpu, bus) || cpu.stop_code != StopCode::unsupported_iac_message)
        return 1;
    if (!cpu.pending_iac_valid || cpu.pending_iac[0] != 0x8f000000u)
        return 2;
    return 0;
}
""")

    def test_normal_synchronous_destination_is_not_plain_ram_write(self):
        word = (0x60 << 24) | (19 << 14) | (2 << 7) | 18
        run_native([word, 0xffffffff], PRELUDE + """
int main() {
    CPU cpu{}; Memory m{{10u, 20u, 30u, 40u}};
    Bus bus{}; bus.ctx = &m; bus.read32 = &rd;
    cpu.r[18] = 0x00500000u; cpu.r[19] = 0x100u;
    if (step(cpu, bus) ||
        cpu.stop_code != StopCode::synchronous_device_unimplemented) return 1;
    if (cpu.pending_iac_valid) return 2;
    return 0;
}
""")

    def test_missing_bus_and_bad_source_fail_closed(self):
        word = (0x60 << 24) | (19 << 14) | (2 << 7) | 18
        run_native([word, 0xffffffff], PRELUDE + """
int main() {
    CPU cpu{}; Bus bus{};
    cpu.r[18] = 0xff000010u; cpu.r[19] = 0x100u;
    if (step(cpu, bus) || cpu.stop_code != StopCode::missing_bus) return 1;
    if (cpu.pending_iac_valid) return 2;
    Memory m{}; bus.ctx = &m; bus.read32 = &rd;
    cpu.r[19] = 0x00000200u;
    try { step(cpu, bus); return 3; }
    catch (const std::runtime_error&) {}
    if (cpu.pending_iac_valid) return 4;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
