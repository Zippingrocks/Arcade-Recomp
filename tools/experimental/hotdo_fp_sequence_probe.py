"""Private original HOTD1 FP instruction-triplet AOT verification.

Requires the authenticated original hotdo 2 MiB CPU image. The ROM is read
locally; generated original-game C++ is confined to TemporaryDirectory,
compiled natively and deleted. Only non-game-derived metadata leaves it.
Tests isolated instruction execution with synthetic CPU state, NOT real arcade
hardware, continuous game boot or original cabinet exception/timing behavior.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ORIGINAL_SHA="da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75"
# Public research metadata: instruction locations and output register indices.
SITES=((0x00000bfc,17),(0x00000c24,21),
       (0x00000c4c,22),(0x00000c7c,21))

RUNNER=r"""
#include <iostream>
using namespace arcaderecomp_generated;
int main(){
    Bus bus{};unsigned count=0;
    std::uint32_t pc,dst,input,first,biased,result,valid;
    while(std::cin>>pc>>dst>>input>>first>>biased>>result>>valid){
        CPU cpu{};cpu.ip=pc;cpu.cc=4;
        for(unsigned i=0;i<32;++i)cpu.r[i]=(i+1u)*0x01020304u;
        cpu.r[23]=input;cpu.r[18]=0x43000000u;
        cpu.r[20]=0xdeadbeefu;
        std::uint32_t before[32]{};
        for(unsigned i=0;i<32;++i)before[i]=cpu.r[i];
        if(!valid){
            if(step(cpu,bus)||
               cpu.stop_code!=StopCode::unsupported_floating_format||
               cpu.ip!=pc||cpu.stop_ip!=pc)return 1;
            for(unsigned i=0;i<32;++i)
                if(cpu.r[i]!=before[i])return 2;
        }else{
            if(!step(cpu,bus)||cpu.ip!=pc+4u||cpu.r[20]!=first)return 3;
            if(!step(cpu,bus)||cpu.ip!=pc+8u||cpu.r[20]!=biased)return 4;
            if(!step(cpu,bus)||cpu.ip!=pc+12u||cpu.r[dst]!=result)return 5;
            for(unsigned i=0;i<32;++i)
                if(i!=20u&&i!=dst&&cpu.r[i]!=before[i])return 6;
            if(cpu.cc!=4||!cpu.cc_defined||
               cpu.stop_code!=StopCode::none)return 7;
        }
        ++count;
    }
    if(!std::cin.eof()||!count)return 8;
    std::cout<<count<<'\n';
    return 0;
}
"""

def single(value):
    return struct.unpack("<I",struct.pack("<f",float(value)))[0]

def samples():
    rng=random.Random(0x0d960)
    for e in range(1,255):
        for sign in range(2):
            for fraction in (0,1,0x123456,0x7fffff):
                yield ((sign<<31)|(e<<23)|fraction,
                       single(e-127),single(e+1),e+1,1)
    for _ in range(700):
        e=rng.randrange(1,255)
        yield ((rng.getrandbits(1)<<31)|(e<<23)|rng.getrandbits(23),
               single(e-127),single(e+1),e+1,1)
    for bits in (0,0x80000000,1,0x807fffff,
                 0x7f800000,0xff800000,0x7fc00001):
        yield (bits,0,0,0,0)

def verify(image:bytes,compilers:list[str])->dict:
    digest=hashlib.sha256(image).hexdigest()
    if len(image)!=0x200000 or digest!=ORIGINAL_SHA:
        raise ValueError("not verified original hotdo CPU image")
    paths=[shutil.which(cxx) for cxx in compilers]
    if not paths or not all(paths):
        raise ValueError("missing compiler")

    sparse=bytearray(b"\xff"*(SITES[-1][0]+16))
    for pc,dst in SITES:
        a,b,c=(decode(image,pc+offset) for offset in (0,4,8))
        if (a.mnemonic,a.operands)!=("logbnr",("g7","g4")):
            raise ValueError("unexpected original LOGBNR")
        if (b.mnemonic,b.operands)!=("addr",("g4","g2","g4")):
            raise ValueError("unexpected original ADDR")
        if (c.mnemonic,c.operands)!=("cvtzri",("g4",f"g{dst-16}")):
            raise ValueError("unexpected original CVTZRI")
        # Generated AOT code is temporary and never exported.
        sparse[pc:pc+12]=image[pc:pc+12]
    native,report=emit_cpp(bytes(sparse),SITES[0][0],64,
                           additional_entries=tuple(pc for pc,_ in SITES[1:]))
    required={pc+offset for pc,_ in SITES for offset in (0,4,8)}
    if report.limit_reached or report.translated!=12 or (
            required & set(report.unsupported)):
        raise ValueError("untranslated original triplet")

    cases=list(samples())
    inputs="".join(
        f"{pc} {dst} {raw} {logb} {total} {integer} {valid}\n"
        for pc,dst in SITES
        for raw,logb,total,integer,valid in cases)
    results=[]
    with tempfile.TemporaryDirectory(prefix="private-hotdo-native-fp-") as folder:
        cpp=Path(folder)/"original.cpp"
        cpp.write_text(native+RUNNER,encoding="utf-8")
        for i,compiler in enumerate(paths):
            exe=Path(folder)/f"runner-{i}"
            built=subprocess.run(
                [compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 "-I",str(ROOT/"runtime"),str(cpp),"-o",str(exe)],
                text=True,capture_output=True,timeout=90)
            if built.returncode:
                raise ValueError("native compiler rejected original triplets")
            run=subprocess.run(
                [str(exe)],input=inputs,text=True,
                capture_output=True,timeout=45)
            if (run.returncode or run.stderr or
                    run.stdout.strip()!=str(len(SITES)*len(cases))):
                raise ValueError("original native outputs differ from oracle")
            results.append({
                "compiler":Path(compiler).name,
                "passed_vectors":len(SITES)*len(cases),
                "ubsan":True})
    return {
        "schema":"hotdo-original-fp-triplets-isolated-v1",
        "cpu_sha256":digest,
        "sites":[f"0x{pc:08x}" for pc,_ in SITES],
        "samples_per_site":len(cases),
        "native_steps_per_normal_case":3,
        "synthetic_cpu_state":True,
        "continuous_boot":False,
        "arcade_hardware_verified":False,
        "rom_or_native_game_code_exported":False,
        "compilers":results}

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--image",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--cxx",action="append")
    args=p.parse_args()
    try:
        if args.output.resolve()==args.image.resolve():
            raise ValueError("must not overwrite original ROM")
        result=verify(args.image.read_bytes(),args.cxx or ["g++","clang++"])
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        # Never echo a compiler diagnostic containing derived original code.
        print("private verification failed: "+type(exc).__name__,file=sys.stderr)
        return 2
    print("Validated four private original instruction triplets with synthetic CPU state.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
