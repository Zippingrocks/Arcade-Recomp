"""Intel KB SCALER exact normal GPR subset; entirely synthetic, ROM-free."""
from fractions import Fraction
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def scaler(power=16, source=17, destination=18, literal=False):
    return (0x67000380 | power | (source << 14) | (destination << 19) |
            (0x800 if literal else 0))


def native(words, body):
    source, report = emit_cpp(struct.pack("<" + "I" * len(words), *words), 0, 64)
    compilers = [p for name in ("g++", "clang++") if (p := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("C++17 compiler required")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-scaler-") as d:
            cpp, exe = Path(d) / "test.cpp", Path(d) / "test"
            cpp.write_text(source + "\n" + body)
            build = subprocess.run([compiler, "-std=c++17", "-O2", "-Wall",
                "-Wextra", "-Werror", "-fsanitize=undefined",
                "-fno-sanitize-recover=all", "-I", str(ROOT / "runtime"),
                str(cpp), "-o", str(exe)], capture_output=True, text=True, timeout=60)
            if build.returncode:
                raise AssertionError(compiler + ": " + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            if run.returncode:
                raise AssertionError(compiler + " exit " + str(run.returncode) + ": " + run.stderr)
    return report


def oracle_rows():
    # Exact rational multiplication, then independent IEEE packing. No
    # expected result is computed by editing the source exponent bits.
    lo, hi = Fraction(1, 1 << 126), Fraction(1 << 128)
    rows = []
    for exponent in range(1, 255):
        for sign in (0, 1):
            for fraction in (0, 1, 0x7fffff):
                bits = (sign << 31) | (exponent << 23) | fraction
                value = Fraction.from_float(struct.unpack("<f", struct.pack("<I", bits))[0])
                for power in (-256, -128, -1, 0, 1, 128, 256):
                    factor = Fraction(1 << power) if power >= 0 else Fraction(1, 1 << -power)
                    result = value * factor
                    accepted = lo <= abs(result) < hi
                    expected = struct.unpack("<I", struct.pack("<f", float(result)))[0] if accepted else 0
                    rows.append((power & 0xffffffff, bits, expected, int(accepted)))
    return rows


class ScalerNativeTests(unittest.TestCase):
    def test_decoder_opcode_operand_order_and_rejected_modes(self):
        instruction = decode(struct.pack("<I", scaler()), 0)
        self.assertEqual((instruction.mnemonic, instruction.operands),
                         ("scaler", ("g0", "g1", "g2")))
        literal = decode(struct.pack("<I", scaler(31, literal=True)), 0)
        self.assertEqual(literal.operands, ("31", "g1", "g2"))
        for flag in (0x20, 0x40, 0x1000, 0x2000, 0x820):
            _, report = emit_cpp(struct.pack("<2I", scaler() | flag, 0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)
        # Long-real SCALERL has a distinct opcode and remains unsupported.
        _, report = emit_cpp(struct.pack("<2I", scaler() ^ 0x80, 0xffffffff), 0, 8)
        self.assertIn(0, report.unsupported)

    def test_aot_against_rational_oracle_all_normal_exponents(self):
        rows = ",\n".join("{" + ",".join(str(x) + "u" for x in row) + "}" for row in oracle_rows())
        body = "static const std::uint32_t rows[][4]={\n" + rows + "\n};\n" + r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    for(const auto& row:rows) for(unsigned cc=0;cc<8u;++cc) {
        CPU cpu{};cpu.r[16]=row[0];cpu.r[17]=row[1];cpu.r[18]=0xdeadbeefu;
        cpu.cc=static_cast<int>(cc);cpu.cc_defined=(cc&1u)!=0u;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        cpu.fp_defined[0]=true;cpu.fp[0].low=0x12345678u;
        const bool ok=step(cpu,bus);
        if(ok!=bool(row[3]))return 1;
        if(ok) {
            if(cpu.r[18]!=row[2] || cpu.ip!=4u || cpu.stop_code!=StopCode::none)return 2;
        } else if(cpu.r[18]!=0xdeadbeefu || cpu.ip!=0u || cpu.stop_ip!=0u ||
                  cpu.stop_code!=StopCode::unsupported_floating_format)return 3;
        if(cpu.r[16]!=row[0] || cpu.r[17]!=row[1] ||
           cpu.cc!=static_cast<int>(cc) || cpu.cc_defined!=bool(cc&1u) ||
           !cpu.integer_overflow_flag || !cpu.integer_overflow_flag_defined ||
           !cpu.fp_defined[0] || cpu.fp[0].low!=0x12345678u)return 4;
    }
    return 0;
}
"""
        report = native([scaler(), 0xffffffff], body)
        self.assertEqual(report.translated, 1)

    def test_literals_and_source_destination_aliases(self):
        native([scaler(16,17,17), scaler(16,17,16), scaler(31,17,18,True), 0xffffffff], r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};CPU cpu{};
    cpu.r[16]=0xffffffffu;cpu.r[17]=0xc0400000u; // -3 scaled by 2^-1.
    if(!step(cpu,bus) || cpu.r[17]!=0xbfc00000u)return 1;
    if(!step(cpu,bus) || cpu.r[16]!=0xbf400000u)return 2; // -0.75, dst aliases count.
    if(!step(cpu,bus) || cpu.r[18]!=0xcf400000u || cpu.ip!=12u)return 3;
    return 0;
}
""")

    def test_special_values_extreme_counts_and_invalid_destination_stop(self):
        native([scaler(), 0xffffffff], r"""
#include <array>
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    for(auto bits:std::array<std::uint32_t,8>{0u,0x80000000u,1u,0x807fffffu,
            0x7f800000u,0xff800000u,0x7fc00001u,0x7f800001u}) {
        CPU cpu{};cpu.r[16]=0u;cpu.r[17]=bits;cpu.r[18]=0xdeadbeefu;
        if(step(cpu,bus) || cpu.r[18]!=0xdeadbeefu || cpu.ip!=0u ||
           cpu.stop_code!=StopCode::unsupported_floating_format)return 1;
    }
    for(auto count:std::array<std::uint32_t,2>{0x80000000u,0x7fffffffu}) {
        CPU cpu{};cpu.r[16]=count;cpu.r[17]=0x3f800000u;cpu.r[18]=123u;
        if(step(cpu,bus) || cpu.r[18]!=123u || cpu.ip!=0u ||
           cpu.stop_code!=StopCode::unsupported_floating_format)return 2;
    }
    CPU cpu{};cpu.ip=0x40u;cpu.r[31]=123u;
    if(scale_real32_exact(cpu,0u,0x3f800000u,32u) || cpu.ip!=0x40u ||
       cpu.r[31]!=123u || cpu.stop_code!=StopCode::untranslated)return 3;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
