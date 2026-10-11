"""Native Intel 80960KB ADDR exact-real subset: original register pattern.

The original HOTD1 instruction candidate 0xC00 uses ADDR g4,g2,g4.
Synthetic GCC/Clang tests compare an independent rational-number
oracle. No ROM code or proprietary assets are checked in.
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


def addr(src1=20, src2=18, dst=20, flags=0):
    return (0x78000780 | src1 | (src2 << 14) | (dst << 19)
            | flags)


def f32(word):
    return struct.unpack("<f", struct.pack("<I", word))[0]


def verdict(a, b):
    ae = (a >> 23) & 255
    be = (b >> 23) & 255
    af = a & 0x7fffff
    bf = b & 0x7fffff
    if ae == 255 or be == 255 or (ae == 0 and af) or (be == 0 and bf):
        return 2, 0  # exceptional input, format handling unavailable
    az = ae == 0
    bz = be == 0
    if az and bz:
        return (1, 0) if (a ^ b) & 0x80000000 else (0, a)
    if az or bz:
        return 0, b if az else a
    if abs(ae-be) > 32:
        return 1, 0  # implementation intentionally conservative
    total = Fraction.from_float(f32(a)) + Fraction.from_float(f32(b))
    if total == 0:
        return 1, 0  # cancellation sign requires AC rounding
    if abs(total) > Fraction.from_float(f32(0x7f7fffff)):
        return 2, 0
    try:
        packed = struct.pack("<f", float(total))
    except (OverflowError, ValueError):
        return 2, 0
    bits = struct.unpack("<I", packed)[0]
    if (bits & 0x7f800000) == 0:
        return 2, 0  # nonnormal result / underflow requires FP status
    if Fraction.from_float(f32(bits)) != total:
        return 1, 0
    return 0, bits


def cases():
    values = [0, 0x80000000, 0x3f800000, 0xbf800000,
              0x40000000, 0xc0000000, 0x3fc00000, 0x3fa00000,
              0x3e800000, 0x4f000000, 0x7f7fffff, 0xff7fffff,
              0x00800000, 0x80800000, 0x00000001, 0x7f800000,
              0xff800000, 0x7fc00001]
    result = [(a, b) for a in values for b in values]
    rng = random.Random(0x78f960)
    for _ in range(500):
        for exp_a, exp_b in (
            (rng.randrange(10, 240), rng.randrange(10, 240)),
            (127, rng.randrange(115, 137)),
        ):
            a = (rng.getrandbits(1)<<31) | (exp_a<<23) | rng.getrandbits(23)
            b = (rng.getrandbits(1)<<31) | (exp_b<<23) | rng.getrandbits(23)
            result.append((a,b))
    return [(a,b,*verdict(a,b)) for a,b in result]


class AddRealNativeTests(unittest.TestCase):
    def test_decode_original_and_reject_unsupported_modes(self):
        ins = decode(struct.pack("<I", addr()), 0)
        self.assertEqual((ins.mnemonic, ins.form, ins.operands),
                         ("addr", "REG", ("g4", "g2", "g4")))
        for mode in (0x20, 0x40, 0x800, 0x1000, 0x2000):
            _, report = emit_cpp(struct.pack("<2I", addr(flags=mode),
                                             0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)

    def test_exact_addition_alias_inexact_and_range(self):
        forms = [addr(), addr(dst=17), addr(src1=18,src2=20)]
        words = forms + [0xffffffff]
        data = ",\n".join("{" + ",".join(str(n)+"u" for n in row) + "}"
                          for row in cases())
        harness = (f"static const std::uint32_t cases[][4] = {{\n"
                   f"{data}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main(){
    Bus bus{};unsigned checked=0;
    for(const auto& v: cases)
    for(unsigned form=0;form<3;++form)
    for(unsigned oldcc=0;oldcc<8;++oldcc) {
        CPU cpu{};cpu.ip=form*4u;
        cpu.r[20]=v[0];cpu.r[18]=v[1];cpu.r[17]=0xbeef1234u;
        cpu.cc=static_cast<int>(oldcc);
        cpu.cc_defined=(oldcc&1u)!=0u;
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        const unsigned dest=(form==1)?17u:20u;
        const std::uint32_t old[3]={cpu.r[20],cpu.r[18],cpu.r[17]};
        const bool done=step(cpu,bus);
        if(v[2]==0u) {
            if(!done||cpu.ip!=(form+1u)*4u||
               cpu.r[dest]!=v[3]||cpu.stop_code!=StopCode::none)return 1;
        } else {
            const StopCode reason=v[2]==1u?
                StopCode::unsupported_floating_rounding:
                StopCode::unsupported_floating_format;
            if(done||cpu.ip!=form*4u||cpu.stop_code!=reason||
               cpu.r[20]!=old[0]||cpu.r[18]!=old[1]||
               cpu.r[17]!=old[2])return 2;
        }
        if((dest!=20u && cpu.r[20]!=old[0])||
           (dest!=18u && cpu.r[18]!=old[1])||
           (dest!=17u && cpu.r[17]!=old[2])||
           cpu.cc!=static_cast<int>(oldcc)||
           cpu.cc_defined!=bool(oldcc&1u)||
           !cpu.integer_overflow_mask_defined||!cpu.integer_overflow_mask||
           !cpu.integer_overflow_flag_defined||!cpu.integer_overflow_flag||
           cpu.pending_integer_overflow.pending)return 3;
        ++checked;
    }
    return checked>10000?0:4;
}
"""
        cpp, report = emit_cpp(
            struct.pack("<" + "I"*len(words), *words), 0, 32)
        self.assertEqual(report.translated, 3)
        self.assertEqual(report.unsupported, (12,))
        compilers = [p for n in ("g++", "clang++") if (p := shutil.which(n))]
        if not compilers:
            raise unittest.SkipTest("No C++17 compiler")
        for compiler in compilers:
            with tempfile.TemporaryDirectory(prefix="arcade-addr-") as folder:
                src = Path(folder)/"native.cpp"
                exe = Path(folder)/"native"
                src.write_text(cpp+"\n"+harness, encoding="utf-8")
                built = subprocess.run([
                    compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                    "-fsanitize=undefined","-fno-sanitize-recover=all",
                    "-I",str(ROOT/"runtime"),str(src),"-o",str(exe)],
                    capture_output=True,text=True,timeout=50)
                if built.returncode:
                    raise AssertionError(compiler+": "+built.stderr)
                ran = subprocess.run([str(exe)],capture_output=True,
                                     text=True,timeout=25)
                if ran.returncode:
                    raise AssertionError(
                        compiler+f": exit {ran.returncode}: "
                        +ran.stdout+ran.stderr)


if __name__=="__main__":
    unittest.main()
