"""ROM-free MC68000 CMPI decoding, native flags, and ordered bus reads."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import table


def cmpi(size, immediate, mode, reg, *extensions):
    opcode = 0x0c00 | {1: 0, 2: 0x40, 4: 0x80}[size] | mode << 3 | reg
    data = (immediate >> 16, immediate & 0xffff) if size == 4 else (immediate,)
    return words(opcode, *data, *extensions)


class M68kCompareImmediateTests(unittest.TestCase):
    def test_decoder_sizes_registers_extensions_and_excluded_modes(self):
        for size in (1, 2, 4):
            immediate = 0x89abcdef if size == 4 else 0xabcd
            masked = immediate & ((1 << (size * 8)) - 1)
            for mode in (0, 2, 5, 7):
                for reg in range(2 if mode == 7 else 8):
                    extension = (0xfff0,) if mode == 5 or (mode, reg) == (7, 0) else (
                        (0x89ab, 0xcdef) if (mode, reg) == (7, 1) else ())
                    displacement = (-16 if len(extension) == 1 else
                                    0x89abcdef if len(extension) == 2 else 0)
                    data = cmpi(size, immediate, mode, reg, *extension)
                    ins = decode(data, 0x100, 0x100)
                    self.assertEqual((ins.mnemonic, ins.size, ins.operands),
                                     ("cmpi", len(data), (size, masked, mode, reg, displacement)))
                    for truncated in range(2, len(data)):
                        with self.assertRaises(ValueError):
                            decode(data[:truncated], 0)
            for mode in (1, 3, 4, 6, 7):
                for reg in range(8):
                    if mode == 7 and reg < 2:
                        continue
                    # An, updating/indexed, PC-relative and immediate EAs are
                    # outside this subset; later 680x0 CMPI PC forms stay out.
                    self.assertEqual(decode(cmpi(size, immediate, mode, reg), 0).mnemonic,
                                     "unsupported")
        for opcode in range(0x0cc0, 0x0d00):
            self.assertEqual(decode(words(opcode), 0).mnemonic, "unsupported")

    def test_native_register_comparison_against_wide_signed_oracle(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            mask = (1 << (size * 8)) - 1
            samples = range(256) if size == 1 else (
                0, 1, 2, mask >> 1, (mask >> 1) - 1, (mask >> 1) + 1,
                (mask >> 1) + 2, mask - 1, mask, 0x55555555 & mask,
                0xaaaaaaaa & mask, 0x9e3779b9 & mask, 0x12345678 & mask,
                0xfedcba98 & mask, 0x80008000 & mask, 0x00ff00ff & mask)
            for index, immediate in enumerate(samples):
                reg = index % 8
                instruction = cmpi(size, immediate, 0, reg)
                rows.append((len(image), size, immediate, reg, len(instruction)))
                image += instruction
        image += words(0xffff)
        source, report = emit_cpp(image, 0)
        self.assertEqual(report.translated, len(rows))
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus bus;
    for(const auto& row:rows) for(unsigned sample=0;sample<(row[1]==1?256u:128u);++sample)
      for(unsigned x=0;x<2;++x) for(unsigned known_x=0;known_x<2;++known_x) {
        const std::uint64_t modulus=std::uint64_t{1}<<(row[1]*8u), mask=modulus-1u;
        const std::uint64_t boundary[]={0,1,modulus/2u-1u,modulus/2u,modulus/2u+1u,mask,row[2]};
        const unsigned full=row[1]==1 ? 0xdead0000u|sample : sample<7 ?
            static_cast<unsigned>(boundary[sample]) : sample*0x9e3779b9u;
        const std::uint64_t value=full&mask;
        const std::int64_t signed_value=static_cast<std::int64_t>(value)-
            (value>=modulus/2u?static_cast<std::int64_t>(modulus):0);
        const std::int64_t signed_immediate=static_cast<std::int64_t>(row[2])-
            (row[2]>=modulus/2u?static_cast<std::int64_t>(modulus):0);
        const std::int64_t exact=signed_value-signed_immediate;
        const bool overflow=exact < -static_cast<std::int64_t>(modulus/2u) ||
                            exact >= static_cast<std::int64_t>(modulus/2u);
        const auto result=(value+modulus-row[2])%modulus;
        const unsigned flags=(result>=modulus/2u?8u:0u)|(result==0?4u:0u)|
                             (overflow?2u:0u)|(value<row[2]?1u:0u);
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);
        for(unsigned i=0;i<8;++i) {cpu.d[i]=0xa5a50000u+i;cpu.a[i]=0xfafa0000u+i;}
        cpu.d[row[3]]=full;cpu.d_known[row[3]]=static_cast<unsigned>(mask);
        cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4));
        cpu.sr_known=static_cast<std::uint16_t>(known_x?0xfff0u:0xffe0u);
        const auto before=cpu;
        if(!step(cpu,bus)||cpu.pc!=row[0]+row[4]||cpu.completed!=1)return 1;
        if(cpu.sr!=(0x2700u|(x<<4)|flags)||cpu.sr_known!=(known_x?0xffffu:0xffefu))return 2;
        if(cpu.d!=before.d||cpu.a!=before.a||cpu.d_known!=before.d_known||cpu.a_known!=before.a_known)return 3;
    }
    for(const auto& row:rows) for(unsigned bit=0;bit<row[1]*8u;++bit) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.d[row[3]]=0xdeadbeef;
        cpu.d_known[row[3]]=0xffffffffu&~(1u<<bit);cpu.sr=0x271f;cpu.sr_known=0xffe0;
        const auto before=cpu;
        if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.pc!=before.pc||cpu.completed)return 4;
        if(cpu.sr!=before.sr||cpu.sr_known!=before.sr_known||cpu.d!=before.d||
           cpu.a!=before.a||cpu.d_known!=before.d_known||cpu.a_known!=before.a_known)return 5;
    }
    return 0;
}
''')

    def test_native_memory_forms_bus_width_order_and_address_wrap(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            immediate = 0x89abcdef & ((1 << (size * 8)) - 1)
            for mode in (2, 5, 7):
                for reg in range(2 if mode == 7 else 8):
                    extension = (0xfffe,) if mode == 5 or (mode, reg) == (7, 0) else (
                        (0x12ff, 0xfffe) if (mode, reg) == (7, 1) else ())
                    instruction = cmpi(size, immediate, mode, reg, *extension)
                    rows.append((len(image), size, immediate, mode, reg, len(instruction)))
                    image += instruction
        image += words(0xffff)
        source, _ = emit_cpp(image, 0)
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
struct Reads:Bus {
    unsigned count=0,widths[2]{},addresses[2]{};std::uint32_t value=0;
    std::uint8_t read8(std::uint32_t address)override {
        if(count>=2)throw std::runtime_error("unexpected read");
        widths[count]=1;addresses[count++]=address;return static_cast<std::uint8_t>(value);
    }
    std::uint16_t read16(std::uint32_t address)override {
        if(count>=2)throw std::runtime_error("unexpected read");
        widths[count]=2;addresses[count++]=address;
        return static_cast<std::uint16_t>(count==1?value>>16u:value);
    }
};
int main() {
    for(const auto& row:rows) {
        CPU cpu;reset_from_vectors(cpu,0x2000,row[0]);cpu.sr=0x271f;
        cpu.a[row[4]]=row[3]==2?0x12fffffeu:0x13000000u;cpu.a_known[row[4]]=true;
        const auto before=cpu;
        Reads bus;bus.value=row[1]==2?row[2]<<16u:row[2];
        if(!step(cpu,bus)||cpu.pc!=row[0]+row[5]||cpu.completed!=1||cpu.sr!=0x2714||cpu.sr_known!=0xffef)return 1;
        if(bus.count!=(row[1]==4?2u:1u)||bus.addresses[0]!=0xfffffeu||bus.widths[0]!=(row[1]==1?1u:2u))return 2;
        if(row[1]==4&&(bus.addresses[1]!=0||bus.widths[1]!=2))return 3;
        if(cpu.d!=before.d||cpu.a!=before.a||cpu.d_known!=before.d_known||cpu.a_known!=before.a_known)return 4;
        if(row[3]!=7) {
            reset_from_vectors(cpu,0x2000,row[0]);cpu.a_known[row[4]]=false;Reads unknown;
            if(step(cpu,unknown)||unknown.count||cpu.stop!=Stop::undefined_state||cpu.pc!=row[0]||cpu.completed)return 5;
        }
    }
    return 0;
}
''')

    def test_native_memory_rejections_and_partial_read_observability(self):
        sources = []
        for size in (1, 2, 4):
            source, _ = emit_cpp(cmpi(size, 0, 2, 3) + words(0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"width_{size}"))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step=bool(*)(CPU&,Bus&);
Step steps[]={width_1::step,width_2::step,width_4::step};
struct Reads:Bus {
    unsigned attempts=0,accepted=0,deny=1,addresses[2]{};
    void record(unsigned address,unsigned width) {
        if(attempts>=2)throw std::runtime_error("unexpected read");
        addresses[attempts++]=address;
        if(attempts==deny)throw BusFault(address,false,static_cast<std::uint8_t>(width));
        ++accepted;
    }
    std::uint8_t read8(std::uint32_t address)override{record(address,1);return 0;}
    std::uint16_t read16(std::uint32_t address)override{record(address,2);return 0;}
};
struct ByteOnly:Bus {
    unsigned reads=0;
    std::uint8_t read8(std::uint32_t)override{++reads;return 0;}
};
int main() {
    for(unsigned index=0;index<3;++index)for(unsigned denial=1;denial<=(index==2?2u:1u);++denial) {
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0xfffffffe;cpu.a_known[3]=true;
        cpu.sr=0x271f;cpu.sr_known=0xffe0;const auto before=cpu;Reads bus;bus.deny=denial;
        if(steps[index](cpu,bus)||cpu.stop!=Stop::bus_access||cpu.stop_pc||cpu.pc||cpu.completed)return 1;
        if(bus.attempts!=denial||bus.accepted!=denial-1u||bus.addresses[0]!=0xfffffeu)return 2;
        if(cpu.access_address!=(denial==1?0xfffffeu:0u)||cpu.access_width!=(index==0?1u:2u)||cpu.access_write)return 3;
        if(cpu.sr!=before.sr||cpu.sr_known!=before.sr_known||cpu.d!=before.d||cpu.a!=before.a||
           cpu.d_known!=before.d_known||cpu.a_known!=before.a_known)return 4;
        if(denial==2&&bus.addresses[1]!=0)return 5;
    }
    for(unsigned index=1;index<3;++index) {
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x01000001;cpu.a_known[3]=true;
        cpu.sr=0x271f;cpu.sr_known=0xffe0;Reads bus;
        if(steps[index](cpu,bus)||bus.attempts||cpu.stop!=Stop::data_address||cpu.access_address!=1||
           cpu.access_width!=(index==1?2u:4u)||cpu.access_write||cpu.pc||cpu.completed||cpu.sr!=0x271f||cpu.sr_known!=0xffe0)return 6;
    }
    for(unsigned index=0;index<3;++index) {
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0xabcdef;cpu.a_known[3]=true;Bus strict;
        if(index!=0)cpu.a[3]&=~1u;
        if(steps[index](cpu,strict)||cpu.stop!=Stop::bus_access||cpu.access_address!=cpu.a[3]||
           cpu.access_width!=(index==0?1u:2u)||cpu.access_write)return 7;
    }
    // A byte comparison at an odd address is permitted; it is one byte read.
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x01000001;cpu.a_known[3]=true;Reads bus;bus.deny=0;
    if(!steps[0](cpu,bus)||bus.attempts!=1||bus.addresses[0]!=1||cpu.sr!=0x2704)return 8;
    // A provider supporting bytes only must not accidentally authorize words.
    for(unsigned index=1;index<3;++index) {
        reset_from_vectors(cpu,0x2000,0);cpu.a[3]=0x2468;cpu.a_known[3]=true;ByteOnly bytes;
        if(steps[index](cpu,bytes)||bytes.reads||cpu.stop!=Stop::bus_access||cpu.access_width!=2)return 9;
    }
    return 0;
}
''')

    def test_native_compare_then_branch_paths_with_synthetic_memory(self):
        # Entire fixture is invented: two long comparisons and BNE branches.
        image = (cmpi(4, 0x12345678, 7, 0, 0x120) + words(0x660c) +
                 cmpi(4, 0x89abcdef, 7, 0, 0x124) + words(0x6602, 0x4e71, 0xffff))
        source, report = emit_cpp(image, 0)
        self.assertEqual((report.translated, report.unsupported), (5, (22,)))
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct SyntheticRAM:Bus {
    unsigned reads=0;bool match_first=true,match_second=true;
    std::uint16_t read16(std::uint32_t address)override {
        ++reads;
        if(address==0x120)return match_first?0x1234:0;
        if(address==0x122)return 0x5678;
        if(address==0x124)return match_second?0x89ab:0;
        if(address==0x126)return 0xcdef;
        throw BusFault(address,false,2);
    }
};
int main() {
    for(unsigned scenario=0;scenario<3;++scenario) {
        CPU cpu;reset_from_vectors(cpu,0x2000,0);SyntheticRAM bus;
        bus.match_first=scenario!=0;bus.match_second=scenario==2;
        while(step(cpu,bus)) {if(cpu.completed>5)return 1;}
        if(cpu.stop!=Stop::unsupported_instruction||cpu.pc!=22||
           cpu.completed!=(scenario==0?2u:scenario==1?4u:5u)||bus.reads!=(scenario==0?2u:4u))return 2;
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
