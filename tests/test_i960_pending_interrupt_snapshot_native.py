"""ROM-free Intel 80960KB pending-table offline validation.

No actual Intel atomic interrupt-table reads/writes, IRQ service or
original HOTD1 ROM/cabinet inputs. Synthetic records are the only fixtures.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

HEADER = r"""
#include "i960_pending_interrupt_snapshot.hpp"
#include "i960_process_controls.hpp"
#include <array>
#include <cstdint>
#include <stdexcept>
using namespace arcaderecomp_generated;

using Table = std::array<std::uint8_t, 36>;
inline void add(Table& t, unsigned vector) {
    t[4u+vector/8u] |= static_cast<std::uint8_t>(1u<<(vector&7u));
    const std::uint32_t bit = std::uint32_t{1u} << (vector/8u);
    for(unsigned i=0;i<4u;++i)
        t[i]|=static_cast<std::uint8_t>((bit>>(8u*i))&0xffu);
}
"""


def run_native(body):
    compilers = [p for name in ("g++", "clang++") if (p := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("C++17 compiler unavailable")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-kb-pending-") as d:
            folder = Path(d)
            source, executable = folder/"test.cpp", folder/"test"
            source.write_text(HEADER + body, encoding="utf-8")
            build = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT/"runtime"), str(source), "-o",
                 str(executable)], capture_output=True, text=True, timeout=45)
            if build.returncode:
                raise AssertionError(compiler+": "+build.stderr)
            run = subprocess.run([str(executable)], capture_output=True,
                                 text=True, timeout=30)
            if run.returncode:
                raise AssertionError(compiler+": exit "+
                                     str(run.returncode)+": "+run.stderr)


class KBPendingSnapshotTests(unittest.TestCase):
    def test_exhaustive_single_vector_all_priorities_and_reserved(self):
        run_native(r"""
int main() {
    for (unsigned v=0; v<256u; ++v) {
        Table data{}; add(data,v);
        for (unsigned current=0;current<=31u;++current) {
            const auto result=review_kb_pending_snapshot(data,current);
            const bool forbidden=(v<8u)||(v>=244u&&v<=251u);
            if(forbidden) {
                if(result.status!=KBPendingSnapshotStatus::reserved_vector_present)
                    return 1;
                continue;
            }
            if(result.vectors_set!=1u ||
               result.reported_priority_mask!=(std::uint32_t{1u}<<(v/8u)) ||
               result.derived_priority_mask!=result.reported_priority_mask)
                return 2;
            const bool eligible=v/8u>current || v/8u==31u;
            if(eligible) {
                if(result.status!=KBPendingSnapshotStatus::eligible_candidate_only ||
                   result.highest_eligible_vector!=v ||
                   result.highest_eligible_priority!=v/8u ||
                   result.eligible_count!=1u)return 3;
            } else {
                if(result.status!=KBPendingSnapshotStatus::no_eligible_vector ||
                   result.eligible_count!=0u)return 4;
            }
        }
    }
    try{(void)review_kb_pending_snapshot(Table{},32u);return 5;}
    catch(const std::out_of_range&){}
    return 0;
}
""")

    def test_mixed_pending_priorities_highest_vector_wins_and_no_mutation(self):
        run_native(r"""
int main() {
    Table data{};
    for(unsigned v : {8u,15u,16u,23u,75u,243u,252u,255u})add(data,v);
    const auto untouched=data;
    for(unsigned current=0;current<=31u;++current) {
        auto review=review_kb_pending_snapshot(data,current);
        if(review.status!=KBPendingSnapshotStatus::eligible_candidate_only ||
           review.highest_eligible_vector!=255u ||
           review.highest_eligible_priority!=31u ||
           review.vectors_set!=8u)return 1;
    }
    if(data!=untouched)return 2;
    data[4u+255u/8u] &=
        static_cast<std::uint8_t>(~(1u<<(255u&7u)));
    auto tie=review_kb_pending_snapshot(data,30u);
    if(tie.status!=KBPendingSnapshotStatus::eligible_candidate_only ||
       tie.highest_eligible_vector!=252u)return 3;
    data[4u+252u/8u] &=
        static_cast<std::uint8_t>(~(1u<<(252u&7u)));
    data[3] &= static_cast<std::uint8_t>(~0x80u);
    auto priority30=review_kb_pending_snapshot(data,29u);
    if(priority30.status!=KBPendingSnapshotStatus::eligible_candidate_only ||
       priority30.highest_eligible_vector!=243u)return 4;
    auto blocked=review_kb_pending_snapshot(data,30u);
    if(blocked.status!=KBPendingSnapshotStatus::no_eligible_vector ||
       blocked.eligible_count!=0u)return 5;
    return 0;
}
""")

    def test_inconsistent_bitmaps_and_reserved_never_claim_no_pending(self):
        run_native(r"""
int main() {
    Table empty{};
    if(review_kb_pending_snapshot(empty,0u).status!=
       KBPendingSnapshotStatus::no_eligible_vector)return 1;
    Table one{};add(one,14u);
    one[0]=0u; // priority bit missing
    if(review_kb_pending_snapshot(one,0u).status!=
       KBPendingSnapshotStatus::inconsistent_priority_mask)return 2;
    one={};add(one,14u);
    one[3]=0x80u; // priority 31 falsely posted
    if(review_kb_pending_snapshot(one,31u).status!=
       KBPendingSnapshotStatus::inconsistent_priority_mask)return 3;
    one={};add(one,244u);
    if(review_kb_pending_snapshot(one,0u).status!=
       KBPendingSnapshotStatus::reserved_vector_present)return 4;
    one={};add(one,7u);
    if(review_kb_pending_snapshot(one,0u).status!=
       KBPendingSnapshotStatus::reserved_vector_present)return 5;
    one={};add(one,251u);
    if(review_kb_pending_snapshot(one,0u).status!=
       KBPendingSnapshotStatus::reserved_vector_present)return 6;
    one={};add(one,252u);
    if(review_kb_pending_snapshot(one,31u).status!=
       KBPendingSnapshotStatus::eligible_candidate_only)return 7;
    return 0;
}
""")

    def test_read_only_snapshot_does_not_bypass_modpc_pending_check(self):
        run_native(r"""
int main() {
    CPU cpu{};
    cpu.ip=0x40u;
    cpu.process_controls=(31u<<16u)|0x2002u;
    cpu.known_process_controls=cpu.process_controls;
    cpu.process_controls_priority_known=true;
    cpu.prcb_loaded=true;
    cpu.reinitialize_count=1u;  // synthetic provenance only
    cpu.r[17]=0u;
    Table zero{};
    const auto scan=review_kb_pending_snapshot(zero,0u);
    if(scan.status!=KBPendingSnapshotStatus::no_eligible_vector)return 1;
    // Even with an invented zero-record, real MODPC cannot be allowed to
    // reduce priority: Intel's atomic table transaction is still absent.
    if(kb_modpc_checked(cpu,0x001f0000u,17u))return 2;
    if(cpu.stop_code!=StopCode::modpc_pending_interrupt_check_unimplemented ||
       cpu.stop_ip!=0x40u || cpu.ip!=0x40u ||
       cpu.process_controls!=((31u<<16u)|0x2002u) ||
       cpu.r[17]!=0u)return 3;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
