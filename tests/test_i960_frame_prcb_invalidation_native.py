"""Native i960KB initial-frame PRCB invalidation and IAC reinitialization.

Synthetic Intel control blocks only; NOT Sega Model 2C hardware evidence.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HEADER = r"""
#include "i960_reinitialize.hpp"
#include "i960_pending_interrupt_acquisition.hpp"
#include <cstdint>
#include <unordered_map>
using namespace arcaderecomp_generated;
struct TestRAM {
    std::unordered_map<std::uint32_t,std::uint32_t> words;
};
inline std::uint32_t rd(void* p, std::uint32_t address) {
    return static_cast<TestRAM*>(p)->words.at(address);
}
inline void put_prcb(TestRAM& ram, std::uint32_t prcb,
                     std::uint32_t itab, std::uint32_t stack,
                     std::uint32_t fault) {
    ram.words[prcb + 4u]=0xcu;
    ram.words[prcb + 20u]=itab;
    ram.words[prcb + 24u]=stack;
    ram.words[prcb + 32u]=0x1ffu;
    ram.words[prcb + 36u]=0x27fu;
    ram.words[prcb + 40u]=fault;
    ram.words[prcb + 44u]=0u;
}
inline void request_iac(CPU& cpu,std::uint32_t sat,
                        std::uint32_t prcb,std::uint32_t ip) {
    cpu.pending_iac[0]=0x93000000u;
    cpu.pending_iac[1]=sat;
    cpu.pending_iac[2]=prcb;
    cpu.pending_iac[3]=ip;
    cpu.pending_iac_valid=true;
}
"""

def native(body):
    cc=[p for name in ("g++","clang++") if (p:=shutil.which(name))]
    if not cc:
        raise unittest.SkipTest("GCC or Clang C++17 required")
    for compiler in cc:
        with tempfile.TemporaryDirectory(prefix="arcade-i960-root-frame-") as tmp:
            src=Path(tmp)/"test.cpp"
            binary=Path(tmp)/"test"
            src.write_text(HEADER+body,encoding="utf-8")
            build=subprocess.run(
                [compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 "-I",str(ROOT/"runtime"),str(src),"-o",str(binary)],
                capture_output=True,text=True,timeout=45)
            if build.returncode:
                raise AssertionError(compiler+": "+build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,
                               text=True,timeout=30)
            if run.returncode:
                raise AssertionError(compiler+" exit "+str(run.returncode)
                                     +": "+run.stdout+run.stderr)

class NativeFramePRCBResetTests(unittest.TestCase):
    def test_direct_iac_helper_requires_opt_in_before_bus_or_reset(self):
        native(r"""
int main() {
    TestRAM ram{};
    put_prcb(ram,0x00510e00u,0x00510800u,0x00510400u,0x210u);
    CPU cpu{};
    if(!frame_init(cpu,0x00510200u,0x80u))return 1;
    cpu.prcb_loaded=true;cpu.prcb_address=0x00511e00u;
    cpu.process_controls_priority_known=true;
    cpu.known_process_controls=0x001f2002u;
    cpu.fp_defined[0]=true;cpu.fp[0].low=0x12345678u;
    request_iac(cpu,0u,0x00510e00u,0x40u);
    // A denied request must stop before even requiring a bus reader.
    Bus absent{};
    if(perform_iac_93_reinitialize(cpu,absent) ||
       cpu.stop_code!=StopCode::iac_reinitialize_pending)return 2;
    // A throwing reader proves that a present bus is not consulted either.
    Bus denied{};
    denied.read32=+[](void*,std::uint32_t)->std::uint32_t { throw 1; };
    try {
        if(perform_iac_93_reinitialize(cpu,denied))return 3;
    } catch(...) { return 4; }
    if(cpu.ip!=0x80u || cpu.r[31]!=0x00510200u ||
       !cpu.prcb_loaded || cpu.prcb_address!=0x00511e00u ||
       !cpu.process_controls_priority_known ||
       cpu.known_process_controls!=0x001f2002u ||
       !cpu.fp_defined[0] || cpu.fp[0].low!=0x12345678u ||
       !cpu.pending_iac_valid || cpu.pending_iac[2]!=0x00510e00u ||
       cpu.reinitialize_count!=0u || cpu.allow_iac_93_reinitialize)
       return 5;
    // Explicit opt-in may resume exactly the preserved pending request.
    Bus allowed{};allowed.ctx=&ram;allowed.read32=&rd;
    cpu.allow_iac_93_reinitialize=true;
    if(!perform_iac_93_reinitialize(cpu,allowed) ||
       cpu.ip!=0x40u || cpu.prcb_address!=0x00510e00u ||
       cpu.reinitialize_count!=1u || cpu.pending_iac_valid ||
       cpu.stop_code!=StopCode::none)return 6;
    return 0;
}
""")

    def test_new_root_frame_invalidates_stale_hardware_metadata(self):
        native(r"""
int main() {
    CPU cpu{};
    cpu.sat_address=0x1000u;
    cpu.prcb_address=0x2000u;
    cpu.interrupt_table_address=0x3000u;
    cpu.interrupt_stack_address=0x4000u;
    cpu.fault_table_address=0x5000u;
    cpu.prcb_loaded=true;
    cpu.process_controls=0x001f2002u;
    cpu.known_process_controls=cpu.process_controls;
    cpu.process_controls_priority_known=true;
    cpu.reinitialize_count=6u; // Audit history, not a PRCB validity flag.
    cpu.allow_iac_93_reinitialize=true; // Caller-owned research opt-in.
    request_iac(cpu,0x1000u,0x2000u,0x40u);
    if(!frame_init(cpu,0x00510400u,0x80u))return 1;
    if(cpu.sat_address || cpu.prcb_address ||
       cpu.interrupt_table_address || cpu.interrupt_stack_address ||
       cpu.fault_table_address || cpu.prcb_loaded ||
       cpu.pending_iac_valid || cpu.process_controls_priority_known ||
       cpu.known_process_controls || cpu.frame_depth ||
       cpu.r[31]!=0x00510400u || cpu.ip!=0x80u ||
       cpu.reinitialize_count!=6u ||
       !cpu.allow_iac_93_reinitialize)return 2;
    if(kb_known_cpu_program_priority(cpu))return 3;
    // No stale interrupt table may be consulted, even if a reader exists.
    Bus bus{};
    if(review_kb_pending_from_native_bus(cpu,bus).status!=
       KBPendingCaptureStatus::cpu_priority_unknown)return 4;
    return 0;
}
""")

    def test_validated_iac_replaces_both_prcbs_not_merely_priority(self):
        native(r"""
int main() {
    TestRAM ram{};
    put_prcb(ram,0x00510e00u,0x00510800u,0x00510400u,0x210u);
    put_prcb(ram,0x00511e00u,0x00511800u,0x00511400u,0x310u);
    Bus bus{};bus.ctx=&ram;bus.read32=&rd;
    CPU cpu{};
    if(!frame_init(cpu,0x00510200u,0x0u))return 1;
    cpu.allow_iac_93_reinitialize=true;
    request_iac(cpu,0u,0x00510e00u,0x40u);
    if(!perform_iac_93_reinitialize(cpu,bus))return 2;
    if(!cpu.prcb_loaded || cpu.prcb_address!=0x00510e00u ||
       cpu.interrupt_table_address!=0x00510800u ||
       cpu.interrupt_stack_address!=0x00510400u ||
       cpu.fault_table_address!=0x210u ||
       !kb_known_cpu_program_priority(cpu) ||
       *kb_known_cpu_program_priority(cpu)!=31u ||
       cpu.reinitialize_count!=1u || cpu.pending_iac_valid)return 3;
    cpu.saved_valid[0]=true;cpu.frame_depth=1u;
    request_iac(cpu,0x1000u,0x00511e00u,0x80u);
    if(!perform_iac_93_reinitialize(cpu,bus))return 4;
    if(!cpu.prcb_loaded || cpu.sat_address!=0x1000u ||
       cpu.prcb_address!=0x00511e00u ||
       cpu.interrupt_table_address!=0x00511800u ||
       cpu.interrupt_stack_address!=0x00511400u ||
       cpu.fault_table_address!=0x310u ||
       cpu.r[31]!=0x00511400u || cpu.ip!=0x80u ||
       cpu.saved_valid[0] || cpu.frame_depth!=0u ||
       cpu.reinitialize_count!=2u || cpu.pending_iac_valid ||
       !kb_known_cpu_program_priority(cpu))return 5;
    // A later new root frame cannot silently inherit that PRCB.
    if(!frame_init(cpu,0x00512400u,0xc0u))return 6;
    if(cpu.prcb_loaded || cpu.prcb_address ||
       cpu.interrupt_table_address || cpu.interrupt_stack_address ||
       cpu.fault_table_address || cpu.sat_address ||
       cpu.process_controls_priority_known ||
       kb_known_cpu_program_priority(cpu) ||
       cpu.reinitialize_count!=2u)return 7;
    return 0;
}
""")

    def test_failed_frame_init_preserves_existing_metadata_and_iac(self):
        native(r"""
int main() {
    CPU cpu{};
    cpu.ip=0x80u;
    cpu.prcb_loaded=true;
    cpu.prcb_address=0x00510e00u;
    cpu.interrupt_table_address=0x00510800u;
    cpu.process_controls_priority_known=true;
    cpu.known_process_controls=0x001f2002u;
    request_iac(cpu,0u,0x00510e00u,0x40u);
    if(frame_init(cpu,0x00510401u,0x40u) ||
       cpu.stop_code!=StopCode::bad_frame_pointer)return 1;
    if(cpu.ip!=0x80u || cpu.prcb_address!=0x00510e00u ||
       cpu.interrupt_table_address!=0x00510800u ||
       !cpu.prcb_loaded || !cpu.pending_iac_valid ||
       !cpu.process_controls_priority_known ||
       cpu.known_process_controls!=0x001f2002u)return 2;
    if(frame_init(cpu,0x00510400u,0x42u) ||
       cpu.stop_code!=StopCode::bad_instruction_pointer)return 3;
    if(cpu.ip!=0x80u || cpu.prcb_address!=0x00510e00u ||
       !cpu.prcb_loaded || !cpu.pending_iac_valid)return 4;
    return 0;
}
""")

if __name__=="__main__":
    unittest.main()
