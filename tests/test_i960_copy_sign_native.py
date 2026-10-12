"""Synthetic Intel KB CPYSRE/CPYRSRE native normal-extended tests."""
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


def opcode(a=0,b=1,d=2,af=True,bf=True,df=True,reverse=False):
    return (0x6e000100 | (0x80 if reverse else 0) | a | (b<<14) | (d<<19) |
            (0x20 if af else 0) | (0x40 if bf else 0) | (0x2000 if df else 0))


def native(words,body):
    cpp,report=emit_cpp(struct.pack("<"+"I"*len(words),*words),0,128)
    compilers=[p for n in ("g++","clang++") if (p:=shutil.which(n))]
    if not compilers: raise unittest.SkipTest("C++17 compiler required")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-copy-sign-") as tmp:
            src,exe=Path(tmp)/"test.cpp",Path(tmp)/"test"
            src.write_text(cpp+"\n"+body)
            result=subprocess.run([compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                "-fsanitize=undefined","-fno-sanitize-recover=all","-I",str(ROOT/"runtime"),
                str(src),"-o",str(exe)],capture_output=True,text=True,timeout=50)
            if result.returncode: raise AssertionError(compiler+": "+result.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
            if result.returncode: raise AssertionError(compiler+" exit "+str(result.returncode)+": "+result.stderr)
    return report


class CopySignNativeTests(unittest.TestCase):
    def test_decoder_order_modes_and_alignment_refusal(self):
        self.assertEqual(decode(struct.pack("<I",opcode()),0).operands,("fp0","fp1","fp2"))
        self.assertEqual(decode(struct.pack("<I",opcode(16,1,24,False,True,False,True)),0).mnemonic,"cpyrsre")
        self.assertEqual(decode(struct.pack("<I",opcode(16,1,24,False,True,False)),0).operands,("g0","fp1","g8"))
        bad=[opcode()|0x800,opcode()|0x1000,opcode(a=4),opcode(b=4),opcode(d=4),
             opcode(17,1,2,False),opcode(0,21,2,True,False),opcode(0,1,25,True,True,False),
             opcode(16,20,24,False,False,False)]
        for word in bad:
            with self.subTest(word=hex(word)):
                _,report=emit_cpp(struct.pack("<2I",word,0xffffffff),0,8)
                self.assertIn(0,report.unsupported)

    def test_all_register_modes_signs_payloads_and_controls(self):
        words=[]
        modes=[]
        for mask in range(1,8):
            af,bf,df=bool(mask&1),bool(mask&2),bool(mask&4)
            for reverse in (False,True):
                words.append(opcode(0 if af else 16,1 if bf else 20,2 if df else 24,af,bf,df,reverse))
                modes.append((int(af),int(bf),int(df),int(reverse)))
        rng=random.Random(0x6e2960)
        rows=[(rng.getrandbits(32),rng.getrandbits(31)|0x80000000,
               rng.choice((1,2,16383,32765,32766))) for _ in range(300)]
        table=",\n".join("{"+",".join(str(v)+"u" for v in row)+"}" for row in rows)
        metadata=",".join("{"+",".join(str(v)+"u" for v in row)+"}" for row in modes)
        body="static const unsigned modes[][4]={"+metadata+"};\nstatic const std::uint32_t rows[][3]={"+table+"};\n"+r"""
using namespace arcaderecomp_generated;
int main(){Bus bus{};
for(unsigned k=0;k<14u;++k) for(const auto& row:rows)
for(unsigned a_sign=0;a_sign<2u;++a_sign) for(unsigned b_sign=0;b_sign<2u;++b_sign)
for(unsigned cc=0;cc<8u;++cc){
    CPU cpu{};cpu.ip=k*4u;cpu.cc=static_cast<int>(cc);cpu.cc_defined=bool(cc&1u);
    cpu.process_controls=0x001f2002u;cpu.known_process_controls=cpu.process_controls;
    cpu.process_controls_priority_known=true;cpu.integer_overflow_flag=true;
    cpu.fp[0]={row[0],row[1],static_cast<std::uint16_t>(row[2]|(a_sign<<15))};
    cpu.fp[1]={0x87654321u,0x80000000u,static_cast<std::uint16_t>(0x4321u|(b_sign<<15))};
    cpu.fp_defined[0]=true;cpu.fp_defined[1]=true;
    cpu.r[16]=row[0];cpu.r[17]=row[1];cpu.r[18]=0xdead0000u|row[2]|(a_sign<<15);
    cpu.r[20]=0x87654321u;cpu.r[21]=0x80000000u;cpu.r[22]=0xbeef4321u|(b_sign<<15);
    cpu.r[27]=0x12345678u;
    if(!step(cpu,bus)||cpu.ip!=(k+1u)*4u)return 1;
    const unsigned expected_high=row[2]|((b_sign^modes[k][3])<<15);
    if(modes[k][2]){
        if(!cpu.fp_defined[2]||cpu.fp[2].low!=row[0]||cpu.fp[2].middle!=row[1]||
           cpu.fp[2].high!=expected_high)return 2;
    } else if(cpu.r[24]!=row[0]||cpu.r[25]!=row[1]||cpu.r[26]!=expected_high)return 3;
    if(cpu.r[27]!=0x12345678u||cpu.r[18]!=(0xdead0000u|row[2]|(a_sign<<15))||
       cpu.r[22]!=(0xbeef4321u|(b_sign<<15))||cpu.cc!=static_cast<int>(cc)||
       cpu.cc_defined!=bool(cc&1u)||cpu.process_controls!=0x001f2002u||
       !cpu.process_controls_priority_known||!cpu.integer_overflow_flag)return 4;
}
return 0;}
"""
        report=native(words+[0xffffffff],body)
        self.assertEqual(report.translated,14)

    def test_aliases_and_reverse_self_sign(self):
        native([opcode(d=0),opcode(d=1,reverse=True),opcode(0,0,0,reverse=True),
                opcode(16,1,16,False,True,False),opcode(0,20,20,True,False,False),0xffffffff],r"""
using namespace arcaderecomp_generated;
int main(){CPU cpu{};Bus bus{};
cpu.fp[0]={1u,0x90000000u,0x3fffu};cpu.fp[1]={2u,0xa0000000u,0xc000u};
cpu.fp_defined[0]=cpu.fp_defined[1]=true;
if(!step(cpu,bus)||cpu.fp[0].high!=0xbfffu||cpu.fp[0].low!=1u)return 1;
if(!step(cpu,bus)||cpu.fp[1].high!=0x3fffu||cpu.fp[1].low!=1u)return 2;
if(!step(cpu,bus)||cpu.fp[0].high!=0x3fffu||cpu.fp[0].low!=1u)return 3;
cpu.r[16]=7u;cpu.r[17]=0xc0000000u;cpu.r[18]=0xffffbfffu;
if(!step(cpu,bus)||cpu.r[16]!=7u||cpu.r[18]!=0x3fffu)return 4;
cpu.r[20]=8u;cpu.r[21]=0x80000000u;cpu.r[22]=0xc001u;
if(!step(cpu,bus)||cpu.r[20]!=1u||cpu.r[21]!=0x90000000u||cpu.r[22]!=0xbfffu)return 5;
return 0;}
""")

    def test_unknown_nonnormal_and_invalid_helpers_preserve_destination(self):
        native([opcode(),0xffffffff],r"""
#include <array>
using namespace arcaderecomp_generated;
int main(){Bus bus{};
for(unsigned which=0;which<2u;++which){
    CPU cpu{};cpu.fp[0]={1u,0x80000000u,0x3fffu};cpu.fp[1]=cpu.fp[0];
    cpu.fp_defined[0]=cpu.fp_defined[1]=true;cpu.fp_defined[which]=false;
    cpu.fp[2]={9u,10u,11u};cpu.fp_defined[2]=true;
    if(step(cpu,bus)||cpu.ip!=0u||cpu.fp[2].low!=9u||cpu.fp[2].middle!=10u||
       cpu.fp[2].high!=11u||!cpu.fp_defined[2]||
       cpu.stop_code!=StopCode::undefined_floating_point_register)return 1;
}
for(unsigned which=0;which<2u;++which)
for(auto high:std::array<unsigned,3>{0u,0x7fffu,0x3fffu}){
    CPU cpu{};cpu.fp[0]={1u,0x80000000u,0x3fffu};cpu.fp[1]=cpu.fp[0];
    cpu.fp_defined[0]=cpu.fp_defined[1]=true;cpu.fp[which].high=static_cast<std::uint16_t>(high);
    if(high==0x3fffu)cpu.fp[which].middle=0u; // unnormal explicit integer bit.
    cpu.fp[2]={9u,10u,11u};cpu.fp_defined[2]=true;
    if(step(cpu,bus)||cpu.ip!=0u||cpu.fp[2].low!=9u||cpu.fp[2].middle!=10u||
       cpu.fp[2].high!=11u||!cpu.fp_defined[2]||
       cpu.stop_code!=StopCode::unsupported_floating_format)return 2;
}
CPU cpu{};cpu.ip=44u;cpu.r[31]=123u;
if(copy_sign_extended_normal(cpu,0u,true,1u,true,31u,false,false)||
   cpu.stop_code!=StopCode::untranslated||cpu.r[31]!=123u||cpu.ip!=44u)return 3;
return 0;}
""")


if __name__=="__main__": unittest.main()
