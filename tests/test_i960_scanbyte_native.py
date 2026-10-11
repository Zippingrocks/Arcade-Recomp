"""80960KB SCANBYTE AOT reference tests, using synthetic opcodes only.

SCANBYTE 5ACh compares corresponding bytes in src1 and src2 and sets CC
to 010 if any one matches, otherwise 000. The 80960KB has this operation,
but does NOT have later-core BSWAP 5ADh: keep that deliberately unsupported.
Reference: Intel 80960KB Programmer's Reference Manual (1988), Chapter 11;
Intel 80960KB product instruction-set summary.
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


def regop(src1=16, src2=17, lit1=False, lit2=False, m3=False, op=0x5ac):
    return (((op & 0xff0) << 20) | ((op & 15) << 7)
            | src1 | (src2 << 14) | (int(lit1) << 11)
            | (int(lit2) << 12) | (int(m3) << 13))


def rows():
    edges = [
        0, 0xffffffff, 0x12345678, 0x78563412, 0x11223344,
        0x00223344, 0x11003344, 0x11220044, 0x11223300,
        0xff00ff00, 0x00ff00ff, 0xaaaaaaaa, 0x55555555,
        0x80000000, 0x7fffffff, 31,
    ]
    result = [(a, b) for a in edges for b in edges]
    rng = random.Random(0x5ac960)
    result.extend((rng.getrandbits(32), rng.getrandbits(32))
                  for _ in range(512))
    return result


class ScanbyteNativeTests(unittest.TestCase):
    def test_decode_and_no_later_core_bswap_translation(self):
        ins = decode(struct.pack("<I", regop()), 0)
        self.assertEqual((ins.mnemonic, ins.form, ins.operands),
                         ("scanbyte", "REG", ("g0", "g1")))
        code, report = emit_cpp(struct.pack("<2I", regop(op=0x5ad),
                                            0xffffffff), 0, 16)
        self.assertIn(0, report.unsupported)
        self.assertEqual(report.translated, 0)
        self.assertIn("return stop(cpu)", code)

    def test_disallowed_special_operand_encodings(self):
        for mask in (0x20, 0x40):
            _, report = emit_cpp(
                struct.pack("<2I", regop() | mask, 0xffffffff), 0, 16)
            self.assertIn(0, report.unsupported)

    def test_native_scanbyte_all_byte_lanes_literals_cc_reset(self):
        forms = (
            regop(),                             # register/register
            regop(src1=17, src2=16),             # reversed registers
            regop(src1=31, lit1=True),           # literal/register
            regop(src2=29, lit2=True),           # register/literal
            regop(src1=31, src2=29, lit1=True, lit2=True),
            regop(m3=True),                      # comparison ignores dest mode
            regop(src1=16, src2=16),             # identical register sources
        )
        image = struct.pack("<" + "I" * (len(forms) + 1),
                            *forms, 0xffffffff)
        cpp, report = emit_cpp(image, 0, 32)
        self.assertEqual(report.translated, len(forms))
        self.assertEqual(report.unsupported, (len(forms) * 4,))

        rows_str = ",\n".join(
            "{" + str(a) + "u," + str(b) + "u}"
            for a, b in rows())
        harness = (f"static const std::uint32_t vectors[][2] = {{\n"
                   f"{rows_str}\n}};\n") + r"""
using namespace arcaderecomp_generated;

static unsigned reference(std::uint32_t a, std::uint32_t b) {
    // Separate per-byte extraction oracle: do not duplicate the emitter's
    // XOR-and-mask implementation.
    for (unsigned i=0; i<4; ++i)
        if (((a >> (i*8u)) & 255u) == ((b >> (i*8u)) & 255u))
            return 2u;
    return 0u;
}
int main() {
    Bus bus{};
    unsigned checked = 0u;
    for (const auto& v : vectors)
    for (unsigned form=0; form<7; ++form)
    for (unsigned cc=0; cc<8; ++cc)
    for (unsigned defined=0; defined<2; ++defined) {
        CPU cpu{};
        cpu.r[16]=v[0]; cpu.r[17]=v[1]; cpu.r[18]=0x87654321u;
        cpu.cc=static_cast<int>(cc); cpu.cc_defined=defined!=0;
        cpu.integer_overflow_mask=true;
        cpu.integer_overflow_mask_defined=true;
        cpu.integer_overflow_flag=true;
        cpu.integer_overflow_flag_defined=true;
        cpu.ip=form*4u;
        const std::uint32_t src1=(form==1)?v[1]:v[0];
        const std::uint32_t src2=(form==1)?v[0]:v[1];
        const std::uint32_t a=(form==2 || form==4)?31u:src1;
        const std::uint32_t b=(form==3 || form==4)?29u:
                              (form==6?v[0]:src2);
        const unsigned want=reference(a,b);
        if (!step(cpu,bus) || cpu.ip != (form+1u)*4u ||
            cpu.cc!=static_cast<int>(want) || !cpu.cc_defined ||
            cpu.r[16]!=v[0] || cpu.r[17]!=v[1] ||
            cpu.r[18]!=0x87654321u ||
            !cpu.integer_overflow_mask || !cpu.integer_overflow_mask_defined ||
            !cpu.integer_overflow_flag || !cpu.integer_overflow_flag_defined ||
            cpu.pending_integer_overflow.pending ||
            cpu.stop_code!=StopCode::none) return 1;
        ++checked;
    }
    return checked > 10000u ? 0 : 2;
}
"""
        compilers = [bin for name in ("g++", "clang++")
                     if (bin := shutil.which(name))]
        if not compilers:
            raise unittest.SkipTest("No C++17 compiler available")
        for compiler in compilers:
            with tempfile.TemporaryDirectory(prefix="arcade-kb-scanbyte-") as folder:
                source = Path(folder) / "test.cpp"
                exe = Path(folder) / "native"
                source.write_text(cpp + "\n" + harness, encoding="utf-8")
                built = subprocess.run([
                    compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=undefined", "-fno-sanitize-recover=all",
                    "-I", str(ROOT / "runtime"), str(source), "-o", str(exe)
                ], capture_output=True, text=True, timeout=45)
                if built.returncode:
                    raise AssertionError(f"{compiler}: {built.stderr}")
                ran = subprocess.run([str(exe)], capture_output=True,
                                     text=True, timeout=25)
                if ran.returncode:
                    raise AssertionError(
                        f"{compiler}: exit {ran.returncode}: {ran.stdout}{ran.stderr}")


if __name__ == "__main__":
    unittest.main()
