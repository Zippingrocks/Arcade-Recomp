"""Intel KB MOVR native tests, using only synthetic instruction words.

The reference vectors use Python's exact rational representation of binary32
values, independently of the runtime's direct exponent/fraction manipulation.
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


def movr(src=16, dst=0, *, src_fp=False, dst_fp=True):
    return (0x6c000480 | 0x1000 | src | (dst << 19) |
            (0x20 if src_fp else 0) | (0x2000 if dst_fp else 0))


def exact_extended(bits):
    value = struct.unpack("<f", struct.pack("<I", bits))[0]
    sign = 0x8000 if bits & 0x80000000 else 0
    if value == 0:
        return (bits, 0, 0, sign)
    numerator, denominator = abs(value).as_integer_ratio()
    exponent = numerator.bit_length() - denominator.bit_length()
    shift = 63 - exponent
    significand = ((numerator << shift) // denominator if shift >= 0
                   else numerator // (denominator << -shift))
    assert 1 << 63 <= significand < 1 << 64
    return (bits, significand & 0xffffffff, significand >> 32,
            sign | (exponent + 16383))


def vectors():
    values = [0, 0x80000000]
    values += [(sign << 31) | (exponent << 23) | fraction
               for sign in range(2) for exponent in range(1, 255)
               for fraction in (0, 1, 0x3fffff, 0x7fffff)]
    rng = random.Random(0x6c9960)
    values += [(rng.getrandbits(1) << 31) | (rng.randrange(1, 255) << 23) |
               rng.getrandbits(23) for _ in range(1024)]
    return [exact_extended(bits) for bits in values]


def native(words, harness):
    image = struct.pack("<" + "I" * len(words), *words)
    cpp, report = emit_cpp(image, 0, len(words) + 8)
    compilers = [path for name in ("g++", "clang++")
                 if (path := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("No C++17 compiler found")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-movr-") as folder:
            source, executable = Path(folder) / "test.cpp", Path(folder) / "test"
            source.write_text(cpp + "\n" + harness, encoding="utf-8")
            built = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT / "runtime"), str(source), "-o", str(executable)],
                capture_output=True, text=True, timeout=45)
            if built.returncode:
                raise AssertionError(compiler + ": " + built.stderr)
            ran = subprocess.run([str(executable)], capture_output=True,
                                 text=True, timeout=25)
            if ran.returncode:
                raise AssertionError(f"{compiler}: exit {ran.returncode}: " +
                                     ran.stdout + ran.stderr)
    return report


COMMON = r"""
using namespace arcaderecomp_generated;
bool same_fp(const ExtendedReal& a,const ExtendedReal& b) {
    return a.low==b.low && a.middle==b.middle && a.high==b.high;
}
bool same_data(const CPU& a,const CPU& b) {
    for(unsigned i=0;i<32u;++i)if(a.r[i]!=b.r[i])return false;
    for(unsigned i=0;i<4u;++i)
        if(!same_fp(a.fp[i],b.fp[i]) || a.fp_defined[i]!=b.fp_defined[i])return false;
    const auto ac=kb_arithmetic_controls_snapshot(a);
    const auto bc=kb_arithmetic_controls_snapshot(b);
    return ac.value==bc.value && ac.known_mask==bc.known_mask &&
           a.ip==b.ip && a.process_controls==b.process_controls &&
           a.trace_controls==b.trace_controls;
}
"""


class MovrNativeTests(unittest.TestCase):
    def test_decode_reserved_modes_and_neighbor_encodings(self):
        for source, destination, src_fp, dst_fp, operands in (
            (16, 0, False, True, ("g0", "fp0")),
            (3, 31, True, False, ("fp3", "g15")),
            (1, 2, True, True, ("fp1", "fp2")),
            (17, 21, False, False, ("g1", "g5")),
        ):
            word = movr(source, destination, src_fp=src_fp, dst_fp=dst_fp)
            ins = decode(struct.pack("<I", word), 0)
            self.assertEqual((ins.mnemonic, ins.operands), ("movr", operands))
        for bad in (
            movr(4, 20, src_fp=True, dst_fp=False), movr(16, 4),
            movr() | 0x800, movr() | 0x40,
            movr() | (1 << 14), movr() & ~0x1000,
            movr() | 0x820,  # unsupported literal, never an FP alias
        ):
            _, report = emit_cpp(struct.pack("<2I", bad, 0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)
        for literal in (movr() | 0x800, movr(0) | 0x800, movr(1) | 0x820):
            self.assertEqual(decode(struct.pack("<I", literal), 0).mnemonic,
                             "unknown")
        # The three existing floating move encodings are independent, not a
        # guessed pattern based on their suffixes. MOVRE remains 6E1 pending
        # resolution of the early manual's contradictory 6E9 table entry.
        for opcode, name in ((0x6c9, "movr"), (0x6d9, "movrl"), (0x6e1, "movre")):
            word = ((opcode >> 4) << 24) | ((opcode & 15) << 7) | 0x3010
            self.assertEqual(decode(struct.pack("<I", word), 0).mnemonic, name)
        self.assertEqual(decode(struct.pack("<I", 0x6e003490), 0).mnemonic,
                         "unknown")

    def test_exact_rational_roundtrips_preserve_ac_and_neighbors(self):
        table = ",\n".join("{" + ",".join(f"{x}u" for x in row) + "}"
                             for row in vectors())
        program = [movr(), movr(0, 21, src_fp=True, dst_fp=False),
                   movr(0, 3, src_fp=True),
                   movr(3, 31, src_fp=True, dst_fp=False),
                   movr(21, 17, dst_fp=False), 0xffffffff]
        report = native(program, "static const std::uint32_t rows[][4]={\n" +
                        table + "\n};\n" + COMMON + r"""
int main() {
    Bus bus{};
    const std::uint32_t controls[]={0u,0xff1f917fu,0x801a1155u};
    for(const auto& row:rows)for(auto ac:controls) {
        CPU cpu{};
        if(!kb_establish_arithmetic_controls(cpu,ac))return 1;
        for(unsigned i=0;i<32u;++i)cpu.r[i]=0xabcdef00u+i;
        cpu.r[16]=row[0];
        CPU expected=cpu;
        if(!step(cpu,bus))return 2;
        expected.ip=4u;expected.fp[0]={row[1],row[2],static_cast<std::uint16_t>(row[3])};
        expected.fp_defined[0]=true;
        if(!same_data(cpu,expected))return 3;
        if(!step(cpu,bus))return 4;
        expected.ip=8u;expected.r[21]=row[0];
        if(!same_data(cpu,expected))return 5;
        if(!step(cpu,bus))return 6;
        expected.ip=12u;expected.fp[3]=expected.fp[0];expected.fp_defined[3]=true;
        if(!same_data(cpu,expected))return 7;
        if(!step(cpu,bus))return 8;
        expected.ip=16u;expected.r[31]=row[0];
        if(!same_data(cpu,expected))return 9;
        if(!step(cpu,bus))return 10;
        expected.ip=20u;expected.r[17]=row[0];
        if(!same_data(cpu,expected) || cpu.stop_code!=StopCode::none ||
           cpu.pending_integer_overflow.pending)return 11;
    }
    return 0;
}
""")
        self.assertEqual(report.translated, 5)
        self.assertEqual(report.unsupported, (20,))

    def test_extended_precision_aliases_and_unknown_control_preservation(self):
        native([movr(0, 0, src_fp=True), 0xffffffff], COMMON + r"""
int main() {
    Bus bus{};
    const ExtendedReal values[]={
        {0u,0u,0u},{0u,0u,0x8000u},
        {1u,0x80000001u,1u}, {0xffffffffu,0xffffffffu,0xfffeu},
        {1u,0x80000000u,16383u}
    };
    for(const auto value:values)for(unsigned src=0;src<4u;++src)
    for(unsigned dst=0;dst<4u;++dst) {
        CPU cpu{};cpu.cc_defined=false;
        cpu.arithmetic_controls_other=0x80040000u;
        cpu.arithmetic_controls_other_defined_mask=0x80040000u;
        cpu.fp[src]=value;cpu.fp_defined[src]=true;
        CPU expected=cpu;expected.fp[dst]=value;expected.fp_defined[dst]=true;
        if(!move_real_exact(cpu,src,true,dst,true)||!same_data(cpu,expected))return 1;
    }
    CPU cpu{};cpu.fp[0]={1u,0x80000000u,16383u};cpu.fp_defined[0]=true;
    CPU expected=cpu;expected.ip=4u;
    if(!step(cpu,bus)||!same_data(cpu,expected))return 2;
    for(unsigned src=0;src<32u;++src)for(unsigned dst=0;dst<32u;++dst) {
        cpu={};cpu.r[src]=0xbf800000u;
        expected=cpu;expected.r[dst]=cpu.r[src];
        if(!move_real_exact(cpu,src,false,dst,false)||!same_data(cpu,expected))return 3;
    }
    return 0;
}
""")

    def test_special_inexact_and_undefined_refusal_is_atomic(self):
        native([movr(), movr(0, 21, src_fp=True, dst_fp=False),
                movr(0, 1, src_fp=True), movr(16, 17, dst_fp=False),
                0xffffffff], COMMON + r"""
int main() {
    Bus bus{};
    const std::uint32_t bad32[]={1u,0x007fffffu,0x80000001u,0x807fffffu,
        0x7f800000u,0xff800000u,0x7fc00000u,0x7f800001u,0xffa00000u};
    for(auto bits:bad32)for(auto pc:{0u,12u}) {
        CPU cpu{};cpu.ip=pc;cpu.r[16]=bits;cpu.r[17]=0xbadbeefu;
        cpu.fp[0]={0xfeedu,0xdeadu,0x8000u};cpu.fp_defined[0]=true;
        if(!kb_establish_arithmetic_controls(cpu,0xff1f917fu))return 1;
        const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=StopCode::unsupported_floating_format ||
           cpu.stop_ip!=pc||!same_data(cpu,before))return 2;
    }
    const ExtendedReal bad80[]={
        {1u,0u,0u},{0u,0x80000000u,0u}, // denormal/pseudo-denormal
        {0u,0u,1u},{1u,0x7fffffffu,16383u}, // noncanonical/unnormal
        {0u,0x80000000u,0x7fffu},{1u,0x80000000u,0x7fffu},
        {0u,0xc0000000u,0xffffu}
    };
    for(auto value:bad80)for(auto pc:{4u,8u}) {
        CPU cpu{};cpu.ip=pc;cpu.r[21]=0x12345678u;
        cpu.fp[0]=value;cpu.fp_defined[0]=true;
        cpu.fp[1]={9u,8u,7u};cpu.fp_defined[1]=true;
        const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=StopCode::unsupported_floating_format ||
           cpu.stop_ip!=pc||!same_data(cpu,before))return 3;
    }
    for(auto value:{ExtendedReal{1u,0x80000000u,16383u},
                   ExtendedReal{0u,0x80000001u,16383u},
                   ExtendedReal{0u,0x80000080u,16383u}}) {
        CPU cpu{};cpu.ip=4u;cpu.r[21]=0xbadc0ffeu;
        cpu.fp[0]=value;cpu.fp_defined[0]=true;
        if(!kb_establish_arithmetic_controls(cpu,0xff1f917fu))return 4;
        const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=StopCode::unsupported_floating_rounding ||
           !same_data(cpu,before))return 5;
    }
    for(auto exponent:{1u,16256u,16511u,32766u}) {
        CPU cpu{};cpu.ip=4u;cpu.r[21]=0xbadbeefu;
        cpu.fp[0]={0u,0x80000000u,static_cast<std::uint16_t>(exponent)};
        cpu.fp_defined[0]=true;const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=StopCode::unsupported_floating_format ||
           !same_data(cpu,before))return 6;
    }
    for(auto pc:{4u,8u}) {
        CPU cpu{};cpu.ip=pc;cpu.fp[0]={0u,0x80000000u,16383u};
        const CPU before=cpu;
        if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_floating_point_register ||
           !same_data(cpu,before))return 7;
    }
    CPU cpu{};cpu.fp_defined[0]=true;
    if(!frame_init(cpu,0x100u,4u))return 8;
    const CPU before=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_floating_point_register ||
       !same_data(cpu,before))return 9;
    return 0;
}
""")

    def test_direct_bounds_and_pending_overflow_guard(self):
        native([movr(), 0xffffffff], COMMON + r"""
int main() {
    const unsigned indices[]={4u,31u,32u,0xffffffffu};
    for(auto index:indices)for(bool fp:{false,true}) {
        if(index<(fp?4u:32u))continue;
        CPU cpu{};cpu.ip=0u;cpu.r[16]=0x3f800000u;
        const CPU before=cpu;
        if(move_real_exact(cpu,index,fp,0u,true)||
           cpu.stop_code!=StopCode::untranslated||!same_data(cpu,before))return 1;
        cpu=before;
        if(move_real_exact(cpu,16u,false,index,fp)||
           cpu.stop_code!=StopCode::untranslated||!same_data(cpu,before))return 2;
    }
    CPU cpu{};Bus bus{};cpu.r[16]=0x3f800000u;
    cpu.pending_integer_overflow.pending=true;
    const CPU before=cpu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::integer_overflow_pending ||
       !same_data(cpu,before)||!cpu.pending_integer_overflow.pending)return 3;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
