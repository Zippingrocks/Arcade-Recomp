"""Independent cross-compiler i960 shift regression oracle; synthetic words only.

Independent oracle: Intel 270567-001 (1988), printed pp. 3-3, 5-6,
11-67, 11-85, 11-110 and 11-117. Original game data never enters CI.
"""
from pathlib import Path
import os
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def regop(op, a, b=0, d=0, literal=False, literal_b=False):
    return ((op >> 4) << 24 | (op & 15) << 7 | a | b << 14 | d << 19
            | int(literal) << 11 | int(literal_b) << 12)


def memop(op, reg, base=16, offset=None):
    mode = (4 << 10) if offset is None else ((1 << 13) | offset)
    return (op << 24) | (reg << 19) | (base << 14) | mode


def native(words, body, entries=(), compiler=None, sanitize=False):
    compiler = compiler or os.environ.get('ARCADERECOMP_TEST_CXX') or shutil.which('g++') or shutil.which('clang++')
    if not compiler:
        raise unittest.SkipTest('C++17 compiler missing')
    image = struct.pack('<' + 'I' * len(words), *words)
    source, report = emit_cpp(image, 0, 256, additional_entries=entries)
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        cpp, exe = directory/'case.cpp', directory/('case.exe' if os.name == 'nt' else 'case')
        cpp.write_text(source + '\n#include "model2c_bus.hpp"\n'
                       + '#include <array>\nusing namespace arcaderecomp_generated;\n'
                       + 'using namespace arcaderecomp_model2c;\n' + body, encoding='utf-8')
        flags = ['-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror']
        if sanitize:
            flags += ['-fsanitize=undefined', '-fno-sanitize-recover=all']
        built = subprocess.run([compiler, *flags, '-I', str(ROOT/'runtime'), str(cpp), '-o', str(exe)],
                               capture_output=True, text=True, timeout=40)
        if built.returncode:
            raise AssertionError(built.stderr)
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
        if run.returncode:
            raise AssertionError(f'Native exit {run.returncode}: {run.stdout}{run.stderr}')
    return report


class KBCrossCompilerShiftTests(unittest.TestCase):
    def test_four_shifts_against_wide_integer_oracle(self):
        rng=random.Random(0x960)
        values=[0,1,2,3,0x7fffffff,0x80000000,0xfffffffd,0xffffffff]+[rng.getrandbits(32) for _ in range(40)]
        counts=list(range(0,66))+[127,255,0x7fffffff,0x80000000,0xffffffff]
        rows=[]
        for value in values:
            signed=value if value < 0x80000000 else value-0x100000000
            for count in counts:
                shlo=(value<<count)&0xffffffff if count<32 else 0
                shro=value>>count if count<32 else 0
                shri=(signed>>count)&0xffffffff if count<32 else (0xffffffff if signed<0 else 0)
                shrdi=((abs(signed)>>count)*(-1 if signed<0 else 1))&0xffffffff if count<32 else 0
                rows.append('{'+','.join(f'0x{x:08x}u' for x in (count,value,shlo,shro,shri,shrdi))+'}')
        cases=','.join(rows)
        words=[regop(op,16,17,18) for op in [0x59c,0x598,0x59b,0x59a]]+[0xffffffff]
        body='''
static const std::uint32_t cases[][6]={'''+cases+'''};
int main(){CPU cpu{};Bus bus{};
for(const auto& row:cases) {
for(unsigned op=0;op<4;++op){
    cpu.ip=4u*op;cpu.r[16]=row[0];cpu.r[17]=row[1];cpu.cc=5;cpu.cc_defined=false;
    if(!step(cpu,bus)||cpu.r[18]!=row[2+op]||cpu.cc!=5||cpu.cc_defined) return 1;
}
}
return 0;}
'''
        compilers=[x for x in (shutil.which('g++'),shutil.which('clang++')) if x]
        if not compilers: self.skipTest('C++ compiler missing')
        for compiler in compilers:
            with self.subTest(compiler=compiler):
                report=native(words,body,compiler=compiler,sanitize=True)
                self.assertEqual(report.translated,4)

    def test_literal_counts_and_destination_aliases(self):
        words=[regop(0x59b,1,16,16,literal=True),regop(0x59a,1,17,17,literal=True),
               regop(0x59c,18,19,18),regop(0x598,18,19,19),0xffffffff]
        native(words,r'''
int main(){CPU cpu{};Bus bus{};cpu.r[16]=0xfffffffdu;cpu.r[17]=0xfffffffdu;
if(!step(cpu,bus)||cpu.r[16]!=0xfffffffeu) return 1;
if(!step(cpu,bus)||cpu.r[17]!=0xffffffffu) return 2;
cpu.r[18]=32;cpu.r[19]=0x80000001u;
if(!step(cpu,bus)||cpu.r[18]!=0) return 3;
cpu.r[18]=32;
if(!step(cpu,bus)||cpu.r[19]!=0) return 4;
return 0;}
''',sanitize=True)


if __name__ == '__main__':
    unittest.main()
