"""Synthetic-only serialized Intel KB pending table transactions.

No physical Intel LOCK signal, Model 2C bus, original ROM bytes,
CPU interrupt acceptance, memory mappings, IRQ frames, or CPU MODPC.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

PREFIX = r"""
#include "i960_pending_transaction_synthetic.hpp"
#include "i960_process_controls.hpp"
#include <array>
#include <atomic>
#include <cstdint>
#include <thread>
#include <vector>
using namespace arcaderecomp_generated;
using Status = KBSyntheticTransactionStatus;
using Table = SyntheticKBPendingTable;
"""


def run_native(body):
    compilers = [x for name in ("g++","clang++") if (x := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("No GCC/Clang C++17 compiler")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-kb-synthetic-transaction-") as d:
            folder=Path(d)
            src=folder/"test.cpp"
            exe=folder/"test"
            src.write_text(PREFIX+body,encoding="utf-8")
            build=subprocess.run(
                [compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                 "-pthread","-fsanitize=undefined","-fno-sanitize-recover=all",
                 "-I",str(ROOT/"runtime"),str(src),"-o",str(exe)],
                capture_output=True,text=True,timeout=45)
            if build.returncode:
                raise AssertionError(compiler+": "+build.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
            if run.returncode:
                raise AssertionError(
                    compiler+" exit "+str(run.returncode)+": "+run.stdout+run.stderr)


class KBSyntheticTransactions(unittest.TestCase):
    def test_concurrent_post_no_lost_bit_or_double_revision(self):
        run_native(r"""
int main() {
    Table table{};
    std::atomic<unsigned> errors{0u};
    std::vector<std::thread> workers;
    // Twelve concurrent agents, each posts 16 unique vectors twice.
    // All 192 vectors 8..199 are valid. No duplicate may advance version.
    for(unsigned worker=0;worker<12u;++worker)
        workers.emplace_back([&table,&errors,worker] {
            for(unsigned i=0;i<16u;++i) {
                const unsigned vector=8u+worker*16u+i;
                const auto first=table.post_for_test(vector);
                const auto again=table.post_for_test(vector);
                if(first.status!=Status::applied ||
                   again.status!=Status::already_present ||
                   again.vector || again.priority)
                    ++errors;
            }
        });
    for(auto& worker:workers)worker.join();
    if(errors.load()!=0u)return 1;
    const auto snap=table.diagnostic_snapshot_for_test();
    if(snap.revision!=192u || !kb_pending_record_valid(snap.record))return 2;
    const auto reviewed=review_kb_pending_snapshot(snap.record,0u);
    if(reviewed.vectors_set!=192u ||
       reviewed.highest_eligible_vector!=199u)return 3;

    // Concurrent takes must produce exactly one successful consumption
    // per vector even though all workers can select the same priority.
    workers.clear();
    for(unsigned worker=0;worker<12u;++worker)
        workers.emplace_back([&table,&errors] {
            for(unsigned i=0;i<16u;++i) {
                auto take=table.take_for_test(0u);
                if(take.status!=Status::applied || take.vector<8u ||
                   take.vector>199u)
                    ++errors;
            }
        });
    for(auto& worker:workers)worker.join();
    if(errors.load()!=0u)return 4;
    const auto empty=table.diagnostic_snapshot_for_test();
    if(empty.revision!=384u ||
       !kb_pending_record_valid(empty.record) ||
       review_kb_pending_snapshot(empty.record,0u).vectors_set)return 5;
    auto none=table.take_for_test(0u);
    if(none.status!=Status::no_eligible_vector ||
       none.vector || none.priority || none.committed_revision!=384u)return 6;
    return 0;
}
""")

    def test_commit_refusal_preserves_record_revision_and_candidate_privacy(self):
        run_native(r"""
int main() {
    Table table{};
    auto first=table.post_for_test(12u);
    if(first.status!=Status::applied || first.vector!=12u ||
       first.priority!=1u || first.committed_revision!=1u)return 1;
    const auto before=table.diagnostic_snapshot_for_test();
    table.set_commit_allowed_for_test(false);
    auto refused=table.post_for_test(255u);
    if(refused.status!=Status::commit_refused ||
       refused.vector || refused.priority ||
       refused.committed_revision!=1u)return 2;
    refused=table.take_for_test(0u);
    if(refused.status!=Status::commit_refused ||
       refused.vector || refused.priority ||
       refused.committed_revision!=1u)return 3;
    const auto after=table.diagnostic_snapshot_for_test();
    if(after.record!=before.record || after.revision!=before.revision ||
       !kb_pending_record_valid(after.record))return 4;
    // Idempotent operations do not write or fake another revision.
    if(table.post_for_test(12u).status!=Status::already_present ||
       table.diagnostic_snapshot_for_test().revision!=1u)return 5;
    table.set_commit_allowed_for_test(true);
    auto complete=table.take_for_test(0u);
    if(complete.status!=Status::applied || complete.vector!=12u ||
       complete.committed_revision!=2u)return 6;
    return 0;
}
""")

    def test_corrupt_input_is_not_repaired_implicitly_or_committed(self):
        run_native(r"""
int main() {
    Table::Record bytes{};
    bytes[5]=0x10u;  // vector 12 without the priority-1 bit
    Table corrupted(bytes);
    auto before=corrupted.diagnostic_snapshot_for_test();
    auto a=corrupted.post_for_test(255u);
    auto b=corrupted.take_for_test(0u);
    if(a.status!=Status::invalid_original_record ||
       b.status!=Status::invalid_original_record ||
       a.vector || b.vector || a.priority || b.priority ||
       a.committed_revision || b.committed_revision)return 1;
    const auto after=corrupted.diagnostic_snapshot_for_test();
    if(after.record!=before.record || after.revision || before.revision)
        return 2;
    auto invalid=corrupted.post_for_test(244u);
    if(invalid.status!=Status::invalid_vector ||
       invalid.vector || invalid.priority)return 3;
    Table empty;
    if(empty.take_for_test(32u).status!=Status::invalid_program_priority)
        return 4;
    for(unsigned v:{0u,7u,244u,251u,256u})
        if(empty.post_for_test(v).status!=Status::invalid_vector)
            return 5;
    return 0;
}
""")

    def test_synthetic_commit_does_not_change_native_modpc_boundary(self):
        run_native(r"""
int main() {
    CPU cpu{};
    cpu.ip=0x40u;
    cpu.process_controls=0x001f2002u;
    cpu.known_process_controls=cpu.process_controls;
    cpu.process_controls_priority_known=true;
    cpu.prcb_loaded=true;
    cpu.reinitialize_count=1u; // synthetic, not Intel hardware evidence
    cpu.r[17]=0u;
    Table table;
    auto committed=table.post_for_test(255u);
    if(committed.status!=Status::applied)return 1;
    // An atomic C++ mutex is NOT Intel's LOCK protocol; MODPC lowering
    // and IRQ service must remain blocked in the native CPU runtime.
    if(kb_modpc_checked(cpu,0x001f0000u,17u) ||
       cpu.stop_code!=StopCode::modpc_pending_interrupt_check_unimplemented ||
       cpu.ip!=0x40u || cpu.process_controls!=0x001f2002u ||
       cpu.r[17]!=0u)return 2;
    return 0;
}
""")


if __name__=="__main__":
    unittest.main()
