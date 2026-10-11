"""Native Intel 80960KB CVTZRI 6C2 tests, using synthetic instructions.

The original HOTD1 has a CVTZRI g4->g1 candidate at 0x00000c04.
Exact signed-real conversions succeed; all cases needing unimplemented
precision/invalid exceptions must stop without modifying registers.
"""
from pathlib import Path
import math
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def cvtzri(source=20, destination=17, source_fp=False, literal=False):
    return (0x6c000100 | 0x1000 | source | (destination << 19)
            | (0x20 if source_fp else 0) | (0x800 if literal else 0))


def native(words, harness):
    image = struct.pack("<" + "I" * len(words), *words)
    emitted, report = emit_cpp(image, 0, 128)
    compilers = [p for n in ("g++", "clang++") if (p := shutil.which(n))]
    if not compilers:
        raise unittest.SkipTest("No C++17 compiler")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-kb-cvtzri-") as d:
            source = Path(d) / "test.cpp"
            binary = Path(d) / "native"
            source.write_text(emitted + "\n" + harness, encoding="utf8")
            built = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                "-Werror", "-fsanitize=undefined",
                "-fno-sanitize-recover=all", "-I", str(ROOT / "runtime"),
                str(source), "-o", str(binary)],
                capture_output=True, text=True, timeout=45)
            if built.returncode:
                raise AssertionError(compiler + ": " + built.stderr)
            run = subprocess.run([str(binary)], capture_output=True,
                                 text=True, timeout=25)
            if run.returncode:
                raise AssertionError(
                    compiler + f": exit {run.returncode}: "
                    + run.stdout + run.stderr)
    return report


def real32_cases():
    rng = random.Random(0x6c2960)
    seeds = [
        0, 0x80000000, 0x3f800000, 0xbf800000, 0x4f000000,
        0xcf000000, 0x4effffff, 0xceffffff, 0x3fc00000,
        0xbfc00000, 0x3f000000, 0x80000001, 0x00000001,
        0x7f800000, 0xff800000, 0x7fc00001, 0xffffffff,
        0x7f7fffff, 0xff7fffff,
    ]
    for x in (0, 1, 2, 3, 7, 17, 31, 32, (1 << 24) - 1,
              1 << 24, 1 << 25, 1 << 30, 1 << 31):
        for sign in (-1, 1):
            seeds.append(struct.unpack("<I", struct.pack(
                "<f", float(sign * x)))[0])
    seeds += [rng.getrandbits(32) for _ in range(600)]
    rows = []
    for word in seeds:
        value = struct.unpack("<f", struct.pack("<I", word))[0]
        rawexp = (word >> 23) & 0xff
        mantissa = word & 0x7fffff
        special = rawexp == 0xff
        zero = rawexp == 0 and mantissa == 0
        exact = zero or (math.isfinite(value) and
                         -2147483648 <= value <= 2147483647 and
                         value.is_integer())
        if exact:
            kind, result = 0, (int(value) & 0xffffffff)
        elif special:
            kind, result = 2, 0
        elif math.isfinite(value) and (
                value < -2147483648 or value > 2147483647):
            kind, result = 3, 0
        else:
            kind, result = 1, 0
        rows.append((word, kind, result))
    return rows


class CVTZRINativeTests(unittest.TestCase):
    def test_decode_and_fail_closed_encodings(self):
        x = decode(struct.pack("<I", cvtzri()), 0)
        self.assertEqual((x.mnemonic, x.form, x.operands),
                         ("cvtzri", "REG", ("g4", "g1")))
        y = decode(struct.pack("<I", cvtzri(2, 18, source_fp=True)), 0)
        self.assertEqual(y.operands, ("fp2", "g2"))
        for invalid in (
            cvtzri(literal=True), cvtzri() | 0x40,
            cvtzri() | (1 << 14), cvtzri() & ~0x1000,
            cvtzri() | 0x2000, cvtzri(4, 18, source_fp=True),
        ):
            _, report = emit_cpp(struct.pack("<2I", invalid, 0xffffffff),
                                 0, 8)
            self.assertIn(0, report.unsupported)

    def test_original_register_form_native_real32(self):
        # At 0xC04 the arcade uses g4 -> g1; include destination=source.
        words = [cvtzri(), cvtzri(20, 20), 0xffffffff]
        serialized = ",\n".join(
            "{" + ",".join(str(x) + "u" for x in row) + "}"
            for row in real32_cases())
        harness = (f"static const std::uint32_t cases[][3] = {{\n"
                   f"{serialized}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    unsigned checked=0u;
    for(const auto& row:cases)
    for(unsigned form=0;form<2;++form)
    for(unsigned cc=0;cc<8;++cc) {
        CPU cpu{};cpu.r[20]=row[0];cpu.r[17]=0xdeadbeefu;
        cpu.ip=form*4u;cpu.cc=static_cast<int>(cc);
        cpu.cc_defined=(cc&1u)!=0u;
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        const bool ok=step(cpu,bus);
        const unsigned dst=form==0?17u:20u;
        if(row[1]==0u) {
            if(!ok||cpu.ip!=(form+1u)*4u||cpu.r[dst]!=row[2]||
               cpu.stop_code!=StopCode::none)return 1;
        } else {
            const StopCode code=row[1]==1u?
                StopCode::unsupported_floating_rounding:
                row[1]==2u?StopCode::unsupported_floating_format:
                StopCode::unsupported_floating_integer_range;
            if(ok||cpu.ip!=form*4u||cpu.r[20]!=row[0]||
               cpu.r[17]!=0xdeadbeefu||cpu.stop_code!=code)return 2;
        }
        if(cpu.cc!=static_cast<int>(cc) ||
           cpu.cc_defined!=bool(cc&1u) ||
           !cpu.integer_overflow_mask_defined||!cpu.integer_overflow_mask||
           !cpu.integer_overflow_flag_defined||!cpu.integer_overflow_flag||
           cpu.pending_integer_overflow.pending)return 3;
        ++checked;
    }
    return checked>10000u?0:4;
}
"""
        report = native(words, harness)
        self.assertEqual(report.translated, 2)
        self.assertEqual(report.unsupported, (8,))

    def test_extended80_exact_integer_boundaries_and_failure(self):
        # Synthetic fp0 contains canonical extended80 with exactly
        # representable integer magnitudes, including INT32_MIN.
        words = [cvtzri(0, 17, source_fp=True), 0xffffffff]
        vectors = [-2147483648, -2147483647, -65537, -1,
                   0, 1, 65537, 2147483647, 2147483648,
                   -2147483649]
        rng = random.Random(0x80c2960)
        vectors += [rng.randint(-2200000000, 2200000000)
                    for _ in range(400)]
        rows = []
        for n in vectors:
            mag = abs(n)
            if not mag:
                rows.append((0, 0, 0, 0))
                continue
            msb = mag.bit_length() - 1
            sig = mag << (63-msb)
            high = (0x8000 if n < 0 else 0) | (16383+msb)
            kind = 0 if -(1<<31) <= n < (1<<31) else 3
            rows.append((sig & 0xffffffff, sig >> 32, high,
                         kind << 32 | (n & 0xffffffff)))
        data = ",\n".join(
            "{" + ",".join(str(x) + "ull" for x in row) + "}"
            for row in rows)
        harness = (f"static const std::uint64_t cases[][4] = {{\n"
                   f"{data}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};unsigned count=0;
    for(const auto& row:cases) {
        CPU cpu{};cpu.fp_defined[0]=true;
        cpu.fp[0].low=static_cast<std::uint32_t>(row[0]);
        cpu.fp[0].middle=static_cast<std::uint32_t>(row[1]);
        cpu.fp[0].high=static_cast<std::uint16_t>(row[2]);
        cpu.r[17]=0xcafebabeu;
        const bool ok=step(cpu,bus);
        const bool supported=(row[3]>>32u)==0u;
        if(supported) {
            if(!ok||cpu.ip!=4u||
               cpu.r[17]!=static_cast<std::uint32_t>(row[3]))return 1;
        } else {
            if(ok||cpu.ip!=0u||
               cpu.r[17]!=0xcafebabeu||
               cpu.stop_code!=StopCode::unsupported_floating_integer_range)
               return 2;
        }
        ++count;
    }
    CPU unknown{};
    if(step(unknown,bus) ||
       unknown.stop_code!=StopCode::undefined_floating_point_register)
       return 3;
    CPU fraction{};fraction.fp_defined[0]=true;
    fraction.fp[0].high=0x3fffu;
    fraction.fp[0].middle=0xc0000000u;
    if(step(fraction,bus) ||
       fraction.stop_code!=StopCode::unsupported_floating_rounding)
       return 4;
    return count>400u?0:5;
}
"""
        report = native(words,harness)
        self.assertEqual(report.translated, 1)


if __name__=="__main__":
    unittest.main()
