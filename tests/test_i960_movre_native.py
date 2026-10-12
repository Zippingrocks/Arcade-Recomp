"""80960KB MOVRE native transfer validation: genuine 80-bit bit payloads.

Covers GP triple -> FP -> GP triple, FP -> FP, zero padding, high-word
discard, uninitialized FP fail-closed, operand fields, and full CPU state.
All synthetic; no Sega ROM bytes or ROM-derived output.
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


def movre(src, dst, *, src_fp=False, dst_fp=False, literal=False):
    return (0x6e000080 | 0x1000 |
            src | (dst << 19) |
            (0x800 if src_fp else 0) |
            (0x2000 if dst_fp else 0) |
            (0x800 if literal else 0))


def run_native(words, harness):
    image = struct.pack("<" + "I"*len(words), *words)
    cpp, report = emit_cpp(image, 0, 128)
    compilers = [p for n in ("g++", "clang++") if (p := shutil.which(n))]
    if not compilers:
        raise unittest.SkipTest("No GCC or Clang compiler found")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcaderecomp-movre-") as tmp:
            source = Path(tmp)/"test.cpp"
            binary = Path(tmp)/"test"
            source.write_text(cpp + "\n" + harness, encoding="utf-8")
            compiled = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT/"runtime"), str(source), "-o", str(binary)],
                capture_output=True, text=True, timeout=45)
            if compiled.returncode:
                raise AssertionError(compiler+": "+compiled.stderr)
            executed = subprocess.run([str(binary)], capture_output=True,
                                      text=True, timeout=25)
            if executed.returncode:
                raise AssertionError(f"{compiler}: exit {executed.returncode}: "
                                     + executed.stdout + executed.stderr)
    return report


class MovreNativeTests(unittest.TestCase):
    def test_decode_and_reserved_modes_fail_closed(self):
        a = decode(struct.pack("<I", movre(16, 1, dst_fp=True)), 0)
        self.assertEqual((a.mnemonic, a.operands), ("movre", ("g0", "fp1")))
        b = decode(struct.pack("<I", movre(1, 20, src_fp=True)), 0)
        self.assertEqual((b.mnemonic, b.operands), ("movre", ("fp1", "g4")))
        for bad in (
            movre(16, 0),                         # no FP operand
            movre(17, 0, dst_fp=True),            # GP source misaligned
            movre(0, 21, src_fp=True),            # GP dest misaligned
            movre(4, 20, src_fp=True),            # invalid FP source
            movre(16, 4, dst_fp=True),            # invalid FP destination
            movre(16, 1, dst_fp=True, literal=True),
            movre(16, 1, dst_fp=True) | 0x40,    # reserved bit 6
            movre(16, 1, dst_fp=True) | (1 << 14), # unused src2
            movre(16, 1, dst_fp=True) & ~0x1000, # unused M2 marker
        ):
            _, report = emit_cpp(struct.pack("<2I", bad, 0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)

    def test_native_bit_exact_fp_roundtrips_and_unknown_sources(self):
        operations = [
            movre(16, 0, dst_fp=True),       # GP triple g0-g2 to fp0
            movre(0, 20, src_fp=True),       # fp0 to g4-g6
            movre(0, 1, src_fp=True, dst_fp=True),  # fp0 -> fp1
            movre(1, 24, src_fp=True),       # fp1 to g8-g10
            movre(0, 28, src_fp=True),       # fp0 to g12-g14
            0xffffffff,
        ]
        vectors = [0, 1, 0xffffffff, 0x80000000, 0x7fffffff,
                   0xaaaaaaaa, 0x55555555, 0x12345678, 0xfedcba98]
        rng = random.Random(0x6e1960)
        triple_rows = [(x, y, z) for x in vectors for y in vectors
                       for z in (0, 0xffffffff)]
        triple_rows += [(rng.getrandbits(32), rng.getrandbits(32),
                         rng.getrandbits(32)) for _ in range(256)]
        table = ",\n".join("{"+",".join(str(n)+"u" for n in row)+"}"
                           for row in triple_rows)
        harness = (f"static const std::uint32_t vectors[][3] = {{\n"
                   f"{table}\n}};\n") + r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{}; unsigned cases=0u;
    for(const auto& row: vectors)
    for(unsigned cc=0;cc<8u;++cc) {
        CPU cpu{};
        cpu.r[16]=row[0]; cpu.r[17]=row[1]; cpu.r[18]=row[2];
        cpu.cc=static_cast<int>(cc);
        cpu.cc_defined=(cc & 1u)!=0u;
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        if (cpu.fp_defined[0]||cpu.fp_defined[1])return 1;
        // Fail closed for unknown fp0, preserving every GPR and IP.
        cpu.ip=4u;
        if (step(cpu,bus) ||
            cpu.stop_code!=StopCode::undefined_floating_point_register ||
            cpu.ip!=4u || cpu.r[20]!=0u) return 2;
        cpu.stop_code=StopCode::none;
        cpu.ip=0u;
        if (!step(cpu,bus)||cpu.ip!=4u||!cpu.fp_defined[0])return 3;
        if (cpu.fp[0].low!=row[0]||
            cpu.fp[0].middle!=row[1]||
            cpu.fp[0].high!=static_cast<std::uint16_t>(row[2]))return 4;
        if (!step(cpu,bus)||cpu.ip!=8u||
            cpu.r[20]!=row[0]||cpu.r[21]!=row[1]||
            cpu.r[22]!=(row[2]&0xffffu))return 5;
        if (!step(cpu,bus)||cpu.ip!=12u||!cpu.fp_defined[1]||
            cpu.fp[1].low!=row[0]||cpu.fp[1].middle!=row[1]||
            cpu.fp[1].high!=static_cast<std::uint16_t>(row[2]))return 6;
        if (!step(cpu,bus)||cpu.ip!=16u||
            cpu.r[24]!=row[0]||cpu.r[25]!=row[1]||
            cpu.r[26]!=(row[2]&0xffffu))return 7;
        if (!step(cpu,bus)||cpu.ip!=20u||
            cpu.r[28]!=row[0]||cpu.r[29]!=row[1]||
            cpu.r[30]!=(row[2]&0xffffu))return 8;
        if (cpu.cc!=static_cast<int>(cc) ||
            cpu.cc_defined!=bool(cc&1u) ||
            !cpu.integer_overflow_mask_defined ||
            !cpu.integer_overflow_mask ||
            !cpu.integer_overflow_flag_defined ||
            !cpu.integer_overflow_flag ||
            cpu.pending_integer_overflow.pending ||
            cpu.stop_code!=StopCode::none)return 9;
        if (cpu.r[16]!=row[0]||cpu.r[17]!=row[1]||
            cpu.r[18]!=row[2]||cpu.r[19]!=0u)return 10;
        ++cases;
    }
    return cases>1000u?0:11;
}
""";
        result = run_native(operations, harness)
        self.assertEqual(result.translated, 5)
        self.assertEqual(result.unsupported, (20,))

    def test_reset_marks_fp_state_unknown(self):
        run_native([movre(0, 1, src_fp=True, dst_fp=True), 0xffffffff], r"""
using namespace arcaderecomp_generated;
int main() {
    CPU cpu{};Bus bus{};
    cpu.fp_defined[0]=true;
    cpu.fp[0].low=123u;
    if(!frame_init(cpu,0x100u,0u)||cpu.fp_defined[0])return 1;
    if(step(cpu,bus) ||
       cpu.stop_code!=StopCode::undefined_floating_point_register)return 2;
    return 0;
}
""")


if __name__=="__main__":
    unittest.main()
