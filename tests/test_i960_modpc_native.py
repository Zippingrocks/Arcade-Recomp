"""Intel 80960KB MODPC 655h: safe AOT subset with refusal tests.

Synthetic instruction words only; no original HOTD1 ROM bytes or unverified
IRQ delivery. Primary Intel KB reference: 1988 manual, MODPC pp. 11-82..83.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def regop(src1=17, mask_src=17, dst=18, literal1=False, literal2=False):
    return ((0x650 << 20) | (5 << 7) | src1 |
            (mask_src << 14) | (dst << 19) |
            (int(literal1) << 11) | (int(literal2) << 12))


def native(source):
    compilers = [c for n in ("g++", "clang++") if (c := shutil.which(n))]
    if not compilers:
        raise unittest.SkipTest("C++17 compiler unavailable")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-modpc-kb-") as d:
            folder = Path(d)
            src, exe = folder / "test.cpp", folder / "test"
            src.write_text(source, encoding="utf-8")
            build = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT / "runtime"), str(src), "-o", str(exe)
            ], capture_output=True, text=True, timeout=45)
            if build.returncode:
                raise AssertionError(compiler + ": " + build.stderr)
            result = subprocess.run([str(exe)], capture_output=True,
                                    text=True, timeout=30)
            if result.returncode:
                raise AssertionError(compiler + ": code " +
                                     str(result.returncode) + ": " +
                                     result.stdout + result.stderr)


class NativeMODPCTests(unittest.TestCase):
    def test_decoder_and_fail_closed_operand_modes(self):
        word = regop()
        d = decode(struct.pack("<I", word), 0)
        self.assertEqual((d.form, d.mnemonic, d.operands),
                         ("REG", "modpc", ("g1", "g1", "g2")))
        for invalid in (0x20, 0x40, 0x2000):
            code, report = emit_cpp(struct.pack("<2I",
                                                  word | invalid, 0xffffffff),
                                     0, 8)
            self.assertIn(0, report.unsupported, code)

    def test_native_aot_read_priority_and_rejected_transitions(self):
        # All instruction words are invented synthetic fixtures.
        words = [
            regop(mask_src=0, literal2=True),  # read PC, mask=0
            regop(),                            # g1 mask, g2 requested
            regop(src1=17, mask_src=17, dst=17),# mask/dst alias
            regop(mask_src=0, literal2=True),  # read after modifying
            0xffffffff,
        ]
        code, report = emit_cpp(struct.pack("<" + "I"*len(words), *words),
                                0, 32)
        self.assertEqual(report.translated, 4)
        self.assertEqual(report.unsupported, (16,))
        self.assertIn("kb_modpc_checked", code)
        fixture = r"""
using namespace arcaderecomp_generated;

static CPU initialized(unsigned priority, bool supervisor=true) {
    CPU cpu{};
    cpu.process_controls=(priority<<16u) |
                         (supervisor?2u:0u) | 0x2000u;
    cpu.known_process_controls=cpu.process_controls;
    cpu.process_controls_priority_known=true;
    cpu.prcb_loaded=true;
    cpu.reinitialize_count=1u;  // synthetic modeled-IAC provenance
    cpu.ip=0u;
    return cpu;
}

int main() {
    Bus bus{};
    for(unsigned priority=0;priority<=31u;++priority) {
        CPU cpu=initialized(priority);
        cpu.r[18]=0xdeadbeefu;
        cpu.cc=4; cpu.cc_defined=false;
        if(!step(cpu,bus) || cpu.ip!=4u ||
           cpu.r[18]!=((priority<<16u)|0x2002u) ||
           cpu.cc!=4 || cpu.cc_defined)return 1;

        for(unsigned later=priority;later<=31u;++later) {
            cpu=initialized(priority);
            cpu.ip=4u;
            cpu.r[17]=0x001f0000u; // allowed priority mask
            cpu.r[18]=(later<<16u) | 0xa5a50000u;
            const auto original=cpu.process_controls;
            if(!step(cpu,bus)||cpu.ip!=8u ||
               cpu.process_controls!=((later<<16u)|0x2002u) ||
               cpu.known_process_controls!=cpu.process_controls ||
               cpu.r[18]!=original ||
               !kb_known_cpu_program_priority(cpu) ||
               *kb_known_cpu_program_priority(cpu)!=later)return 2;
        }

        if(priority>0u) {
            cpu=initialized(priority);
            cpu.ip=4u;
            cpu.r[17]=0x001f0000u;
            cpu.r[18]=0u;
            const auto original=cpu.process_controls;
            if(step(cpu,bus) ||
               cpu.stop_code!=
                  StopCode::modpc_pending_interrupt_check_unimplemented ||
               cpu.stop_ip!=4u || cpu.ip!=4u ||
               cpu.process_controls!=original ||
               cpu.r[18]!=0u ||
               !kb_known_cpu_program_priority(cpu) ||
               *kb_known_cpu_program_priority(cpu)!=priority)return 3;
        }
    }
    // A read-only MODPC is available even in synthetic user mode.
    auto cpu=initialized(5u,false);
    cpu.r[18]=0xffffffffu;
    if(!step(cpu,bus)||cpu.r[18]!=(5u<<16u|0x2000u))return 4;

    // Nonzero MODPC in user mode needs architected type-mismatch fault.
    cpu=initialized(5u,false);
    cpu.ip=4u;
    cpu.r[17]=0x001f0000u;
    cpu.r[18]=0x00100000u;
    if(step(cpu,bus) ||
       cpu.stop_code!=StopCode::modpc_type_mismatch_unimplemented ||
       cpu.r[18]!=0x00100000u ||
       cpu.process_controls!=(5u<<16u|0x2000u))return 5;

    // Neither a host zero-initialized PC nor arbitrary PC bytes imply
    // that MODPC may read the actual hardware process-controls register.
    cpu=CPU{}; cpu.r[18]=0xfeedfaceu;
    if(step(cpu,bus)||cpu.stop_code!=StopCode::undefined_process_controls ||
       cpu.r[18]!=0xfeedfaceu)return 6;

    // Even writing the original value into an unsupported field is refused.
    cpu=initialized(5u);
    cpu.ip=4u;
    cpu.r[17]=1u;cpu.r[18]=cpu.process_controls;
    if(step(cpu,bus) ||
       cpu.stop_code!=StopCode::modpc_unsupported_fields ||
       cpu.process_controls!=(5u<<16u|0x2002u))return 7;

    // Aliasing mask and dst: snapshot mask BEFORE old-PC replaces dst.
    cpu=initialized(3u);
    cpu.ip=8u;
    cpu.r[17]=0u; // mask 0 => read-only even when aliasing
    if(!step(cpu,bus) ||
       cpu.r[17]!=(3u<<16u|0x2002u) ||
       cpu.ip!=12u)return 8;

    // Next read reflects previously committed priority updates, not a
    // stale reinitialization snapshot.
    cpu=initialized(4u);
    cpu.ip=4u;cpu.r[17]=0x001f0000u;cpu.r[18]=7u<<16u;
    if(!step(cpu,bus))return 9;
    cpu.ip=12u;cpu.r[18]=0u;
    if(!step(cpu,bus)||cpu.r[18]!=(7u<<16u|0x2002u))return 10;
    return 0;
}
"""
        native(code+"\n"+fixture)

    def test_reinitialize_known_priority_requires_pending_scan_on_lowering(self):
        code = r"""
#include "i960_reinitialize.hpp"
#include "i960_process_controls.hpp"
#include <unordered_map>
using namespace arcaderecomp_generated;
struct Mem {std::unordered_map<std::uint32_t,std::uint32_t> w;};
inline std::uint32_t rd(void* context,std::uint32_t a) {
    return static_cast<Mem*>(context)->w.at(a);
}
int main() {
    CPU cpu{};
    if(!frame_init(cpu,0x00510200u,0u))return 1;
    if(kb_modpc_checked(cpu,0u,18u) ||
       cpu.stop_code!=StopCode::undefined_process_controls)return 2;
    Mem m{};
    constexpr auto P=0x00510e00u;
    m.w[P+4u]=0cu;m.w[P+20u]=0x00510800u;
    m.w[P+24u]=0x00510400u;m.w[P+32u]=0x1ffu;
    m.w[P+36u]=0x27fu;m.w[P+40u]=0x210u;m.w[P+44u]=0u;
    Bus b{};b.ctx=&m;b.read32=&rd;
    cpu.pending_iac_valid=true;
    cpu.pending_iac[0]=0x93000000u;
    cpu.pending_iac[1]=0u;cpu.pending_iac[2]=P;
    cpu.pending_iac[3]=0x40u;
    if(!perform_iac_93_reinitialize(cpu,b))return 3;
    if(!kb_modpc_checked(cpu,0u,18u) ||
       cpu.r[18]!=0x001f2002u)return 4;
    cpu.r[17]=0x001f0000u;cpu.r[18]=0u;
    if(kb_modpc_checked(cpu,cpu.r[17],18u) ||
       cpu.stop_code!=
           StopCode::modpc_pending_interrupt_check_unimplemented ||
       cpu.process_controls!=0x001f2002u || cpu.r[18]!=0u)return 5;
    return 0;
}
"""
        native(code)


if __name__ == "__main__":
    unittest.main()
