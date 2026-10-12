"""Native MC68000 MOVE.W/L An to non-updating memory; no ROM bytes."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


def move_address(size, source, mode, reg, *extensions):
    opcode = {2: 0x3000, 4: 0x2000}[size]
    return words(opcode | reg << 9 | mode << 6 | 1 << 3 | source,
                 *extensions)


def table(name, rows):
    return f"static const unsigned {name}[][" + str(len(rows[0])) + "]={" + ",".join(
        "{" + ",".join(f"{value & 0xffffffff}u" for value in row) + "}" for row in rows) + "};\n"


class M68kMoveAddressToMemoryTests(unittest.TestCase):
    def test_decoder_all_registers_modes_extensions_and_exclusions(self):
        cases = (
            (2, 3, (), 0, 2),
            (5, 6, (0xfffe,), -2, 4),
            (7, 0, (0x8000,), -32768, 4),
            (7, 1, (0x1234, 0x5678), 0x12345678, 6),
        )
        for size in (2, 4):
            for source in range(8):
                for mode, reg, extensions, displacement, length in cases:
                    ins = decode(move_address(size, source, mode, reg,
                                              *extensions), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (length, "move_address_to_memory",
                                      (size, source, mode, reg, displacement)))
        for source in range(8):
            for mode, reg, extensions, _, _ in cases:
                opcode = 0x1000 | reg << 9 | mode << 6 | 1 << 3 | source
                self.assertEqual(decode(words(opcode, *extensions), 0).mnemonic,
                                 "unsupported")
        for image in (move_address(2, 0, 5, 1),
                      move_address(4, 0, 7, 0),
                      move_address(4, 0, 7, 1, 0x1234)):
            with self.assertRaises(ValueError):
                decode(image, 0)

    def test_native_values_addresses_word_order_flags_and_aliases(self):
        image, rows = bytearray(), []
        for size in (2, 4):
            for source in range(8):
                for mode, registers in ((2, range(8)), (5, range(8))):
                    for reg in registers:
                        rows.append((len(image), size, source, mode, reg,
                                     -2 if mode == 5 else 0,
                                     4 if mode == 5 else 2))
                        image += move_address(size, source, mode, reg,
                                              *((0xfffe,) if mode == 5 else ()))
                rows.append((len(image), size, source, 7, 0, -2, 4))
                image += move_address(size, source, 7, 0, 0xfffe)
                rows.append((len(image), size, source, 7, 1, 0x00fffffe, 6))
                image += move_address(size, source, 7, 1, 0x00ff, 0xfffe)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
struct Writes:Bus {
    unsigned count=0,addresses[2]{},values[2]{};
    void write16(std::uint32_t address,std::uint16_t value)override {
        if(count>=2)throw std::runtime_error("extra write");
        addresses[count]=address;values[count]=value;++count;
    }
};
int main() {
    const unsigned samples[]={0u,2u,0x7ffeu,0x8000u,0xffff0000u,
                              0x80000000u,0xfffffffeu};
    for(const auto& row:rows)for(unsigned input:samples)
      for(unsigned x=0;x<2;++x)for(unsigned known_x=0;known_x<2;++known_x) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for(unsigned i=0;i<8;++i){cpu.a[i]=0x12001000u+i*4u;cpu.a_known[i]=true;}
        cpu.a[row[2]]=input;
        cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));
        cpu.sr_known=static_cast<std::uint16_t>(known_x?0xfff0u:0xffe0u);
        const auto before=cpu;Writes bus;
        if(!step(cpu,bus)||cpu.stop!=Stop::none||cpu.pc!=row[0]+row[6]||cpu.completed!=1)return 1;
        const unsigned mask=row[1]==2?0xffffu:0xffffffffu;
        const unsigned value=input&mask;
        const unsigned logical=row[3]==7?row[5]:before.a[row[4]]+row[5];
        const unsigned address=logical&0xffffffu;
        if(bus.count!=(row[1]==4?2u:1u)||bus.addresses[0]!=address||
           bus.values[0]!=(row[1]==4?value>>16u:value))return 2;
        if(row[1]==4&&(bus.addresses[1]!=((address+2u)&0xffffffu)||
                       bus.values[1]!=(value&0xffffu)))return 3;
        const unsigned sign=row[1]==2?0x8000u:0x80000000u;
        const unsigned flags=(value&sign?8u:0u)|(value==0?4u:0u);
        if(cpu.sr!=(0x2700u|(x<<4)|flags)||
           cpu.sr_known!=(known_x?0xffffu:0xffefu))return 4;
        if(cpu.a!=before.a||cpu.a_known!=before.a_known||cpu.d!=before.d||
           cpu.d_known!=before.d_known)return 5;
    }
    return 0;
}
''')

    def test_unknown_alignment_and_write_faults_preserve_uncommitted_cpu_state(self):
        images = (
            move_address(2, 3, 2, 4),
            move_address(4, 3, 5, 4, 0xfffe),
            move_address(4, 3, 7, 0, 0xfffe),
        )
        sources = []
        for index, image in enumerate(images):
            source, _ = emit_cpp(image + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated",
                                          f"store_{index}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);
Step steps[]={store_0::step,store_1::step,store_2::step};
struct Writes:Bus {
    unsigned attempts=0,accepted=0,deny=0,addresses[2]{},values[2]{};
    void write16(std::uint32_t address,std::uint16_t value)override {
        if(attempts>=2)throw std::runtime_error("extra write");
        addresses[attempts]=address;values[attempts]=value;++attempts;
        if(attempts==deny)throw BusFault(address,true,2);
        ++accepted;
    }
};
bool unchanged(const CPU& cpu,const CPU& before) {
    return cpu.d==before.d&&cpu.a==before.a&&cpu.d_known==before.d_known&&
           cpu.a_known==before.a_known&&cpu.sr==before.sr&&
           cpu.sr_known==before.sr_known&&cpu.pc==before.pc&&
           cpu.completed==before.completed;
}
CPU initial() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x89abcdefu;
    cpu.a[4]=0x01000000u;cpu.a_known[3]=cpu.a_known[4]=true;
    cpu.sr=0x271fu;cpu.sr_known=0xfff0u;return cpu;
}
int main() {
    for(unsigned index=0;index<3;++index) {
        auto cpu=initial();cpu.a_known[3]=false;const auto before=cpu;Writes bus;
        if(steps[index](cpu,bus)||cpu.stop!=Stop::undefined_state||bus.attempts||
           !unchanged(cpu,before))return 1;
    }
    for(unsigned index=0;index<2;++index) {
        auto cpu=initial();cpu.a_known[4]=false;const auto before=cpu;Writes bus;
        if(steps[index](cpu,bus)||cpu.stop!=Stop::undefined_state||bus.attempts||
           !unchanged(cpu,before))return 2;
    }
    for(unsigned index=0;index<3;++index)for(unsigned denial=1;
        denial<=(index?2u:1u);++denial) {
        auto cpu=initial();const auto before=cpu;Writes bus;bus.deny=denial;
        if(steps[index](cpu,bus)||cpu.stop!=Stop::bus_access||
           !unchanged(cpu,before)||bus.attempts!=denial||
           bus.accepted!=denial-1u||!cpu.access_write||cpu.access_width!=2)return 3;
        if(index&&bus.addresses[0]!=0xfffffeu)return 4;
        if(index&&denial==2&&bus.addresses[1]!=0u)return 5;
    }
    for(unsigned index=0;index<2;++index) {
        auto cpu=initial();cpu.a[4]=index?3u:1u;const auto before=cpu;Writes bus;
        if(steps[index](cpu,bus)||cpu.stop!=Stop::data_address||bus.attempts||
           !unchanged(cpu,before)||cpu.access_address!=(index?1u:1u)||
           !cpu.access_write||cpu.access_width!=(index?4u:2u))return 6;
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
