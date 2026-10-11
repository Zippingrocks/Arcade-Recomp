"""Intel 80960KB MODIFY (650h) native AOT validation with synthetic bytes.

The destination is read-modify-written: (src2 & src1) | (old_dst & ~src1).
Intel 80960KB Programmer's Reference Manual (1988), Chapter 11 MODIFY.
No ROM bytes, generated original-game source or game assets are included.
"""
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
OPCODE = 0x650
FORMS = (
    (16, 17, 18, False, False),
    (16, 17, 16, False, False),  # mask aliases destination
    (16, 17, 17, False, False),  # replacement aliases destination
    (16, 16, 18, False, False),  # mask and source same register
    (31, 17, 18, True, False),  # literal mask
    (16, 29, 18, False, True),  # literal source
    (31, 29, 18, True, True),  # both literals
)


def regop(src1=16, src2=17, dst=18, literal1=False, literal2=False):
    return (((OPCODE & 0xff0) << 20) | ((OPCODE & 15) << 7) |
            src1 | (src2 << 14) | (dst << 19) |
            (int(literal1) << 11) | (int(literal2) << 12))


def rows():
    edges = [0, 1, 2, 31, 0x80000000, 0x7fffffff,
             0xaaaaaaaa, 0x55555555, 0xfffffffe, 0xffffffff]
    data = [(a, b, c) for a in edges for b in edges for c in (0, 0xffffffff)]
    rng = random.Random(0x650960)
    data.extend((rng.getrandbits(32), rng.getrandbits(32), rng.getrandbits(32))
                for _ in range(512))
    return data


class ModifyNativeTests(unittest.TestCase):
    def test_decoder_and_fail_closed_reg_modes(self):
        inst = decode(struct.pack("<I", regop()), 0)
        self.assertEqual((inst.mnemonic, inst.form, inst.operands),
                         ("modify", "REG", ("g0", "g1", "g2")))
        for mask in (0x20, 0x40, 0x2000):
            _, report = emit_cpp(struct.pack("<2I", regop() | mask,
                                             0xffffffff), 0, 8)
            self.assertIn(0, report.unsupported)

    def test_native_masked_merge_alias_literals_and_control_preservation(self):
        words = [regop(*form) for form in FORMS] + [0xffffffff]
        cpp, report = emit_cpp(struct.pack("<" + "I" * len(words), *words),
                               0, 32)
        self.assertEqual(report.translated, len(FORMS))
        self.assertEqual(report.unsupported, (len(FORMS)*4,))
        vectors = ",\n".join("{" + ",".join(str(x) + "u" for x in row) + "}"
                              for row in rows())
        harness = (f"static const std::uint32_t vectors[][3] = {{\n"
                   f"{vectors}\n}};\n") + r"""
using namespace arcaderecomp_generated;
static std::uint32_t oracle(std::uint32_t mask, std::uint32_t source,
                            std::uint32_t old_dst) {
    // Independently assemble the expected word one bit at a time.
    std::uint32_t result=0;
    for(unsigned i=0;i<32u;++i) {
        const bool chosen=(mask & (1u << i))!=0u;
        const bool bit=(((chosen ? source : old_dst) >> i) & 1u)!=0u;
        if(bit)result|=1u<<i;
    }
    return result;
}
int main(){
    Bus bus{};
    unsigned checked=0;
    for(const auto& row: vectors)
    for(unsigned form=0;form<7u;++form)
    for(unsigned oldcc=0;oldcc<8u;++oldcc)
    for(unsigned defined=0;defined<2u;++defined){
        CPU cpu{};
        cpu.r[16]=row[0];cpu.r[17]=row[1];cpu.r[18]=row[2];
        cpu.ip=form*4u;
        cpu.cc=static_cast<int>(oldcc);cpu.cc_defined=defined!=0;
        cpu.integer_overflow_mask=true;
        cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;
        cpu.integer_overflow_flag_defined=true;
        const unsigned dst=(form==1?16u:form==2?17u:18u);
        std::uint32_t before[32]{};
        for(unsigned i=0;i<32u;++i)before[i]=cpu.r[i];
        const std::uint32_t mask=(form>=4 && (form==4 || form==6))?
                                 31u:before[16];
        const std::uint32_t replacement=(form>=5)?29u:
                                         form==3?before[16]:before[17];
        const std::uint32_t expected=oracle(mask,replacement,before[dst]);
        if(!step(cpu,bus)||cpu.ip!=(form+1u)*4u||
           cpu.r[dst]!=expected||cpu.cc!=static_cast<int>(oldcc)||
           cpu.cc_defined!=bool(defined)||
           !cpu.integer_overflow_mask_defined||!cpu.integer_overflow_mask||
           !cpu.integer_overflow_flag_defined||!cpu.integer_overflow_flag||
           cpu.pending_integer_overflow.pending||
           cpu.stop_code!=StopCode::none)return 1;
        for(unsigned i=0;i<32u;++i)
            if(i!=dst&&cpu.r[i]!=before[i])return 2;
        ++checked;
    }
    return checked>10000u?0:3;
}
"""
        compilers = [path for name in ("g++", "clang++")
                     if (path := shutil.which(name))]
        if not compilers:
            raise unittest.SkipTest("No C++17 compiler")
        for compiler in compilers:
            with tempfile.TemporaryDirectory(prefix="arcade-modify-") as folder:
                source = Path(folder)/"test.cpp"
                exe = Path(folder)/"test"
                source.write_text(cpp+"\n"+harness, encoding="utf-8")
                built = subprocess.run(
                    [compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                     "-fsanitize=undefined","-fno-sanitize-recover=all",
                     "-I",str(ROOT/"runtime"),str(source),"-o",str(exe)],
                    capture_output=True,text=True,timeout=45)
                if built.returncode:
                    raise AssertionError(compiler+": "+built.stderr)
                run = subprocess.run([str(exe)],capture_output=True,
                                     text=True,timeout=25)
                if run.returncode:
                    raise AssertionError(
                        f"{compiler}: exit {run.returncode}: {run.stdout}{run.stderr}")


if __name__ == "__main__":
    unittest.main()
