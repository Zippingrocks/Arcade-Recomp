"""Executable, independent i960 condition-code conformance tests.

Synthetic i960 instructions only; no original game bytes or generated
commercial translation is committed.
"""
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
import unittest

from arcaderecomp.i960_cpp import emit_cpp

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"


def native_run(words, cases, initial_ip=0, steps=2):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("A C++ compiler is not installed")
    image = struct.pack("<" + "I" * len(words), *words)
    cpp, report = emit_cpp(image, initial_ip, max_instructions=64)
    scenario = "\n".join(f"""
    cpu.ip = 0u; cpu.cc = 0; cpu.r[17] = {value}u;
    if (!step(cpu, bus) || cpu.cc != {expected_cc}) return {i * 2 + 1};
    {"if (!step(cpu, bus)) return " + str(i * 2 + 2) + ";" if steps == 2 else ""}
    if (cpu.ip != {expected_ip}u) return {i * 2 + 2};
    """ for i, (value, expected_cc, expected_ip) in enumerate(cases))
    main = """
int main() {
    using namespace arcaderecomp_generated;
    CPU cpu{}; Bus bus{};
""" + scenario + """
    return 0;
}
"""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)
        (path / "test.cpp").write_text(cpp + "\n" + main, encoding="utf-8")
        command = [compiler, "-std=c++17", "-O2", "-Wall",
                   "-I", str(RUNTIME), str(path / "test.cpp"),
                   "-o", str(path / "cc_test")]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        result = subprocess.run([str(path / "cc_test")],
                                capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise AssertionError(f"native check failed {result.returncode}: {result.stderr}")
    return report


class ConditionCodeTests(unittest.TestCase):
    def test_all_ctrl_branch_masks_against_less_equal_greater(self):
        # cmpo literal 2,g1. The published Intel i960 CC convention is:
        # src1 < src2 -> 0b100, == -> 0b010, > -> 0b001.
        cmpo = (0x5a << 24) | (17 << 14) | (1 << 11) | 2
        conditions = {
            0x10: (False, False, False),  # bno: integer comparison is ordered
            0x11: (True, False, False),   # bg
            0x12: (False, True, False),   # be
            0x13: (True, True, False),    # bge
            0x14: (False, False, True),   # bl
            0x15: (True, False, True),    # bne
            0x16: (False, True, True),    # ble
            0x17: (True, True, True),     # bo
        }
        for opcode, (greater, equal, less) in conditions.items():
            with self.subTest(branch=f"{opcode:02x}"):
                # b<cc> instruction is located at 4, target = 12.
                image = [cmpo, (opcode << 24) | 8,
                         0xffffffff, 0x0a000000]
                report = native_run(image,
                    [(1, 1, 12 if greater else 8),
                     (2, 2, 12 if equal else 8),
                     (3, 4, 12 if less else 8)])
                self.assertGreaterEqual(report.translated, 2)

    def test_signed_i960_cmp_inverts_unsigned_order_where_appropriate(self):
        cmpi = (0x5a << 24) | (17 << 14) | (1 << 11) | 0 | (1 << 7)
        # cmpi is extended opcode 0x5a1, i.e. subop bit 7 set.
        report = native_run([cmpi, 0x11000008, 0xffffffff, 0x0a000000],
                            [(0xffffffff, 1, 12), (1, 4, 8), (0, 2, 8)])
        self.assertEqual(report.translated, 2)

    def test_full_cobr_comparison_updates_cc_and_conditional_branch(self):
        # cmpibne 5,g1,+8. Equal g1=5 -> no branch; otherwise branch.
        for op, condition in ((0x3d, "ne"), (0x3a, "be")):
            with self.subTest(op=condition):
                cobr = (op << 24) | (5 << 19) | (17 << 14) | (1 << 13) | 8
                report = native_run([cobr, 0xffffffff, 0x0a000000],
                                    [(5, 2, 4 if op == 0x3d else 8),
                                     (6, 4, 8 if op == 0x3d else 4),
                                     (4, 1, 8 if op == 0x3d else 4)], steps=1)
                self.assertGreaterEqual(report.translated, 1)


if __name__ == "__main__":
    unittest.main()
