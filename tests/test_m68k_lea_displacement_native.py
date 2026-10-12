"""Native MC68000 LEA (d16,An),Am coverage; no original ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def lea(source, dest, displacement):
    return words(0x41e8 | dest << 9 | source, displacement & 0xffff)


class M68kLeaDisplacementTests(unittest.TestCase):
    def test_decoder_all_registers_displacements_and_truncation(self):
        for source in range(8):
            for dest in range(8):
                for encoded, expected in ((0, 0), (1, 1), (0x7fff, 32767),
                                          (0x8000, -32768), (0xffff, -1)):
                    ins = decode(lea(source, dest, encoded), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (4, "lea_displacement",
                                      (source, dest, expected)))
        with self.assertRaisesRegex(ValueError, "Truncated"):
            decode(words(0x41e8), 0)
        for opcode in (0x41d0, 0x41e0, 0x41f0, 0x41fa, 0x41fb):
            self.assertNotEqual(decode(words(opcode, 0), 0).mnemonic,
                                "lea_displacement")

    def test_native_all_register_pairs_boundaries_aliasing_and_flags(self):
        image, rows = bytearray(), []
        displacements = (0, 1, 0x7fff, 0x8000, 0xffff)
        for source in range(8):
            for dest in range(8):
                for displacement in displacements:
                    rows.append((len(image), source, dest, displacement))
                    image += lea(source, dest, displacement)
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
    for(const auto& row:rows){
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for(unsigned r=0;r<8;++r){cpu.a[r]=0x89abcdefu+r;cpu.a_known[r]=true;}
        const unsigned base=cpu.a[row[1]];
        const unsigned displacement=(row[3]&0x8000u)?row[3]|0xffff0000u:row[3];
        const unsigned expected=base+displacement;
        cpu.sr=0x271fu;cpu.sr_known=0xffe5u;NoBus bus;
        if(!step(cpu,bus))return 1;
        if(cpu.a[row[2]]!=expected)return 2;
        if(!cpu.a_known[row[2]])return 3;
        if(cpu.sr!=0x271fu||cpu.sr_known!=0xffe5u)return 4;
        if(bus.calls)return 5;
    }
    return 0;
}
''')

    def test_unknown_source_fails_atomically_without_bus_access(self):
        source, _ = emit_cpp(lea(3, 3, -2) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct NoBus:Bus{
    unsigned calls=0;
    std::uint16_t read16(std::uint32_t)override{++calls;return 0;}
    void write16(std::uint32_t,std::uint16_t)override{++calls;}
};
int main(){
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x12345678u;
    cpu.a_known[3]=false;cpu.sr=0x2715u;cpu.sr_known=0xffe0u;
    const CPU before=cpu;NoBus bus;
    if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.pc!=before.pc||
       cpu.a!=before.a||cpu.a_known!=before.a_known||cpu.sr!=before.sr||
       cpu.sr_known!=before.sr_known||cpu.completed||bus.calls)return 1;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
