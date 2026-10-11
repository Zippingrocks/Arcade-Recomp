"""Synthetic-only native locked pending-table provider contract, GCC/Clang."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
HEADER=r"""
#include "i960_pending_interrupt_acquisition.hpp"
#include "i960_process_controls.hpp"
#include "model2c_bus.hpp"
#include <cstddef>
#include <cstdint>
#include <vector>
using namespace arcaderecomp_generated;
using namespace arcaderecomp_model2c;
struct Provider {
    unsigned called=0, normal_reads=0;
    bool accept=true;
    unsigned variant=0; // 0 empty, 1 valid, 2 corrupt, 3 reserved
    std::uint32_t addr=0;
    std::size_t count=0;
};
inline std::uint32_t normal_read(void* ctx,std::uint32_t) {
    ++static_cast<Provider*>(ctx)->normal_reads;return 0u;
}
inline bool locked_fixture(void* ctx,std::uint32_t addr,
                           std::uint8_t* bytes,std::size_t n) {
    auto& p=*static_cast<Provider*>(ctx);
    ++p.called;p.addr=addr;p.count=n;
    if(n!=36u || !bytes)return false;
    if(!p.accept){bytes[35u]=0xffu;return false;} // poison scratch
    for(unsigned i=0;i<36u;++i)bytes[i]=0u;
    if(p.variant==1u) {
        bytes[0]=0x02u;bytes[5]=0x10u; // vector 12, priority 1
        bytes[3]=0x80u;bytes[35]=0x80u; // vector 255, priority 31
    } else if(p.variant==2u)bytes[3]=0x80u; // phantom priority
    else if(p.variant==3u){bytes[3]=0x40u;bytes[34]=0x10u;} // vector 244
    return true;
}
inline CPU known() {
    CPU c{};c.process_controls=0x001f2002u;
    c.known_process_controls=c.process_controls;
    c.process_controls_priority_known=true;
    c.prcb_loaded=true;c.reinitialize_count=1u;
    c.interrupt_table_address=0x00510800u;c.ip=0x40u;
    return c;
}
"""
def native(body):
    cc=[x for name in ("g++","clang++") if (x:=shutil.which(name))]
    if not cc:raise unittest.SkipTest("No GCC/Clang C++17")
    for compiler in cc:
        with tempfile.TemporaryDirectory(prefix="arcade-pending-bus-") as d:
            root=Path(d);src=root/"test.cpp";exe=root/"test"
            src.write_text(HEADER+body,encoding="utf-8")
            x=subprocess.run([compiler,"-std=c++17","-O2","-Wall","-Wextra",
                "-Werror","-fsanitize=undefined","-fno-sanitize-recover=all",
                "-I",str(ROOT/"runtime"),str(src),"-o",str(exe)],
                capture_output=True,text=True,timeout=45)
            if x.returncode:raise AssertionError(compiler+" "+x.stderr)
            y=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
            if y.returncode:raise AssertionError(compiler+" "+y.stderr+" exit "+str(y.returncode))

class KBPendingNativeBusTests(unittest.TestCase):
    def test_missing_provider_and_cpu_state_fail_without_fallback(self):
        native(r"""
int main(){
    Provider p{};Bus bus{};bus.ctx=&p;
    bus.read32=&normal_read;bus.read_pending_record_locked=&locked_fixture;
    CPU cpu{};
    auto r=review_kb_pending_from_native_bus(cpu,bus);
    if(r.status!=KBPendingCaptureStatus::cpu_priority_unknown || p.called)return 1;
    cpu=known();
    for(auto a:{0u,1u,0xffffffddu,0xfffffffcu}) {
        cpu.interrupt_table_address=a;
        r=review_kb_pending_from_native_bus(cpu,bus);
        if(r.status!=KBPendingCaptureStatus::invalid_interrupt_table_address ||
           p.called || p.normal_reads || r.snapshot.eligible_count)return 2;
    }
    cpu=known();cpu.process_controls^=0x10000u;
    r=review_kb_pending_from_native_bus(cpu,bus);
    if(r.status!=KBPendingCaptureStatus::cpu_priority_unknown ||
       p.called || p.normal_reads)return 3;
    cpu=known();bus.read_pending_record_locked=nullptr;
    r=review_kb_pending_from_native_bus(cpu,bus);
    if(r.status!=KBPendingCaptureStatus::locked_provider_unavailable ||
       p.called || p.normal_reads)return 4;
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    board.write(0x00510800u,4u,0u);
    const auto callbacks=board.callbacks();
    if(callbacks.read_pending_record_locked ||
       review_kb_pending_from_native_bus(cpu,callbacks).status!=
          KBPendingCaptureStatus::locked_provider_unavailable)return 5;
    return 0;
}
""")

    def test_rejected_partial_and_corrupt_records_cannot_leak_candidate(self):
        native(r"""
int main(){
    Provider p{};Bus b{};b.ctx=&p;b.read32=&normal_read;
    b.read_pending_record_locked=&locked_fixture;
    const auto cpu=known();
    p.accept=false;
    auto r=review_kb_pending_from_native_bus(cpu,b);
    if(r.status!=KBPendingCaptureStatus::locked_provider_refused ||
       p.called!=1u || p.addr!=0x00510800u || p.count!=36u ||
       r.snapshot.eligible_count || r.snapshot.highest_eligible_vector ||
       r.snapshot.reported_priority_mask || p.normal_reads)return 1;
    p.accept=true;
    for(auto variant:{2u,3u}) {
        p.variant=variant;
        r=review_kb_pending_from_native_bus(cpu,b);
        if(r.status!=KBPendingCaptureStatus::invalid_record ||
           r.snapshot.eligible_count || r.snapshot.highest_eligible_vector ||
           r.snapshot.reported_priority_mask || p.normal_reads)return 2;
    }
    return 0;
}
""")

    def test_observation_is_not_modpc_priority_lowering_or_irq_delivery(self):
        native(r"""
int main(){
    Provider p{};Bus b{};b.ctx=&p;b.read32=&normal_read;
    b.read_pending_record_locked=&locked_fixture;
    auto cpu=known();
    auto r=review_kb_pending_from_native_bus(cpu,b);
    if(r.status!=KBPendingCaptureStatus::provider_asserted_unverified ||
       r.snapshot.status!=KBPendingSnapshotStatus::no_eligible_vector ||
       r.snapshot.eligible_count)return 1;
    p.variant=1u;
    r=review_kb_pending_from_native_bus(cpu,b);
    if(r.status!=KBPendingCaptureStatus::provider_asserted_unverified ||
       r.snapshot.highest_eligible_vector!=255u ||
       r.snapshot.highest_eligible_priority!=31u ||
       r.snapshot.eligible_count!=1u ||
       r.snapshot.vectors_set!=2u || p.normal_reads ||
       cpu.ip!=0x40u || cpu.process_controls!=0x001f2002u)return 2;
    cpu.r[17]=0u;
    if(kb_modpc_checked(cpu,0x001f0000u,17u) ||
       cpu.stop_code!=StopCode::modpc_pending_interrupt_check_unimplemented ||
       cpu.ip!=0x40u || cpu.process_controls!=0x001f2002u ||
       cpu.r[17]!=0u)return 3;
    return 0;
}
""")

if __name__=="__main__":unittest.main()
