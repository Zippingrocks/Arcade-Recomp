"""Original Intel KB signed-add/subtract tests. All instruction bytes are synthetic.

Oracle: Python unbounded signed arithmetic, independent of the unsigned C++
overflow detection. Native programs run under GCC/Clang and UBSan when installed.
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


def regop(op, a=16, b=17, d=18, la=False, lb=False):
    return (op >> 4) << 24 | (op & 15) << 7 | a | b << 14 | d << 19 | int(la) << 11 | int(lb) << 12


def native(words, body, both=True):
    image = struct.pack('<' + 'I' * len(words), *words)
    code, report = emit_cpp(image, 0, 512)
    compilers = [p for name in ('g++', 'clang++') if (p := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest('C++17 compiler missing')
    for cxx in compilers if both else compilers[:1]:
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            source, exe = work/'case.cpp', work/'case'
            source.write_text(code + '\n#include <initializer_list>\nusing namespace arcaderecomp_generated;\n[[maybe_unused]] static auto const test_step = &step;\n' + body, encoding='utf-8')
            p = subprocess.run([cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I', str(ROOT/'runtime'),
                str(source), '-o', str(exe)], capture_output=True, text=True, timeout=35)
            if p.returncode:
                raise AssertionError(cxx + ': ' + p.stderr)
            p = subprocess.run([str(exe)], capture_output=True, text=True, timeout=15)
            if p.returncode:
                raise AssertionError(f'{cxx}: native exit {p.returncode}: {p.stdout}{p.stderr}')
    return report


def pairs():
    edge = [0, 1, 2, 0x7fffffff, 0x80000000, 0x80000001, 0xfffffffe, 0xffffffff]
    rng = random.Random(0x591593)
    return [(a, b) for a in edge for b in edge] + [(rng.getrandbits(32), rng.getrandbits(32)) for _ in range(512)]


def oracle_rows():
    rows = []
    for a, b in pairs():
        sa, sb = (a if a < 2**31 else a-2**32), (b if b < 2**31 else b-2**32)
        total, diff = sb+sa, sb-sa
        rows.append('{' + ','.join(str(x)+'u' for x in
            (a, b, total & 0xffffffff, diff & 0xffffffff,
             int(not -2**31 <= total < 2**31), int(not -2**31 <= diff < 2**31))) + '}')
    return 'static const std::uint32_t rows[][6] = {' + ','.join(rows) + '};\n'


class SignedArithmeticTests(unittest.TestCase):
    def test_all_controls_and_compare_states_against_unbounded_oracle(self):
        report = native([regop(0x591), regop(0x593), 0xffffffff], oracle_rows() + r'''
int main() {
    unsigned checked=0; Bus bus{};
    for (const auto& row:rows) for(unsigned op=0;op<2;++op)
    for(unsigned state=0;state<16;++state) for(bool cc_known:{false,true}) {
        CPU cpu{};cpu.ip=op*4;cpu.r[16]=row[0];cpu.r[17]=row[1];cpu.r[18]=0xdeadbeefu;
        cpu.integer_overflow_mask_defined=state&1;cpu.integer_overflow_mask=state&2;
        cpu.integer_overflow_flag_defined=state&4;cpu.integer_overflow_flag=state&8;
        cpu.cc=5;cpu.cc_defined=cc_known;
        const bool overflow=row[4+op]!=0;
        const bool unknown=overflow && !(state&1);
        const bool trap=overflow && (state&1) && !(state&2);
        const bool masked=overflow && (state&1) && (state&2);
        bool ok=step(cpu,bus);
        if(ok != (!unknown && !trap))return 1;
        if(cpu.r[18] != (unknown?0xdeadbeefu:row[2+op]))return 2;
        if(cpu.integer_overflow_flag != (masked?true:bool(state&8)))return 3;
        if(cpu.integer_overflow_flag_defined != (masked?true:bool(state&4)))return 4;
        if(cpu.integer_overflow_mask_defined!=bool(state&1)||cpu.integer_overflow_mask!=bool(state&2))return 5;
        if(cpu.cc!=5||cpu.cc_defined!=cc_known)return 6;
        if(cpu.ip != op*4+(ok?4:0))return 7;
        if(unknown && cpu.stop_code!=StopCode::undefined_integer_controls)return 8;
        if(cpu.pending_integer_overflow.pending!=trap)return 9;
        if(trap && (cpu.stop_code!=StopCode::integer_overflow_pending ||
            cpu.pending_integer_overflow.instruction_ip!=op*4 ||
            cpu.pending_integer_overflow.resume_ip!=op*4+4 ||cpu.stop_ip!=op*4))return 10;
        if(cpu.r[16]!=row[0]||cpu.r[17]!=row[1])return 11;
        ++checked;
    }
    return checked==36864u?0:12;
}
''')
        self.assertEqual(report.translated, 2)

    def test_both_sources_can_alias_destination(self):
        words = [regop(op, d=dst) for op in (0x591,0x593) for dst in (16,17)] + [0xffffffff]
        native(words, oracle_rows()+r'''
int main(){Bus bus{};
for(const auto& row:rows) { for(unsigned op=0;op<2;++op) { for(unsigned alias=0;alias<2;++alias) {
 CPU cpu{};cpu.ip=op*8+alias*4;cpu.r[16]=row[0];cpu.r[17]=row[1];
 establish_integer_controls(cpu,0x1000u);
 if(!step(cpu,bus)||cpu.r[16+alias]!=row[2+op])return 1;
 if(cpu.r[17-alias]!=row[1-alias])return 2;
}}}
return 0;}
''')

    def test_literal_operands_in_both_slots(self):
        words=[]
        for op in (0x591,0x593):
            for a in range(32):
                words.append(regop(op,a=a,b=31-a,la=True,lb=True))
        report=native(words+[0xffffffff], r'''
int main(){CPU cpu{};Bus bus{};
for(unsigned op=0;op<2;++op) { for(unsigned a=0;a<32;++a) {
 const std::uint32_t expected=op?(31u-a)-a:31u;
 if(!step(cpu,bus)||cpu.r[18]!=expected)return 1;
 if(cpu.integer_overflow_mask_defined||cpu.integer_overflow_flag_defined)return 2;
}}
return 0;}
''')
        self.assertEqual(report.translated,64)

    def test_unmasked_fault_writes_result_and_cannot_be_reexecuted(self):
        native([regop(0x591,d=17),regop(0x5cc,a=3,d=20,la=True),0xffffffff],r'''
int main(){CPU cpu{};Bus bus{};establish_integer_controls(cpu,0);
 cpu.r[16]=1;cpu.r[17]=0x7fffffffu;
 if(step(cpu,bus)||cpu.r[17]!=0x80000000u||cpu.integer_overflow_flag)return 1;
 if(!cpu.pending_integer_overflow.pending||cpu.pending_integer_overflow.resume_ip!=4)return 2;
 for(unsigned i=0;i<10;++i)if(step(cpu,bus)||cpu.r[17]!=0x80000000u)return 3;
 // Even a caller moving IP must not silently run the following MOV.
 cpu.ip=4;establish_integer_controls(cpu,0x1000u);
 if(step(cpu,bus)||cpu.r[20]!=0||cpu.stop_ip!=0)return 4;
 return 0;}
''')

    def test_masked_flag_is_sticky_and_compare_flags_untouched(self):
        native([regop(0x591),regop(0x593),0xffffffff],r'''
int main(){CPU cpu{};Bus bus{};establish_integer_controls(cpu,0x1000u);
 cpu.r[16]=1;cpu.r[17]=0x7fffffffu;cpu.cc=4;cpu.cc_defined=false;
 if(!step(cpu,bus)||!cpu.integer_overflow_flag||!cpu.integer_overflow_flag_defined)return 1;
 cpu.r[16]=1;cpu.r[17]=10;
 if(!step(cpu,bus)||cpu.r[18]!=9||!cpu.integer_overflow_flag)return 2;
 if(cpu.cc!=4||cpu.cc_defined)return 3;
 establish_integer_controls(cpu,0x1000u);if(cpu.integer_overflow_flag)return 4;
 return 0;}
''')

    def test_unknown_mask_does_not_guess_or_mutate_result(self):
        native([regop(0x593),0xffffffff],r'''
int main(){CPU cpu{};Bus bus{};cpu.r[16]=1;cpu.r[17]=0x80000000u;cpu.r[18]=99;
 if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_integer_controls||cpu.r[18]!=99)return 1;
 if(cpu.pending_integer_overflow.pending||cpu.integer_overflow_flag_defined)return 2;
 // Establishing the mask explicitly permits reevaluation after this diagnostic.
 establish_integer_controls(cpu,0x1000u);
 if(!step(cpu,bus)||cpu.r[18]!=0x7fffffffu||!cpu.integer_overflow_flag)return 3;
 return 0;}
''')

    def test_reset_discards_control_knowledge_and_pending_handoff(self):
        native([regop(0x591),0xffffffff],r'''
int main(){CPU cpu{};establish_integer_controls(cpu,0x1100u);
 cpu.pending_integer_overflow={true,100,104};
 if(!frame_init(cpu,0x1000,0))return 1;
 if(cpu.integer_overflow_mask_defined||cpu.integer_overflow_flag_defined||cpu.pending_integer_overflow.pending)return 2;
 return 0;}
''')

    def test_successful_iac_reinitialize_invalidates_control_bits(self):
        native([regop(0x591),0xffffffff],r'''
#include "i960_reinitialize.hpp"
int main(){CPU cpu{};Bus bus{};establish_integer_controls(cpu,0x1100u);
 cpu.pending_integer_overflow={true,100,104};cpu.pending_iac_valid=true;
 cpu.pending_iac[0]=0x93000000u;cpu.pending_iac[1]=0;cpu.pending_iac[2]=0x2000;cpu.pending_iac[3]=0;
 bus.read32=[](void*,std::uint32_t a)->std::uint32_t {
   switch(a){case 0x2004:return 12;case 0x2014:return 0x3000;case 0x2018:return 0x4000;
    case 0x2020:return 0x1ff;case 0x2024:return 0x27f;case 0x2028:return 0x210;case 0x202c:return 0;}
   throw 1;
 };
 if(!perform_iac_93_reinitialize(cpu,bus))return 1;
 if(cpu.integer_overflow_mask_defined||cpu.integer_overflow_flag_defined||cpu.pending_integer_overflow.pending)return 2;
 return 0;}
''')

    def test_invalid_iac_does_not_clear_existing_control_or_fault_state(self):
        native([regop(0x591),0xffffffff],r'''
#include "i960_reinitialize.hpp"
int main(){CPU cpu{};Bus bus{};establish_integer_controls(cpu,0x1100u);
 cpu.pending_integer_overflow={true,100,104};
 if(perform_iac_93_reinitialize(cpu,bus))return 1;
 if(!cpu.integer_overflow_mask_defined||!cpu.integer_overflow_flag_defined||!cpu.pending_integer_overflow.pending)return 2;
 return 0;}
''')

    def test_special_register_encodings_remain_unsupported(self):
        for mask in (0x20,0x40,0x2000):
            for op in (0x591,0x593):
                _,report=emit_cpp(struct.pack('<2I',regop(op)|mask,0xffffffff),0,8)
                self.assertIn(0,report.unsupported)

    def test_direct_helper_rejects_invalid_dest_and_next_ip(self):
        native([regop(0x591),0xffffffff],r'''
int main(){CPU cpu{};cpu.r[18]=42;
 if(integer_add_sub(cpu,1,2,32,4,false))return 1;
 if(integer_add_sub(cpu,1,2,18,3,false))return 2;
 if(cpu.r[18]!=42||cpu.pending_integer_overflow.pending)return 3;
 return 0;}
''')

if __name__=='__main__':unittest.main()
