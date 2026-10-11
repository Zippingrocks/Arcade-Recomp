"""ROM-free 80960KB vector priority and Model 2C candidate classification.

Derives vector metadata from primary Intel KB 1988 Chapter 8; only
synthetic pin asserts, not authentic cabinet timing or CPU IRQ delivery.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def native(code):
    cc = [p for name in ("g++", "clang++") if (p := shutil.which(name))]
    if not cc:
        raise unittest.SkipTest("Need GCC or Clang C++17")
    for compiler in cc:
        with tempfile.TemporaryDirectory(prefix="arcade-kb-priority-") as tmp:
            folder = Path(tmp)
            src, output = folder / "priority.cpp", folder / "priority"
            src.write_text(
                '#include "i960_interrupt_priority.hpp"\n'
                '#include "model2c_irq_observation.hpp"\n'
                'using namespace arcaderecomp_generated;\n'
                'using namespace arcaderecomp_model2c;\n'+code,
                encoding="utf-8")
            compile_result = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT / "runtime"), str(src), "-o", str(output)],
                capture_output=True, text=True, timeout=45)
            if compile_result.returncode:
                raise AssertionError(compiler + ": " + compile_result.stderr)
            run = subprocess.run([str(output)], capture_output=True,
                                 text=True, timeout=30)
            if run.returncode:
                raise AssertionError(compiler + " failed: " + run.stderr +
                                     " exit " + str(run.returncode))


class KBVectorPriorityTests(unittest.TestCase):
    def test_exhaustive_vector_and_program_priority_pairs(self):
        native(r"""
int main() {
    for (unsigned vector=0; vector<=255u; ++vector) {
        for (unsigned current=0; current<=31u; ++current) {
            const auto result=review_kb_vector_priority(vector,current);
            if (result.vector!=vector) return 1;
            if (vector<8u) {
                if (result.disposition!=KBVectorDisposition::invalid_vector)
                    return 2;
                continue;
            }
            if (vector>=244u && vector<=251u) {
                if (result.disposition!=KBVectorDisposition::reserved_vector)
                    return 3;
                continue;
            }
            const unsigned level=vector/8u;
            if (result.vector_priority!=level ||
                result.handler_offset!=4u*(vector+1u) ||
                result.pending_vector_byte_offset!=4u+level ||
                result.pending_vector_bit!=(1u<<(vector&7u)) ||
                result.pending_priority_bit!=(std::uint32_t{1u}<<level))
                return 4;
            const bool eligible=(level==31u || level>current);
            if ((result.disposition==
                 KBVectorDisposition::higher_priority_candidate)!=eligible)
                return 5;
            if ((result.disposition==
                 KBVectorDisposition::would_post_pending)==eligible)
                return 6;
        }
    }
    if(review_kb_vector_priority(256u,0u).disposition!=
       KBVectorDisposition::invalid_vector)return 7;
    try{(void)review_kb_vector_priority(8u,32u);return 8;}
    catch(const std::out_of_range&){}
    if(review_kb_vector_priority(8u,0u).handler_offset!=36u ||
       review_kb_vector_priority(243u,0u).handler_offset!=976u ||
       review_kb_vector_priority(255u,31u).handler_offset!=1024u ||
       review_kb_vector_priority(255u,31u).disposition!=
            KBVectorDisposition::higher_priority_candidate)return 9;
    return 0;
}
""")

    def test_hotd1_icr_direct_vectors_and_explicit_current_priority(self):
        native(r"""
int main() {
    CPU cpu{};
    cpu.interrupt_control_register=0x0f0e0d0cu;
    PartialIRQRegisters board{};
    board.request_enable_update(0x0c07u);
    board.advance_cpu_cycles(2u);
    for (unsigned bit : {0u, 1u, 2u, 10u})
        board.inject_enabled_source_for_test(bit);
    const auto snapshot=observe_model2c_irq(board,cpu);
    if(snapshot.asserted_line_count!=4u ||
       snapshot.direct_candidate_count!=4u)return 1;
    const auto low=review_model2c_irq_priorities(snapshot,0u);
    if(low.higher_priority_candidates!=4u ||
       low.would_post_pending || low.invalid_or_reserved_vectors ||
       low.non_direct_asserted_pins)return 2;
    const auto same=review_model2c_irq_priorities(snapshot,1u);
    if(same.higher_priority_candidates ||
       same.would_post_pending!=4u ||
       same.invalid_or_reserved_vectors)return 3;
    for (unsigned pin=0; pin<4u; ++pin) {
        if(!low.pins[pin].evaluated || !same.pins[pin].evaluated ||
           low.pins[pin].vector.vector!=12u+pin ||
           low.pins[pin].vector.vector_priority!=1u ||
           low.pins[pin].vector.pending_vector_byte_offset!=5u ||
           low.pins[pin].vector.pending_priority_bit!=2u ||
           low.pins[pin].vector.pending_vector_bit!=(1u<<(4u+pin)) ||
           same.pins[pin].vector.disposition!=
                KBVectorDisposition::would_post_pending)
            return 4;
    }
    // Merely inspecting possible vectors MUST NEVER mutate the board or CPU.
    if(board.request()!=0x407u || board.enable()!=0xc07u ||
       cpu.interrupt_control_register!=0x0f0e0d0cu ||
       cpu.frame_depth!=0u || cpu.ip!=0u || cpu.prcb_loaded)return 5;
    try{(void)review_model2c_irq_priorities(snapshot,32u);return 6;}
    catch(const std::out_of_range&){}
    return 0;
}
""")

    def test_reset_multiplexing_and_reserved_vectors_not_delivered(self):
        native(r"""
int main() {
    PartialIRQRegisters board{};
    board.request_enable_update(0x0c07u);
    board.advance_cpu_cycles(2u);
    for(unsigned bit : {0u,1u,2u,10u})
        board.inject_enabled_source_for_test(bit);
    CPU cpu{}; // Intel reset ICR = FF000000
    auto reset=review_model2c_irq_priorities(observe_model2c_irq(board,cpu),0u);
    if(reset.non_direct_asserted_pins!=3u ||
       reset.invalid_or_reserved_vectors!=1u ||
       reset.higher_priority_candidates!=0u)return 1;
    if(reset.pins[0].evaluated||reset.pins[2].evaluated||
       reset.pins[3].evaluated||!reset.pins[1].evaluated||
       reset.pins[1].vector.disposition!=
           KBVectorDisposition::invalid_vector)return 2;

    cpu.interrupt_control_register=0x1014f50cu; // vectors 12,245,20,16
    auto configured=review_model2c_irq_priorities(
        observe_model2c_irq(board,cpu),1u);
    if(configured.non_direct_asserted_pins!=0u ||
       configured.invalid_or_reserved_vectors!=1u ||
       configured.higher_priority_candidates!=2u ||
       configured.would_post_pending!=1u)return 3;
    if(configured.pins[1].vector.disposition!=
        KBVectorDisposition::reserved_vector)return 4;

    cpu.interrupt_control_register=0x0c14ff10u; // 16,255,20,12
    auto highest=review_model2c_irq_priorities(
        observe_model2c_irq(board,cpu),31u);
    if(highest.higher_priority_candidates!=1u ||
       highest.pins[1].vector.vector_priority!=31u ||
       highest.pins[1].vector.disposition!=
          KBVectorDisposition::higher_priority_candidate ||
       highest.would_post_pending!=3u)return 5;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
