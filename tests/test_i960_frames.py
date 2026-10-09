"""Executable tests for i960KB CALL/RET frame semantics using synthetic opwords.

All generated code comes from synthetic instructions and contains no game data.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp


ROOT = Path(__file__).resolve().parents[1]


def compile_and_run(source, harness):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("Host C++ compiler not available")
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        generated = folder / "test.cpp"
        executable = folder / "test"
        generated.write_text(source + "\n" + harness, encoding="utf-8")
        result = subprocess.run(
            [compiler, "-std=c++17", "-Wall", "-Wextra", "-O2",
             "-I", str(ROOT / "runtime"), str(generated), "-o", str(executable)],
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError("Native compilation failed:\n" + result.stderr)
        result = subprocess.run([str(executable)], capture_output=True,
                                text=True, timeout=10)
        if result.returncode:
            raise AssertionError(f"Native test exit code {result.returncode}:\n"
                                 + result.stdout + result.stderr)


def sequence(nested_calls=5):
    """call pc+8 ; ret pc+4 ; ... ; ret leaf."""
    words = []
    for _ in range(nested_calls):
        words.extend((0x09000008, 0x0a000000))
    words.append(0x0a000000)
    return struct.pack("<" + "I" * len(words), *words)


BUS = """
#include <unordered_map>
#include <cstdint>
struct RAM {
    std::unordered_map<std::uint32_t, std::uint32_t> words;
    std::size_t reads = 0;
    std::size_t writes = 0;
};
static std::uint32_t read(void* opaque, std::uint32_t address) {
    RAM& ram = *static_cast<RAM*>(opaque);
    ++ram.reads;
    auto it = ram.words.find(address);
    return it == ram.words.end() ? 0u : it->second;
}
static void write(void* opaque, std::uint32_t address, std::uint32_t value) {
    RAM& ram = *static_cast<RAM*>(opaque);
    ++ram.writes;
    ram.words[address] = value;
}
"""


class I960LocalFrameTests(unittest.TestCase):
    def test_nested_local_calls_restore_registers_and_memory_spills(self):
        source, report = emit_cpp(sequence(5), 0, 64)
        self.assertEqual(report.discovered, 11)
        self.assertEqual(report.translated, 11)
        self.assertEqual(report.unsupported, ())
        compile_and_run(source, BUS + """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{};
    RAM mem{};
    Bus bus{&mem, &read, &write};
    if (!frame_init(cpu, 0x00510400u, 0u)) return 1;
    cpu.r[16] = 0xdeadbeefu; // g0 persists through every local call
    cpu.r[3] = 0xa0u;
    for (unsigned depth = 1; depth <= 5; ++depth) {
        if (!step(cpu, bus)) return 2;
        if (cpu.frame_depth != depth) return 3;
        if (cpu.r[31] != 0x00510400u + 64u * depth) return 4;
        if (cpu.r[0] != 0x00510400u + 64u * (depth - 1)) return 5;
        if (cpu.r[1] != 0x00510440u + 64u * depth) return 6;
        if (cpu.r[16] != 0xdeadbeefu) return 7;
        cpu.r[3] = 0xa0u + depth;
    }
    if (cpu.frame_spills != 2u || mem.writes != 32u) return 8;
    for (unsigned depth = 5; depth > 0; --depth) {
        if (!step(cpu, bus)) return 9;
        if (cpu.frame_depth != depth - 1) return 10;
        if (cpu.r[3] != 0xa0u + depth - 1) return 11;
        if (cpu.r[16] != 0xdeadbeefu) return 12;
    }
    if (cpu.frame_reloads != 2u || mem.reads != 32u) return 13;
    if (cpu.ip != 4u || cpu.r[31] != 0x00510400u) return 14;
    if (step(cpu, bus)) return 15; // Callerless ret explicitly rejected
    if (cpu.stop_code != StopCode::return_without_caller) return 16;
    return 0;
}
""")

    def test_bus_is_required_before_first_spill(self):
        source, _ = emit_cpp(sequence(5), 0, 64)
        compile_and_run(source, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{};
    Bus no_bus{};
    if (!frame_init(cpu, 0x00510400u, 0u)) return 1;
    for (unsigned i = 0; i < 3; ++i)
        if (!step(cpu, no_bus)) return 2;
    if (cpu.frame_spills != 0u) return 3;
    if (step(cpu, no_bus)) return 4; // depth 4 requires a spill
    if (cpu.stop_code != StopCode::missing_bus) return 5;
    if (cpu.frame_depth != 3u || cpu.stop_ip != 24u) return 6;
    return 0;
}
""")

    def test_unsupported_return_status_fails_without_returning(self):
        source, _ = emit_cpp(sequence(1), 0, 16)
        compile_and_run(source, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{};
    Bus bus{};
    if (!frame_init(cpu, 0x00510400u, 0u)) return 1;
    if (!step(cpu, bus) || cpu.ip != 8u || cpu.frame_depth != 1u) return 2;
    cpu.r[0] |= 1u; // fault-return type, intentionally not implemented
    if (step(cpu, bus)) return 3;
    if (cpu.frame_depth != 1u || cpu.stop_code != StopCode::unsupported_return_status) return 4;
    return 0;
}
""")

    def test_callx_uses_indirect_operand_but_aot_opcode(self):
        # MEMB: callx absolute 0x10 ; ret after call ; return at 0x10.
        word = (0x86 << 24) | (12 << 10)
        data = struct.pack("<6I", word, 0x10, 0x0a000000,
                           0xffffffff, 0x0a000000, 0xffffffff)
        source, report = emit_cpp(data, 0, 32)
        self.assertGreaterEqual(report.translated, 1)
        # CALLX destinations are not yet resolved by the graph builder. The
        # emitted native opcode must still perform the correct call transition.
        self.assertIn("frame_call(", source)
        compile_and_run(source, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{};
    if (!frame_init(cpu, 0x00510400u, 0u)) return 1;
    if (!step(cpu, bus)) return 2;
    if (cpu.ip != 16u || cpu.frame_depth != 1u) return 3;
    if (cpu.r[31] != 0x00510440u) return 4;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
