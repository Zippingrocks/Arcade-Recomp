"""Native Intel 80960KB SCANBIT/SPANBIT with independent bit_length oracle.

Intel 80960KB Programmer's Reference Manual (1988): SCANBIT 641h and
SPANBIT 640h select the most significant set / clear bit respectively.
No matching bit sets destination FFFFFFFFh and AC.cc=000; otherwise
destination is bit index [0..31] and AC.cc=010.
All inputs and instruction encodings in this test are synthetic.
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
OPS = (("spanbit", 0x640), ("scanbit", 0x641))


def regop(op, src=16, dst=18, literal=False, dest_special=False):
    return (((op & 0xff0) << 20) | ((op & 15) << 7) |
            src | (dst << 19) | (int(literal) << 11) |
            (int(dest_special) << 13))


def inputs():
    edge = [0, 1, 2, 31, 32, 63, 0x80000000, 0x7fffffff,
            0xffffffff, 0xfffffffe, 0x0000ffff, 0xffff0000,
            0xaaaaaaaa, 0x55555555]
    edge.extend(1 << pos for pos in range(32))
    edge.extend(0xffffffff ^ (1 << pos) for pos in range(32))
    rng = random.Random(0x640641)
    edge.extend(rng.getrandbits(32) for _ in range(512))
    return edge


def expected(value, op):
    bits = value ^ 0xffffffff if op == 0 else value
    return (bits.bit_length() - 1, 2) if bits else (0xffffffff, 0)


class ScanAndSpanBitNativeTests(unittest.TestCase):
    def test_decoder_and_reserved_operands(self):
        for mnemonic, opcode in OPS:
            word = regop(opcode)
            ins = decode(struct.pack("<I", word), 0)
            self.assertEqual((ins.mnemonic, ins.form, ins.operands),
                             (mnemonic, "REG", ("g0", "g2")))
            # SFR read and SFR destination are deliberately unimplemented.
            for mask in (0x20, 0x40, 0x2000):
                _, report = emit_cpp(
                    struct.pack("<2I", word | mask, 0xffffffff), 0, 8)
                self.assertIn(0, report.unsupported)

    def test_native_msb_search_literals_aliases_and_condition_code(self):
        # Includes src==dst, a register other than g0 and a source literal.
        forms = [
            (16, 18, False),
            (16, 16, False),
            (17, 18, False),
            (31, 18, True),
            (0, 17, True),
        ]
        words = [regop(opcode, src, dst, lit)
                 for _, opcode in OPS for src, dst, lit in forms]
        words.append(0xffffffff)
        cpp, report = emit_cpp(
            struct.pack("<" + "I" * len(words), *words), 0, 64)
        self.assertEqual(report.translated, 10)
        self.assertEqual(report.unsupported, (40,))

        rows = []
        for value in inputs():
            span, span_cc = expected(value, 0)
            scan, scan_cc = expected(value, 1)
            rows.append((value, span, span_cc, scan, scan_cc))
        data = ",\n".join("{" + ",".join(str(x) + "u" for x in row) + "}"
                          for row in rows)
        harness = (f"static const std::uint32_t cases[][5] = {{\n{data}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    unsigned checked=0;
    for (const auto& row: cases)
    for (unsigned op=0; op<2; ++op)
    for (unsigned form=0; form<5; ++form)
    for (unsigned old_cc=0; old_cc<8; ++old_cc)
    for (unsigned defined=0; defined<2; ++defined) {
        CPU cpu{};
        cpu.r[16] = row[0];
        cpu.r[17] = row[0];
        cpu.r[18] = 0xa5a55a5au;
        cpu.ip = (op*5u+form)*4u;
        cpu.cc=static_cast<int>(old_cc);
        cpu.cc_defined=defined!=0;
        cpu.integer_overflow_mask=true;
        cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;
        cpu.integer_overflow_flag_defined=true;
        std::uint32_t original[32]{};
        for (unsigned i=0;i<32;++i) original[i]=cpu.r[i];
        const unsigned dst=(form==1?16u:form==4?17u:18u);
        const std::uint32_t val=(form==3?31u:form==4?0u:row[0]);
        std::uint32_t want = op==0?row[1]:row[3];
        int cc = static_cast<int>(op==0?row[2]:row[4]);
        if(form>=3) {
            const std::uint32_t search = op==0?(val^0xffffffffu):val;
            if(search==0u){want=0xffffffffu;cc=0;}
            else {
                // Independent oracle: count bits by successive division.
                std::uint32_t rem=search;
                unsigned index=0u;
                while((rem >>= 1u)!=0u)++index;
                want=index;cc=2;
            }
        }
        if(!step(cpu,bus) || cpu.ip!=(op*5u+form+1u)*4u ||
           cpu.r[dst]!=want || cpu.cc!=cc || !cpu.cc_defined ||
           cpu.stop_code!=StopCode::none ||
           cpu.pending_integer_overflow.pending) return 1;
        for(unsigned i=0;i<32;++i)
            if(i!=dst && cpu.r[i]!=original[i])return 2;
        if(!cpu.integer_overflow_mask_defined ||
           !cpu.integer_overflow_mask ||
           !cpu.integer_overflow_flag_defined ||
           !cpu.integer_overflow_flag)return 3;
        ++checked;
    }
    return checked > 10000u ? 0 : 4;
}
"""
        compilers = [path for name in ("g++", "clang++")
                     if (path := shutil.which(name))]
        if not compilers:
            raise unittest.SkipTest("No C++17 compiler available")
        for compiler in compilers:
            with tempfile.TemporaryDirectory(prefix="arcade-kb-bitsearch-") as tmp:
                source = Path(tmp) / "native.cpp"
                binary = Path(tmp) / "native"
                source.write_text(cpp + "\n" + harness, encoding="utf-8")
                build = subprocess.run(
                    [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                     "-Werror", "-fsanitize=undefined",
                     "-fno-sanitize-recover=all", "-I", str(ROOT/"runtime"),
                     str(source), "-o", str(binary)],
                    capture_output=True, text=True, timeout=45)
                if build.returncode:
                    raise AssertionError(compiler + ": " + build.stderr)
                run = subprocess.run([str(binary)], capture_output=True,
                                     text=True, timeout=25)
                if run.returncode:
                    raise AssertionError(compiler + ": exit " +
                                         str(run.returncode) + ": " +
                                         run.stdout + run.stderr)


if __name__ == "__main__":
    unittest.main()
