"""Native Intel 80960KB conditional compare (5A2/5A3) correctness tests.

1988 KB Programmer's Reference Manual, §6/§11 (CONCMPI/CONCMPO):
if incoming AC.cc bit 2 is set, preserve it; otherwise CC is 010
for src1 <= src2 and 001 for src1 > src2. These are two-outcome
inclusive comparisons, not the ordinary three-outcome CMP instructions.
Original ROM bytes are deliberately excluded from these tests.
"""
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def regop(op=0x5a2, a=16, b=17, literal_a=False, literal_b=False,
          m3=False):
    return ((op & 0xff0) << 20 | (op & 15) << 7 |
            a | b << 14 | int(literal_a) << 11 |
            int(literal_b) << 12 | int(m3) << 13)


def samples():
    edge = [0, 1, 2, 31, 32, 0x7fffffff, 0x80000000,
            0x80000001, 0xfffffffe, 0xffffffff, 0x55555555,
            0xaaaaaaaa, 0x11223344, 0x44332211]
    data = [(a, b) for a in edge for b in edge]
    rng = random.Random(0x5a2960)
    data += [(rng.getrandbits(32), rng.getrandbits(32))
             for _ in range(320)]
    return data


FORMS = [
    (16, 17, False, False, False),
    (17, 16, False, False, False),
    (31, 17, True, False, False),
    (16, 29, False, True, False),
    (31, 29, True, True, False),
    (16, 17, False, False, True),
    (16, 16, False, False, False),
]


class ConditionalCompareNativeTests(unittest.TestCase):
    def test_decode_and_reject_special_registers(self):
        for opcode, name in ((0x5a2, "concmpo"), (0x5a3, "concmpi")):
            ins = decode(struct.pack("<I", regop(opcode)), 0)
            self.assertEqual((ins.mnemonic, ins.form, ins.operands),
                             (name, "REG", ("g0", "g1")))
            for mask in (0x20, 0x40):
                _, report = emit_cpp(
                    struct.pack("<2I", regop(opcode) | mask, 0xffffffff),
                    0, 8)
                self.assertIn(0, report.unsupported)

    def test_native_inclusive_bounds_signedness_and_original_cc(self):
        words = [regop(opcode, a, b, la, lb, m3)
                 for opcode in (0x5a2, 0x5a3)
                 for a, b, la, lb, m3 in FORMS]
        cpp, report = emit_cpp(struct.pack(
            "<" + "I" * (len(words) + 1), *words, 0xffffffff), 0, 64)
        self.assertEqual(report.translated, len(words))
        self.assertEqual(report.unsupported, (4 * len(words),))
        fixtures = ",\n".join(
            f"{{{a}u,{b}u}}" for a, b in samples())
        harness = (f"static const std::uint32_t fixtures[][2] = {{\n"
                   f"{fixtures}\n}};\n") + r"""
using namespace arcaderecomp_generated;

static bool less_equal(std::uint32_t a, std::uint32_t b, bool sign) {
    // Independent oracle: signed key transform, separately compare equality.
    // No host signed-overflow or implementation-defined signed conversions.
    if (sign) { a ^= 0x80000000u; b ^= 0x80000000u; }
    return (a < b) || (a == b);
}
int main() {
    Bus bus{};
    unsigned checked=0;
    for (const auto& v : fixtures)
    for (unsigned op=0; op<2; ++op)
    for (unsigned form=0; form<7; ++form)
    for (unsigned cc=0; cc<8; ++cc)
    for (unsigned defined=0; defined<2; ++defined) {
        CPU cpu{};
        cpu.r[16]=v[0];
        cpu.r[17]=v[1];
        cpu.r[18]=0x12348765u;
        cpu.cc=static_cast<int>(cc);
        cpu.cc_defined=defined!=0;
        cpu.integer_overflow_mask=true;
        cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;
        cpu.integer_overflow_flag_defined=true;
        cpu.ip=4u*(op*7u+form);
        const std::uint32_t a=(form==1)?v[1]:
            (form==2||form==4)?31u:v[0];
        const std::uint32_t b=(form==1)?v[0]:
            (form==3||form==4)?29u:
            form==6?v[0]:v[1];
        const unsigned want=(cc & 4u)?cc:
                            less_equal(a,b,op==1u)?2u:1u;
        const bool ok=step(cpu,bus);
        if (!defined) {
            if (ok || cpu.stop_code!=StopCode::undefined_condition_code ||
                cpu.ip!=4u*(op*7u+form) || cpu.cc!=int(cc) ||
                cpu.r[16]!=v[0] || cpu.r[17]!=v[1] ||
                cpu.r[18]!=0x12348765u) return 1;
        } else {
            if (!ok || cpu.ip!=4u*(op*7u+form+1u) ||
                cpu.cc!=int(want) || !cpu.cc_defined ||
                cpu.stop_code!=StopCode::none ||
                cpu.r[16]!=v[0] || cpu.r[17]!=v[1] ||
                cpu.r[18]!=0x12348765u ||
                cpu.pending_integer_overflow.pending ||
                !cpu.integer_overflow_mask_defined || !cpu.integer_overflow_mask ||
                !cpu.integer_overflow_flag_defined || !cpu.integer_overflow_flag)
                return 2;
        }
        ++checked;
    }
    return checked > 100000u ? 0 : 3;
}
"""
        compilers = [p for name in ("g++", "clang++")
                     if (p := shutil.which(name))]
        if not compilers:
            raise unittest.SkipTest("No C++17 compiler")
        for compiler in compilers:
            with tempfile.TemporaryDirectory(prefix="arcade-concmp-native-") as td:
                source = Path(td) / "test.cpp"
                exe = Path(td) / "native"
                source.write_text(cpp + "\n" + harness, encoding="utf-8")
                built = subprocess.run([
                    compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all",
                    "-I", str(ROOT / "runtime"), str(source), "-o", str(exe),
                ], capture_output=True, text=True, timeout=50)
                if built.returncode:
                    raise AssertionError(f"{compiler}: {built.stderr}")
                run = subprocess.run([str(exe)], capture_output=True,
                                     text=True, timeout=30)
                if run.returncode:
                    raise AssertionError(f"{compiler}: exit {run.returncode}: "
                                         + run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
