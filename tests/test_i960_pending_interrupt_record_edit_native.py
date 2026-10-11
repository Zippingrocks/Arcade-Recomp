"""Pure Intel KB 36-byte pending-table post/take drafts. Synthetic only."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PREFIX=r"""
#include "i960_pending_interrupt_record_edit.hpp"
#include <array>
#include <cstdint>
#include <initializer_list>
using namespace arcaderecomp_generated;
using Table=std::array<std::uint8_t,36>;
inline bool zeroed(const Table& data) {
    for (auto b:data)if(b)return false;
    return true;
}
"""
def native(body):
    compilers=[p for name in ("g++","clang++") if(p:=shutil.which(name))]
    if not compilers:raise unittest.SkipTest("C++17 compiler unavailable")
    for cc in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-i960-pending-edits-") as d:
            root=Path(d); src=root/"case.cpp"; exe=root/"case"
            src.write_text(PREFIX+body,encoding="utf-8")
            build=subprocess.run(
                [cc,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 "-I",str(ROOT/"runtime"),str(src),"-o",str(exe)],
                capture_output=True,text=True,timeout=45)
            if build.returncode:raise AssertionError(cc+" "+build.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=25)
            if run.returncode:raise AssertionError(cc+" exit "+str(run.returncode)+" "+run.stderr)

class PendingRecordEditTests(unittest.TestCase):
    def test_all_single_vectors_at_all_32_cpu_priorities(self):
        native(r"""
int main(){
    Table blank{};
    for(unsigned v=0u;v<256u;++v) {
        const auto p=draft_kb_pending_post(blank,v);
        if(!kb_pending_vector_valid(v)) {
            if(p.status!=KBPendingEditStatus::invalid_vector ||
               !zeroed(p.resulting_record) || p.candidate_vector)return 1;
            continue;
        }
        if(p.status!=KBPendingEditStatus::applied ||
           p.candidate_vector!=v || p.candidate_priority!=v/8u ||
           !kb_pending_record_valid(p.resulting_record) ||
           !zeroed(blank))return 2;
        const auto& one=p.resulting_record;
        if(one[4u+v/8u]!=(1u<<(v&7u)) ||
           one[(v/8u)/8u]!=(1u<<((v/8u)&7u)))return 3;
        const auto repeated=draft_kb_pending_post(one,v);
        if(repeated.status!=KBPendingEditStatus::already_present ||
           repeated.resulting_record!=one)return 4;
        for(unsigned current=0u;current<32u;++current){
            const auto taken=draft_kb_pending_take(one,current);
            const bool eligible=(v/8u)>current || (v/8u)==31u;
            if(eligible){
                if(taken.status!=KBPendingEditStatus::applied ||
                   taken.candidate_vector!=v ||
                   taken.candidate_priority!=v/8u ||
                   !zeroed(taken.resulting_record))return 5;
            } else {
                if(taken.status!=KBPendingEditStatus::no_eligible_vector ||
                   taken.resulting_record!=one ||
                   taken.candidate_vector)return 6;
            }
        }
    }
    return 0;
}
""")
    def test_same_priority_pairs_tiebreak_and_last_bit(self):
        native(r"""
int main(){
    Table empty{};
    for(unsigned p=1u;p<=31u;++p)for(unsigned a=0u;a<8u;++a)
      for(unsigned b=a+1u;b<8u;++b){
        const unsigned v1=8u*p+a, v2=8u*p+b;
        if(!kb_pending_vector_valid(v1)||!kb_pending_vector_valid(v2))
            continue;
        auto first=draft_kb_pending_post(empty,v1);
        auto second=draft_kb_pending_post(first.resulting_record,v2);
        if(!kb_pending_record_valid(second.resulting_record))return 1;
        auto highest=draft_kb_pending_take(second.resulting_record,0u);
        if(highest.status!=KBPendingEditStatus::applied ||
           highest.candidate_vector!=v2 ||
           highest.resulting_record[4u+p]!=(1u<<a) ||
           (highest.resulting_record[p/8u]&(1u<<(p&7u)))==0u ||
           !kb_pending_record_valid(highest.resulting_record))return 2;
        auto next=draft_kb_pending_take(highest.resulting_record,0u);
        if(next.candidate_vector!=v1 ||
           !zeroed(next.resulting_record))return 3;
    }
    return 0;
}
""")
    def test_full_valid_vector_queue_drains_in_descending_order(self):
        native(r"""
int main(){
    Table queue{};
    unsigned total=0;
    for(unsigned vector=8u;vector<256u;++vector) {
        if(!kb_pending_vector_valid(vector))continue;
        auto x=draft_kb_pending_post(queue,vector);
        if(x.status!=KBPendingEditStatus::applied ||
           !kb_pending_record_valid(x.resulting_record))return 1;
        queue=x.resulting_record;++total;
    }
    if(total!=240u)return 2;
    for(unsigned vector=255u;vector>=8u;--vector){
        if(!kb_pending_vector_valid(vector))continue;
        auto x=draft_kb_pending_take(queue,0u);
        if(x.status!=KBPendingEditStatus::applied ||
           x.candidate_vector!=vector ||
           !kb_pending_record_valid(x.resulting_record))return 3;
        queue=x.resulting_record;
    }
    if(!zeroed(queue) ||
       draft_kb_pending_take(queue,0u).status!=
           KBPendingEditStatus::no_eligible_vector)return 4;
    return 0;
}
""")
    def test_invalid_inputs_never_yield_edited_bytes(self):
        native(r"""
int main(){
    Table empty{};
    auto badPri=draft_kb_pending_take(empty,32u);
    if(badPri.status!=KBPendingEditStatus::invalid_program_priority ||
       !zeroed(badPri.resulting_record))return 1;
    for(unsigned v:{0u,7u,244u,251u,256u,0xffffffffu}){
        auto x=draft_kb_pending_post(empty,v);
        if(x.status!=KBPendingEditStatus::invalid_vector ||
           !zeroed(x.resulting_record) || x.candidate_vector)return 2;
    }
    Table malformed{};malformed[5]=0x10u; // vector12 without priority1
    for(unsigned v:{8u,15u,255u}){
        auto x=draft_kb_pending_post(malformed,v);
        if(x.status!=KBPendingEditStatus::invalid_original_record ||
           !zeroed(x.resulting_record) || x.candidate_vector)return 3;
    }
    for(unsigned priority:{0u,31u}) {
        auto x=draft_kb_pending_take(malformed,priority);
        if(x.status!=KBPendingEditStatus::invalid_original_record ||
           !zeroed(x.resulting_record) || x.candidate_vector)return 4;
    }
    malformed={};malformed[3]=0x80u; // orphan priority31
    if(draft_kb_pending_take(malformed,31u).status!=
       KBPendingEditStatus::invalid_original_record)return 5;
    malformed={};malformed[3]=0x40u;malformed[34]=0x10u; // reserved244
    if(draft_kb_pending_take(malformed,0u).status!=
       KBPendingEditStatus::invalid_original_record)return 6;
    if(draft_kb_pending_post(malformed,252u).status!=
       KBPendingEditStatus::invalid_original_record)return 7;
    return 0;
}
""")
if __name__=="__main__": unittest.main()
