"""80960KB LOGBNR AOT exponent extraction tests (synthetic only).

Intel 80960KB Programmer's Reference Manual (Mar 1988) and GNU i960
opcodes: REG 68Ah, src1/dst (R_2D); floating registers are fp0..fp3.
Both GCC/Clang UBSan and an independent Python IEEE-754 exponent oracle.
Unimplemented special cases must stop before modifying CPU state.
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


def logbnr(src=16, dst=18, *, src_fp=False, dst_fp=False, literal=False):
    return (0x68000500 | 0x1000 | src | (dst << 19) |
            (0x20 if src_fp else 0) | (0x2000 if dst_fp else 0) |
            (0x800 if literal else 0))


def fp80_integer_bits(number):
    magnitude = abs(number)
    if magnitude == 0:
        return 0, 0, 0
    msb = magnitude.bit_length() - 1
    sig = magnitude << (63 - msb)
    return sig & 0xffffffff, sig >> 32, (0x8000 if number < 0 else 0) | (16383 + msb)


def normal_real32_rows():
    rng = random.Random(0x68A960)
    inputs = []
    for exp in range(1, 255):
        for mantissa in (0, 1, 0x123456, 0x7fffff):
            for sign in (0, 1):
                inputs.append((sign << 31) | (exp << 23) | mantissa)
    for _ in range(700):
        exp = rng.randrange(1, 255)
        inputs.append((rng.getrandbits(1) << 31) | (exp << 23) |
                      rng.getrandbits(23))
    result = []
    for value in inputs:
        logb = ((value >> 23) & 255) - 127
        bits = struct.unpack("<I", struct.pack("<f", float(logb)))[0]
        sig0, sig1, ex80 = fp80_integer_bits(logb)
        result.append((value, bits, sig0, sig1, ex80))
    return result


def build_test(words, harness):
    cpp, report = emit_cpp(struct.pack("<" + "I" * len(words), *words), 0, 64)
    cc = [x for name in ("g++", "clang++") if (x := shutil.which(name))]
    if not cc:
        raise unittest.SkipTest("No C++17 compiler")
    for compiler in cc:
        with tempfile.TemporaryDirectory(prefix="arcade-i960-logbnr-") as root:
            source = Path(root) / "test.cpp"
            exe = Path(root) / "test"
            source.write_text(cpp + "\n" + harness, encoding="utf8")
            built = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT / "runtime"), str(source), "-o", str(exe)
            ], capture_output=True, text=True, timeout=50)
            if built.returncode:
                raise AssertionError(compiler + ": " + built.stderr)
            ran = subprocess.run([str(exe)], capture_output=True, text=True,
                                 timeout=40)
            if ran.returncode:
                raise AssertionError(f"{compiler}: exit {ran.returncode}: " +
                                     ran.stdout + ran.stderr)
    return report


class LogbnrNativeTests(unittest.TestCase):
    def test_decoder_and_reserved_modes(self):
        inst = decode(struct.pack("<I", logbnr(src=17, dst=20)), 0)
        self.assertEqual((inst.mnemonic, inst.form, inst.operands),
                         ("logbnr", "REG", ("g1", "g4")))
        other = decode(struct.pack(
            "<I", logbnr(2, 3, src_fp=True, dst_fp=True)), 0)
        self.assertEqual(other.operands, ("fp2", "fp3"))
        for bad in (
            logbnr(literal=True),
            logbnr() | 0x40,
            logbnr() | (1 << 14),
            logbnr() & ~0x1000,
            logbnr(4, 20, src_fp=True),
            logbnr(16, 4, dst_fp=True),
        ):
            _, report = emit_cpp(struct.pack("<2I", bad, 0xffffffff),
                                 0, 8)
            self.assertIn(0, report.unsupported)

    def test_native_normal_float_to_float_or_extended(self):
        words = [logbnr(), logbnr(16, 0, dst_fp=True), 0xffffffff]
        vectors = ",\n".join("{" + ",".join(str(v) + "u" for v in row) + "}"
                              for row in normal_real32_rows())
        harness = (f"static const std::uint32_t vectors[][5] = {{\n"
                   f"{vectors}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{}; unsigned checked = 0u;
    for (const auto& row : vectors)
    for (unsigned cc = 0u; cc < 8u; ++cc)
    for (unsigned defined = 0u; defined < 2u; ++defined) {
        CPU cpu{}; cpu.r[16]=row[0]; cpu.r[18]=0xa5a5a5a5u;
        cpu.cc=static_cast<int>(cc); cpu.cc_defined=defined!=0;
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        if(!step(cpu,bus)||cpu.ip!=4u||cpu.r[18]!=row[1] ||
           cpu.r[16]!=row[0] || cpu.stop_code!=StopCode::none)return 1;
        if(!step(cpu,bus)||cpu.ip!=8u||!cpu.fp_defined[0] ||
           cpu.fp[0].low!=row[2]||cpu.fp[0].middle!=row[3]||
           cpu.fp[0].high!=row[4])return 2;
        if(cpu.cc!=static_cast<int>(cc)||cpu.cc_defined!=bool(defined)||
           !cpu.integer_overflow_mask||!cpu.integer_overflow_mask_defined||
           !cpu.integer_overflow_flag||!cpu.integer_overflow_flag_defined||
           cpu.pending_integer_overflow.pending)return 3;
        ++checked;
    }
    return checked > 30000u ? 0 : 4;
}
"""
        report = build_test(words, harness)
        self.assertEqual(report.translated, 2)
        self.assertEqual(report.unsupported, (8,))

    def test_native_extended_source_alias_and_fail_closed(self):
        words = [logbnr(0, 1, src_fp=True, dst_fp=True),
                 logbnr(0, 20, src_fp=True),
                 logbnr(16, 16), 0xffffffff]
        harness = r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    // Canonical extended 1.5 * 2^E (including huge exponents), both signs.
    for(unsigned e=1;e<32767u;e+=97u)
    for(unsigned sign=0;sign<2;++sign) {
        CPU cpu{};
        cpu.fp[0].high=static_cast<std::uint16_t>(
            e | (sign ? 0x8000u : 0u));
        cpu.fp[0].middle=0xc0000000u;
        cpu.fp[0].low=0x12345678u;
        cpu.fp_defined[0]=true;
        const std::int32_t exponent=static_cast<std::int32_t>(e)-16383;
        if(!step(cpu,bus)||cpu.ip!=4u||!cpu.fp_defined[1])return 1;
        // Independence check: copy result from internal FP format through
        // bit-exact MOVRE-style integer conversion properties.
        const ExtendedReal result=cpu.fp[1];
        const bool neg=exponent<0;
        const std::uint32_t mag=static_cast<std::uint32_t>(
            neg ? -exponent : exponent);
        if(!mag) {
            if(result.low||result.middle||result.high)return 2;
        } else {
            unsigned msb=0u;
            while((mag >> (msb+1u))!=0u)++msb;
            const std::uint64_t sig=static_cast<std::uint64_t>(mag)
                << (63u-msb);
            if(result.low!=static_cast<std::uint32_t>(sig)||
               result.middle!=static_cast<std::uint32_t>(sig>>32u)||
               result.high!=static_cast<std::uint16_t>(
                   (neg?0x8000u:0u) | (16383u+msb)))return 3;
        }
        if(!step(cpu,bus)||cpu.ip!=8u)return 4;
        // Independently form IEEE binary32 result via exact host integer
        // conversion; all exponents are within binary32 24-bit precision.
        if(cpu.r[20]!=static_cast<std::uint32_t>(
            (neg?0x80000000u:0u) |
            (mag ? (([&](){
                unsigned k=0u;
                while((mag>>(k+1u))!=0u)++k;
                return ((127u+k)<<23u) |
                       ((mag << (23u-k)) & 0x7fffffu);
            })()) : 0u)))return 5;
    }
    CPU cpu{}; cpu.ip=0u;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_floating_point_register||
       cpu.ip!=0u || cpu.fp_defined[1])return 6;
    for(auto bad : {0u, 0x7f800000u, 0x7fc00001u, 1u, 0x80000000u}) {
        CPU test{}; test.ip=8u;test.r[16]=bad;
        if(step(test,bus)||
           test.stop_code!=StopCode::unsupported_floating_format||
           test.ip!=8u||test.r[16]!=bad)return 7;
    }
    for (auto badexp : {0u, 32767u}) {
        CPU test{}; test.fp_defined[0]=true;test.fp[0].high=
            static_cast<std::uint16_t>(badexp);
        test.fp[0].middle=0x80000000u;
        test.ip=0;
        if(step(test,bus)||
           test.stop_code!=StopCode::unsupported_floating_format||
           test.fp_defined[1])return 8;
    }
    return 0;
}
"""
        # Use only standard headers available via emitted runtime.
        harness = "#include <initializer_list>\n" + harness
        report = build_test(words, harness)
        self.assertEqual(report.translated, 3)
        self.assertEqual(report.unsupported, (12,))


if __name__ == "__main__":
    unittest.main()
