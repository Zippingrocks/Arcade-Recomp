"""Native MC68000 SUBI, memory-source ADD and memory SUBQ coverage."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


SIZE_BITS = {1: 0, 2: 0x40, 4: 0x80}


def subi(size, reg, immediate, mode=0):
    values = (immediate,) if size != 4 else (immediate >> 16, immediate & 0xffff)
    return words(0x0400 | SIZE_BITS[size] | mode << 3 | reg,
                 *(value & 0xffff for value in values))


def memory_extensions(mode, reg, displacement):
    if mode == 5 or (mode, reg) == (7, 0):
        return (displacement & 0xffff,)
    if (mode, reg) == (7, 1):
        return (displacement >> 16, displacement & 0xffff)
    return ()


def add_memory(size, mode, source, dest, displacement=0):
    return words(0xd000 | dest << 9 | SIZE_BITS[size] | mode << 3 | source,
                 *memory_extensions(mode, source, displacement))


def subq_memory(size, immediate, mode, reg, displacement=0):
    return words(0x5100 | (immediate & 7) << 9 | SIZE_BITS[size] |
                 mode << 3 | reg, *memory_extensions(mode, reg, displacement))


class M68kArithmeticFrontierTests(unittest.TestCase):
    def test_decoder_widths_fields_extensions_exclusions_and_truncation(self):
        for size in (1, 2, 4):
            values = (0, 1, 0x7f, 0x80, 0xffff, 0x89abcdef)
            for reg in range(8):
                for value in values:
                    ins = decode(subi(size, reg, value), 0)
                    mask = (1 << (size * 8)) - 1
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (6 if size == 4 else 4, "subi_d",
                                      (size, reg, value & mask)))
                for mode in range(1, 8):
                    self.assertNotEqual(decode(subi(size, reg, 0, mode), 0).mnemonic,
                                        "subi_d")
            for mode, reg, displacement, length in (
                    (2, 3, 0, 2), (5, 4, -2, 4),
                    (7, 0, -32768, 4), (7, 1, 0x12345678, 6)):
                for dest in range(8):
                    add = decode(add_memory(size, mode, reg, dest, displacement), 0)
                    self.assertEqual((add.size, add.mnemonic, add.operands),
                                     (length, "add_memory_to_d",
                                      (size, mode, reg, displacement, dest)))
                for immediate in range(1, 9):
                    sub = decode(subq_memory(size, immediate, mode, reg,
                                             displacement), 0)
                    self.assertEqual((sub.size, sub.mnemonic, sub.operands),
                                     (length, "subq_memory",
                                      (size, mode, reg, displacement, immediate)))
        for image in (subi(2, 0, 0)[:2], subi(4, 0, 0)[:4],
                      add_memory(4, 5, 0, 0)[:2],
                      subq_memory(2, 1, 7, 1)[:4]):
            with self.assertRaises(ValueError):
                decode(image, 0)
        self.assertEqual(decode(words(0x04c0, 0), 0).mnemonic, "unsupported")
        for mode in (0, 1, 3, 4, 6):
            self.assertNotEqual(decode(add_memory(2, mode, 0, 0, 0), 0).mnemonic,
                                "add_memory_to_d")
            self.assertNotEqual(decode(subq_memory(2, 1, mode, 0, 0), 0).mnemonic,
                                "subq_memory")

    def test_native_subi_exhaustive_byte_and_wide_boundaries(self):
        image, rows = bytearray(), []
        immediates = {1: (0, 1, 0x7f, 0x80, 0xff),
                      2: (0, 1, 0x7fff, 0x8000, 0xffff),
                      4: (0, 1, 0x7fffffff, 0x80000000, 0xffffffff)}
        for size in (1, 2, 4):
            for reg in range(8):
                for immediate in immediates[size]:
                    rows.append((len(image), size, reg, immediate,
                                 6 if size == 4 else 4))
                    image += subi(size, reg, immediate)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][5]={" + ",".join(
            "{" + ",".join(f"{value}u" for value in row) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    const unsigned boundaries[]={0u,1u,2u,0x7fffu,0x8000u,0x8001u,
        0xffffu,0x7fffffffu,0x80000000u,0x80000001u,0xfffffffeu,0xffffffffu};
    Bus strict;
    for (const auto& row:rows) {
        const unsigned bits=row[1]*8u;
        const unsigned mask=row[1]==4u?0xffffffffu:(1u<<bits)-1u;
        const unsigned sign=1u<<(bits-1u),immediate=row[3]&mask;
        const unsigned samples=row[1]==1u?256u:sizeof(boundaries)/sizeof(boundaries[0]);
        for (unsigned sample=0;sample<samples;++sample) {
            const unsigned value=(row[1]==1u?sample:boundaries[sample])&mask;
            const unsigned result=(value-immediate)&mask;
            CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
            cpu.d[row[2]]=(0xa5a55a5au&~mask)|value;cpu.d_known[row[2]]=mask;
            cpu.sr=0x271fu;cpu.sr_known=0xffe0u;const auto before=cpu;
            if (!step(cpu,strict)||cpu.pc!=row[0]+row[4]||cpu.completed!=1u) return 1;
            if (cpu.d[row[2]]!=((before.d[row[2]]&~mask)|result)||
                cpu.d_known[row[2]]!=mask) return 2;
            const bool overflow=((value^immediate)&(value^result)&sign)!=0u;
            const unsigned flags=(value<immediate?17u:0u)|(result&sign?8u:0u)|
                                 (result==0u?4u:0u)|(overflow?2u:0u);
            if (cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu) return 3;
        }
    }
    return 0;
}
''')

    def test_native_memory_add_values_addresses_flags_and_read_order(self):
        image, rows = bytearray(), []
        forms = ((2, 2, 0), (5, 3, -2), (7, 0, -2),
                 (7, 1, 0x00fffffe))
        for size in (1, 2, 4):
            for mode, reg, displacement in forms:
                for dest in range(8):
                    rows.append((len(image), size, mode, reg, displacement,
                                 dest, len(add_memory(size, mode, reg, dest,
                                                      displacement))))
                    image += add_memory(size, mode, reg, dest, displacement)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][7]={" + ",".join(
            "{" + ",".join(f"{value & 0xffffffff}u" for value in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct Reads:Bus {
    unsigned count=0,bytes=0,value=0,addresses[2]{},widths[2]{};
    std::uint8_t read8(std::uint32_t a)override{addresses[count]=a;widths[count++]=1;return static_cast<std::uint8_t>(value);}
    std::uint16_t read16(std::uint32_t a)override{addresses[count]=a;widths[count++]=2;
      return static_cast<std::uint16_t>(bytes==4u&&count==1u?value>>16u:value);}
};
int main() {
    const unsigned pairs[][2]={{0u,0u},{1u,1u},{0x7fu,1u},{0x7fu,0x80u},
      {0x80u,0x80u},{0xffffu,1u},{0x7fffffffu,1u},{0x80000000u,0x80000000u},
      {0xffffffffu,1u}};
    for (const auto& row:rows) {
        for (const auto& pair:pairs) {
            const unsigned bits=row[1]*8u;
            const unsigned mask=row[1]==4u?0xffffffffu:(1u<<bits)-1u;
            const unsigned sign=1u<<(bits-1u),destination=pair[0]&mask,source=pair[1]&mask;
            const unsigned result=(destination+source)&mask;
            CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
            cpu.d[row[5]]=(0xa5a55a5au&~mask)|destination;cpu.d_known[row[5]]=mask;
            cpu.a[row[3]]=2u;cpu.a_known[row[3]]=true;cpu.sr=0x271fu;cpu.sr_known=0xffe0u;
            const auto before=cpu;Reads bus;bus.bytes=row[1];bus.value=source;
            if (!step(cpu,bus)||cpu.pc!=row[0]+row[6]||cpu.completed!=1u) return 1;
            const unsigned logical=row[2]==7u?row[4]:before.a[row[3]]+row[4];
            const unsigned address=logical&0xffffffu;
            if (bus.addresses[0]!=address||bus.widths[0]!=(row[1]==1u?1u:2u)||
                bus.count!=(row[1]==4u?2u:1u)) return 2;
            if (row[1]==4u&&bus.addresses[1]!=((address+2u)&0xffffffu)) return 3;
            if (cpu.d[row[5]]!=((before.d[row[5]]&~mask)|result)) return 4;
            const bool carry=static_cast<std::uint64_t>(destination)+source>mask;
            const bool overflow=(~(destination^source)&(destination^result)&sign)!=0u;
            const unsigned flags=(carry?17u:0u)|(result&sign?8u:0u)|
                                 (result==0u?4u:0u)|(overflow?2u:0u);
            if (cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu) return 5;
        }
    }
    return 0;
}
''')

    def test_native_memory_subq_rmw_order_flags_and_invalid_helpers(self):
        image, rows = bytearray(), []
        forms = ((2, 2, 0), (5, 3, -2), (7, 0, -2),
                 (7, 1, 0x00fffffe))
        for size in (1, 2, 4):
            for immediate in range(1, 9):
                for mode, reg, displacement in forms:
                    data = subq_memory(size, immediate, mode, reg, displacement)
                    rows.append((len(image), size, immediate, mode, reg,
                                 displacement, len(data)))
                    image += data
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][7]={" + ",".join(
            "{" + ",".join(f"{value & 0xffffffff}u" for value in row) + "}"
            for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct RMW:Bus {
    unsigned count=0,reads=0,bytes=0,value=0,addresses[4]{},widths[4]{},values[4]{};bool writes[4]{};
    void record(unsigned a,unsigned w,unsigned v,bool write){addresses[count]=a;widths[count]=w;
      values[count]=v;writes[count]=write;++count;}
    std::uint8_t read8(std::uint32_t a)override{record(a,1,value,false);++reads;return static_cast<std::uint8_t>(value);}
    std::uint16_t read16(std::uint32_t a)override{const unsigned v=bytes==4u&&reads==0u?value>>16u:value;
      record(a,2,v,false);++reads;return static_cast<std::uint16_t>(v);}
    void write8(std::uint32_t a,std::uint8_t v)override{record(a,1,v,true);}
    void write16(std::uint32_t a,std::uint16_t v)override{record(a,2,v,true);}
};
int main() {
    const unsigned values[]={0u,1u,2u,7u,8u,0x7fu,0x80u,0xffu,0x7fffu,
      0x8000u,0xffffu,0x7fffffffu,0x80000000u,0xffffffffu};
    for (const auto& row:rows) {
        for (unsigned raw:values) {
            const unsigned bits=row[1]*8u;
            const unsigned mask=row[1]==4u?0xffffffffu:(1u<<bits)-1u;
            const unsigned sign=1u<<(bits-1u),value=raw&mask,result=(value-row[2])&mask;
            CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.a[row[4]]=2u;
            cpu.a_known[row[4]]=true;cpu.sr=0x271fu;cpu.sr_known=0xffe0u;
            const auto before=cpu;RMW bus;bus.bytes=row[1];bus.value=value;
            if (!step(cpu,bus)||cpu.pc!=row[0]+row[6]||cpu.completed!=1u) return 1;
            const unsigned logical=row[3]==7u?row[5]:before.a[row[4]]+row[5];
            const unsigned address=logical&0xffffffu,half=row[1]==4u?2u:1u;
            if (bus.count!=half*2u||bus.addresses[0]!=address||bus.writes[0]) return 2;
            if (!bus.writes[half]||bus.values[half]!=(row[1]==4u?result>>16u:result)) return 3;
            const bool overflow=((value^row[2])&(value^result)&sign)!=0u;
            const unsigned flags=(value<row[2]?17u:0u)|(result&sign?8u:0u)|
                                 (result==0u?4u:0u)|(overflow?2u:0u);
            if (cpu.sr!=(0x2700u|flags)||cpu.sr_known!=0xffffu||
                cpu.d!=before.d||cpu.a!=before.a) return 4;
        }
    }
    for (unsigned bytes:{0u,3u,5u}) {
        CPU cpu;RMW bus;
        if (subtract_quick_memory(cpu,bus,0,bytes,1,2)||
            cpu.stop!=Stop::unsupported_instruction||bus.count) return 5;
    }
    for (unsigned immediate:{0u,9u}) {
        CPU cpu;RMW bus;
        if (subtract_quick_memory(cpu,bus,0,1,immediate,2)||
            cpu.stop!=Stop::unsupported_instruction||bus.count) return 6;
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
