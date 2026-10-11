"""Synthetic Intel 80960KB FLUSHREG AOT tests: frames, bus and fail-closed encodings.

Reference: Intel 80960KB Programmer's Reference Manual (1988), 4-7 and
FLUSHREG instruction entry. All ROM-derived bytes are excluded from tests.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp


ROOT = Path(__file__).resolve().parents[1]
FLUSHREG = 0x66003e80  # Intel documented no-operand opcode, not original ROM data.


def native(harness):
    source, report = emit_cpp(struct.pack("<2I", FLUSHREG, 0xffffffff), 0, 8)
    compilers = [path for name in ("g++", "clang++")
                 if (path := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("No C++17 compiler installed")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-flushreg-synthetic-") as folder:
            path = Path(folder)
            cpp = path / "test.cpp"
            exe = path / "test"
            cpp.write_text(source + "\n" + harness, encoding="utf-8")
            build = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT / "runtime"), str(cpp), "-o", str(exe)],
                capture_output=True, text=True, timeout=45)
            if build.returncode:
                raise AssertionError(compiler + ": " + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
            if run.returncode:
                raise AssertionError(
                    f"{compiler}: exit {run.returncode}: {run.stdout}{run.stderr}")
    return report


class FlushregNativeTests(unittest.TestCase):
    def test_canonical_decode_and_conservative_encoding(self):
        ins = decode(struct.pack("<I", FLUSHREG), 0)
        self.assertEqual((ins.mnemonic, ins.form, ins.operands),
                         ("flushreg", "REG", ()))
        _, report = emit_cpp(struct.pack("<2I", FLUSHREG, 0xffffffff), 0, 8)
        self.assertEqual(report.translated, 1)
        self.assertEqual(report.unsupported, (4,))
        # Invalid operand fields cannot silently turn into a frame flush.
        for altered in (FLUSHREG | 1, FLUSHREG | (1 << 19), FLUSHREG ^ 0x800):
            _, invalid = emit_cpp(struct.pack("<2I", altered, 0xffffffff), 0, 8)
            self.assertIn(0, invalid.unsupported)

    def test_cached_caller_frames_are_spilled_and_reloaded(self):
        report = native(r"""
#include <cstdlib>
using namespace arcaderecomp_generated;
struct Memory {
    std::uint32_t data[512]{};
    unsigned writes = 0, reads = 0;
};
static std::uint32_t read_word(void* p, std::uint32_t a) {
    auto& mem = *static_cast<Memory*>(p);
    if (a & 3u || a / 4 >= 512u) std::abort();
    ++mem.reads;
    return mem.data[a / 4];
}
static void write_word(void* p, std::uint32_t a, std::uint32_t value) {
    auto& mem = *static_cast<Memory*>(p);
    if (a & 3u || a / 4 >= 512u) std::abort();
    ++mem.writes;
    mem.data[a / 4] = value;
}
int main() {
    CPU cpu{};
    Memory mem{};
    Bus bus{};
    bus.ctx = &mem;
    bus.read32 = &read_word;
    bus.write32 = &write_word;
    if (!frame_init(cpu, 0x100u, 0u)) return 1;
    cpu.r[5] = 0x11111111u;
    if (!frame_call(cpu, bus, 0u, 4u)) return 2;
    cpu.r[5] = 0x22222222u;
    if (!frame_call(cpu, bus, 0u, 8u)) return 3;
    cpu.r[5] = 0x33333333u;
    if (!step(cpu, bus)) return 4;
    if (cpu.ip != 4u || cpu.frame_depth != 2u ||
        cpu.frame_spills != 2u || mem.writes != 32u) return 5;
    if (cpu.saved_valid[0] || cpu.saved_valid[1]) return 6;
    if (mem.data[0x100 / 4 + 5] != 0x11111111u ||
        mem.data[0x140 / 4 + 5] != 0x22222222u ||
        mem.data[0x180 / 4 + 5] != 0u) return 7;
    if (cpu.r[5] != 0x33333333u) return 8;
    if (!frame_return(cpu, bus) || cpu.ip != 8u ||
        cpu.r[5] != 0x22222222u || cpu.frame_depth != 1u) return 9;
    if (!frame_return(cpu, bus) || cpu.ip != 4u ||
        cpu.r[5] != 0x11111111u || cpu.frame_depth != 0u) return 10;
    if (cpu.frame_reloads != 2u || mem.reads != 32u) return 11;
    return 0;
}
""")
        self.assertEqual(report.translated, 1)

    def test_fail_closed_and_no_cached_frames(self):
        native(r"""
using namespace arcaderecomp_generated;
struct Memory { unsigned writes = 0; };
static void write_word(void* p, std::uint32_t, std::uint32_t) {
    ++static_cast<Memory*>(p)->writes;
}
int main() {
    CPU cpu{}; Bus no_bus{};
    cpu.ip = 0;
    if (step(cpu, no_bus) ||
        cpu.stop_code != StopCode::frame_uninitialized) return 1;
    cpu.frame_initialized = true; cpu.stop_code = StopCode::none;
    cpu.r[5] = 123u;
    if (!step(cpu, no_bus) || cpu.ip != 4u || cpu.r[5] != 123u)
        return 2;
    cpu.ip = 0; cpu.saved_valid[1] = true;
    cpu.saved_fp[1] = 0x140u;
    if (step(cpu, no_bus) ||
        cpu.stop_code != StopCode::missing_bus ||
        !cpu.saved_valid[1] || cpu.ip != 0u) return 3;
    Memory mem{}; Bus bus{}; bus.ctx = &mem; bus.write32 = &write_word;
    cpu.saved_fp[1] = 0x141u;
    if (step(cpu, bus) ||
        cpu.stop_code != StopCode::bad_frame_pointer ||
        mem.writes != 0u || !cpu.saved_valid[1]) return 4;
    cpu.saved_fp[1] = 0x140u;
    cpu.stop_code = StopCode::none;
    if (!step(cpu, bus) || cpu.ip != 4u ||
        mem.writes != 16u || cpu.saved_valid[1]) return 5;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
