"""Intel 80960KB MULR exact real32 AOT tests: original opcode, invented inputs.

Two original HOTD1 code candidates use MULR 78C with ordinary GPR sources,
at 0x1390 and 0x13D88. The test words are independently constructed from
published Intel opcode layouts; no original ROM words or assets are included.
Expected outputs use exact Fraction arithmetic and independent Python binary32
conversion, then execute GCC/Clang native code with UBSan.
"""
from fractions import Fraction
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


def mulr(first=21, second=29, dst=20, flags=0):
    return 0x78000600 | first | (second << 14) | (dst << 19) | flags


def f32(raw):
    return struct.unpack("<f", struct.pack("<I", raw))[0]


MIN_NORMAL = Fraction(1, 1 << 126)
MAX_NORMAL = Fraction.from_float(f32(0x7f7fffff))


def oracle(a, b):
    ae, be = (a >> 23) & 255, (b >> 23) & 255
    af, bf = a & 0x7fffff, b & 0x7fffff
    if ae == 255 or be == 255 or (ae == 0 and af) or (be == 0 and bf):
        return 2, 0  # unmodeled special/subnormal input
    if ae == 0 or be == 0:
        return 0, (a ^ b) & 0x80000000
    exact = Fraction.from_float(f32(a)) * Fraction.from_float(f32(b))
    if abs(exact) < MIN_NORMAL or abs(exact) > MAX_NORMAL:
        return 2, 0  # underflow / overflow
    packed = struct.pack("<f", float(exact))
    bits = struct.unpack("<I", packed)[0]
    if Fraction.from_float(f32(bits)) != exact:
        return 1, 0  # requires IEEE rounding and AC inexact handling
    return 0, bits


def cases():
    boundaries = [
        0, 0x80000000, 0x3f800000, 0xbf800000,
        0x40000000, 0xc0000000, 0x3f000000, 0xbf000000,
        0x3fc00000, 0x3fa00000, 0x3e800000, 0xbe800000,
        0x00800000, 0x80800000, 0x7f7fffff, 0xff7fffff,
        0x00000001, 0x007fffff, 0x7f800000, 0xff800000,
        0x7fc00001, 0xffc01234, 0x3f800001, 0x3f800002,
    ]
    pairs = [(a, b) for a in boundaries for b in boundaries]
    rng = random.Random(0x78c960)
    for _ in range(950):
        ae, be = rng.randrange(1, 255), rng.randrange(1, 255)
        a = (rng.getrandbits(1) << 31) | (ae << 23) | rng.getrandbits(23)
        b = (rng.getrandbits(1) << 31) | (be << 23) | rng.getrandbits(23)
        pairs.append((a, b))
    for _ in range(350):
        ae, be = rng.randrange(108, 146), rng.randrange(108, 146)
        a = (rng.getrandbits(1) << 31) | (ae << 23) | rng.getrandbits(23)
        b = (rng.getrandbits(1) << 31) | (be << 23) | rng.getrandbits(23)
        pairs.append((a, b))
    return [(a, b, *oracle(a, b)) for a, b in pairs]


class MulrNativeTests(unittest.TestCase):
    def test_decode_original_register_shapes_and_refuse_unsupported_modes(self):
        one = decode(struct.pack("<I", mulr()), 0)
        self.assertEqual((one.mnemonic, one.form, one.operands),
                         ("mulr", "REG", ("g5", "g13", "g4")))
        two = decode(struct.pack("<I", mulr(21, 7, 21)), 0)
        self.assertEqual(two.operands, ("g5", "r7", "g5"))
        for mask in (0x20, 0x40, 0x800, 0x1000, 0x2000):
            _, report = emit_cpp(
                struct.pack("<2I", mulr(flags=mask), 0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)

    def test_exact_multiply_sign_alias_and_fail_closed(self):
        # Destination separate, aliases source1, or aliases source2.
        words = [
            mulr(21, 29, 20),
            mulr(21, 7, 21),
            mulr(21, 29, 29),
            0xffffffff,
        ]
        image = struct.pack("<" + "I" * len(words), *words)
        generated, report = emit_cpp(image, 0, 24)
        self.assertEqual(report.translated, 3)
        self.assertEqual(report.unsupported, (12,))
        numbers = ",\n".join(
            "{" + ",".join(str(i) + "u" for i in row) + "}"
            for row in cases())
        harness = (f"static const std::uint32_t inputs[][4] = {{\n"
                   f"{numbers}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main(){
    Bus bus{}; unsigned pass=0u, inexact=0u, format=0u;
    for(const auto& values:inputs)
    for(unsigned form=0;form<3u;++form)
    for(unsigned cc=0;cc<8u;++cc)
    for(unsigned defined=0;defined<2u;++defined){
        CPU cpu{};
        cpu.ip=form*4u;
        cpu.r[21]=values[0];cpu.r[29]=values[1];
        cpu.r[7]=values[1];cpu.r[20]=0x12345678u;
        cpu.cc=static_cast<int>(cc);cpu.cc_defined=(defined!=0u);
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        const unsigned dst=(form==0u?20u:form==1u?21u:29u);
        std::uint32_t original[32]{};
        for(unsigned i=0;i<32u;++i)original[i]=cpu.r[i];
        const bool stepped=step(cpu,bus);
        if(values[2]==0u) {
            if(!stepped||cpu.stop_code!=StopCode::none||
               cpu.ip!=(form+1u)*4u||cpu.r[dst]!=values[3])return 1;
            ++pass;
        } else {
            const StopCode reason=values[2]==1u?
                StopCode::unsupported_floating_rounding:
                StopCode::unsupported_floating_format;
            if(stepped||cpu.stop_code!=reason||cpu.ip!=form*4u)return 2;
            if(values[2]==1u)++inexact;
            else ++format;
        }
        for(unsigned i=0;i<32u;++i)
            if((values[2]!=0u||i!=dst)&&cpu.r[i]!=original[i])return 3;
        if(cpu.cc!=static_cast<int>(cc)||
           cpu.cc_defined!=(defined!=0u)||
           !cpu.integer_overflow_mask||!cpu.integer_overflow_mask_defined||
           !cpu.integer_overflow_flag||!cpu.integer_overflow_flag_defined||
           cpu.pending_integer_overflow.pending)return 4;
    }
    return pass>1000u && inexact>100u && format>100u?0:5;
}
""";
        compilers=[p for name in ("g++", "clang++")
                   if (p:=shutil.which(name))]
        if not compilers:
            raise unittest.SkipTest("No C++17 compiler available")
        for compiler in compilers:
            with tempfile.TemporaryDirectory(prefix="arcade-mulr-native-") as directory:
                source=Path(directory)/"mulr.cpp"
                binary=Path(directory)/"mulr"
                source.write_text(generated+"\n"+harness,encoding="utf-8")
                built=subprocess.run(
                    [compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                     "-fsanitize=undefined","-fno-sanitize-recover=all",
                     "-I",str(ROOT/"runtime"),str(source),"-o",str(binary)],
                    capture_output=True,text=True,timeout=60)
                if built.returncode:
                    raise AssertionError(compiler+": "+built.stderr)
                ran=subprocess.run([str(binary)],capture_output=True,
                                   text=True,timeout=40)
                if ran.returncode:
                    raise AssertionError(compiler+f": exit {ran.returncode}: "+
                                         ran.stdout+ran.stderr)


if __name__=="__main__":
    unittest.main()
