"""ROM-free tests for proven Intel KB program priority after opt-in IAC 0x93.

Never claims real cabinet status, CPU IRQ acceptance or actual priority
through untranslated MODPC/process-control changes.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

CODE=r"""
#include "i960_reinitialize.hpp"
#include "model2c_irq_observation.hpp"
#include <cstdint>
#include <unordered_map>
using namespace arcaderecomp_generated;
using namespace arcaderecomp_model2c;

struct Memory {
    std::unordered_map<std::uint32_t,std::uint32_t> words;
    unsigned reads=0;
};
inline std::uint32_t read32(void* ctx,std::uint32_t address) {
    auto& mem=*static_cast<Memory*>(ctx);
    ++mem.reads;
    return mem.words.at(address);
}
inline Memory make_memory(){
    Memory m{};
    constexpr auto P=0x00510e00u;
    m.words[P+4u]=0xcu;
    m.words[P+20u]=0x00510800u;
    m.words[P+24u]=0x00510400u;
    m.words[P+32u]=0x1ffu;
    m.words[P+36u]=0x27fu;
    m.words[P+40u]=0x210u;
    m.words[P+44u]=0u;
    return m;
}
int main() {
    CPU cpu{};
    PartialIRQRegisters board{};
    board.request_enable_update(0x000fu);
    board.advance_cpu_cycles(2u);
    for(unsigned bit : {0u,1u,2u,3u})
        board.inject_enabled_source_for_test(bit);
    cpu.interrupt_control_register=0x0f0e0d0cu;
    auto snapshot=observe_model2c_irq(board,cpu);

    // No unverified zero-initialized or manually written PC priority.
    if(kb_known_cpu_program_priority(cpu).has_value())return 1;
    if(review_model2c_irq_known_cpu_priority(snapshot,cpu))return 2;
    cpu.process_controls=0x001f2002u; // coincidental data, not evidence
    if(kb_known_cpu_program_priority(cpu))return 3;
    if(!frame_init(cpu,0x00510200u,0u))return 4;
    if(kb_known_cpu_program_priority(cpu))return 5;

    Memory mem=make_memory();
    Bus bus{};bus.ctx=&mem;bus.read32=&read32;
    cpu.pending_iac_valid=true;
    cpu.allow_iac_93_reinitialize=true;
    cpu.pending_iac[0]=0x93000000u;
    cpu.pending_iac[1]=0u;
    cpu.pending_iac[2]=0x00510e00u;
    cpu.pending_iac[3]=0x40u;

    // Invalid aligned stack prevents a false "known" marker.
    mem.words[0x00510e00u+24u]=0x00510401u;
    if(perform_iac_93_reinitialize(cpu,bus))return 6;
    if(cpu.process_controls_priority_known ||
       kb_known_cpu_program_priority(cpu))return 7;
    mem.words[0x00510e00u+24u]=0x00510400u;
    if(!perform_iac_93_reinitialize(cpu,bus))return 8;
    const auto known=kb_known_cpu_program_priority(cpu);
    if(!known || *known!=31u || cpu.process_controls!=0x001f2002u ||
       cpu.known_process_controls!=cpu.process_controls ||
       cpu.reinitialize_count!=1u)return 9;

    // A synthetic priority-31 observation of vectors 12..15 is pending,
    // not a delivered IRQ; process reinit also reset the Intel ICR mux.
    cpu.interrupt_control_register=0x0f0e0d0cu;
    snapshot=observe_model2c_irq(board,cpu);
    const auto evaluated=review_model2c_irq_known_cpu_priority(snapshot,cpu);
    if(!evaluated || evaluated->externally_supplied_current_priority!=31u ||
       evaluated->would_post_pending!=3u ||
       evaluated->higher_priority_candidates ||
       evaluated->non_direct_asserted_pins)return 10;
    if(cpu.frame_depth || cpu.ip!=0x40u || board.request()!=0xfu)return 11;

    // Any out-of-band PC modification invalidates the proven value.
    cpu.process_controls^=0x00010000u;
    if(kb_known_cpu_program_priority(cpu) ||
       review_model2c_irq_known_cpu_priority(snapshot,cpu))return 12;
    cpu.process_controls=cpu.known_process_controls;
    if(!kb_known_cpu_program_priority(cpu))return 13;
    if(!frame_init(cpu,0x00510200u,0u))return 14;
    if(kb_known_cpu_program_priority(cpu))return 15;
    return 0;
}
"""


class I960KnownPriorityTests(unittest.TestCase):
    def test_known_reset_priority_requires_successful_iac_93(self):
        compilers=[p for n in ("g++","clang++") if (p:=shutil.which(n))]
        if not compilers:
            raise unittest.SkipTest("No C++17 compiler")
        for cc in compilers:
            with self.subTest(compiler=cc):
                with tempfile.TemporaryDirectory(prefix="arcade-priority-provenance-") as folder:
                    path=Path(folder)
                    src,exe=path/"test.cpp",path/"test"
                    src.write_text(CODE,encoding="utf-8")
                    compiled=subprocess.run(
                        [cc,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                         "-fsanitize=undefined","-fno-sanitize-recover=all",
                         "-I",str(ROOT/"runtime"),str(src),"-o",str(exe)],
                        capture_output=True,text=True,timeout=45)
                    self.assertEqual(compiled.returncode,0,compiled.stderr)
                    run=subprocess.run([str(exe)],capture_output=True,text=True,
                                       timeout=25)
                    self.assertEqual(run.returncode,0,
                                     f"{cc}: {run.stdout}{run.stderr} exit {run.returncode}")


if __name__=="__main__":
    unittest.main()
