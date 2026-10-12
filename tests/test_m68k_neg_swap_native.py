"""Native MC68000 NEG and SWAP data-register coverage; no ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def neg(size, reg, mode=0):
    return words(0x4400 | {1: 0, 2: 0x40, 4: 0x80}[size] |
                 mode << 3 | reg)


def swap(reg):
    return words(0x4840 | reg)


class M68kNegateAndSwapTests(unittest.TestCase):
    def test_decoder_all_registers_widths_and_exclusions(self):
        for size in (1, 2, 4):
            for reg in range(8):
                ins = decode(neg(size, reg), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (2, "neg_d", (size, reg)))
                for mode in range(1, 8):
                    self.assertNotEqual(decode(neg(size, reg, mode), 0).mnemonic,
                                        "neg_d")
        for reg in range(8):
            ins = decode(swap(reg), 0)
            self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                             (2, "swap_d", (reg,)))
        for opcode in (0x44c0, 0x483f, 0x4848):
            self.assertEqual(decode(words(opcode), 0).mnemonic, "unsupported")

    def test_native_neg_exhaustive_byte_and_wide_boundaries(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for reg in range(8):
                rows.append((len(image), size, reg))
                image += neg(size, reg)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][3]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    const unsigned boundaries[]={0u,1u,2u,0x7fffu,0x8000u,0x8001u,
        0xffffu,0x7fffffffu,0x80000000u,0x80000001u,0xfffffffeu,0xffffffffu};
    Bus strict;
    for (const auto& row:rows) {
        const unsigned bits=row[1]*8u;
        const unsigned mask=row[1]==4u?0xffffffffu:(1u<<bits)-1u;
        const unsigned sign=1u<<(bits-1u);
        const unsigned samples=row[1]==1u?256u:sizeof(boundaries)/sizeof(boundaries[0]);
        for (unsigned sample=0;sample<samples;++sample) {
            for (unsigned old_flags=0;old_flags<32u;++old_flags) {
                const unsigned input=(row[1]==1u?sample:boundaries[sample])&mask;
                const unsigned result=(0u-input)&mask;
                CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
                cpu.d[row[2]]=(0xa5a55a5au&~mask)|input;
                cpu.d_known[row[2]]=mask;
                cpu.sr=static_cast<std::uint16_t>(0x2700u|old_flags);
                cpu.sr_known=0xffffu;
                const auto before=cpu;
                if (!step(cpu,strict)||cpu.stop!=Stop::none||cpu.pc!=row[0]+2u||
                    cpu.completed!=1u) return 1;
                if (cpu.d[row[2]]!=((before.d[row[2]]&~mask)|result)||
                    cpu.d_known[row[2]]!=mask) return 2;
                const unsigned flags=(input!=0u?17u:0u)|(result&sign?8u:0u)|
                                     (result==0u?4u:0u)|(input==sign?2u:0u);
                if (cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu) return 3;
                for (unsigned reg=0;reg<8u;++reg) {
                    if (reg!=row[2]&&(cpu.d[reg]!=before.d[reg]||
                        cpu.d_known[reg]!=before.d_known[reg])) return 4;
                }
                if (cpu.a!=before.a||cpu.a_known!=before.a_known) return 5;
            }
        }
    }
    return 0;
}
''')

    def test_native_swap_flags_unknown_inputs_and_invalid_helpers(self):
        image = b"".join(swap(reg) for reg in range(8)) + words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, 8)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
bool unchanged(const CPU& cpu,const CPU& before) {
    return cpu.d==before.d&&cpu.a==before.a&&cpu.d_known==before.d_known&&
           cpu.a_known==before.a_known&&cpu.sr==before.sr&&
           cpu.sr_known==before.sr_known&&cpu.pc==before.pc&&
           cpu.completed==before.completed;
}
CPU initial() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.sr=0x271fu;cpu.sr_known=0xffffu;
    for (unsigned reg=0;reg<8u;++reg) {
        cpu.d[reg]=0x01234567u+reg*0x11111111u;cpu.d_known[reg]=0xffffffffu;
    }
    return cpu;
}
int main() {
    const unsigned values[]={0u,1u,0x7fffu,0x8000u,0xffffu,0x7fffffffu,
                             0x80000000u,0xffff0000u,0xffffffffu};
    Bus strict;
    for (unsigned reg=0;reg<8u;++reg) {
        for (unsigned value:values) {
            for (unsigned x=0;x<2u;++x) {
                for (unsigned known_x=0;known_x<2u;++known_x) {
                    CPU cpu=initial();cpu.pc=reg*2u;cpu.d[reg]=value;
                    cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4u));
                    cpu.sr_known=static_cast<std::uint16_t>(known_x?0xffffu:0xffefu);
                    const auto before=cpu;
                    if (!step(cpu,strict)||cpu.stop!=Stop::none||cpu.pc!=reg*2u+2u||
                        cpu.completed!=1u) return 1;
                    const unsigned result=(value<<16u)|(value>>16u);
                    if (cpu.d[reg]!=result||cpu.d_known[reg]!=0xffffffffu) return 2;
                    const unsigned flags=(result&0x80000000u?8u:0u)|(result==0u?4u:0u);
                    if (cpu.sr!=(0x2700u|(x<<4u)|flags)||
                        cpu.sr_known!=(known_x?0xffffu:0xffefu)) return 3;
                    for (unsigned other=0;other<8u;++other) {
                        if (other!=reg&&(cpu.d[other]!=before.d[other]||
                            cpu.d_known[other]!=before.d_known[other])) return 4;
                    }
                    if (cpu.a!=before.a||cpu.a_known!=before.a_known) return 5;
                }
            }
        }
    }
    for (unsigned reg=0;reg<8u;++reg) {
        CPU cpu=initial();cpu.pc=reg*2u;cpu.d_known[reg]^=1u;const auto before=cpu;
        if (step(cpu,strict)||cpu.stop!=Stop::undefined_state||!unchanged(cpu,before)) return 6;
    }
    for (unsigned bytes:{0u,3u,5u}) {
        CPU cpu=initial();const auto before=cpu;
        if (negate_data(cpu,bytes,3u,2u)||cpu.stop!=Stop::unsupported_instruction||
            !unchanged(cpu,before)) return 7;
    }
    CPU cpu=initial();const auto before=cpu;
    if (negate_data(cpu,1u,8u,2u)||cpu.stop!=Stop::unsupported_instruction||
        !unchanged(cpu,before)) return 8;
    cpu=initial();const auto before_swap=cpu;
    if (swap_data(cpu,8u,2u)||cpu.stop!=Stop::unsupported_instruction||
        !unchanged(cpu,before_swap)) return 9;
    cpu=initial();cpu.d_known[3]=0xfffffffeu;const auto before_neg=cpu;
    if (negate_data(cpu,1u,3u,2u)||cpu.stop!=Stop::undefined_state||
        !unchanged(cpu,before_neg)) return 10;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
