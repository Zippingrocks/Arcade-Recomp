"""Native Intel 80960KB MOVRL tests: exact long-real to extended transfers.

Independent Python integer-bit oracle, compiler native execution, and
fail-closed exception cases. Synthetic instruction bytes only.
Source: Intel 80960KB Programmer's Reference Manual (Mar 1988), MOVRL.
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


def movrl(src=16, dst=0, *, src_fp=False, dst_fp=True, literal=False):
    return (0x6d000480 | 0x1000 | src | (dst << 19) |
            (0x800 if src_fp else 0) | (0x2000 if dst_fp else 0) |
            (0x800 if literal else 0))


def rows():
    seeds = [
        0, 0x8000000000000000,
        0x3ff0000000000000, 0xbff0000000000000,
        0x3ff8000000000000, 0xbfe0000000000000,
        0x0010000000000000, 0x8010000000000000,
        0x7fefffffffffffff, 0xffefffffffffffff,
        0x3ff0000000000001, 0x400921fb54442d18,
    ]
    rng = random.Random(0x6d9960)
    for _ in range(512):
        exponent = rng.randrange(1, 2047)
        frac = rng.getrandbits(52)
        sign = rng.getrandbits(1)
        seeds.append((sign << 63) | (exponent << 52) | frac)
    result = []
    for bits in seeds:
        exponent = (bits >> 52) & 0x7ff
        fraction = bits & ((1 << 52) - 1)
        if exponent == 0:
            sig = 0
            high = (bits >> 48) & 0x8000
        else:
            sig = ((1 << 52) | fraction) << 11
            high = (((bits >> 48) & 0x8000) | (exponent + 15360))
        result.append((bits & 0xffffffff, bits >> 32,
                       sig & 0xffffffff, sig >> 32, high))
    return result


def native(words, harness):
    image = struct.pack("<" + "I" * len(words), *words)
    cpp, report = emit_cpp(image, 0, len(words) + 10)
    compilers = [x for name in ("g++", "clang++")
                 if (x := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("No C++17 compiler found")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-movrl-") as folder:
            path = Path(folder)
            source = path / "test.cpp"
            exe = path / "test"
            source.write_text(cpp + "\n" + harness, encoding="utf-8")
            compiled = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT / "runtime"), str(source), "-o", str(exe)],
                capture_output=True, text=True, timeout=45)
            if compiled.returncode:
                raise AssertionError(compiler + ": " + compiled.stderr)
            ran = subprocess.run([str(exe)], capture_output=True,
                                 text=True, timeout=25)
            if ran.returncode:
                raise AssertionError(f"{compiler}: exit {ran.returncode}: "
                                     + ran.stdout + ran.stderr)
    return report


class MovrlExactNativeTests(unittest.TestCase):
    def test_decode_and_reject_unsupported_forms(self):
        a = decode(struct.pack("<I", movrl()), 0)
        self.assertEqual((a.mnemonic, a.operands),
                         ("movrl", ("g0", "fp0")))
        b = decode(struct.pack("<I", movrl(1, 20, src_fp=True, dst_fp=False)), 0)
        self.assertEqual((b.mnemonic, b.operands),
                         ("movrl", ("fp1", "g4")))
        for bad in (
            movrl(dst_fp=False),
            movrl(17),                # odd GPR source
            movrl(1, 21, src_fp=True, dst_fp=False),
            movrl(4, 20, src_fp=True, dst_fp=False),
            movrl(16, 4),
            movrl(literal=True),     # FP literals need separate semantics
            movrl() | 0x40,
            movrl() | (1 << 14),
            movrl() & ~0x1000,
        ):
            _, report = emit_cpp(struct.pack("<2I", bad, 0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)

    def test_normal_finite_and_signed_zero_roundtrips(self):
        program = [
            movrl(16, 0),                # g0/g1 -> fp0
            movrl(0, 20, src_fp=True, dst_fp=False),  # fp0 -> g4/g5
            movrl(0, 1, src_fp=True),    # fp0 -> fp1
            movrl(1, 24, src_fp=True, dst_fp=False),  # fp1 -> g8/g9
            0xffffffff,
        ]
        vector_text = ",\n".join(
            "{" + ",".join(str(x) + "u" for x in row) + "}"
            for row in rows())
        harness = (f"static const std::uint32_t vectors[][5] = {{\n"
                   f"{vector_text}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main(){
    Bus bus{}; unsigned checked=0;
    for(const auto& row : vectors)
    for(unsigned cc=0;cc<8u;++cc) {
        CPU cpu{};
        cpu.r[16]=row[0]; cpu.r[17]=row[1];
        cpu.r[20]=0x12345678u; cpu.r[21]=0xfedcba98u;
        cpu.r[24]=0xcafef00du; cpu.r[25]=0xbadbeefu;
        cpu.cc=static_cast<int>(cc); cpu.cc_defined=bool(cc&1u);
        cpu.integer_overflow_mask=true; cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true; cpu.integer_overflow_flag_defined=true;
        if(!step(cpu,bus) || cpu.ip!=4u || !cpu.fp_defined[0] ||
           cpu.fp[0].low!=row[2] || cpu.fp[0].middle!=row[3] ||
           cpu.fp[0].high!=row[4])return 1;
        if(!step(cpu,bus) || cpu.ip!=8u ||
           cpu.r[20]!=row[0] || cpu.r[21]!=row[1])return 2;
        if(!step(cpu,bus) || cpu.ip!=12u || !cpu.fp_defined[1] ||
           cpu.fp[1].low!=row[2] || cpu.fp[1].middle!=row[3] ||
           cpu.fp[1].high!=row[4])return 3;
        if(!step(cpu,bus) || cpu.ip!=16u ||
           cpu.r[24]!=row[0] || cpu.r[25]!=row[1])return 4;
        if(cpu.r[16]!=row[0] || cpu.r[17]!=row[1] ||
           cpu.cc!=static_cast<int>(cc) || cpu.cc_defined!=bool(cc&1u) ||
           !cpu.integer_overflow_mask || !cpu.integer_overflow_mask_defined ||
           !cpu.integer_overflow_flag || !cpu.integer_overflow_flag_defined ||
           cpu.stop_code!=StopCode::none || cpu.pending_integer_overflow.pending)
           return 5;
        ++checked;
    }
    return checked>1000u?0:6;
}
"""
        report = native(program, harness)
        self.assertEqual(report.translated, 4)
        self.assertEqual(report.unsupported, (16,))

    def test_fail_closed_special_subnormal_and_inexact_cases(self):
        native([movrl(), movrl(0, 20, src_fp=True, dst_fp=False),
                0xffffffff], r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{}; CPU cpu{};
    const std::uint64_t bad[]={
        0x0000000000000001ull, 0x800fffffffffffffull,
        0x7ff0000000000000ull, 0x7ff8000000000001ull,
        0xfff0000000000000ull
    };
    for(auto bits:bad) {
        cpu={}; cpu.r[16]=static_cast<std::uint32_t>(bits);
        cpu.r[17]=static_cast<std::uint32_t>(bits>>32u);
        cpu.ip=0;
        if(step(cpu,bus) ||
           cpu.stop_code!=StopCode::unsupported_floating_format ||
           cpu.fp_defined[0] || cpu.ip!=0u)return 1;
    }
    cpu={};cpu.ip=4u;cpu.r[20]=0x12345678u;
    if(step(cpu,bus) ||
       cpu.stop_code!=StopCode::undefined_floating_point_register ||
       cpu.r[20]!=0x12345678u || cpu.ip!=4u)return 2;
    cpu={};cpu.ip=4u;cpu.fp_defined[0]=true;
    cpu.fp[0].high=16383u;cpu.fp[0].middle=0x80000000u;
    cpu.fp[0].low=1u;cpu.r[20]=0x12345678u;
    if(step(cpu,bus) ||
       cpu.stop_code!=StopCode::unsupported_floating_rounding ||
       cpu.r[20]!=0x12345678u || cpu.ip!=4u)return 3;
    cpu={};cpu.ip=4u;cpu.fp_defined[0]=true;
    cpu.fp[0].high=0x7ffeu;cpu.fp[0].middle=0x80000000u;
    cpu.r[20]=0x12345678u;
    if(step(cpu,bus) ||
       cpu.stop_code!=StopCode::unsupported_floating_format ||
       cpu.r[20]!=0x12345678u || cpu.ip!=4u)return 4;
    return 0;
}
""")

if __name__ == "__main__":
    unittest.main()
