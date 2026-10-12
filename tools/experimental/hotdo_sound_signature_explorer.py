"""Explore every bounded HOTD ``ErrorSet`` startup state class privately.

The supplied ROM is authenticated before translation. Explicit RAM premises
represent the 257 classes proven by ``sound_startup_signature``; they are not
claims about physical reset contents or a substitute for cabinet evidence.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from arcaderecomp.m68k_cpp import emit_cpp
from arcaderecomp.sound_control_audit import authenticate_chip


HARNESS = r'''
#include "m68k_sound_bus.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <tuple>
#include <vector>
using namespace arcaderecomp_m68k_generated;
using Key=std::tuple<unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned>;
static void byte(SoundROMBus& bus,unsigned a,unsigned v) {
    if(!bus.establish_sound_ram_byte_research(a,static_cast<std::uint8_t>(v)))throw std::runtime_error("premise");
}
static void word(SoundROMBus& bus,unsigned a,std::uint32_t v) {
    for(unsigned i=0;i<4;++i)byte(bus,a+i,v>>(24u-i*8u));
}
static Key run(const std::vector<std::uint8_t>& image,unsigned kind,unsigned saved) {
    auto be32=[&](unsigned o){return std::uint32_t(image[o])<<24|std::uint32_t(image[o+1])<<16|
        std::uint32_t(image[o+2])<<8|image[o+3];};
    CPU cpu;if(!reset_from_vectors(cpu,be32(0),be32(4)))throw std::runtime_error("vectors");
    SoundROMBus bus(image);bus.enable_common_control_research(true);
    bus.enable_hotd_sound_control_research(true);bus.enable_sound_ram_research(true);
    if(kind==0)word(bus,0xc08u,0u);
    else {word(bus,0xc08u,0x4572726fu);word(bus,0xc0cu,kind==1?0u:0x72536574u);if(kind==2)byte(bus,0xc04u,saved);}
    while(cpu.completed<500000u&&step(cpu,bus)){}
    std::uint8_t stored=0xffu;const bool known=bus.sound_ram().read8(0xc04u,stored);
    return {static_cast<unsigned>(cpu.stop),cpu.pc,cpu.access_address,cpu.access_width,
            cpu.access_write?1u:0u,cpu.completed,known?stored:0x100u,bus.sound_ram().known_bytes()};
}
int main(int argc,char** argv) {
    if(argc!=2)return 2;
    std::ifstream file(argv[1],std::ios::binary);
    if(!file)return 3;
    std::vector<std::uint8_t> image((std::istreambuf_iterator<char>(file)),{});
    if(image.size()!=0x80000u)return 4;
    const Key first=run(image,0,0),second=run(image,1,0);
    auto same_boundary=[](const Key& a,const Key& b) {
        return std::get<0>(a)==std::get<0>(b)&&std::get<1>(a)==std::get<1>(b)&&
            std::get<2>(a)==std::get<2>(b)&&std::get<3>(a)==std::get<3>(b)&&
            std::get<4>(a)==std::get<4>(b)&&std::get<7>(a)==std::get<7>(b);
    };
    if(!same_boundary(first,second)||std::get<6>(first)!=0u||std::get<6>(second)!=0u)return 5;
    unsigned marker_completed=0;
    for(unsigned saved=0;saved<256u;++saved) {
        const Key result=run(image,2,saved);
        if(!same_boundary(first,result)||std::get<6>(result)!=saved)return 6;
        if(saved==0)marker_completed=std::get<5>(result);
        else if(std::get<5>(result)!=marker_completed)return 7;
    }
    std::cout<<"{\"representative_paths\":258,\"architectural_classes\":257,"
       <<"\"mismatch_completed\":["<<std::get<5>(first)<<','<<std::get<5>(second)<<"],"
       <<"\"marker_completed\":"<<marker_completed<<",\"marker_stored_byte_domain\":256,"
       <<"\"common_boundary\":{\"stop_code\":"<<std::get<0>(first)
       <<",\"pc\":"<<std::get<1>(first)<<",\"address\":"<<std::get<2>(first)
       <<",\"width\":"<<std::get<3>(first)<<",\"write\":"<<(std::get<4>(first)?"true":"false")
       <<",\"known_ram_bytes\":"<<std::get<7>(first)<<"}}\n";
    return 0;
}
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chip", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, default=ROOT / "build" / "m68k-sound-signature")
    parser.add_argument("--compiler", default=shutil.which("g++") or shutil.which("clang++"))
    args = parser.parse_args(argv)
    if not args.compiler:
        parser.error("A C++17 g++/clang++ compiler is required")
    output = args.work_dir.resolve()
    build_root = (ROOT / "build").resolve()
    if not output.is_relative_to(build_root) or output == build_root:
        parser.error("Private generated output must stay below this checkout's ignored build/")
    image, identity = authenticate_chip(args.chip)
    source, translation = emit_cpp(image, int.from_bytes(image[4:8], "big"), base=0x600000)
    output.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    cpp, binary, image_path = run_dir / "private.cpp", run_dir / "probe", run_dir / "audiocpu.bin"
    cpp.write_text(source + HARNESS, encoding="utf-8")
    image_path.write_bytes(image)
    subprocess.run([args.compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all", "-I", str(ROOT / "runtime"),
                    str(cpp), "-o", str(binary)], check=True, timeout=60)
    result = subprocess.run([str(binary), str(image_path)], check=True, capture_output=True,
                            text=True, timeout=60)
    print(json.dumps({"schema": "hotdo-sound-signature-explorer-v1",
                      "chip_identity": identity, "image_sha256": hashlib.sha256(image).hexdigest(),
                      "proof": "explicit exhaustive software-state partition; not physical reset evidence",
                      "translation": asdict(translation), "execution": json.loads(result.stdout)}, indent=2))


if __name__ == "__main__":
    main()
