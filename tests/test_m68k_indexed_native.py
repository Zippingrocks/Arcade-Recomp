"""Native original-MC68000 brief indexed effective-address coverage."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


SIZE_BITS = {1: 0, 2: 0x40, 4: 0x80}
MOVE_TOP = {1: 0x1000, 2: 0x3000, 4: 0x2000}


def extension(index, address=False, long=False, displacement=0):
    return ((0x8000 if address else 0) | index << 12 |
            (0x0800 if long else 0) | (displacement & 0xff))


def clr_indexed(size, base, ext):
    return words(0x4200 | SIZE_BITS[size] | 6 << 3 | base, ext)


def movea_indexed(size, base, dest, ext):
    return words((0x3040 if size == 2 else 0x2040) | dest << 9 |
                 6 << 3 | base, ext)


def move_indexed_to_d(size, base, dest, ext):
    return words(MOVE_TOP[size] | dest << 9 | 6 << 3 | base, ext)


def move_d_to_indexed(size, source, base, ext):
    return words(MOVE_TOP[size] | base << 9 | 6 << 6 | source, ext)


class M68kIndexedAddressTests(unittest.TestCase):
    def test_decoder_forms_fields_reserved_bits_and_truncation(self):
        extensions = (extension(0, displacement=-128),
                      extension(7, long=True, displacement=127),
                      extension(3, address=True, displacement=-1),
                      extension(4, address=True, long=True, displacement=1))
        for size in (1, 2, 4):
            for base in range(8):
                ext = extensions[(size + base) % len(extensions)]
                ins = decode(clr_indexed(size, base, ext), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                 (4, "clr_memory_indexed", (size, base, ext)))
                for reg in range(8):
                    load = decode(move_indexed_to_d(size, base, reg, ext), 0)
                    store = decode(move_d_to_indexed(size, reg, base, ext), 0)
                    self.assertEqual((load.size, load.mnemonic, load.operands),
                                     (4, "move_indexed_to_d",
                                      (size, base, reg, ext)))
                    self.assertEqual((store.size, store.mnemonic, store.operands),
                                     (4, "move_d_to_indexed",
                                      (size, reg, base, ext)))
        for size in (2, 4):
            for base in range(8):
                for dest in range(8):
                    ext = extensions[(base + dest) % len(extensions)]
                    ins = decode(movea_indexed(size, base, dest, ext), 0)
                    self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                                     (4, "movea_indexed",
                                      (size, base, dest, ext)))
        invalid = extension(0) | 0x0100
        for image in (clr_indexed(1, 0, invalid),
                      movea_indexed(4, 0, 0, invalid),
                      move_indexed_to_d(2, 0, 0, invalid),
                      move_d_to_indexed(4, 0, 0, invalid)):
            self.assertEqual(decode(image, 0).mnemonic, "unsupported")
        for image in (words(0x4230), words(0x2070), words(0x3030),
                      words(0x2180)):
            with self.assertRaises(ValueError):
                decode(image, 0)

    def test_native_address_oracle_and_knownness_guards(self):
        source, _ = emit_cpp(words(0x4e71, 0xffff), 0)
        native(source, r'''
using namespace arcaderecomp::m68k;
bool same(const CPU& cpu,const CPU& before) {
    return cpu.d==before.d&&cpu.a==before.a&&cpu.d_known==before.d_known&&
           cpu.a_known==before.a_known&&cpu.sr==before.sr&&
           cpu.sr_known==before.sr_known&&cpu.pc==before.pc&&
           cpu.completed==before.completed;
}
CPU initial() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);
    for (unsigned reg=0;reg<8u;++reg) {
        cpu.d[reg]=0x70008000u+reg*0x1111u;cpu.d_known[reg]=0xffffffffu;
        cpu.a[reg]=0x12002000u+reg*0x101u;cpu.a_known[reg]=true;
    }
    return cpu;
}
int main() {
    const unsigned displacements[]={0u,1u,0x7fu,0x80u,0xffu};
    for (unsigned base=0;base<8u;++base) {
        for (unsigned index=0;index<8u;++index) {
            for (unsigned address_index=0;address_index<2u;++address_index) {
                for (unsigned long_index=0;long_index<2u;++long_index) {
                    for (unsigned displacement:displacements) {
                        CPU cpu=initial();std::uint32_t actual=0xdeadbeefu;
                        const unsigned ext=(address_index<<15u)|(index<<12u)|
                                           (long_index<<11u)|displacement;
                        if (!indexed_address(cpu,base,static_cast<std::uint16_t>(ext),actual)) return 1;
                        unsigned value=address_index?cpu.a[index]:cpu.d[index];
                        if (!long_index) value=(value&0x8000u)?
                            ((value&0xffffu)|0xffff0000u):(value&0xffffu);
                        const unsigned disp=(displacement&0x80u)?
                            (displacement|0xffffff00u):displacement;
                        if (actual!=cpu.a[base]+value+disp) return 2;
                    }
                }
            }
        }
    }
    for (unsigned kind=0;kind<3u;++kind) {
        CPU cpu=initial();std::uint32_t actual=0xdeadbeefu;
        const unsigned ext=kind==2u?0x3800u:0xb000u;
        if (kind==0u) cpu.a_known[0]=false;
        else if (kind==1u) cpu.a_known[3]=false;
        else cpu.d_known[3]=0xffffu;
        const auto before=cpu;
        if (indexed_address(cpu,0,static_cast<std::uint16_t>(ext),actual)||
            cpu.stop!=Stop::undefined_state||actual!=0xdeadbeefu||!same(cpu,before)) return 3;
    }
    for (unsigned ext:{0x0100u,0x0200u,0x0400u,0x0700u}) {
        CPU cpu=initial();std::uint32_t actual=0xdeadbeefu;const auto before=cpu;
        if (indexed_address(cpu,0,static_cast<std::uint16_t>(ext),actual)||
            cpu.stop!=Stop::unsupported_instruction||actual!=0xdeadbeefu||!same(cpu,before)) return 4;
    }
    CPU cpu=initial();std::uint32_t actual=0xdeadbeefu;const auto before=cpu;
    if (indexed_address(cpu,8,0,actual)||cpu.stop!=Stop::unsupported_instruction||
        actual!=0xdeadbeefu||!same(cpu,before)) return 5;
    return 0;
}
''')

    def test_native_four_instruction_families_values_flags_and_transactions(self):
        image, rows = bytearray(), []
        ext = extension(4, displacement=16)
        for size in (1, 2, 4):
            for base in range(8):
                reg = (base + 1) & 7
                if reg == 4:
                    reg = 5
                rows.append((len(image), 0, size, base, reg))
                image += clr_indexed(size, base, ext)
                rows.append((len(image), 1, size, base, reg))
                image += move_indexed_to_d(size, base, reg, ext)
                rows.append((len(image), 2, size, base, reg))
                image += move_d_to_indexed(size, reg, base, ext)
                if size != 1:
                    rows.append((len(image), 3, size, base, base))
                    image += movea_indexed(size, base, base, ext)
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][5]={" + ",".join(
            "{" + ",".join(map(str, row)) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
struct Events:Bus {
    unsigned count=0,reads=0,bytes=0,value=0,addresses[4]{},widths[4]{},values[4]{};
    bool writes[4]{};
    void record(unsigned address,unsigned width,unsigned data,bool write) {
        addresses[count]=address;widths[count]=width;values[count]=data;writes[count]=write;++count;
    }
    std::uint8_t read8(std::uint32_t a)override {
        record(a,1,value&0xffu,false);++reads;return static_cast<std::uint8_t>(value);
    }
    std::uint16_t read16(std::uint32_t a)override {
        const unsigned result=bytes==4u&&reads==0u?value>>16u:value&0xffffu;
        record(a,2,result,false);++reads;return static_cast<std::uint16_t>(result);
    }
    void write8(std::uint32_t a,std::uint8_t v)override{record(a,1,v,true);}
    void write16(std::uint32_t a,std::uint16_t v)override{record(a,2,v,true);}
};
int main() {
    for (const auto& row:rows) {
        const unsigned mask=row[2]==4u?0xffffffffu:(1u<<(row[2]*8u))-1u;
        const unsigned sign=1u<<(row[2]*8u-1u);
        const unsigned input=0x80000081u&mask;
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for (unsigned reg=0;reg<8u;++reg) {
            cpu.a[reg]=0x12001000u+reg*0x100u;cpu.a_known[reg]=true;
            cpu.d[reg]=0xa5a55a5au;cpu.d_known[reg]=0xffffffffu;
        }
        cpu.d[4]=(cpu.d[4]&0xffff0000u)|0xfff0u;
        cpu.d[row[4]]=(cpu.d[row[4]]&~mask)|input;
        if (row[4]==4u) cpu.d[4]=(cpu.d[4]&0xffff0000u)|0xfff0u;
        cpu.sr=0x271fu;cpu.sr_known=0xffffu;
        const auto before=cpu;const unsigned address=before.a[row[3]]&0xffffffu;
        Events bus;bus.bytes=row[2];bus.value=input;
        if (!step(cpu,bus)||cpu.stop!=Stop::none||cpu.pc!=row[0]+4u||
            cpu.completed!=1u) return 1;
        if (bus.addresses[0]!=address) return 2;
        if (row[1]==0u) {
            const unsigned expected=row[2]==4u?4u:2u;
            if (bus.count!=expected||!bus.writes[expected-1u]||
                cpu.sr!=0x2714u||cpu.sr_known!=0xffffu) return 4;
            for (unsigned event=expected/2u;event<expected;++event) {
                if (!bus.writes[event]||bus.values[event]!=0u) return 10;
            }
            if (cpu.d!=before.d||cpu.d_known!=before.d_known||cpu.a!=before.a||
                cpu.a_known!=before.a_known) return 11;
        } else if (row[1]==1u) {
            const unsigned expected=row[2]==4u?2u:1u;
            if (bus.count!=expected||bus.writes[0]||
                cpu.d[row[4]]!=((before.d[row[4]]&~mask)|input)) return 5;
            const unsigned flags=(input&sign?8u:0u)|(input==0u?4u:0u);
            if (cpu.sr!=(0x2710u|flags)||cpu.sr_known!=0xffffu) return 6;
        } else if (row[1]==2u) {
            const unsigned expected=row[2]==4u?2u:1u;
            if (bus.count!=expected||!bus.writes[0]) return 7;
            if (bus.values[0]!=(row[2]==4u?input>>16u:input)||
                (row[2]==4u&&bus.values[1]!=(input&0xffffu))) return 12;
            const unsigned flags=(input&sign?8u:0u)|(input==0u?4u:0u);
            if (cpu.sr!=(0x2710u|flags)||cpu.sr_known!=0xffffu) return 8;
            if (cpu.d!=before.d||cpu.d_known!=before.d_known||cpu.a!=before.a||
                cpu.a_known!=before.a_known) return 13;
        } else {
            const unsigned expected=row[2]==4u?2u:1u;
            const unsigned result=row[2]==2u&&input&0x8000u?input|0xffff0000u:input;
            if (bus.count!=expected||bus.writes[0]||cpu.a[row[4]]!=result||
                !cpu.a_known[row[4]]||cpu.sr!=before.sr||
                cpu.sr_known!=before.sr_known) return 9;
        }
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
