"""ROM-free MC68000 CLR memory semantics and ordered transaction boundaries."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import table


def clr(size, mode, reg, *extension):
    return words(0x4200 | {1: 0, 2: 1, 4: 2}[size] << 6 | mode << 3 | reg, *extension)


def forms():
    image, rows = bytearray(), []
    for size in (1, 2, 4):
        for mode in (2, 3, 5, 7):
            for reg in range(2 if mode == 7 else 8):
                extension = (0xfffc,) if mode == 5 else (0xfffe,) if (mode, reg) == (7, 0) else (
                    (0x12ff, 0xfffe) if (mode, reg) == (7, 1) else ())
                data = clr(size, mode, reg, *extension)
                rows.append((len(image), size, mode, reg, len(data)))
                image += data
    return bytes(image) + words(0xffff), rows


BUS = r'''
using namespace arcaderecomp_m68k_generated;
struct Ordered:Bus {
    unsigned size=0,base=0xfffffeu,attempts=0,accepted=0,deny=0,writes=0;
    unsigned high=0x8123u,low=0x4567u;
    void access(unsigned address,unsigned width,bool write,unsigned value=0) {
        const bool long_access=size==4;
        const unsigned count=long_access?4u:2u;
        if(attempts>=count)throw std::runtime_error("extra transaction");
        const unsigned index=attempts++;
        const unsigned expected_address=(long_access&&(index==1||index==2))?(base+2u)&0xffffffu:base;
        if(address!=expected_address||width!=(size==1?1u:2u)||write!=(index>=(long_access?2u:1u)))
            throw std::runtime_error("incorrect CLR transaction order/width");
        if(attempts==deny)throw BusFault(address,write,static_cast<std::uint8_t>(width));
        ++accepted;
        if(write) {
            if(value)throw std::runtime_error("CLR write must be zero");
            ++writes;
            if(address==base)high=0;else low=0;
        }
    }
    std::uint8_t read8(std::uint32_t a)override{access(a,1,false);return 0x81;}
    std::uint16_t read16(std::uint32_t a)override{access(a,2,false);return static_cast<std::uint16_t>(a==base?high:low);}
    void write8(std::uint32_t a,std::uint8_t v)override{access(a,1,true,v);}
    void write16(std::uint32_t a,std::uint16_t v)override{access(a,2,true,v);}
};
bool unchanged(const CPU& cpu,const CPU& before) {
    return cpu.d==before.d&&cpu.d_known==before.d_known&&cpu.a==before.a&&cpu.a_known==before.a_known&&
           cpu.pc==before.pc&&cpu.sr==before.sr&&cpu.sr_known==before.sr_known&&cpu.completed==before.completed;
}
CPU initial(const unsigned* row,unsigned flags=31,unsigned known=0) {
    CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
    for(unsigned reg=0;reg<8;++reg) {
        cpu.d[reg]=0xdeadbeefu+reg;cpu.d_known[reg]=0xff00ff00u^reg;
        cpu.a[reg]=0x12345678u+reg;cpu.a_known[reg]=false;
    }
    if(row[2]!=7) {cpu.a[row[3]]=row[2]==5?2u:0xfffffffeu;cpu.a_known[row[3]]=true;}
    cpu.sr=static_cast<std::uint16_t>(0x2700u|flags);
    cpu.sr_known=static_cast<std::uint16_t>(0xffe0u|known);
    return cpu;
}
'''


class M68kClrMemoryTests(unittest.TestCase):
    def test_decoder_sizes_modes_extensions_and_exclusions(self):
        for size in (1, 2, 4):
            for mode in (2, 3, 5, 7):
                for reg in range(2 if mode == 7 else 8):
                    ext = (0xfffc,) if mode == 5 or (mode, reg) == (7, 0) else (
                        (0x89ab, 0xcdef) if (mode, reg) == (7, 1) else ())
                    displacement = -4 if len(ext) == 1 else 0x89abcdef if ext else 0
                    data = clr(size, mode, reg, *ext)
                    ins = decode(data, 0x100, 0x100)
                    self.assertEqual((ins.mnemonic, ins.size, ins.operands),
                                     ("clr_memory", len(data), (size, mode, reg, displacement)))
                    for end in range(2, len(data)):
                        with self.assertRaises(ValueError):
                            decode(data[:end], 0)
            for mode, reg in ((1, 0), (4, 0), (6, 0), (7, 2), (7, 3), (7, 4), (7, 5), (7, 7)):
                self.assertEqual(decode(clr(size, mode, reg, 0, 0), 0).mnemonic, "unsupported")
        for mode in range(8):
            self.assertEqual(decode(words(0x42c0 | mode << 3, 0, 0), 0).mnemonic, "unsupported")

    def test_native_all_forms_flags_knownness_postincrement_and_bus_order(self):
        image, rows = forms()
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        native(source, table("rows", rows) + BUS + r'''
int main() {
    for(const auto& row:rows)for(unsigned flags=0;flags<32;++flags)for(unsigned known=0;known<32;++known) {
        auto cpu=initial(row,flags,known);const auto before=cpu;Ordered bus;bus.size=row[1];
        if(!step(cpu,bus)||cpu.stop!=Stop::none||cpu.pc!=row[0]+row[4]||cpu.completed!=1)return 1;
        if(bus.attempts!=(row[1]==4?4u:2u)||bus.accepted!=bus.attempts||
           bus.writes!=(row[1]==4?2u:1u)||bus.high||bus.low!=(row[1]==4?0u:0x4567u))return 2;
        if(cpu.sr!=(0x2704u|(flags&16u))||cpu.sr_known!=(0xffefu|(known&16u)))return 3;
        if(cpu.d!=before.d||cpu.d_known!=before.d_known||cpu.a_known!=before.a_known)return 4;
        for(unsigned reg=0;reg<8;++reg) {
            const unsigned increment=row[1]==1&&reg==7?2u:row[1];
            const unsigned expected=before.a[reg]+(row[2]==3&&row[3]==reg?increment:0u);
            if(cpu.a[reg]!=expected)return 5;
        }
    }
    for(const auto& row:rows)if(row[2]!=7) {
        auto cpu=initial(row);cpu.a_known[row[3]]=false;const auto before=cpu;Ordered bus;bus.size=row[1];
        if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||bus.attempts||!unchanged(cpu,before))return 6;
    }
    return 0;
}
''')

    def test_native_every_refused_transaction_preserves_cpu_and_accepted_bus_effects(self):
        image, rows = forms()
        source, _ = emit_cpp(image, 0)
        native(source, table("rows", rows) + BUS + r'''
int main() {
    for(const auto& row:rows)for(unsigned deny=1;deny<=(row[1]==4?4u:2u);++deny) {
        auto cpu=initial(row);const auto before=cpu;Ordered bus;bus.size=row[1];bus.deny=deny;
        if(step(cpu,bus)||cpu.stop!=Stop::bus_access||cpu.stop_pc!=row[0]||!unchanged(cpu,before))return 1;
        if(bus.attempts!=deny||bus.accepted!=deny-1u||bus.high!=0x8123u||
           bus.low!=(row[1]==4&&deny==4?0u:0x4567u)||bus.writes!=(deny==4?1u:0u))return 2;
        const unsigned address=row[1]==4&&(deny==2||deny==3)?0u:0xfffffeu;
        if(cpu.access_address!=address||cpu.access_width!=(row[1]==1?1u:2u)||
           cpu.access_write!=(deny>(row[1]==4?2u:1u)))return 3;
        // A failed generated step is latched. Calling it again is not a retry.
        if(step(cpu,bus)||bus.attempts!=deny||bus.accepted!=deny-1u||!unchanged(cpu,before))return 4;
    }
    return 0;
}
''')

    def test_native_alignment_strict_widths_and_discarded_word_read_contract(self):
        image, rows = forms()
        source, _ = emit_cpp(image, 0)
        native(source, table("rows", rows) + BUS + r'''
struct ByteOnly:Bus {
    unsigned bytes=0;
    std::uint8_t read8(std::uint32_t)override{++bytes;return 0;}
    void write8(std::uint32_t,std::uint8_t)override{++bytes;}
};
struct DiscardOnly:Bus {
    unsigned calls=0;
    void read16_discard(std::uint32_t address)override {
        if(address!=0xfffffeu)throw BusFault(address,false,2);
        if(calls++)throw std::runtime_error("extra discarded read");
    }
    void write16(std::uint32_t address,std::uint16_t value)override {
        if(address!=0xfffffeu||value||calls++!=1)throw std::runtime_error("bad discard/write sequence");
    }
};
int main() {
    for(const auto& row:rows) {
        auto cpu=initial(row);const auto before=cpu;Bus strict;
        if(step(cpu,strict)||cpu.stop!=Stop::bus_access||!unchanged(cpu,before)||cpu.access_write||
           cpu.access_address!=0xfffffeu||cpu.access_width!=(row[1]==1?1u:2u))return 1;
        if(row[1]!=1) {
            cpu=initial(row);ByteOnly bytes;
            if(step(cpu,bytes)||cpu.stop!=Stop::bus_access||bytes.bytes||cpu.access_width!=2)return 2;
        }
        if(row[2]==2||row[2]==3) {
            cpu=initial(row);cpu.a[row[3]]=0x01000001u;const auto odd_before=cpu;
            Ordered bus;bus.size=row[1];bus.base=1;
            if(row[1]==1) {
                if(!step(cpu,bus)||bus.attempts!=2||cpu.a[row[3]]!=
                   odd_before.a[row[3]]+(row[2]==3?(row[3]==7?2u:1u):0u))return 3;
            } else if(step(cpu,bus)||cpu.stop!=Stop::data_address||bus.attempts||!unchanged(cpu,odd_before)||
                      cpu.access_address!=1||cpu.access_width!=row[1]||cpu.access_write)return 4;
        }
        if(row[1]==2) {
            cpu=initial(row);DiscardOnly bus;
            try{(void)bus.read16(0xfffffeu);return 5;}catch(const BusFault&){}
            if(!step(cpu,bus)||bus.calls!=2)return 6;
        }
        if(row[1]==4) {
            cpu=initial(row);const auto long_before=cpu;DiscardOnly bus;
            if(step(cpu,bus)||cpu.stop!=Stop::bus_access||bus.calls!=1||cpu.access_address||
               cpu.access_write||!unchanged(cpu,long_before))return 7;
        }
    }
    CPU cpu;Bus strict;
    if(clear_memory(cpu,strict,0,3)||cpu.stop!=Stop::unsupported_instruction)return 8;
    return 0;
}
''')

    def test_native_synthetic_clear_postincrement_loop(self):
        # Invented program: clear three longs using LEA, MOVEQ and DBRA.
        image = words(0x41f8, 0x1000, 0x7402) + clr(4, 3, 0) + words(0x51ca, 0xfffc, 0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual((report.translated, report.unsupported), (4, (12,)))
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct Memory:Bus {
    std::array<std::uint16_t,6> memory{{1,2,3,4,5,6}};unsigned calls=0;
    void check(unsigned address,bool write) {
        if(calls>=12)throw std::runtime_error("extra access");
        const unsigned offset=calls%4;
        const unsigned expected=0x1000u+(calls/4)*4u+((offset==1||offset==2)?2u:0u);
        if(address!=expected||write!=(offset>=2))throw std::runtime_error("wrong loop access");
        ++calls;
    }
    std::uint16_t read16(std::uint32_t a)override{check(a,false);return memory[(a-0x1000u)/2];}
    void write16(std::uint32_t a,std::uint16_t v)override{check(a,true);memory[(a-0x1000u)/2]=v;}
};
int main() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);Memory bus;
    while(step(cpu,bus))if(cpu.completed>8)return 1;
    if(cpu.completed!=8||cpu.stop!=Stop::unsupported_instruction||cpu.pc!=12||cpu.a[0]!=0x100cu||
       cpu.d[2]!=0xffffu||bus.calls!=12||cpu.sr!=0x2704u)return 2;
    for(const auto value:bus.memory)if(value)return 3;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
