"""Intel 80960KB native Boolean, ALTERBIT and ROTATE regression checks.

Original Intel 80960KB Programmer's Reference Manual (1988), instruction
reference 11-10, 11-91 to 11-96, 11-103. Synthetic words only.
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
OPS = [
    ("notand", 0x584), ("nor", 0x588), ("xnor", 0x589),
    ("ornot", 0x58b), ("notor", 0x58d), ("nand", 0x58e),
    ("alterbit", 0x58f), ("rotate", 0x59d),
]
FORMS = (
    (16, 17, 18, False, False),
    (16, 17, 16, False, False),  # dst aliases src1
    (16, 17, 17, False, False),  # dst aliases src2
    (31, 17, 18, True, False),  # maximum literal src1
    (16, 29, 18, False, True),  # literal src2
    (31, 29, 18, True, True),  # both literals
)


def regop(opcode, first, second, dest, lit_first=False, lit_second=False):
    return (((opcode & 0xff0) << 20) | ((opcode & 0xf) << 7) |
            first | (second << 14) | (dest << 19) |
            (int(lit_first) << 11) | (int(lit_second) << 12))


def generate():
    words = [regop(op, *form) for _, op in OPS for form in FORMS]
    words.append(0xffffffff)
    cpp, report = emit_cpp(struct.pack("<" + "I" * len(words), *words),
                           0, len(words) + 2)
    return cpp, report


def vectors():
    rng = random.Random(0x960584)
    edge = [0, 1, 2, 31, 32, 63, 64, 0x7fffffff,
            0x80000000, 0x80000001, 0xfffffffe, 0xffffffff,
            0x55555555, 0xaaaaaaaa, 0x12345678, 0xfedcba98]
    vals = [(a, b) for a in edge for b in edge]
    vals += [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(256)]
    return vals


def native(harness):
    cpp, report = generate()
    compilers = [tool for name in ("g++", "clang++")
                 if (tool := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("No available C++17 compiler")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-i960-bit-") as folder:
            work = Path(folder)
            source = work / "native.cpp"
            exe = work / "native"
            source.write_text(cpp + "\n" + harness, encoding="utf-8")
            built = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT / "runtime"), str(source), "-o", str(exe)],
                capture_output=True, text=True, timeout=50)
            if built.returncode:
                raise AssertionError(f"{compiler}: {built.stderr}")
            run = subprocess.run([str(exe)], capture_output=True,
                                 text=True, timeout=25)
            if run.returncode:
                raise AssertionError(
                    f"{compiler}: exit {run.returncode}: {run.stdout}{run.stderr}")
    return report


def case_table():
    return ("static const std::uint32_t cases[][2] = {\n" +
            ",\n".join("{" + str(a) + "u," + str(b) + "u}"
                       for a, b in vectors()) + "\n};\n")


class I960LogicRotateNativeTests(unittest.TestCase):
    def test_decoder_and_rejection_of_special_register_modes(self):
        for name, opcode in OPS:
            ins = decode(struct.pack("<I", regop(opcode, *FORMS[0])), 0)
            self.assertEqual(ins.mnemonic, name)
            self.assertEqual(ins.form, "REG")
            for mask in (0x20, 0x40, 0x2000):
                bad = regop(opcode, *FORMS[0]) | mask
                _, report = emit_cpp(struct.pack("<2I", bad, 0xffffffff), 0, 8)
                self.assertIn(0, report.unsupported)

    def test_native_logic_rotate_bit_controls_and_aliasing(self):
        harness = case_table() + r"""
#include <cstdio>
using namespace arcaderecomp_generated;

static std::uint32_t expected(unsigned op, std::uint32_t a,
                              std::uint32_t b, unsigned cc) {
    switch (op) {
    case 0: return a & (~b);
    case 1: return (~a) & (~b);
    case 2: return (a & b) | ((~a) & (~b));
    case 3: return b | (~a);
    case 4: return a | (~b);
    case 5: return ~(a & b);
    case 6: {
        const unsigned shift = a % 32u;
        const std::uint32_t mask = std::uint32_t{1} << shift;
        return (cc & 2u) ? b | mask : b & ~mask;
    }
    case 7: {
        const unsigned shift = a % 32u;
        if (!shift) return b;
        return (b << shift) | (b >> (32u - shift));
    }
    default: return 0;
    }
}
int main() {
    Bus bus{};
    unsigned checked=0u;
    for (const auto& row : cases)
    for (unsigned op=0;op<8;op++)
    for (unsigned form=0;form<6;form++)
    for (unsigned cc=0;cc<8;cc++)
    for (unsigned defined=0;defined<2;defined++) {
        CPU cpu{};
        const std::uint32_t a=row[0], b=row[1];
        cpu.r[16]=a; cpu.r[17]=b; cpu.r[18]=0xbeef1234u;
        cpu.cc=static_cast<int>(cc);
        cpu.cc_defined=defined!=0;
        cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_mask=true;
        cpu.integer_overflow_flag_defined=true;
        cpu.integer_overflow_flag=true;
        cpu.ip = (op * 6u + form) * 4u;
        const std::uint32_t before0=cpu.r[16], before1=cpu.r[17],
                            before2=cpu.r[18];
        const std::uint32_t ea=(form>=3 && (form==3 || form==5))?31u:a;
        const std::uint32_t eb=(form>=4)?29u:b;
        const std::uint32_t want=expected(op,ea,eb,cc);
        const unsigned dst=(form==1?16u:form==2?17u:18u);
        const bool ok=step(cpu,bus);
        if (op==6 && defined==0) {
            if(ok || cpu.stop_code!=StopCode::undefined_condition_code ||
               cpu.ip!=(op*6u+form)*4u || cpu.r[16]!=before0 ||
               cpu.r[17]!=before1 || cpu.r[18]!=before2)
                return 1;
            continue;
        }
        if (!ok || cpu.ip!=(op*6u+form+1u)*4u ||
            cpu.r[dst]!=want || cpu.stop_code!=StopCode::none) {
            std::fprintf(stderr,"op=%u form=%u cc=%u defined=%u a=%x b=%x got=%x want=%x stop=%u\n",
                         op,form,cc,defined,a,b,cpu.r[dst],want,
                         static_cast<unsigned>(cpu.stop_code));
            return 2;
        }
        if ((dst!=16u&&cpu.r[16]!=before0) ||
            (dst!=17u&&cpu.r[17]!=before1) ||
            (dst!=18u&&cpu.r[18]!=before2)) return 3;
        if (cpu.cc!=static_cast<int>(cc) || cpu.cc_defined!=bool(defined) ||
            !cpu.integer_overflow_mask_defined || !cpu.integer_overflow_mask ||
            !cpu.integer_overflow_flag_defined || !cpu.integer_overflow_flag ||
            cpu.pending_integer_overflow.pending) return 4;
        ++checked;
    }
    return checked > 100000u ? 0 : 5;
}
"""
        report = native(harness)
        self.assertEqual(report.translated, len(OPS) * len(FORMS))
        self.assertEqual(report.unsupported, (len(OPS) * len(FORMS) * 4,))


if __name__ == "__main__":
    unittest.main()
