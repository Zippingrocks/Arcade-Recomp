"""Native integrated 80960KB FP sequence test, synthetic ROM-free bytes.

LOG BINARY REAL -> ADD REAL -> CONVERT TOWARD ZERO.
Uses different registers than HOTD original. Independent IEEE-754 oracle:
for normal single-precision input with stored exponent E, output is E+1.
"""
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def enc(opcode, a, b, d, flags=0):
    return ((opcode >> 4) << 24) | ((opcode & 15) << 7) | (
        d << 19) | (b << 14) | a | flags


def float_bits(value):
    return struct.unpack("<I", struct.pack("<f", float(value)))[0]


def native_run(harness):
    image = struct.pack("<4I",
        enc(0x68a, 24, 0, 25, 0x1000), # synthetic g8 -> g9
        enc(0x78f, 25, 21, 25),        # synthetic g9 + g5 -> g9
        enc(0x6c2, 25, 0, 19, 0x1000), # synthetic g9 -> g3
        0xffffffff)
    cpp, report = emit_cpp(image, 0, 12)
    if report.translated != 3 or report.unsupported != (12,):
        raise AssertionError(report)
    compilers = [p for name in ("g++", "clang++")
                 if (p := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("No C++17 compiler")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-fp-sequence-") as d:
            src = Path(d)/"native.cpp"
            exe = Path(d)/"native"
            src.write_text(cpp+"\n"+harness, encoding="utf-8")
            built = subprocess.run(
                [compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 "-I",str(ROOT/"runtime"),str(src),"-o",str(exe)],
                text=True,capture_output=True,timeout=60)
            if built.returncode:
                raise AssertionError(compiler+": "+built.stderr)
            ran = subprocess.run([str(exe)],text=True,
                                 capture_output=True,timeout=40)
            if ran.returncode:
                raise AssertionError(compiler+": "+str(ran.returncode)+
                                     " "+ran.stderr)
    return report


class NativeFPSequence(unittest.TestCase):
    def test_all_normal_exponents_signed_values_and_aliases(self):
        rng = random.Random(0x960c04)
        values = []
        for e in range(1,255):
            for sign in range(2):
                for frac in (0,1,0x123456,0x7fffff):
                    values.append(((sign<<31)|(e<<23)|frac,
                        float_bits(e-127),float_bits(e+1),e+1))
        for _ in range(700):
            e = rng.randrange(1,255)
            values.append(((rng.getrandbits(1)<<31)|(e<<23)|
                rng.getrandbits(23),float_bits(e-127),float_bits(e+1),e+1))
        data = ",\n".join("{" + ",".join(str(i)+"u" for i in row) + "}"
                          for row in values)
        harness = ("static const std::uint32_t cases[][4] = {\n" +
                   data + "\n};\n") + r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};unsigned checked=0;
    for(const auto& row:cases)
    for(unsigned cc=0;cc<8u;++cc)
    for(unsigned defined=0;defined<2u;++defined) {
        CPU cpu{};
        for(unsigned i=0;i<32;++i)cpu.r[i]=(i+3u)*0x01030709u;
        cpu.r[24]=row[0];cpu.r[21]=0x43000000u;
        cpu.cc=static_cast<int>(cc);cpu.cc_defined=defined!=0u;
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        std::uint32_t saved[32]{};
        for(unsigned i=0;i<32;++i)saved[i]=cpu.r[i];
        if(!step(cpu,bus)||cpu.ip!=4u||cpu.r[25]!=row[1])return 1;
        if(!step(cpu,bus)||cpu.ip!=8u||cpu.r[25]!=row[2])return 2;
        if(!step(cpu,bus)||cpu.ip!=12u||cpu.r[19]!=row[3])return 3;
        for(unsigned i=0;i<32;++i)
            if(i!=19u&&i!=25u&&cpu.r[i]!=saved[i])return 4;
        if(cpu.cc!=static_cast<int>(cc)||cpu.cc_defined!=bool(defined)||
           !cpu.integer_overflow_mask||!cpu.integer_overflow_mask_defined||
           !cpu.integer_overflow_flag||!cpu.integer_overflow_flag_defined||
           cpu.pending_integer_overflow.pending||
           cpu.stop_code!=StopCode::none)return 5;
        ++checked;
    }
    return checked>30000u?0:6;
}
"""
        self.assertEqual(native_run(harness).translated, 3)

    def test_special_values_stop_at_first_step_without_partial_state(self):
        native_run(r"""
using namespace arcaderecomp_generated;
int main(){
    Bus bus{};
    const std::uint32_t bad[]={0u,0x80000000u,1u,
        0x807fffffu,0x7f800000u,0xff800000u,0x7fc00001u};
    for(auto bits:bad){
        CPU cpu{};
        cpu.r[24]=bits;cpu.r[25]=0xdeadbeefu;
        cpu.r[19]=0xfacefeedu;cpu.r[21]=0x43000000u;
        cpu.cc=4;
        if(step(cpu,bus)||
           cpu.stop_code!=StopCode::unsupported_floating_format||
           cpu.stop_ip!=0u||cpu.ip!=0u||
           cpu.r[24]!=bits||cpu.r[25]!=0xdeadbeefu||
           cpu.r[19]!=0xfacefeedu||cpu.r[21]!=0x43000000u||
           cpu.cc!=4||!cpu.cc_defined)return 1;
    }
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
