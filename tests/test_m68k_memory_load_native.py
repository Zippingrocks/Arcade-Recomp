"""ROM-free non-updating MC68000 memory MOVE and absolute-short LEA."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import move, table


class M68kMemoryLoadTests(unittest.TestCase):
    def test_decoder_load_forms_extensions_and_subset_boundaries(self):
        for size in (1, 2, 4):
            for mode in (2, 5, 7):
                for source in range(2 if mode == 7 else 8):
                    ext = (0xfffc,) if mode == 5 or (mode, source) == (7, 0) else (
                        (0x89ab, 0xcdef) if (mode, source) == (7, 1) else ())
                    displacement = -4 if len(ext) == 1 else 0x89abcdef if ext else 0
                    for dest in range(8):
                        data = move(size, mode, source, 0, dest, *ext)
                        ins = decode(data, 0x100, 0x100)
                        self.assertEqual((ins.mnemonic, ins.size, ins.operands),
                            ("move_memory_to_d", len(data), (size, mode, source, displacement, dest)))
                        for end in range(2, len(data)):
                            with self.assertRaises(ValueError):
                                decode(data[:end], 0)
            # Predecrement and PC-relative forms remain outside this extension.
            for mode, source in ((4, 7), (7, 2), (7, 3), (7, 5)):
                self.assertEqual(decode(move(size, mode, source, 0, 0, 0, 0), 0).mnemonic,
                                 "unsupported")
            for dest_mode in (1, 2, 3, 4, 5, 6, 7):
                if size != 1 and dest_mode == 1:
                    expected = "movea"
                elif dest_mode in (2, 5, 7):
                    expected = "move_memory_to_memory"
                else:
                    expected = "unsupported"
                self.assertEqual(decode(move(size, 2, 0, dest_mode, 0, 0, 0), 0).mnemonic,
                                 expected)
        for reg in range(8):
            for address in (0, 1, 0x7fff, 0x8000, 0xfffe, 0xffff):
                ins = decode(words(0x41f8 | reg << 9, address), 0)
                self.assertEqual((ins.size, ins.mnemonic, ins.operands),
                    (4, "lea_absolute", (reg, address if address < 0x8000 else address - 0x10000)))
            with self.assertRaises(ValueError):
                decode(words(0x41f8 | reg << 9), 0)
        for opcode in (0x41d0, 0x41e0, 0x41f0, 0x41fa, 0x41fb, 0x41fc):
            self.assertEqual(decode(words(opcode, 0, 0), 0).mnemonic, "unsupported")

    def test_native_all_load_sizes_registers_knownness_flags_and_word_order(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            for mode in (2, 5, 7):
                for source in range(2 if mode == 7 else 8):
                    ext = (0xfffc,) if mode == 5 else (0xfffe,) if (mode, source) == (7, 0) else (
                        (0x34ff, 0xfffe) if (mode, source) == (7, 1) else ())
                    for dest in range(8):
                        instruction = move(size, mode, source, 0, dest, *ext)
                        rows.append((len(image), size, mode, source, dest, len(instruction)))
                        image += instruction
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
struct Reads:Bus {
    unsigned count=0;std::uint32_t value=0;unsigned bytes=0;
    std::uint8_t read8(std::uint32_t address)override {
        if(bytes!=1||count++||address!=0xfffffeu)throw std::runtime_error("bad byte read");
        return static_cast<std::uint8_t>(value);
    }
    std::uint16_t read16(std::uint32_t address)override {
        if(bytes==1||count>1||address!=(count==0?0xfffffeu:0u))throw std::runtime_error("bad word read");
        ++count;return static_cast<std::uint16_t>(bytes==4&&count==1?value>>16u:value);
    }
};
int main() {
    for(const auto& row:rows)for(unsigned sample=0;sample<(row[1]==1?256u:64u);++sample)
      for(unsigned x=0;x<2;++x)for(unsigned known_x=0;known_x<2;++known_x) {
        const unsigned mask=row[1]==4?0xffffffffu:(1u<<(row[1]*8u))-1u;
        const unsigned sign=1u<<(row[1]*8u-1u);
        const unsigned boundaries[]={0,1,sign-1u,sign,sign+1u,mask};
        const unsigned value=row[1]==1?sample:(sample<6?boundaries[sample]:sample*0x9e3779b9u)&mask;
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for(unsigned i=0;i<8;++i) {
            cpu.d[i]=0xdeadbeefu^i;cpu.d_known[i]=(sample%3==0?0u:sample%3==1?0xff00ff00u:0xffffffffu);
            cpu.a[i]=0x12345678u+i;cpu.a_known[i]=false;
        }
        if(row[2]!=7) {cpu.a[row[3]]=row[2]==2?0x12fffffeu:0x13000002u;cpu.a_known[row[3]]=true;}
        cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));
        cpu.sr_known=static_cast<std::uint16_t>(known_x?0xfff0u:0xffe0u);
        const auto before=cpu;Reads bus;bus.bytes=row[1];bus.value=value;
        if(!step(cpu,bus)||cpu.pc!=row[0]+row[5]||cpu.completed!=1||cpu.stop!=Stop::none)return 1;
        if(bus.count!=(row[1]==4?2u:1u))return 2;
        const unsigned flags=(value&sign?8u:0u)|(value==0?4u:0u);
        if(cpu.sr!=(0x2700u|(x<<4)|flags)||cpu.sr_known!=(known_x?0xffffu:0xffefu))return 3;
        for(unsigned reg=0;reg<8;++reg) {
            const unsigned expected=reg==row[4]?(before.d[reg]&~mask)|value:before.d[reg];
            const unsigned known=before.d_known[reg]|(reg==row[4]?mask:0u);
            if(cpu.d[reg]!=expected||cpu.d_known[reg]!=known)return 4;
        }
        if(cpu.a!=before.a||cpu.a_known!=before.a_known)return 5;
    }
    for(const auto& row:rows)if(row[2]!=7) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.a_known[row[3]]=false;
        cpu.d[row[4]]=0xdeadbeef;cpu.d_known[row[4]]=0xff00ff00;cpu.sr=0x271f;
        const auto before=cpu;Reads bus;
        if(step(cpu,bus)||bus.count||cpu.stop!=Stop::undefined_state||cpu.pc!=row[0]||cpu.completed)return 6;
        if(cpu.d!=before.d||cpu.d_known!=before.d_known||cpu.a!=before.a||cpu.a_known!=before.a_known||
           cpu.sr!=before.sr||cpu.sr_known!=before.sr_known)return 7;
    }
    return 0;
}
''')

    def test_native_rejected_reads_preserve_destination_flags_and_pc(self):
        sources = []
        for size in (1, 2, 4):
            source, _ = emit_cpp(move(size, 2, 3, 0, 3) + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"load_{size}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);
Step steps[]={load_1::step,load_2::step,load_4::step};
struct Reads:Bus {
    unsigned attempts=0,accepted=0,deny=0,addresses[2]{};
    void record(unsigned address,unsigned width) {
        if(attempts>=2)throw std::runtime_error("extra transaction");
        addresses[attempts++]=address;
        if(attempts==deny)throw BusFault(address,false,static_cast<std::uint8_t>(width));
        ++accepted;
    }
    std::uint8_t read8(std::uint32_t a)override{record(a,1);return 0x80;}
    std::uint16_t read16(std::uint32_t a)override{record(a,2);return 0x1234;}
};
struct ByteOnly:Bus {
    unsigned reads=0;
    std::uint8_t read8(std::uint32_t)override{++reads;return 0;}
};
bool unchanged(const CPU& cpu,const CPU& before) {
    return cpu.d==before.d&&cpu.a==before.a&&cpu.d_known==before.d_known&&cpu.a_known==before.a_known&&
           cpu.sr==before.sr&&cpu.sr_known==before.sr_known&&cpu.pc==before.pc&&cpu.completed==before.completed;
}
CPU initial() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0xfffffffeu;cpu.a_known[3]=true;
    cpu.d[3]=0xdeadbeef;cpu.d_known[3]=0xf00f00f0;cpu.sr=0x271f;cpu.sr_known=0xfff0;
    return cpu;
}
int main() {
    for(unsigned index=0;index<3;++index)for(unsigned denial=1;denial<=(index==2?2u:1u);++denial) {
        auto cpu=initial();const auto before=cpu;Reads bus;bus.deny=denial;
        if(steps[index](cpu,bus)||cpu.stop!=Stop::bus_access||cpu.stop_pc||!unchanged(cpu,before))return 1;
        if(bus.attempts!=denial||bus.accepted!=denial-1u||bus.addresses[0]!=0xfffffeu||
           (denial==2&&bus.addresses[1]!=0))return 2;
        if(cpu.access_address!=(denial==1?0xfffffeu:0)||cpu.access_width!=(index==0?1u:2u)||cpu.access_write)return 3;
    }
    for(unsigned index=1;index<3;++index) {
        auto cpu=initial();cpu.a[3]=0x01000001;const auto before=cpu;Reads bus;
        if(steps[index](cpu,bus)||cpu.stop!=Stop::data_address||bus.attempts||!unchanged(cpu,before)||
           cpu.access_address!=1||cpu.access_write||cpu.access_width!=(index==1?2u:4u))return 4;
        cpu=initial();ByteOnly bytes;
        if(steps[index](cpu,bytes)||cpu.stop!=Stop::bus_access||bytes.reads||cpu.access_width!=2)return 5;
    }
    for(unsigned index=0;index<3;++index) {
        auto cpu=initial();const auto before=cpu;Bus strict;
        if(steps[index](cpu,strict)||cpu.stop!=Stop::bus_access||!unchanged(cpu,before)||
           cpu.access_address!=0xfffffeu||cpu.access_width!=(index==0?1u:2u)||cpu.access_write)return 6;
    }
    auto cpu=initial();cpu.a[3]=0x01000001;Reads bus;
    if(!steps[0](cpu,bus)||bus.attempts!=1||bus.addresses[0]!=1||cpu.d[3]!=0xdeadbe80||cpu.sr!=0x2718)return 7;
    return 0;
}
''')

    def test_native_absolute_short_lea_preserves_all_flags_without_bus_access(self):
        image, rows = bytearray(), []
        for reg in range(8):
            for address in (0, 1, 0x1234, 0x7ffe, 0x7fff, 0x8000, 0xfffe, 0xffff):
                rows.append((len(image), reg, address))
                image += words(0x41f8 | reg << 9, address)
        image += words(0xffff)
        source, _ = emit_cpp(image, 0)
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus strict;
    for(const auto& row:rows)for(unsigned flags=0;flags<32;++flags)for(unsigned known=0;known<32;++known) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for(unsigned reg=0;reg<8;++reg){cpu.a[reg]=0xdeadbeefu+reg;cpu.a_known[reg]=reg%2;}
        cpu.sr=static_cast<std::uint16_t>(0x2700u|flags);cpu.sr_known=static_cast<std::uint16_t>(0xffe0u|known);
        const auto before=cpu;
        if(!step(cpu,strict)||cpu.pc!=row[0]+4||cpu.completed!=1)return 1;
        const unsigned address=row[2]<0x8000u?row[2]:row[2]|0xffff0000u;
        for(unsigned reg=0;reg<8;++reg) {
            if(cpu.a[reg]!=(reg==row[1]?address:before.a[reg])||
               cpu.a_known[reg]!=(reg==row[1]?true:before.a_known[reg]))return 2;
        }
        if(cpu.d!=before.d||cpu.d_known!=before.d_known||cpu.sr!=before.sr||cpu.sr_known!=before.sr_known)return 3;
    }
    return 0;
}
''')

    def test_synthetic_memory_load_lea_and_compare_sequence(self):
        image = (move(1, 7, 0, 0, 4, 0x1234) + words(0x41f8, 0xffff) +
                 words(0x0c04, 0x80, 0x6702, 0xffff, 0xffff))
        source, report = emit_cpp(image, 0)
        self.assertEqual((report.translated, report.unsupported), (4, (14, 16)))
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct Data:Bus {
    unsigned reads=0;
    std::uint8_t read8(std::uint32_t address)override {
        if(address!=0x1234)throw BusFault(address,false);
        ++reads;return 0x80;
    }
};
int main() {
    CPU cpu;reset_from_vectors(cpu,0x2000,0);Data bus;
    cpu.d[4]=0xdeadbeef;cpu.sr=0x271f;
    while(step(cpu,bus))if(cpu.completed>4)return 1;
    if(cpu.stop!=Stop::unsupported_instruction||cpu.pc!=16||cpu.completed!=4||bus.reads!=1||
       cpu.d[4]!=0xdeadbe80||cpu.d_known[4]!=0xff||cpu.a[0]!=0xffffffffu||!cpu.a_known[0]||
       cpu.sr!=0x2714||cpu.sr_known!=0xffef)return 2;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
