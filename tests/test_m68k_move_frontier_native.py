"""Native MC68000 immediate/postincrement MOVE frontier coverage."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import move


def immediate_words(size, value):
    return ((value & 0xffff,) if size != 4 else
            ((value >> 16) & 0xffff, value & 0xffff))


def destination_words(mode, reg, displacement):
    if mode == 5 or (mode, reg) == (7, 0):
        return (displacement & 0xffff,)
    if (mode, reg) == (7, 1):
        return ((displacement >> 16) & 0xffff, displacement & 0xffff)
    return ()


def move_immediate(size, value, mode, reg, displacement=0):
    return move(size, 7, 4, mode, reg,
                *immediate_words(size, value),
                *destination_words(mode, reg, displacement))


def move_postincrement(size, source, mode, reg, displacement=0):
    return move(size, 3, source, mode, reg,
                *destination_words(mode, reg, displacement))


class M68kMoveFrontierTests(unittest.TestCase):
    def test_decoder_immediate_and_postincrement_forms_extensions_truncation(self):
        forms = ((2, 3, 0), (3, 4, 0), (5, 5, -2),
                 (7, 0, -32768), (7, 1, 0x12345678))
        for size in (1, 2, 4):
            mask = (1 << (size * 8)) - 1
            for mode, reg, displacement in forms:
                data = move_immediate(size, 0x89abcdef, mode, reg,
                                      displacement)
                ins = decode(data, 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (len(data), "move",
                                  (size, 1, 0x89abcdef & mask, mode, reg,
                                   displacement)))
                if mode != 3:
                    for source in range(8):
                        data = move_postincrement(size, source, mode, reg,
                                                  displacement)
                        ins = decode(data, 0)
                        self.assertEqual(
                            (ins.size, ins.mnemonic, ins.operands),
                            (len(data), "move_postincrement_to_memory",
                             (size, source, mode, reg, displacement)))
        for image in (move_immediate(4, 0x12345678, 5, 0, -2)[:4],
                      move_immediate(4, 0x12345678, 5, 0, -2)[:6],
                      move_postincrement(2, 0, 7, 1, 0x12345678)[:4]):
            with self.assertRaises(ValueError):
                decode(image, 0)
        for size in (1, 2, 4):
            for mode in (0, 1, 4, 6):
                self.assertNotEqual(
                    decode(move_postincrement(size, 0, mode, 0), 0).mnemonic,
                    "move_postincrement_to_memory")

    def test_native_immediate_values_flags_widths_addresses_and_postincrement(self):
        image, rows = bytearray(), []
        forms = ((2, 2, 0), (3, 3, 0), (5, 4, -2),
                 (7, 0, -2), (7, 1, 0x00fffffe))
        values = (0, 1, 0x80, 0x8000, 0x80000000, 0xffffffff)
        for size in (1, 2, 4):
            for value in values:
                for mode, reg, displacement in forms:
                    data = move_immediate(size, value, mode, reg, displacement)
                    rows.append((len(image), size, value, mode, reg,
                                 displacement, len(data)))
                    image += data
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][7]={" + ",".join(
            "{" + ",".join(f"{v & 0xffffffff}u" for v in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct Writes:Bus {
    unsigned count=0,addresses[2]{},widths[2]{},values[2]{};
    void write8(std::uint32_t a,std::uint8_t v)override{addresses[count]=a;widths[count]=1;values[count++]=v;}
    void write16(std::uint32_t a,std::uint16_t v)override{addresses[count]=a;widths[count]=2;values[count++]=v;}
};
int main() {
    for (const auto& row:rows) {
        const unsigned mask=row[1]==4u?0xffffffffu:(1u<<(row[1]*8u))-1u;
        const unsigned sign=1u<<(row[1]*8u-1u),value=row[2]&mask;
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for (unsigned reg=0;reg<8u;++reg){cpu.a[reg]=2u+reg*0x100u;cpu.a_known[reg]=true;}
        cpu.sr=0x271fu;cpu.sr_known=0xffefu;const auto before=cpu;Writes bus;
        if (!step(cpu,bus)||cpu.pc!=row[0]+row[6]||cpu.completed!=1u) return 1;
        const unsigned logical=row[3]==7u?row[5]:before.a[row[4]]+row[5];
        const unsigned address=logical&0xffffffu,expected=row[1]==4u?2u:1u;
        if (bus.count!=expected||bus.addresses[0]!=address||
            bus.widths[0]!=(row[1]==1u?1u:2u)||
            bus.values[0]!=(row[1]==4u?value>>16u:value)) return 2;
        if (row[1]==4u&&(bus.addresses[1]!=((address+2u)&0xffffffu)||
            bus.values[1]!=(value&0xffffu))) return 3;
        const unsigned flags=(value&sign?8u:0u)|(value==0u?4u:0u);
        if (cpu.sr!=(0x2710u|flags)||cpu.sr_known!=0xffefu) return 4;
        for (unsigned reg=0;reg<8u;++reg) {
            const unsigned increment=row[3]==3u&&reg==row[4]?
                (row[1]==1u&&reg==7u?2u:row[1]):0u;
            if (cpu.a[reg]!=before.a[reg]+increment||
                cpu.a_known[reg]!=before.a_known[reg]) return 5;
        }
        if (cpu.d!=before.d||cpu.d_known!=before.d_known) return 6;
    }
    return 0;
}
''')

    def test_native_postincrement_source_order_aliases_values_and_flags(self):
        image, rows = bytearray(), []
        forms = ((2, 2, 0), (5, 3, -2), (7, 0, -2),
                 (7, 1, 0x00fffffe))
        for size in (1, 2, 4):
            for source in range(8):
                for mode, reg, displacement in forms:
                    data = move_postincrement(size, source, mode, reg,
                                              displacement)
                    rows.append((len(image), size, source, mode, reg,
                                 displacement, len(data)))
                    image += data
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][7]={" + ",".join(
            "{" + ",".join(f"{v & 0xffffffff}u" for v in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct Transfers:Bus {
    unsigned count=0,reads=0,bytes=0,value=0,addresses[4]{},values[4]{};bool writes[4]{};
    void record(unsigned a,unsigned v,bool write){addresses[count]=a;values[count]=v;writes[count]=write;++count;}
    std::uint8_t read8(std::uint32_t a)override{record(a,value,false);++reads;return static_cast<std::uint8_t>(value);}
    std::uint16_t read16(std::uint32_t a)override{const unsigned v=bytes==4u&&reads==0u?value>>16u:value;
      record(a,v,false);++reads;return static_cast<std::uint16_t>(v);}
    void write8(std::uint32_t a,std::uint8_t v)override{record(a,v,true);}
    void write16(std::uint32_t a,std::uint16_t v)override{record(a,v,true);}
};
int main() {
    const unsigned values[]={0u,1u,0x80u,0x8000u,0x80000000u,0xffffffffu};
    for (const auto& row:rows) {
        for (unsigned raw:values) {
            const unsigned mask=row[1]==4u?0xffffffffu:(1u<<(row[1]*8u))-1u;
            const unsigned sign=1u<<(row[1]*8u-1u),value=raw&mask;
            CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
            for (unsigned reg=0;reg<8u;++reg){cpu.a[reg]=2u+reg*0x100u;cpu.a_known[reg]=true;}
            cpu.sr=0x271fu;cpu.sr_known=0xffefu;const auto before=cpu;
            const unsigned increment=row[1]==1u&&row[2]==7u?2u:row[1];
            Transfers bus;bus.bytes=row[1];bus.value=value;
            if (!step(cpu,bus)||cpu.pc!=row[0]+row[6]||cpu.completed!=1u) return 1;
            const unsigned source_address=before.a[row[2]]&0xffffffu;
            const unsigned destination_logical=row[3]==7u?row[5]:
                before.a[row[4]]+row[5]+(row[2]==row[4]?increment:0u);
            const unsigned destination_address=destination_logical&0xffffffu;
            const unsigned half=row[1]==4u?2u:1u;
            if (bus.count!=half*2u||bus.addresses[0]!=source_address||
                bus.writes[0]||bus.addresses[half]!=destination_address||
                !bus.writes[half]||bus.values[half]!=(row[1]==4u?value>>16u:value)) return 2;
            if (cpu.a[row[2]]!=before.a[row[2]]+increment) return 3;
            const unsigned flags=(value&sign?8u:0u)|(value==0u?4u:0u);
            if (cpu.sr!=(0x2710u|flags)||cpu.sr_known!=0xffefu) return 4;
        }
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
