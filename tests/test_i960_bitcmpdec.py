"""Synthetic native tests for i960 bit operations and compare/decrement.

The original commercial i960 ROM is not included in CI. Expectations come
from public Intel instruction documentation and independent bit arithmetic.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def execute(opwords, body):
    cxx = shutil.which("g++") or shutil.which("clang++")
    if not cxx:
        raise unittest.SkipTest("C++17 compiler unavailable")
    binary, report = emit_cpp(
        struct.pack("<" + "I" * len(opwords), *opwords), 0, 64)
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        src = tmp / "test.cpp"
        src.write_text(binary + "\n" + body, encoding="utf-8")
        exe = tmp / "run"
        compiled = subprocess.run(
            [cxx, "-std=c++17", "-O2", "-Wall", "-Wextra",
             "-I", str(ROOT / "runtime"), str(src), "-o", str(exe)],
            capture_output=True, text=True, timeout=30)
        if compiled.returncode:
            raise AssertionError(compiled.stderr)
        result = subprocess.run([str(exe)], capture_output=True,
                                text=True, timeout=10)
        if result.returncode:
            raise AssertionError(f"Native exit {result.returncode}: "
                                 + result.stdout + result.stderr)
    return report


class IntelBitAndCompareDecrementTests(unittest.TestCase):
    def test_set_clear_toggle_bit_zero(self):
        def logical(op):
            return ((0x58 << 24) | (4 << 19) | (4 << 14)
                    | (op << 7) | (1 << 11))
        report = execute([logical(3), logical(12), logical(0), 0xffffffff], """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    cpu.r[4] = 0x12345678u;
    if (!step(cpu, bus) || cpu.r[4] != 0x12345679u) return 1;
    if (!step(cpu, bus) || cpu.r[4] != 0x12345678u) return 2;
    if (!step(cpu, bus) || cpu.r[4] != 0x12345679u) return 3;
    return 0;
}
""")
        self.assertEqual(report.translated, 3)

    def test_bit_position_modulo_32_and_host_shift_safety(self):
        def logical(op):
            return ((0x58 << 24) | (4 << 19) | (4 << 14)
                    | (op << 7) | 16)   # uses g0 (index16) as bit position
        report = execute([logical(3), logical(12), 0xffffffff], """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    cpu.r[4] = 0x80000000u;
    cpu.r[16] = 32u; // modulo 32 = bit 0
    if (!step(cpu, bus) || cpu.r[4] != 0x80000001u) return 1;
    if (!step(cpu, bus) || cpu.r[4] != 0x80000000u) return 2;
    return 0;
}
""")
        self.assertEqual(report.translated, 2)

    def test_compare_then_decrement_aliasing_loop(self):
        # 0: cmpdeci 1,r3,r3
        # 4: bne 0
        # 8: ret (never called)
        cmpdeci = ((0x5a << 24) | (3 << 19) | (3 << 14)
                   | (7 << 7) | (1 << 11) | 1)
        report = execute([cmpdeci, 0x15fffffc, 0x0a000000], """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0; cpu.r[3] = 3u;
    if (!step(cpu, bus) || cpu.r[3] != 2u || cpu.cc != 4) return 1;
    if (!step(cpu, bus) || cpu.ip != 0u) return 2;
    if (!step(cpu, bus) || cpu.r[3] != 1u || cpu.cc != 4) return 3;
    if (!step(cpu, bus) || cpu.ip != 0u) return 4;
    if (!step(cpu, bus) || cpu.r[3] != 0u || cpu.cc != 2) return 5;
    if (!step(cpu, bus) || cpu.ip != 8u) return 6;
    return 0;
}
""")
        self.assertEqual(report.translated, 3)

    def test_cmpdeci_signed_overflow_suppressed(self):
        cmpdeci = ((0x5a << 24) | (3 << 19) | (3 << 14)
                   | (7 << 7) | (1 << 11) | 1)
        report = execute([cmpdeci, 0xffffffff], """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    cpu.r[3] = 0x80000000u;
    if (!step(cpu, bus)) return 1;
    // 1 > INT32_MIN before decrement, then wrapping result.
    if (cpu.cc != 1 || cpu.r[3] != 0x7fffffffu) return 2;
    return 0;
}
""")
        self.assertEqual(report.translated, 1)

    def test_cmpdeco_is_unsigned(self):
        cmpdeco = ((0x5a << 24) | (3 << 19) | (3 << 14)
                   | (6 << 7) | (1 << 11) | 1)
        report = execute([cmpdeco, 0xffffffff], """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{}; cpu.ip = 0;
    cpu.r[3] = 0u;
    if (!step(cpu, bus)) return 1;
    // Ordinal 1 > ordinal 0; source 0 decrements with uint32 wrapping.
    if (cpu.cc != 1 || cpu.r[3] != 0xffffffffu) return 2;
    return 0;
}
""")
        self.assertEqual(report.translated, 1)


if __name__ == "__main__":
    unittest.main()
