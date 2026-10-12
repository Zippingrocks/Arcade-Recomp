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


# The exact original sequence at 0x600288 masks the selector with 0x0e, then
# 0x600292 forms A1 from the PC-relative jump table at 0x600298.  Therefore
# JMP (A1) at 0x600296 can reach exactly these eight even instruction roots.
# Supplying the bounded set enrolls code for the native dispatcher; JMP itself
# still consumes and validates the run-time register value.
PROVEN_JMP_A1_TARGETS = tuple(range(0x00600298, 0x006002A8, 2))


HARNESS = r'''
#include "m68k_sound_bus.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <tuple>
#include <vector>
using namespace arcaderecomp_m68k_generated;
using Key=std::tuple<unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,
    unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,
    unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,
    unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,
    unsigned,unsigned,unsigned,unsigned,unsigned>;
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
    bus.enable_slot_mixer_research(true);
    bus.enable_dsp_registers_research(true);
    if(kind==0)word(bus,0xc08u,0u);
    else {word(bus,0xc08u,0x4572726fu);word(bus,0xc0cu,kind==1?0u:0x72536574u);if(kind==2)byte(bus,0xc04u,saved);}
    while(cpu.completed<500000u&&step(cpu,bus)){}
    std::uint8_t stored=0xffu;const bool known=bus.sound_ram().read8(0xc04u,stored);
    return {static_cast<unsigned>(cpu.stop),cpu.pc,cpu.access_address,cpu.access_width,
            cpu.access_write?1u:0u,cpu.completed,known?stored:0x100u,bus.sound_ram().known_bytes(),
            static_cast<unsigned>(bus.slot_mixer_control().completed_discarded_reads()),
            static_cast<unsigned>(bus.slot_mixer_control().completed_writes()),
            static_cast<unsigned>(bus.dsp_coefficients().completed_discarded_reads()),
            static_cast<unsigned>(bus.dsp_coefficients().completed_writes()),
            static_cast<unsigned>(bus.dsp_memory_addresses().completed_discarded_reads()),
            static_cast<unsigned>(bus.dsp_memory_addresses().completed_writes()),
            static_cast<unsigned>(bus.dsp_prohibited_clear_window().completed_discarded_word_reads()),
            static_cast<unsigned>(bus.dsp_prohibited_clear_window().completed_zero_word_writes()),
            static_cast<unsigned>(bus.dsp_microprogram().completed_discarded_reads()),
            static_cast<unsigned>(bus.dsp_microprogram().completed_writes()),
            static_cast<unsigned>(bus.slot_input_mixer_control().completed_writes()),
            static_cast<unsigned>(bus.slot_volume_modulation_control().completed_discarded_reads()),
            static_cast<unsigned>(bus.slot_volume_modulation_control().completed_writes()),
            static_cast<unsigned>(bus.slot_input_mixer_control().completed_discarded_reads()),
            static_cast<unsigned>(bus.slot_lfo_control().completed_discarded_reads()),
            static_cast<unsigned>(bus.slot_lfo_control().completed_writes()),
            static_cast<unsigned>(bus.slot_envelope_release_control().completed_writes()),
            static_cast<unsigned>(bus.slot_loop_key_control().completed_writes()),
            static_cast<unsigned>(bus.slot_loop_key_control().completed_executions()),
            static_cast<unsigned>(bus.timers().completed_writes()),
            static_cast<unsigned>(bus.interrupt_control().completed_writes()),
            bus.interrupt_control().enable(0),bus.interrupt_control().enable_known_mask(0),
            bus.interrupt_control().pending(0),bus.interrupt_control().pending_known_mask(0),
            cpu.d[0]&0xffu,cpu.d_known[0]&0xffu,cpu.a[1],cpu.a_known[1]?1u:0u,
            cpu.a[0],cpu.a_known[0]?1u:0u,cpu.a[4],cpu.a_known[4]?1u:0u,
            cpu.d[2],cpu.d_known[2],cpu.d[6],cpu.d_known[6]};
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
            std::get<4>(a)==std::get<4>(b)&&std::get<7>(a)==std::get<7>(b)&&
            std::get<8>(a)==std::get<8>(b)&&std::get<9>(a)==std::get<9>(b)&&
            std::get<10>(a)==std::get<10>(b)&&std::get<11>(a)==std::get<11>(b)&&
            std::get<12>(a)==std::get<12>(b)&&std::get<13>(a)==std::get<13>(b)&&
            std::get<14>(a)==std::get<14>(b)&&std::get<15>(a)==std::get<15>(b)&&
            std::get<16>(a)==std::get<16>(b)&&std::get<17>(a)==std::get<17>(b)&&
            std::get<18>(a)==std::get<18>(b)&&std::get<19>(a)==std::get<19>(b)&&
            std::get<20>(a)==std::get<20>(b)&&std::get<21>(a)==std::get<21>(b)&&
            std::get<22>(a)==std::get<22>(b)&&std::get<23>(a)==std::get<23>(b)&&
            std::get<24>(a)==std::get<24>(b)&&std::get<25>(a)==std::get<25>(b)&&
            std::get<26>(a)==std::get<26>(b)&&std::get<27>(a)==std::get<27>(b)&&
            std::get<28>(a)==std::get<28>(b)&&std::get<29>(a)==std::get<29>(b)&&
            std::get<30>(a)==std::get<30>(b)&&std::get<31>(a)==std::get<31>(b)&&
            std::get<32>(a)==std::get<32>(b)&&std::get<33>(a)==std::get<33>(b)&&
            std::get<34>(a)==std::get<34>(b)&&std::get<35>(a)==std::get<35>(b)&&
            std::get<36>(a)==std::get<36>(b)&&std::get<37>(a)==std::get<37>(b)&&
            std::get<38>(a)==std::get<38>(b)&&std::get<39>(a)==std::get<39>(b)&&
            std::get<40>(a)==std::get<40>(b)&&std::get<41>(a)==std::get<41>(b)&&
            std::get<42>(a)==std::get<42>(b)&&std::get<43>(a)==std::get<43>(b)&&
            std::get<44>(a)==std::get<44>(b);
    };
    auto diagnostic=[](const char* name,const Key& value){
        std::cerr<<name<<": stop="<<std::get<0>(value)<<" pc="<<std::get<1>(value)
          <<" address="<<std::get<2>(value)<<" width="<<std::get<3>(value)
          <<" write="<<std::get<4>(value)<<" completed="<<std::get<5>(value)<<'\n';
    };
    if(!same_boundary(first,second)||std::get<6>(first)!=0u||std::get<6>(second)!=0u){
        diagnostic("mismatch",first);diagnostic("empty",second);return 5;
    }
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
       <<",\"known_ram_bytes\":"<<std::get<7>(first)
       <<",\"slot_mixer_discarded_reads\":"<<std::get<8>(first)
       <<",\"slot_mixer_writes\":"<<std::get<9>(first)
       <<",\"dsp_coefficient_discarded_reads\":"<<std::get<10>(first)
       <<",\"dsp_coefficient_writes\":"<<std::get<11>(first)
       <<",\"dsp_address_discarded_reads\":"<<std::get<12>(first)
       <<",\"dsp_address_writes\":"<<std::get<13>(first)
       <<",\"dsp_prohibited_discarded_reads\":"<<std::get<14>(first)
       <<",\"dsp_prohibited_zero_writes\":"<<std::get<15>(first)
       <<",\"dsp_microprogram_discarded_reads\":"<<std::get<16>(first)
       <<",\"dsp_microprogram_writes\":"<<std::get<17>(first)
       <<",\"slot_input_mixer_writes\":"<<std::get<18>(first)
       <<",\"slot_volume_modulation_discarded_reads\":"<<std::get<19>(first)
       <<",\"slot_volume_modulation_writes\":"<<std::get<20>(first)
       <<",\"slot_input_mixer_discarded_reads\":"<<std::get<21>(first)
       <<",\"slot_lfo_discarded_reads\":"<<std::get<22>(first)
       <<",\"slot_lfo_writes\":"<<std::get<23>(first)
       <<",\"slot_envelope_release_writes\":"<<std::get<24>(first)
       <<",\"slot_key_writes\":"<<std::get<25>(first)
       <<",\"slot_key_executions\":"<<std::get<26>(first)
       <<",\"timer_writes\":"<<std::get<27>(first)
       <<",\"interrupt_control_writes\":"<<std::get<28>(first)
       <<",\"sound_interrupt_enable\":"<<std::get<29>(first)
       <<",\"sound_interrupt_enable_known\":"<<std::get<30>(first)
       <<",\"sound_interrupt_pending\":"<<std::get<31>(first)
       <<",\"sound_interrupt_pending_known\":"<<std::get<32>(first)
       <<",\"boundary_d0_low\":"<<std::get<33>(first)
       <<",\"boundary_d0_low_known\":"<<std::get<34>(first)
       <<",\"boundary_a1\":"<<std::get<35>(first)
       <<",\"boundary_a1_known\":"<<std::get<36>(first)
       <<",\"boundary_a0\":"<<std::get<37>(first)
       <<",\"boundary_a0_known\":"<<std::get<38>(first)
       <<",\"boundary_a4\":"<<std::get<39>(first)
       <<",\"boundary_a4_known\":"<<std::get<40>(first)
       <<",\"boundary_d2\":"<<std::get<41>(first)
       <<",\"boundary_d2_known\":"<<std::get<42>(first)
       <<",\"boundary_d6\":"<<std::get<43>(first)
       <<",\"boundary_d6_known\":"<<std::get<44>(first)<<"}}\n";
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
    source, translation = emit_cpp(
        image, int.from_bytes(image[4:8], "big"), base=0x600000,
        additional_entries=PROVEN_JMP_A1_TARGETS)
    output.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    cpp, binary, image_path = run_dir / "private.cpp", run_dir / "probe", run_dir / "audiocpu.bin"
    cpp.write_text(source + HARNESS, encoding="utf-8")
    image_path.write_bytes(image)
    subprocess.run([args.compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all", "-I", str(ROOT / "runtime"),
                    str(cpp), "-o", str(binary)], check=True, timeout=60)
    result = subprocess.run([str(binary), str(image_path)], check=False, capture_output=True,
                            text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f"native explorer failed ({result.returncode}): {result.stderr.strip()}")
    print(json.dumps({"schema": "hotdo-sound-signature-explorer-v1",
                      "chip_identity": identity, "image_sha256": hashlib.sha256(image).hexdigest(),
                      "proof": "explicit exhaustive software-state partition; not physical reset evidence",
                      "translation": asdict(translation), "execution": json.loads(result.stdout)}, indent=2))


if __name__ == "__main__":
    main()
