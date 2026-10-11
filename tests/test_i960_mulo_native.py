"""Native Intel 80960KB MULO tests using synthetic instruction bytes only.

Reference: Intel 80960KB Programmer's Reference Manual, MULO (701h).
GCC and Clang independently compile the generated ahead-of-time C++.
All expected products come from Python's unbounded integer arithmetic.
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


def regop(a=16, b=17, d=18, literal_a=False, literal_b=False):
    # Deliberately synthetic i960 REG MULO encoding, no original ROM bytes.
    return ((0x701 >> 4) << 24 | (0x701 & 15) << 7 |
            a | b << 14 | d << 19 |
            int(literal_a) << 11 | int(literal_b) << 12)


def native(words, harness):
    image = struct.pack('<' + 'I' * len(words), *words)
    cpp, report = emit_cpp(image, 0, 128)
    compilers = [p for n in ('g++', 'clang++') if (p := shutil.which(n))]
    if not compilers:
        raise unittest.SkipTest('No C++17 compiler installed')
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix='arcade-mulo-synthetic-') as folder:
            work = Path(folder)
            source, exe = work / 'test.cpp', work / 'test'
            source.write_text(cpp + '\n' + harness, encoding='utf-8')
            built = subprocess.run(
                [compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                 '-fsanitize=undefined', '-fno-sanitize-recover=all',
                 '-I', str(ROOT / 'runtime'), str(source), '-o', str(exe)],
                capture_output=True, text=True, timeout=40)
            if built.returncode:
                raise AssertionError(compiler + ': ' + built.stderr)
            ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
            if ran.returncode:
                raise AssertionError(
                    f'{compiler}: exit {ran.returncode}: {ran.stdout}{ran.stderr}')
    return report


def vectors():
    edge = [0, 1, 2, 31, 0x7fffffff, 0x80000000,
            0x80000001, 0xfffffffe, 0xffffffff]
    rng = random.Random(0x701960)
    pairs = [(a, b) for a in edge for b in edge]
    pairs += [(rng.getrandbits(32), rng.getrandbits(32))
              for _ in range(512)]
    return pairs


def reference_rows():
    # Six outcomes: source register/register, aliases, and literal forms.
    return ('static const std::uint32_t cases[][6] = {\n' +
            ',\n'.join('{' + ','.join(str(v) + 'u' for v in
                (a, b, (a*b) & 0xffffffff,
                 (31*b) & 0xffffffff, (a*29) & 0xffffffff,
                 (31*29) & 0xffffffff)) + '}'
                for a, b in vectors()) + '\n};\n')


class MuloNativeTests(unittest.TestCase):
    def test_decode_synthetic_mulo(self):
        word = regop(a=19, b=20, d=21)
        inst = decode(struct.pack('<I', word), 0)
        self.assertEqual(inst.mnemonic, 'mulo')
        self.assertEqual(inst.form, 'REG')
        self.assertEqual(inst.operands, ('g3', 'g4', 'g5'))

    def test_native_product_aliases_literals_and_unchanged_controls(self):
        words = [
            regop(),                                  # g0 * g1 -> g2
            regop(d=16),                              # dst aliases first operand
            regop(d=17),                              # dst aliases second operand
            regop(a=31, literal_a=True),              # literal * register
            regop(b=29, literal_b=True),              # register * literal
            regop(a=31, b=29, literal_a=True, literal_b=True),
            0xffffffff
        ]
        harness = reference_rows() + r'''
using namespace arcaderecomp_generated;
int main() {
    Bus bus{}; unsigned checked=0;
    for(const auto& row : cases)
    for(unsigned op=0;op<6;++op)
    for(unsigned control=0;control<8;++control) {
        CPU cpu{}; cpu.ip=op*4u;
        cpu.r[16]=row[0]; cpu.r[17]=row[1]; cpu.r[18]=0xcafef00du;
        cpu.cc=5; cpu.cc_defined=(control&1u)!=0;
        cpu.integer_overflow_mask_defined=(control&2u)!=0;
        cpu.integer_overflow_mask=(control&2u)!=0;
        cpu.integer_overflow_flag_defined=(control&4u)!=0;
        cpu.integer_overflow_flag=(control&4u)!=0;
        std::uint32_t before[32]{};
        for(unsigned i=0;i<32;++i) before[i]=cpu.r[i];
        const unsigned dst=(op==1?16u:op==2?17u:18u);
        const std::uint32_t expected=(op<3?row[2]:
                                     op==3?row[3]:op==4?row[4]:row[5]);
        if(!step(cpu,bus))return 1;
        if(cpu.ip!=(op+1)*4u||cpu.r[dst]!=expected)return 2;
        for(unsigned i=0;i<32;++i)
            if(i!=dst&&cpu.r[i]!=before[i])return 3;
        if(cpu.cc!=5||cpu.cc_defined!=bool(control&1u))return 4;
        if(cpu.integer_overflow_mask_defined!=bool(control&2u)||
           cpu.integer_overflow_mask!=bool(control&2u))return 5;
        if(cpu.integer_overflow_flag_defined!=bool(control&4u)||
           cpu.integer_overflow_flag!=bool(control&4u))return 6;
        if(cpu.pending_integer_overflow.pending||cpu.stop_code!=StopCode::none)
            return 7;
        ++checked;
    }
    return checked==sizeof(cases)/sizeof(cases[0])*6u*8u?0:8;
}
'''
        result = native(words, harness)
        self.assertEqual(result.translated, 6)
        self.assertEqual(result.unsupported, (24,))

    def test_unsupported_special_register_and_destination_modes(self):
        # Existing conservative handling of unimplemented register modes.
        for mask in (0x20, 0x40, 0x2000):
            _, report = emit_cpp(struct.pack(
                '<2I', regop() | mask, 0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)

    def test_result_keeps_low_word_at_unsigned_extremes(self):
        native([regop(d=17), 0xffffffff], r'''
using namespace arcaderecomp_generated;
int main() {
    CPU cpu{};Bus bus{};
    cpu.r[16]=0xffffffffu;cpu.r[17]=0xffffffffu;
    if(!step(cpu,bus)||cpu.r[17]!=1u||cpu.ip!=4u)return 1;
    return 0;
}
''')


if __name__ == '__main__':
    unittest.main()
