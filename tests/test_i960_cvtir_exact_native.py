"""Intel 80960KB CVTIR exact conversions, preserving undefined FP controls.

Only original 1988 Intel KB opcode metadata and synthetic instructions.
GCC/Clang UBSan execute native emitted code. Independent Python IEEE-754
binary32 and integer 80-bit bit pattern oracles test result fidelity.
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
OPCODE = 0x674


def instr(src=16, dst=17, *, literal=False, fp=False):
    return (0x67000200 | 0x1000 | src | (dst << 19) |
            (0x800 if literal else 0) | (0x2000 if fp else 0))


def reference(raw):
    signed = raw if raw < 0x80000000 else raw - 0x100000000
    magnitude = abs(signed)
    if not magnitude:
        extended = (0, 0, 0)
    else:
        msb = magnitude.bit_length() - 1
        significand = magnitude << (63 - msb)
        extended = (significand & 0xffffffff,
                    (significand >> 32) & 0xffffffff,
                    (0x8000 if signed < 0 else 0) | (16383 + msb))
    packed = struct.pack("<f", float(signed))
    back = struct.unpack("<f", packed)[0]
    binary32 = struct.unpack("<I", packed)[0]
    exact = int(back) == signed
    return binary32, int(exact), *extended


def synthetic_rows():
    values = [0, 1, 2, 3, 7, 17, 31, 32, 0x7fffffff,
              0x80000000, 0x80000001, 0xffffffff,
              0x01000000, 0x01000001, 0x01000002,
              0xff000000, 0xfeffffff, 0x7fffff00,
              0x80000100, 0x7f800000]
    values.extend(1 << p for p in range(32))
    values.extend(((1 << p) - 1) & 0xffffffff for p in range(32))
    for n in (1<<24, (1<<24)+1, (1<<25)+2, (1<<30)+128):
        values.extend((n, (-n)&0xffffffff))
    rng = random.Random(0x674960)
    values.extend(rng.getrandbits(32) for _ in range(512))
    return [(v, *reference(v)) for v in values]


class CvtirExactNativeTests(unittest.TestCase):
    def test_decoder_and_fail_closed_modes(self):
        self.assertEqual(decode(struct.pack("<I", instr()), 0).operands,
                         ("g0", "g1"))
        self.assertEqual(decode(struct.pack("<I", instr(4, 2, fp=True)), 0).operands,
                         ("r4", "fp2"))
        for word in (
            instr() | 0x20,     # no floating source
            instr() | 0x40,     # no src2 special function
            instr() | (1<<14), # src2 unused
            instr() & ~0x1000, # unused M2 field not canonical
            instr(16,4,fp=True),  # FP register number out of range
        ):
            _, report = emit_cpp(struct.pack("<2I", word, 0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)

    def test_native_binary32_exact_only_and_extended80_all_inputs(self):
        # GP dest aliases src, separate dest, FP dest, and integer literal.
        words = [instr(16,17), instr(16,16), instr(16,1,fp=True),
                 instr(31,18,literal=True), 0xffffffff]
        cpp, report = emit_cpp(struct.pack("<5I", *words), 0, 32)
        self.assertEqual(report.translated, 4)
        self.assertEqual(report.unsupported, (16,))
        values = ",\n".join("{"+",".join(str(x)+"u" for x in row)+"}"
                             for row in synthetic_rows())
        harness = (f"static const std::uint32_t cases[][6] = {{\n"
                   f"{values}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main(){
    Bus bus{};unsigned successful=0,declined=0;
    for(const auto& row: cases)
    for(unsigned kind=0;kind<4;++kind)
    for(unsigned oldcc=0;oldcc<8;++oldcc) {
        CPU cpu{};cpu.ip=kind*4u;
        cpu.r[16]=row[0];cpu.r[17]=0xa5a55a5au;cpu.r[18]=0xdeadbeefu;
        cpu.cc=static_cast<int>(oldcc);cpu.cc_defined=(oldcc&1u)!=0u;
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        const std::uint32_t before[3]={cpu.r[16],cpu.r[17],cpu.r[18]};
        const std::uint32_t wanted=(kind==3)?0x41f80000u:row[1];
        const bool exact=(kind==3 || kind==2 || row[2]!=0u);
        const bool result=step(cpu,bus);
        if(!exact) {
            if(result||cpu.ip!=kind*4u||
               cpu.stop_code!=StopCode::unsupported_floating_rounding||
               cpu.r[16]!=before[0]||cpu.r[17]!=before[1]||
               cpu.r[18]!=before[2]||cpu.fp_defined[1])return 1;
            ++declined;continue;
        }
        if(!result||cpu.ip!=(kind+1u)*4u||
           cpu.stop_code!=StopCode::none)return 2;
        if(kind==2) {
            if(!cpu.fp_defined[1] ||
               cpu.fp[1].low!=row[3] ||
               cpu.fp[1].middle!=row[4] ||
               cpu.fp[1].high!=row[5])return 3;
            if(cpu.r[16]!=before[0]||cpu.r[17]!=before[1]||
               cpu.r[18]!=before[2])return 4;
        } else {
            const unsigned dest=kind==0?17u:kind==1?16u:18u;
            if(cpu.r[dest]!=wanted)return 5;
            if(dest!=16u && cpu.r[16]!=before[0])return 6;
            if(dest!=17u && cpu.r[17]!=before[1])return 7;
            if(dest!=18u && cpu.r[18]!=before[2])return 8;
        }
        if(cpu.cc!=static_cast<int>(oldcc) ||
           cpu.cc_defined!=bool(oldcc&1u) ||
           !cpu.integer_overflow_mask_defined || !cpu.integer_overflow_mask ||
           !cpu.integer_overflow_flag_defined || !cpu.integer_overflow_flag ||
           cpu.pending_integer_overflow.pending)return 9;
        ++successful;
    }
    return (successful>1000u && declined>100u)?0:10;
}
""";
        compilers = [p for name in ("g++", "clang++")
                     if (p := shutil.which(name))]
        if not compilers:
            raise unittest.SkipTest("No C++17 compilers available")
        for compiler in compilers:
            with tempfile.TemporaryDirectory(prefix="arcade-cvtir-") as folder:
                source = Path(folder)/"native.cpp"
                binary = Path(folder)/"native"
                source.write_text(cpp+"\n"+harness, encoding="utf-8")
                built = subprocess.run(
                    [compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                     "-fsanitize=undefined","-fno-sanitize-recover=all",
                     "-I",str(ROOT/"runtime"),str(source),"-o",str(binary)],
                    capture_output=True,text=True,timeout=45)
                if built.returncode:
                    raise AssertionError(compiler+": "+built.stderr)
                ran = subprocess.run([str(binary)],capture_output=True,
                                     text=True,timeout=25)
                if ran.returncode:
                    raise AssertionError(
                        f"{compiler}: exit {ran.returncode}: "
                        +ran.stdout+ran.stderr)


if __name__ == "__main__":
    unittest.main()
