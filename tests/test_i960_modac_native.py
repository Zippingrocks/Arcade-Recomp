"""Intel KB MODAC and coherent AC snapshots, using synthetic code only."""
from pathlib import Path
import random
import shutil
import struct
import subprocess
import tempfile
import unittest

from arcaderecomp.i960 import decode
from arcaderecomp.i960_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]
FIELDS = 0xFF1F917F
FORMS = (
    (16, 17, 18, False, False),
    (16, 17, 16, False, False),
    (16, 17, 17, False, False),
    (16, 16, 18, False, False),
    (16, 16, 16, False, False),
    (31, 17, 18, True, False),
    (16, 29, 18, False, True),
    (31, 29, 18, True, True),
)


def regop(opcode=0x645, src1=16, src2=17, dst=18,
          literal1=False, literal2=False):
    return (((opcode & 0xFF0) << 20) | ((opcode & 15) << 7) |
            src1 | (src2 << 14) | (dst << 19) |
            (int(literal1) << 11) | (int(literal2) << 12))


def native(source):
    compilers = [p for n in ("g++", "clang++") if (p := shutil.which(n))]
    if not compilers:
        raise unittest.SkipTest("C++17 compiler unavailable")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-modac-") as folder:
            src, exe = Path(folder)/"test.cpp", Path(folder)/"test"
            src.write_text(source, encoding="utf-8")
            built = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT/"runtime"), str(src), "-o", str(exe)
            ], capture_output=True, text=True, timeout=45)
            if built.returncode:
                raise AssertionError(compiler+": "+built.stderr)
            result = subprocess.run([str(exe)], capture_output=True,
                                    text=True, timeout=30)
            if result.returncode:
                raise AssertionError(
                    f"{compiler}: exit {result.returncode}: "
                    f"{result.stdout}{result.stderr}")


class NativeMODACTests(unittest.TestCase):
    def test_decode_and_reject_special_modes(self):
        instruction = decode(struct.pack("<I", regop()), 0)
        self.assertEqual((instruction.mnemonic, instruction.operands),
                         ("modac", ("g0", "g1", "g2")))
        literal = decode(struct.pack("<I", regop(
            src1=31, src2=29, literal1=True, literal2=True)), 0)
        self.assertEqual(literal.operands, ("31", "29", "g2"))
        for invalid in (0x20, 0x40, 0x2000):
            _, report = emit_cpp(struct.pack("<2I", regop() | invalid,
                                             0xFFFFFFFF), 0, 8)
            self.assertIn(0, report.unsupported)

    def test_native_masks_literals_and_all_source_destination_aliases(self):
        words = [regop(0x645, *f) for f in FORMS] + [0xFFFFFFFF]
        code, report = emit_cpp(struct.pack("<"+"I"*len(words), *words),
                                0, 64)
        self.assertEqual(report.translated, len(FORMS))
        self.assertEqual(report.unsupported, (len(FORMS)*4,))
        rng = random.Random(0x645960)
        rows = [(a, b, c) for a in (0, 0xFFFFFFFF, FIELDS)
                for b in (0, 0xFFFFFFFF, FIELDS)
                for c in (0, FIELDS)]
        # Each implemented and reserved bit is independently set/cleared.
        rows += [(1 << bit, source, old) for bit in range(32)
                 for source in (0, 1 << bit) for old in (0, FIELDS)]
        rows += [(rng.getrandbits(32), rng.getrandbits(32),
                  rng.getrandbits(32) & FIELDS) for _ in range(1024)]
        vectors = ",\n".join("{"+",".join(f"{x}u" for x in row)+"}"
                              for row in rows)
        fixture = "static const unsigned vectors[][3] = {\n"+vectors+"\n};\n"
        fixture += r"""
using namespace arcaderecomp_generated;
static std::uint32_t oracle(std::uint32_t old, std::uint32_t mask,
                            std::uint32_t source) {
    std::uint32_t result=0u;
    for(unsigned bit=0u;bit<32u;++bit) {
        const auto chosen=((mask>>bit)&1u)?source:old;
        if((chosen>>bit)&1u)result|=1u<<bit;
    }
    return result;
}
int main() {
    Bus bus{};
    unsigned checked=0u;
    for(const auto& row:vectors)for(unsigned form=0;form<8u;++form) {
        CPU cpu{};
        if(!kb_establish_arithmetic_controls(cpu,row[2]))return 1;
        cpu.ip=form*4u;
        cpu.r[16]=row[0];cpu.r[17]=row[1];cpu.r[18]=0xfeedfaceu;
        cpu.process_controls=0x001f2002u;
        const bool literal1=form==5u||form==7u;
        const bool literal2=form>=6u;
        const auto mask=literal1?31u:cpu.r[16];
        const auto src=literal2?29u:(form==3u||form==4u)?cpu.r[16]:cpu.r[17];
        const auto dst=(form==1u||form==4u)?16u:form==2u?17u:18u;
        const auto expected=oracle(row[2],mask,src);
        const CPU before=cpu;
        const bool valid=(expected&0x00e06e80u)==0u;
        if(step(cpu,bus)!=valid)return 2;
        const auto after=kb_arithmetic_controls_snapshot(cpu);
        if(after.known_mask!=0xffffffffu)return 3;
        if(valid) {
            if(cpu.ip!=(form+1u)*4u || cpu.r[dst]!=row[2] ||
               after.value!=expected || cpu.cc!=int(expected&7u) ||
               cpu.integer_overflow_mask!=bool(expected&0x1000u) ||
               cpu.integer_overflow_flag!=bool(expected&0x100u))return 4;
        } else if(cpu.ip!=form*4u || cpu.r[dst]!=before.r[dst] ||
                  after.value!=row[2] ||
                  cpu.stop_code!=StopCode::reserved_arithmetic_controls ||
                  cpu.stop_ip!=cpu.ip)return 5;
        for(unsigned r=0u;r<32u;++r)
            if((!valid||r!=dst)&&cpu.r[r]!=before.r[r])return 6;
        if(cpu.process_controls!=before.process_controls ||
           cpu.pending_integer_overflow.pending)return 7;
        ++checked;
    }
    return checked>9000u?0:8;
}
"""
        native(code+"\n"+fixture)

    def test_unknown_reserved_and_pending_states_refuse_without_mutation(self):
        code, _ = emit_cpp(struct.pack("<2I", regop(), 0xFFFFFFFF), 0, 8)
        native(code+r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    for(unsigned scenario=0u;scenario<8u;++scenario) {
        CPU cpu{};
        if(scenario && !kb_establish_arithmetic_controls(cpu,0xff1f917fu))return 1;
        switch(scenario) {
        case 1:cpu.cc_defined=false;break;
        case 2:cpu.integer_overflow_mask_defined=false;break;
        case 3:cpu.integer_overflow_flag_defined=false;break;
        case 4:cpu.arithmetic_controls_other_defined_mask&=~0x80000000u;break;
        case 5:cpu.cc=8;break;
        case 6:cpu.arithmetic_controls_other|=0x80u;break;
        case 7:cpu.pending_integer_overflow={true,0x40u,0x44u};break;
        default:break;
        }
        cpu.r[16]=0xffffffffu;cpu.r[17]=0;cpu.r[18]=0xabcdef01u;
        const auto before=kb_arithmetic_controls_snapshot(cpu);
        if(step(cpu,bus)||cpu.ip!=0u||cpu.r[18]!=0xabcdef01u)return 2;
        const auto after=kb_arithmetic_controls_snapshot(cpu);
        if(before.value!=after.value||before.known_mask!=after.known_mask)return 3;
        const auto expected=scenario==7u?StopCode::integer_overflow_pending:
            scenario==6u?StopCode::reserved_arithmetic_controls:
                         StopCode::undefined_arithmetic_controls;
        if(cpu.stop_code!=expected||cpu.stop_ip!=(scenario==7u?0x40u:0u))return 4;
    }
    CPU cpu{};
    if(!kb_establish_arithmetic_controls(cpu,0x1000u))return 5;
    const auto before=kb_arithmetic_controls_snapshot(cpu);
    if(kb_establish_arithmetic_controls(cpu,0x80u))return 6;
    const auto after=kb_arithmetic_controls_snapshot(cpu);
    if(after.value!=before.value||after.known_mask!=before.known_mask)return 7;
    if(kb_modac_checked(cpu,0u,0u,32u)||cpu.stop_code!=StopCode::untranslated)return 8;
    return 0;
}
""")

    def test_guest_controls_compare_overflow_sequence_and_reset_invalidation(self):
        words = [
            regop(),                                  # set overflow mask
            regop(0x591, 20, 21, 22),                  # overflowing ADDI
            regop(src1=0, literal1=True),              # read AC
            regop(0x5A0, 20, 21, 0),                   # CMPO changes live CC
            regop(src1=0, literal1=True),              # read current AC
            regop(),                                  # clear overflow flag
            0xFFFFFFFF,
        ]
        code, report = emit_cpp(struct.pack("<"+"I"*len(words), *words), 0, 32)
        self.assertEqual(report.translated, 6)
        native(code+r"""
using namespace arcaderecomp_generated;
static std::uint32_t read_prcb(void*,std::uint32_t address) {
    switch(address) {
    case 0x204u:return 0xcu;
    case 0x214u:return 0x800u;
    case 0x218u:return 0x400u;
    case 0x220u:return 0x1ffu;
    case 0x224u:return 0x27fu;
    case 0x228u:return 0x1000u;
    case 0x22cu:return 0u;
    default:return 0xffffffffu;
    }
}
int main() {
    CPU cpu{};Bus bus{};
    if(!kb_establish_arithmetic_controls(cpu,0xc0008002u))return 1;
    cpu.r[16]=0x1000u;cpu.r[17]=0x1000u;
    if(!step(cpu,bus)||cpu.r[18]!=0xc0008002u)return 2;
    cpu.r[20]=1u;cpu.r[21]=0x7fffffffu;
    if(!step(cpu,bus)||cpu.r[22]!=0x80000000u)return 3;
    if(!step(cpu,bus)||cpu.r[18]!=0xc0009102u)return 4;
    if(!step(cpu,bus)||cpu.cc!=4)return 5;
    if(!step(cpu,bus)||cpu.r[18]!=0xc0009104u)return 6;
    cpu.r[16]=0x100u;cpu.r[17]=0u;
    if(!step(cpu,bus)||cpu.r[18]!=0xc0009104u||
       kb_arithmetic_controls_snapshot(cpu).value!=0xc0009004u)return 7;
    // Only the existing integer bits become known through the old fixture API.
    CPU partial{};establish_integer_controls(partial,0x1000u);
    if(kb_modac_checked(partial,0u,0u,18u)||
       partial.stop_code!=StopCode::undefined_arithmetic_controls)return 8;
    if(!frame_init(cpu,0x100u,0x20u))return 9;
    if(kb_modac_checked(cpu,0u,0u,18u)||
       cpu.stop_code!=StopCode::undefined_arithmetic_controls)return 10;
    if(!kb_establish_arithmetic_controls(cpu,0xff1f917fu))return 11;
    bus.read32=&read_prcb;
    cpu.pending_iac_valid=true;cpu.allow_iac_93_reinitialize=true;
    cpu.pending_iac[0]=0x93000000u;cpu.pending_iac[1]=0u;
    cpu.pending_iac[2]=0x200u;cpu.pending_iac[3]=0x40u;
    if(!perform_iac_93_reinitialize(cpu,bus))return 12;
    if(kb_arithmetic_controls_snapshot(cpu).known_mask!=0u ||
       kb_modac_checked(cpu,0u,0u,18u)||
       cpu.stop_code!=StopCode::undefined_arithmetic_controls)return 13;
    return 0;
}
""")

    def test_guest_fp_controls_preserved_by_exact_and_refused_fp_operations(self):
        words = [regop(), regop(0x78F, 20, 21, 22),
                 regop(src1=0, literal1=True), regop(0x78F, 20, 21, 22),
                 0xFFFFFFFF]
        code, report = emit_cpp(struct.pack("<5I", *words), 0, 32)
        self.assertEqual(report.translated, 4)
        native(code+r"""
using namespace arcaderecomp_generated;
int main() {
    Bus bus{};
    for(unsigned rounding=0;rounding<4u;++rounding)
    for(unsigned normalize=0;normalize<2u;++normalize) {
        CPU cpu{};
        if(!kb_establish_arithmetic_controls(cpu,0u))return 1;
        const auto controls=(rounding<<30u)|(normalize<<29u)|0x151b9046u;
        cpu.r[16]=0xffffffffu;cpu.r[17]=controls;
        if(!step(cpu,bus)||cpu.r[18]!=0u)return 2;
        cpu.r[20]=0x3f800000u;cpu.r[21]=0x3f800000u; // 1 + 1
        if(!step(cpu,bus)||cpu.r[22]!=0x40000000u)return 3;
        if(!step(cpu,bus)||cpu.r[18]!=controls)return 4;
        // 1 + 2^-25 needs currently unsupported precision/rounding behavior.
        cpu.r[20]=0x3f800000u;cpu.r[21]=0x33000000u;
        cpu.r[22]=0xdeadbeefu;
        if(step(cpu,bus)||cpu.ip!=12u||cpu.r[22]!=0xdeadbeefu ||
           cpu.stop_code!=StopCode::unsupported_floating_rounding)return 5;
        const auto ac=kb_arithmetic_controls_snapshot(cpu);
        if(ac.value!=controls||ac.known_mask!=0xffffffffu)return 6;
    }
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
