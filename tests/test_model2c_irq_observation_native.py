"""ROM-free Model 2C board-pin and Intel 80960KB ICR observation tests.

Only provisional, explicit synthetic IRQ events are used. This module must
NEVER deliver a CPU interrupt or authenticate physical Sega timing.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def compile_and_run(source):
    compilers = [p for name in ("g++", "clang++") if (p := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("C++17 compiler unavailable")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-irq-snapshot-") as d:
            work = Path(d)
            src, exe = work / "case.cpp", work / "case"
            src.write_text('#include "model2c_irq_observation.hpp"\n'
                           'using namespace arcaderecomp_model2c;\n'
                           'using namespace arcaderecomp_generated;\n'
                           + source, encoding="utf-8")
            result = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                 "-Werror", "-fsanitize=undefined",
                 "-fno-sanitize-recover=all", "-I", str(ROOT / "runtime"),
                 str(src), "-o", str(exe)],
                capture_output=True, text=True, timeout=45)
            if result.returncode:
                raise AssertionError(compiler + ": " + result.stderr)
            run = subprocess.run([str(exe)], capture_output=True,
                                 text=True, timeout=20)
            if run.returncode:
                raise AssertionError(compiler + ": exit "
                                     + str(run.returncode) + ": " + run.stderr)


class Model2CIRQSnapshotTests(unittest.TestCase):
    def test_delayed_enable_explicit_requests_and_reset_mux(self):
        compile_and_run(r"""
int main() {
    CPU cpu{};
    PartialIRQRegisters board{};
    const auto at_reset = observe_model2c_irq(board, cpu);
    if(at_reset.asserted_line_count || at_reset.direct_candidate_count ||
       at_reset.unresolved_non_vector_count ||
       at_reset.intel_icr != 0xff000000u)return 1;
    if(at_reset.pins[0].role!=KBPinRole::iac_notification ||
       at_reset.pins[2].role!=KBPinRole::external_intr ||
       at_reset.pins[3].role!=KBPinRole::external_inta)return 2;

    board.request_enable_update(0x0c05u); // bits 0, 2, 10, 11
    board.advance_cpu_cycles(1u);
    board.inject_enabled_source_for_test(2u); // still disabled
    const auto pending = observe_model2c_irq(board, cpu);
    if(pending.request_register || pending.enabled_register ||
       pending.queued_enable_cycles!=1u)return 3;
    board.advance_cpu_cycles(1u);
    for (unsigned bit : {0u,2u,10u})
        board.inject_enabled_source_for_test(bit);
    const auto active = observe_model2c_irq(board, cpu);
    if(active.request_register!=0x405u ||
       active.enabled_register!=0xc05u ||
       active.asserted_line_count!=3u ||
       active.unresolved_non_vector_count!=3u ||
       active.direct_candidate_count!=0u)return 4;
    if(active.pins[0].requested_source_bits!=1u ||
       active.pins[2].requested_source_bits!=4u ||
       active.pins[3].requested_source_bits!=0x400u)return 5;
    cpu.interrupt_control_register=0x0f0e0d0cu; // observed HOTD1 host ICR
    const auto routed = observe_model2c_irq(board, cpu);
    if(routed.asserted_line_count!=3u ||
       routed.direct_candidate_count!=3u ||
       routed.unresolved_non_vector_count!=0u)return 6;
    for(unsigned pin=0u;pin<4u;++pin) {
        if(routed.pins[pin].configured_vector!=12u+pin ||
           routed.pins[pin].role!=KBPinRole::direct_vector)return 7;
    }
    // Only the provisional Sega pending register is acknowledged.
    board.acknowledge(~std::uint32_t(4u));
    if(observe_model2c_irq(board,cpu).pins[2].asserted)return 8;
    if(cpu.interrupt_control_register!=0x0f0e0d0cu)return 9;
    return 0;
}
""")

    def test_exhaustive_synthetic_12bit_request_grouping_no_state_mutation(self):
        compile_and_run(r"""
int main() {
    CPU cpu{};
    cpu.interrupt_control_register=0x0f0e0d0cu;
    PartialIRQRegisters board{};
    board.request_enable_update(0xfffu);
    board.advance_cpu_cycles(2u);
    constexpr std::uint32_t masks[4]={1u,2u,0x3fcu,0xc00u};
    for (std::uint32_t bits=0u;bits<4096u;++bits) {
        board.acknowledge(0u);
        for (unsigned bit=0u;bit<12u;++bit)
            if (bits & (1u<<bit))
                board.inject_enabled_source_for_test(bit);
        const auto first=observe_model2c_irq(board,cpu);
        const auto second=observe_model2c_irq(board,cpu);
        unsigned count=0u;
        for (unsigned pin=0u;pin<4u;++pin) {
            const auto expected=bits & masks[pin];
            const auto& a=first.pins[pin];
            const auto& b=second.pins[pin];
            if(a.requested_source_bits!=expected ||
               a.asserted!=(expected!=0u) ||
               a.direct_vector_candidate!=(expected!=0u) ||
               a.configured_vector!=12u+pin ||
               a.role!=KBPinRole::direct_vector ||
               a.requested_source_bits!=b.requested_source_bits ||
               a.configured_vector!=b.configured_vector)return 1;
            if(expected)++count;
        }
        if(first.request_register!=bits || board.request()!=bits ||
           first.asserted_line_count!=count ||
           first.direct_candidate_count!=count ||
           first.unresolved_non_vector_count!=0u ||
           board.enable()!=0xfffu ||
           cpu.interrupt_control_register!=0x0f0e0d0cu)return 2;
    }
    try{(void)PartialIRQRegisters::pin_source_mask(4u);return 3;}
    catch(const std::out_of_range&){}
    return 0;
}
""")

    def test_int0_iac_and_int2_intr_role_never_claim_direct_vector(self):
        compile_and_run(r"""
int main() {
    CPU cpu{}; // documented KB reset ICR
    PartialIRQRegisters board{};
    board.request_enable_update(0x0c05u);
    board.advance_cpu_cycles(2u);
    for(unsigned bit : {0u,2u,10u})board.inject_enabled_source_for_test(bit);
    const auto a=observe_model2c_irq(board,cpu);
    if(a.direct_candidate_count || a.unresolved_non_vector_count!=3u)return 1;
    if(a.pins[0].role!=KBPinRole::iac_notification ||
       a.pins[0].direct_vector_candidate ||
       a.pins[2].role!=KBPinRole::external_intr ||
       a.pins[3].role!=KBPinRole::external_inta)return 2;
    cpu.interrupt_control_register=0xff000e00u;
    const auto b=observe_model2c_irq(board,cpu);
    if(b.direct_candidate_count || b.unresolved_non_vector_count!=3u)return 3;
    cpu.interrupt_control_register=0x00020001u; // INT0=1 INT2=2
    const auto c=observe_model2c_irq(board,cpu);
    if(c.direct_candidate_count!=3u ||
       c.pins[0].configured_vector!=1u ||
       c.pins[2].configured_vector!=2u ||
       c.pins[3].configured_vector!=0u ||
       c.unresolved_non_vector_count)return 4;
    return 0;
}
""")


if __name__=="__main__":
    unittest.main()
