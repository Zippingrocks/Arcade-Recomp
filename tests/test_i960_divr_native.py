"""Synthetic Intel 80960KB DIVR (78Bh) native tests; original candidate 0x11F8.
Fraction oracle independent of implementation. No original game instruction
bytes or assets, no inferred Sega serial status, no fake FP exceptions.
"""
from fractions import Fraction
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest
from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ROOT=Path(__file__).resolve().parents[1]


def opcode(d=4,n=20,out=22,mode=0):
    return 0x78000580 | d | n<<14 | out<<19 | mode


def f32(raw):
    return struct.unpack("<f",struct.pack("<I",raw))[0]


def oracle(d,n):
    de,ne=(d>>23)&255,(n>>23)&255
    df,nf=d&0x7fffff,n&0x7fffff
    if de==255 or ne==255 or (de==0 and df) or (ne==0 and nf):
        return 2,0
    if de==0:
        return 3,0
    if ne==0:
        return 0,(d^n)&0x80000000
    result=Fraction.from_float(f32(n))/Fraction.from_float(f32(d))
    if abs(result)<Fraction(1,1<<126) or abs(result)>Fraction.from_float(f32(0x7f7fffff)):
        return 2,0
    bits=struct.unpack("<I",struct.pack("<f",float(result)))[0]
    return (0,bits) if Fraction.from_float(f32(bits))==result else (1,0)


def samples():
    edges=(0,0x80000000,0x3f800000,0xbf800000,0x40000000,
           0xc0000000,0x40400000,0x3f000000,0x00800000,
           0x7f7fffff,0xff7fffff,1,0x7f800000,0x7fc00001,
           0x3f800001,0x3f800002)
    pairs=[(a,b) for a in edges for b in edges]
    rng=random.Random(0x78b960)
    for _ in range(900):
        de,ne=rng.randrange(1,255),rng.randrange(1,255)
        pairs.append(((rng.getrandbits(1)<<31)|(de<<23)|rng.getrandbits(23),
                      (rng.getrandbits(1)<<31)|(ne<<23)|rng.getrandbits(23)))
    return [(d,n,*oracle(d,n)) for d,n in pairs]


class DivrNativeTests(unittest.TestCase):
    def test_decode_order_and_rejected_register_modes(self):
        op=decode(struct.pack("<I",opcode()),0)
        self.assertEqual((op.mnemonic,op.form,op.operands),
                         ("divr","REG",("r4","g4","g6")))
        for mode in (0x20,0x40,0x800,0x1000,0x2000):
            _,report=emit_cpp(struct.pack("<2I",opcode(mode=mode),0xffffffff),0,8)
            self.assertIn(0,report.unsupported)

    def test_native_exact_division_and_fail_closed_alias(self):
        words=[opcode(),opcode(out=4),opcode(out=20),0xffffffff]
        emitted,report=emit_cpp(struct.pack("<4I",*words),0,32)
        self.assertEqual(report.translated,3)
        self.assertEqual(report.unsupported,(12,))
        vectors=",\n".join("{"+",".join(str(x)+"u" for x in row)+"}"
                           for row in samples())
        harness=("static const std::uint32_t rows[][4]={\n"+
                 vectors+"\n};\n")+r"""
using namespace arcaderecomp_generated;
int main(){
    Bus bus{}; unsigned good=0,round=0,format=0,fault=0;
    for(const auto& row:rows)for(unsigned form=0;form<3u;++form)
    for(unsigned cc=0;cc<8u;++cc){
        CPU cpu{};cpu.ip=form*4u;
        cpu.r[4]=row[0];cpu.r[20]=row[1];cpu.r[22]=0xdeadbeefu;
        cpu.cc=static_cast<int>(cc);cpu.cc_defined=bool(cc&1u);
        cpu.integer_overflow_mask=true;cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;cpu.integer_overflow_flag_defined=true;
        const unsigned dst=form==0?22u:form==1?4u:20u;
        std::uint32_t before[32]{};
        for(unsigned i=0;i<32;++i)before[i]=cpu.r[i];
        const bool ok=step(cpu,bus);
        if(row[2]==0){
            if(!ok||cpu.ip!=(form+1u)*4u||cpu.r[dst]!=row[3]||
               cpu.stop_code!=StopCode::none)return 1;
            ++good;
        }else{
            const StopCode kind=row[2]==1u?StopCode::unsupported_floating_rounding:
                row[2]==2u?StopCode::unsupported_floating_format:
                StopCode::unsupported_floating_division_fault;
            if(ok||cpu.ip!=form*4u||cpu.stop_code!=kind)return 2;
            if(row[2]==1u)++round;else if(row[2]==2u)++format;else ++fault;
        }
        for(unsigned i=0;i<32;++i)
            if((row[2]!=0||i!=dst)&&cpu.r[i]!=before[i])return 3;
        if(cpu.cc!=static_cast<int>(cc)||
           cpu.cc_defined!=bool(cc&1u)||
           !cpu.integer_overflow_mask_defined||!cpu.integer_overflow_mask||
           !cpu.integer_overflow_flag_defined||!cpu.integer_overflow_flag||
           cpu.pending_integer_overflow.pending)return 4;
    }
    return good>100u&&round>100u&&format>100u&&fault>10u?0:5;
}
""";
        compilers=[p for name in ("g++","clang++") if (p:=shutil.which(name))]
        if not compilers:raise unittest.SkipTest("No C++17 compiler")
        for cc in compilers:
            with tempfile.TemporaryDirectory(prefix="arcade-divr-") as directory:
                src=Path(directory)/"test.cpp";binary=Path(directory)/"test"
                src.write_text(emitted+"\n"+harness,encoding="utf-8")
                built=subprocess.run([cc,"-std=c++17","-O2","-Wall","-Wextra",
                    "-Werror","-fsanitize=undefined","-fno-sanitize-recover=all",
                    "-I",str(ROOT/"runtime"),str(src),"-o",str(binary)],
                    capture_output=True,text=True,timeout=50)
                if built.returncode:raise AssertionError(cc+": "+built.stderr)
                done=subprocess.run([str(binary)],capture_output=True,
                                    text=True,timeout=30)
                if done.returncode:raise AssertionError(
                    cc+": exit "+str(done.returncode)+" "+done.stderr)


if __name__=="__main__":unittest.main()
