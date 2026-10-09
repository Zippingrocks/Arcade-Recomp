"""ROM-free native tests grounded in Intel's 1988 KB manual.

Compiler and UBSan test generated instructions, not just Python decode output.
CXX selects the compiler; unsupported hardware remains an explicit stop.
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


def regop(op, first, second=0, dest=0, literal=False):
    return ((op >> 4) << 24) | ((op & 15) << 7) | first | (second << 14) | (dest << 19) | (0x800 if literal else 0)


def native(words, main):
    compiler = shutil.which(os.environ.get('CXX', 'g++'))
    if not compiler:
        raise unittest.SkipTest('C++17 compiler required')
    image = struct.pack('<'+'I'*len(words), *words)
    source, report = emit_cpp(image, 0, 128)
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root/'test.cpp').write_text(source + '\n#include "model2c_bus.hpp"\n' + main, encoding='utf-8')
        built = subprocess.run([compiler, '-std=c++17', '-O1', '-Wall', '-Wextra',
            '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I', str(ROOT/'runtime'),
            str(root/'test.cpp'), '-o', str(root/'test')], capture_output=True, text=True, timeout=30)
        if built.returncode:
            raise AssertionError(built.stderr)
        run = subprocess.run([str(root/'test')], capture_output=True, text=True, timeout=10)
        if run.returncode:
            raise AssertionError(f'Native exit {run.returncode}\n{run.stdout}{run.stderr}')
    return report

PREAMBLE = '''
using namespace arcaderecomp_generated;
using namespace arcaderecomp_model2c;
int main() {
    CPU cpu{};
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0));
    Bus bus = board.callbacks();
'''


class DataSemanticsTests(unittest.TestCase):
    def test_all_group_widths_and_both_memory_encodings(self):
        for load, store, count in [(0x98, 0x9a, 2), (0xa0, 0xa2, 3), (0xb0, 0xb2, 4)]:
            for mode in ['MEMA', 'MEMB']:
                with self.subTest(width=count, mode=mode):
                    # Base g8 + 4 uses MEMA. Absolute 0x00510004 uses MEMB.
                    # Four-byte but not 8/16-byte aligned, no forced quad alignment.
                    if mode == 'MEMA':
                        mem = lambda op,r: [(op<<24)|(r<<19)|(24<<14)|0x2004]
                    else:
                        mem = lambda op,r: [(op<<24)|(r<<19)|0x3000, 0x00510004]
                    words = mem(store, 16) + mem(load, 20) + [0xffffffff]
                    checks = '\n'.join(f'if (cpu.r[{20+i}] != {0x10203040+i}u) return {10+i};' for i in range(count))
                    report = native(words, PREAMBLE + f'''
    cpu.r[24] = 0x00510000u;
    for (unsigned i=0; i<4; ++i) {{ cpu.r[16+i]=0x10203040u+i; cpu.r[20+i]=0xabcdef00u; }}
    if (!step(cpu,bus) || !step(cpu,bus)) return 1;
    {checks}
    if (cpu.r[20+{count}] != {'0x00510000u' if count==4 else '0xabcdef00u'}) return 2;
    if (board.read(0x00510004u,1)!=0x40u || board.read(0x00510007u,1)!=0x10u) return 3;
    if (board.writes().size() != {count}u) return 4;
    return 0;
}}
''')
                    self.assertEqual(report.translated, 2)

    def test_load_evaluates_aliasing_base_before_destination_changes(self):
        # ldq (g0),g0: overwriting g0 must not change addresses of words 2..4.
        instruction = (0xb0<<24)|(16<<19)|(16<<14)|0x1000
        native([instruction,0xffffffff], PREAMBLE + '''
    cpu.r[16]=0x00510100u;
    for (unsigned i=0;i<4;++i) board.write(0x00510100u+4*i,4,100u+i);
    if (!step(cpu,bus)) return 1;
    for (unsigned i=0;i<4;++i) if (cpu.r[16+i]!=100u+i) return 2;
    return 0;
}
''')

    def test_memb_scaled_index_and_displacement(self):
        # LDL 8(g4)[g5*4],g0 with independent base/index.
        instruction=(0x98<<24)|(16<<19)|(20<<14)|(15<<10)|(2<<7)|21
        native([instruction,8,0xffffffff], PREAMBLE + '''
    cpu.r[20]=0x00510000u; cpu.r[21]=3;
    board.write(0x00510014u,4,0x11223344); board.write(0x00510018u,4,0x55667788);
    if (!step(cpu,bus) || cpu.ip!=8u) return 1;
    if (cpu.r[16]!=0x11223344u || cpu.r[17]!=0x55667788u) return 2;
    return 0;
}
''')

    def test_cross_boundary_store_has_no_partial_ram_write(self):
        instruction=(0xb2<<24)|(16<<19)|0x3000
        native([instruction,0x005ffff8,0xffffffff], PREAMBLE + '''
    cpu.r[16]=1;cpu.r[17]=2;cpu.r[18]=3;cpu.r[19]=4;
    const auto before=board.writes().size();
    if (step(cpu,bus)) return 1;
    if (cpu.stop_code!=StopCode::unsupported_block_transfer || cpu.ip!=0) return 2;
    if (board.read(0x005ffff8u,4)!=0 || board.writes().size()!=before) return 3;
    return 0;
}
''')

    def test_cross_boundary_load_keeps_all_destination_registers(self):
        instruction=(0xb0<<24)|(16<<19)|0x3000
        native([instruction,0x005ffff8,0xffffffff], PREAMBLE + '''
    for(unsigned i=0;i<4;++i) cpu.r[16+i]=0xabc00000u+i;
    if(step(cpu,bus)) return 1;
    for(unsigned i=0;i<4;++i) if(cpu.r[16+i]!=0xabc00000u+i) return 2;
    return 0;
}
''')

    def test_readonly_rom_and_mmio_refused_before_writes(self):
        instruction=(0xb2<<24)|(16<<19)|(20<<14)|0x1000
        native([instruction,0xffffffff], PREAMBLE + '''
    for(auto address : {0u,0x01c00014u,0x00f80000u,0x00e00000u,0x00e80000u,0xfffffffcu}) {
        cpu.ip=0;cpu.r[20]=address;
        if(step(cpu,bus)) return 1;
        if(cpu.stop_code!=StopCode::unsupported_block_transfer) return 2;
        if(!board.writes().empty()) return 3;
    }
    return 0;
}
''')

    def test_unaligned_and_missing_block_bus_refused(self):
        instruction=(0x98<<24)|(16<<19)|(20<<14)|0x1000
        native([instruction,0xffffffff], PREAMBLE + '''
    cpu.r[20]=0x00510001u;cpu.r[16]=123;
    if(step(cpu,bus) || cpu.r[16]!=123u) return 1;
    cpu.r[20]=0x00510000u;Bus no_block{};
    no_block.read32=[](void*,std::uint32_t)->std::uint32_t {return 42u;};
    if(step(cpu,no_block) || cpu.stop_code!=StopCode::missing_bus || cpu.r[16]!=123u) return 2;
    return 0;
}
''')

    def test_multiword_moves_all_widths_preserve_flags(self):
        for op,count in [(0x5dc,2),(0x5ec,3),(0x5fc,4)]:
            with self.subTest(op=op):
                report=native([regop(op,4,dest=20),0xffffffff], PREAMBLE + f'''
    cpu.cc=4;cpu.cc_defined=false;
    for(unsigned i=0;i<4;++i) {{cpu.r[4+i]=100+i;cpu.r[20+i]=999;}}
    if(!step(cpu,bus)) return 1;
    for(unsigned i=0;i<{count};++i) if(cpu.r[20+i]!=100+i) return 2;
    if(cpu.cc!=4 || cpu.cc_defined) return 3;
    return 0;
}}
''')
                self.assertEqual(report.translated,1)

    def test_bad_or_overlapping_group_encodings_are_not_guessed(self):
        for word in [(0x98<<24)|(17<<19)|0x3000, (0xb0<<24)|(30<<19)|0x3000,
                     regop(0x5dc,5,dest=20), regop(0x5fc,16,dest=16),
                     regop(0x5dc,3,dest=20,literal=True)]:
            _,r=emit_cpp(struct.pack('<3I',word,0x00510000,0xffffffff),0,16)
            self.assertIn(0,r.unsupported)

    def test_shifts_against_independent_python_oracle_with_ubsan(self):
        rng=random.Random(0x960)
        values=[0,1,0xffffffff,0xfffffffd,0x80000000,0x7fffffff,0x80000001]
        values += [rng.getrandbits(32) for _ in range(80)]
        counts=list(range(66))+[255,0x7fffffff,0x80000000,0xffffffff]
        for name,op in [('shlo',0x59c),('shro',0x598),('shri',0x59b),('shrdi',0x59a)]:
            vectors=[]
            for value in values:
                signed=value-(1<<32) if value & 0x80000000 else value
                for count in counts:
                    if name=='shlo': result=(value<<count)&0xffffffff if count<32 else 0
                    elif name=='shro': result=value>>count if count<32 else 0
                    elif name=='shri': result=(signed>>min(count,32))&0xffffffff
                    else:
                        mag=abs(signed)>>count if count<32 else 0
                        result=(-mag if signed<0 else mag)&0xffffffff
                    vectors.append(f'{{{value}u,{count}u,{result}u}}')
            body='''
#include <cstdio>
using namespace arcaderecomp_generated;
struct V {std::uint32_t value,count,result;};
static constexpr V vectors[] = {'''+','.join(vectors)+'''};
int main() {CPU cpu{};Bus bus{};
    for (const auto& v:vectors) {
        cpu.ip=0; cpu.r[16]=v.count;cpu.r[17]=v.value;cpu.cc=4;cpu.cc_defined=false;
        if(!step(cpu,bus))return 1;
        if(cpu.r[17]!=v.result){std::printf("value=%x count=%x got=%x expected=%x\\n",v.value,v.count,cpu.r[17],v.result);return 2;}
        if(cpu.cc!=4 || cpu.cc_defined || cpu.ip!=4)return 3;
    }return 0;
}
'''
            with self.subTest(op=name):
                r=native([regop(op,16,17,17),0xffffffff],body)
                self.assertEqual(r.translated,1)

if __name__=='__main__': unittest.main()
