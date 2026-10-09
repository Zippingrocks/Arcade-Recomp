"""Intel-manual-derived synthetic native conformance vectors; no ROM bytes."""
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def regop(op, src=16, src2=17, dst=18, literal=False):
    return ((op >> 4) << 24) | (dst << 19) | (src2 << 14) | ((op & 15) << 7) | (0x800 if literal else 0) | src


def memb(op, dst, base=16):
    return (op << 24) | (dst << 19) | (base << 14) | (4 << 10)


def run_native(words, harness, roots=(), sanitize=False):
    compiler = shutil.which('g++') or shutil.which('clang++')
    if compiler is None:
        raise unittest.SkipTest('Host C++17 compiler required')
    image = struct.pack('<'+'I'*len(words), *words)
    source, report = emit_cpp(image, 0, 256, additional_entries=roots)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d); cpp = d/'test.cpp'; binary = d/'test'
        cpp.write_text(source + '\n' + harness, encoding='utf-8')
        args = [compiler, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-I', str(ROOT/'runtime'), str(cpp), '-o', str(binary)]
        if sanitize: args += ['-fsanitize=undefined', '-fno-sanitize-recover=undefined']
        compiled = subprocess.run(args, capture_output=True, text=True, timeout=45)
        if compiled.returncode: raise AssertionError(compiled.stderr)
        executed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
        if executed.returncode: raise AssertionError(f'Native exit {executed.returncode}: {executed.stdout}{executed.stderr}')
    return report


MEMORY = r'''
#include <array>
#include <stdexcept>
#include <vector>
using namespace arcaderecomp_generated;
struct RAM {
    std::array<std::uint32_t, 16> data{};
    std::vector<std::uint32_t> reads, writes;
    std::uint32_t fail = 0xffffffffu;
};
std::uint32_t rd(void* p, std::uint32_t a) {
    auto& m = *static_cast<RAM*>(p);
    if (a==m.fail || a<0x1000u || a>=0x1040u || a%4u) throw std::out_of_range("bus");
    m.reads.push_back(a); return m.data[(a-0x1000u)/4u];
}
void wr(void* p, std::uint32_t a, std::uint32_t v) {
    auto& m = *static_cast<RAM*>(p);
    if (a==m.fail || a<0x1000u || a>=0x1040u || a%4u) throw std::out_of_range("bus");
    m.writes.push_back(a); m.data[(a-0x1000u)/4u]=v;
}
'''


class TransferAndShiftTests(unittest.TestCase):
    def test_all_four_shifts_against_python_vectors_with_ubsan(self):
        rng = random.Random(80960)
        vals = [0,1,2,3,0x7fffffff,0x80000000,0x80000001,0xfffffffd,0xffffffff]
        counts = [0,1,2,15,30,31,32,33,63,64,0x80000000,0xffffffff]
        pairs = [(v,c) for v in vals for c in counts]
        pairs += [(rng.getrandbits(32),rng.choice(counts)) for _ in range(256)]
        words = [0xffffffff]*16
        cases=[]
        for n, op in enumerate([0x59c,0x598,0x59b,0x59a]):
            words[n*4] = regop(op, dst=17) # dst aliases the source value
            for v,c in pairs:
                signed = v if v<0x80000000 else v-0x100000000
                if n==0: expected=(v<<c)&0xffffffff if c<32 else 0
                elif n==1: expected=v>>c if c<32 else 0
                elif n==2: expected=(signed>>c)&0xffffffff if c<32 else (0xffffffff if signed<0 else 0)
                else: expected=(((-1 if signed<0 else 1)*(abs(signed)>>c))&0xffffffff) if c<32 else 0
                cases.append(f'{{{n*16}u,{c}u,{v}u,{expected}u}}')
        harness = r'''
#include <cstdint>
#include <iostream>
using namespace arcaderecomp_generated;
struct Case { std::uint32_t ip,count,value,result; };
static const Case cases[]={''' + ','.join(cases) + r'''};
int main(){
    CPU cpu{}; Bus bus{};
    for(const auto& c: cases){
        cpu.ip=c.ip;cpu.r[16]=c.count;cpu.r[17]=c.value;cpu.cc=5;cpu.cc_defined=true;
        if(!step(cpu,bus)||cpu.r[17]!=c.result||cpu.ip!=c.ip+4||cpu.cc!=5||!cpu.cc_defined){
            std::cerr<<c.ip<<" count="<<c.count<<" value="<<c.value<<" got="<<cpu.r[17]<<" expected="<<c.result;return 1;
        }
    }return 0;
}'''
        report=run_native(words,harness,(16,32,48),sanitize=True)
        self.assertEqual(report.translated,4)

    def test_loads_and_stores_all_group_sizes_and_address_forms(self):
        for count,ld,st in [(2,0x98,0x9a),(3,0xa0,0xa2),(4,0xb0,0xb2)]:
            for mode in ['memb','mema']:
                with self.subTest(count=count,mode=mode):
                    load=memb(ld,4);store=memb(st,4,17)
                    if mode=='mema':
                        load=(ld<<24)|(4<<19)|(16<<14)|(1<<13)|4
                        store=(st<<24)|(4<<19)|(17<<14)|(1<<13)|4
                    offset=4 if mode=='mema' else 0
                    body=MEMORY+f'''
int main() {{
    CPU cpu{{}}; RAM memory{{}}; Bus bus{{&memory,&rd,&wr}};
    for(unsigned i=0;i<16;++i)memory.data[i]=0xaabb0000u+i;
    cpu.r[16]=0x1004u;cpu.r[17]=0x1024u;cpu.cc=4;
    if(!step(cpu,bus))return 1;
    for(unsigned n=0;n<{count};++n)if(cpu.r[4+n]!=0xaabb0000u+1u+{offset//4}+n)return 2;
    if(!step(cpu,bus))return 3;
    for(unsigned n=0;n<{count};++n)if(memory.data[9+{offset//4}+n]!=cpu.r[4+n])return 4;
    if(memory.reads.size()!={count}||memory.writes.size()!={count}||cpu.cc!=4)return 5;
    return 0;
}}'''
                    self.assertEqual(run_native([load,store,0xffffffff],body).translated,2)

    def test_load_base_and_index_alias_are_evaluated_before_destinations(self):
        # LDQ (g0)[g1*4],g0: both base AND index belong to overwritten group.
        load=(0xb0<<24)|(16<<19)|(16<<14)|(7<<10)|(2<<7)|17
        body=MEMORY+r'''
int main(){CPU cpu{};RAM memory{};Bus bus{&memory,&rd,&wr};
 for(unsigned i=0;i<16;++i)memory.data[i]=0x87650000u+i;
 cpu.r[16]=0x1000u;cpu.r[17]=1u;
 if(!step(cpu,bus))return 1;
 for(unsigned n=0;n<4;++n)if(cpu.r[16+n]!=0x87650001u+n)return 2;
 if(memory.reads!=std::vector<std::uint32_t>({0x1004,0x1008,0x100c,0x1010}))return 3;
 return 0;}'''
        self.assertEqual(run_native([load,0xffffffff],body).translated,1)

    def test_multiword_move_literal_and_separate_register_banks(self):
        for count,op in [(2,0x5dc),(3,0x5ec),(4,0x5fc)]:
            with self.subTest(count=count):
                words=[regop(op,src=4,src2=0,dst=20),regop(op,src=31,src2=0,dst=8,literal=True),0xffffffff]
                body=f'''
using namespace arcaderecomp_generated;
int main(){{CPU cpu{{}};Bus bus{{}};
 for(unsigned n=0;n<4;++n){{cpu.r[4+n]=0xaaab0000u+n;cpu.r[8+n]=~0u;}}
 if(!step(cpu,bus))return 1;
 for(unsigned n=0;n<{count};++n)if(cpu.r[20+n]!=cpu.r[4+n])return 2;
 if(!step(cpu,bus)||cpu.r[8]!=31)return 3;
 for(unsigned n=1;n<{count};++n)if(cpu.r[8+n]!=0)return 4;
 return 0;}}'''
                self.assertEqual(run_native(words,body).translated,2)

    def test_unpredictable_register_groups_stop_without_bus_access(self):
        cases=[memb(0x98,5),memb(0xb0,6),memb(0xa0,14),regop(0x5dc,src=4,dst=4,src2=0),regop(0x5fc,src=4,dst=6,src2=0)]
        for word in cases:
            with self.subTest(word=hex(word)):
                body=MEMORY+r'''
int main(){CPU cpu{};RAM memory{};Bus bus{&memory,&rd,&wr};cpu.r[16]=0x1000u;
 if(step(cpu,bus)||cpu.ip!=0||!memory.reads.empty()||!memory.writes.empty())return 1;
 return 0;}'''
                self.assertEqual(run_native([word,0xffffffff],body).translated,0)

    def test_missing_bus_and_faults_not_silently_skipped(self):
        body=MEMORY+r'''
int main(){CPU cpu{};Bus bus{};cpu.r[16]=0x1000u;cpu.r[4]=0xfeedu;
 if(step(cpu,bus)||cpu.stop_code!=StopCode::missing_bus)return 1;
 RAM memory{};memory.fail=0x1008u;bus={&memory,&rd,&wr};
 try{step(cpu,bus);return 2;}catch(const std::out_of_range&){}
 if(cpu.ip!=0||cpu.r[4]!=0xfeedu)return 3;
 return 0;}'''
        run_native([memb(0xb0,4),0xffffffff],body)
        body=MEMORY+r'''
int main(){CPU cpu{};RAM memory{};Bus bus{&memory,&rd,&wr};
 cpu.r[16]=0x1000;cpu.r[4]=1;cpu.r[5]=2;cpu.r[6]=3;cpu.r[7]=4;memory.fail=0x1008;
 try{step(cpu,bus);return 1;}catch(const std::out_of_range&){}
 if(cpu.ip!=0||memory.writes.size()!=2||memory.data[0]!=1||memory.data[1]!=2)return 2;
 return 0;}'''
        run_native([memb(0xb2,4),0xffffffff],body)

    def test_strict_bus_does_not_turn_multitransfers_into_peripheral_ram(self):
        body=r'''
#include "model2c_bus.hpp"
using namespace arcaderecomp_generated;
using namespace arcaderecomp_model2c;
int main(){StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0));
 CPU cpu{};Bus bus=board.callbacks();cpu.r[16]=0x00f80000;
 try{step(cpu,bus);return 1;}catch(const DeviceAccessFault&){}
 if(cpu.ip!=0||!board.writes().empty())return 2;
 return 0;}'''
        run_native([memb(0xb2,4),0xffffffff],body)


if __name__=='__main__': unittest.main()
