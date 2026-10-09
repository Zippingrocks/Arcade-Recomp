"""Compile and execute AOT output from artificial i960 input, never game ROMs."""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp


def words(*items):
    return struct.pack("<" + "I" * len(items), *items)


def compile_and_run(source, harness):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if compiler is None:
        raise unittest.SkipTest("No C++ compiler installed")
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        cpp = root / "generated.cpp"
        program = root / "generated_test"
        cpp.write_text(source + "\n" + harness, encoding="utf-8")
        result = subprocess.run([compiler, "-std=c++17", "-O2", "-Wall",
                                 str(cpp), "-o", str(program)],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise AssertionError(f"Native compilation failed:\n{result.stderr}")
        result = subprocess.run([str(program)], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            raise AssertionError(f"Compiled semantics failed ({result.returncode}):\n{result.stderr}")


class NativeTranslationTests(unittest.TestCase):
    def test_generated_native_executes_immediate_add_and_direct_loop(self):
        # Independent synthetic sequence: lda 0x1000,g0; addo 3,g0,g1; b 0x8
        synthetic = words(0x8c803000, 0x1000, 0x598c0803,
                          0x08fffffc, 0x0a000000)
        source, report = emit_cpp(synthetic, 0)
        self.assertEqual(report.discovered, 3)
        self.assertEqual(report.translated, 3)
        self.assertEqual(report.unsupported, ())
        compile_and_run(source, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    if (!step(cpu, bus) || cpu.ip != 8 || cpu.r[16] != 0x1000u) return 1;
    if (!step(cpu, bus) || cpu.ip != 12 || cpu.r[17] != 0x1003u) return 2;
    if (!step(cpu, bus) || cpu.ip != 8) return 3;
    return 0;
}
""")

    def test_generated_native_memory_bus_read_write(self):
        # lda 0x1000,g0; lda 0xdeadbeef,g1; st g1,(g0); ld (g0),g2.
        store = (0x92 << 24) | (17 << 19) | (16 << 14) | (4 << 10)
        load = (0x90 << 24) | (18 << 19) | (16 << 14) | (4 << 10)
        synthetic = words(0x8c803000, 0x1000, 0x8c883000, 0xdeadbeef,
                          store, load, 0xffffffff)
        source, report = emit_cpp(synthetic, 0)
        self.assertEqual(report.translated, 4)
        self.assertEqual(report.unsupported, (24,))
        compile_and_run(source, """
struct Memory { unsigned int value = 0; };
std::uint32_t read(void* p, std::uint32_t addr) {
    if (addr != 0x1000u) return 0u;
    return static_cast<Memory*>(p)->value;
}
void write(void* p, std::uint32_t addr, std::uint32_t value) {
    if (addr == 0x1000u) static_cast<Memory*>(p)->value = value;
}
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Memory ram{}; Bus bus{&ram, &read, &write}; cpu.ip = 0;
    for (int i = 0; i < 4; ++i) if (!step(cpu, bus)) return 1;
    if (cpu.r[18] != 0xdeadbeefu || ram.value != 0xdeadbeefu) return 2;
    if (step(cpu, bus) || cpu.stop_ip != 24u) return 3;
    return 0;
}
""")

    def test_direct_conditional_branch_uses_comparison_result(self):
        # cmpo literal 2,g1; bl +8 (branch based on unsigned g1 < 2)
        cmp = (0x5a << 24) | (17 << 14) | (1 << 13) | (1 << 11) | 2
        synthetic = words(cmp, 0x14000008, 0xffffffff, 0x0a000000)
        source, report = emit_cpp(synthetic, 0)
        self.assertIn(8, report.unsupported)
        compile_and_run(source, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0; cpu.r[17] = 1;
    if (!step(cpu, bus) || cpu.cc != -1) return 1;
    if (!step(cpu, bus) || cpu.ip != 12) return 2;
    return 0;
}
""")

    def test_unimplemented_call_fails_closed(self):
        # No fake call-stack implementation; stop at the call opcode.
        synthetic = words(0x09000008, 0x0a000000, 0x0a000000)
        source, report = emit_cpp(synthetic, 0)
        self.assertIn(0, report.unsupported)
        compile_and_run(source, """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    if (step(cpu, bus) || cpu.stop_ip != 0) return 1;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
