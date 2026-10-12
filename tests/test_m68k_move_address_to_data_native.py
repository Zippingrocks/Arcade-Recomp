"""Native MC68000 MOVE.W/L An,Dn coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def move_address(size, source, dest):
    return words(({2: 3, 4: 2}[size] << 12) | dest << 9 | 1 << 3 | source)


class M68kMoveAddressToDataTests(unittest.TestCase):
    def test_decoder_all_word_long_register_pairs_and_byte_exclusion(self):
        for size in (2, 4):
            for source in range(8):
                for dest in range(8):
                    ins = decode(move_address(size, source, dest), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (2, "move_address_to_d",
                                      (size, source, dest)))
        for source in range(8):
            for dest in range(8):
                opcode = 0x1000 | dest << 9 | 1 << 3 | source
                self.assertEqual(decode(words(opcode), 0).mnemonic,
                                 "unsupported")

    def test_native_values_register_pairs_width_knownness_flags_and_no_bus(self):
        image, rows = bytearray(), []
        for size in (2, 4):
            for source in range(8):
                for dest in range(8):
                    rows.append((len(image), size, source, dest))
                    image += move_address(size, source, dest)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][4]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct NoBus:Bus{
    unsigned calls=0;
    std::uint16_t read16(std::uint32_t)override{++calls;return 0;}
    void write16(std::uint32_t,std::uint16_t)override{++calls;}
};
int main(){
    const unsigned samples[]={0u,1u,0x7fffu,0x8000u,0xffffu,
                              0x7fffffffu,0x80000000u,0xffffffffu};
    for(const auto& row:rows)for(unsigned input:samples){
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        cpu.a[row[2]]=input;cpu.a_known[row[2]]=true;
        cpu.d[row[3]]=0xa5a55a5au;cpu.d_known[row[3]]=0x5a5aa5a5u;
        cpu.sr=0x271fu;cpu.sr_known=0xffe0u;NoBus bus;
        const unsigned mask=row[1]==2?0xffffu:0xffffffffu;
        const unsigned sign=row[1]==2?0x8000u:0x80000000u;
        const unsigned value=input&mask;
        const unsigned expected=(0xa5a55a5au&~mask)|value;
        const unsigned flags=(value&sign?8u:0u)|(value==0?4u:0u);
        if(!step(cpu,bus)||cpu.d[row[3]]!=expected||
           cpu.d_known[row[3]]!=(0x5a5aa5a5u|mask)||
           cpu.sr!=(0x2710u|flags)||cpu.sr_known!=0xffefu||bus.calls)return 1;
    }
    return 0;
}
''')

    def test_unknown_address_source_fails_atomically_without_bus(self):
        source, _ = emit_cpp(move_address(4, 3, 7) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct NoBus:Bus{
    unsigned calls=0;
    std::uint16_t read16(std::uint32_t)override{++calls;return 0;}
    void write16(std::uint32_t,std::uint16_t)override{++calls;}
};
int main(){
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x89abcdefu;
    cpu.a_known[3]=false;cpu.d[7]=0x12345678u;cpu.d_known[7]=0xffffffffu;
    cpu.sr=0x2715u;cpu.sr_known=0xffe0u;const CPU before=cpu;NoBus bus;
    if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.pc!=before.pc||
       cpu.a!=before.a||cpu.a_known!=before.a_known||cpu.d!=before.d||
       cpu.d_known!=before.d_known||cpu.sr!=before.sr||
       cpu.sr_known!=before.sr_known||cpu.completed||bus.calls)return 1;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
