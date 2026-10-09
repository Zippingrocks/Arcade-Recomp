"""Synthetic Intel i960 logical-mask test derived from CPU semantics, not ROM bytes.

The test is shaped like a generic polling loop without copying Sega code.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"


class I960LogicalTests(unittest.TestCase):
    def test_mask_compare_and_branch_as_compiled_native_code(self):
        cxx = shutil.which("g++") or shutil.which("clang++")
        if not cxx:
            raise unittest.SkipTest("C++ compiler not installed")
        # mov 12,r4; and r4,g2,g2; cmpi r4,g2;
        # be to 0x14; b to 0x04; unknown at 0x14.
        and_op = (0x58 << 24) | (18 << 19) | (18 << 14) | (1 << 7) | 4
        cmpi = (0x5a << 24) | (18 << 14) | (1 << 7) | 4
        code = struct.pack("<6I", 0x5c201e0c, and_op, cmpi,
                           0x12000008, 0x08fffff4, 0xffffffff)
        source, report = emit_cpp(code, 0, 64)
        self.assertEqual(report.translated, 5)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            cpp = path / "native.cpp"
            cpp.write_text(source + """
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    CPU equal{};
    equal.ip = 0;
    equal.r[18] = 0xfcu; // masked -> 12
    for (int i = 0; i < 4; ++i)
        if (!step(equal, bus)) return 1;
    if (equal.r[18] != 12u || equal.cc != 2 || equal.ip != 0x14u)
        return 2;

    CPU waiting{};
    waiting.ip = 0;
    waiting.r[18] = 4u;
    for (int i = 0; i < 5; ++i)
        if (!step(waiting, bus)) return 3;
    if (waiting.r[18] != 4u || waiting.cc != 1 || waiting.ip != 4u)
        return 4;
    return 0;
}
""", encoding="utf-8")
            binary = path / "native"
            compile_result = subprocess.run(
                [cxx, "-std=c++17", "-O2", "-Wall", "-Wextra",
                 "-I", str(RUNTIME), str(cpp), "-o", str(binary)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == "__main__":
    unittest.main()
