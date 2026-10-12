"""ROM-free immediate logic: encoding, independent truth tables and knownness."""
import unittest

from arcaderecomp.m68k import decode
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words
from test_m68k_moves_shifts_native import table


def logic(size, kind, reg, immediate):
    op = (0x0000, 0x0200, 0x0a00)[kind] | {1: 0, 2: 0x40, 4: 0x80}[size] | reg
    data = (immediate >> 16, immediate & 65535) if size == 4 else (immediate,)
    return words(op, *data)


class M68kImmediateLogicTests(unittest.TestCase):
    def test_encodings_lengths_and_excluded_effective_addresses(self):
        for kind, prefix in enumerate((0x0000, 0x0200, 0x0a00)):
            for size in (1, 2, 4):
                for reg in range(8):
                    immediate = 0x89abcdef if size == 4 else 0xabcd
                    data = logic(size, kind, reg, immediate)
                    ins = decode(data, 0x100, 0x100)
                    self.assertEqual((ins.mnemonic, ins.size, ins.operands),
                                     ("logic_immediate_d", len(data),
                                      (size, kind, reg, immediate & ((1 << (size * 8)) - 1))))
                    for length in range(2, len(data)):
                        with self.assertRaises(ValueError):
                            decode(data[:length], 0)
                for ea in range(8, 64):
                    opcode = prefix | {1: 0, 2: 0x40, 4: 0x80}[size] | ea
                    self.assertEqual(decode(words(opcode, 0, 0, 0), 0).mnemonic,
                                     "unsupported")
            for ea in range(64):
                self.assertEqual(decode(words(prefix | 0xc0 | ea), 0).mnemonic, "unsupported")

    def test_native_all_byte_pairs_and_wide_register_forms(self):
        image, rows = bytearray(), []
        for size in (1, 2, 4):
            mask = (1 << (size * 8)) - 1
            samples = range(256) if size == 1 else (0, 1, mask, mask >> 1,
                       1 << (size * 8 - 1), 0x55555555 & mask, 0xaaaaaaaa & mask, 0x12345678 & mask)
            for kind in range(3):
                for index, imm in enumerate(samples):
                    reg = index % 8
                    data = logic(size, kind, reg, imm)
                    rows.append((len(image), len(data), size, kind, reg, imm))
                    image += data
        source, report = emit_cpp(image + words(0xffff), 0)
        self.assertEqual(report.translated, len(rows))
        native(source, table("rows", rows) + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus bus;
    for(const auto& row:rows) {
      for(unsigned sample=0;sample<256;++sample) {
        for(unsigned flags=0;flags<4;++flags) {
          CPU c;reset_from_vectors(c,0x2000,row[0]);
          for(unsigned r=0;r<8;++r) {c.d[r]=0xface0000u+r;c.d_known[r]=0x55550000u+r;}
          const unsigned mask=row[2]==4?0xffffffffu:(1u<<(row[2]*8u))-1u;
          const unsigned input=row[2]==1?0x12340000u|sample:sample*0x9e3779b9u;
          c.d[row[4]]=input;c.d_known[row[4]]=0xa5a50000u|mask;
          c.sr=static_cast<std::uint16_t>(0x270fu|((flags&1u)<<4));
          c.sr_known=static_cast<std::uint16_t>(0xffefu|((flags&2u)<<3));
          const auto before=c;
          // Independent per-bit Boolean truth table, not the helper's bitwise expressions.
          unsigned result=0;
          for(unsigned bit=0;bit<row[2]*8u;++bit) {
            const bool a=(input>>bit)&1u,b=(row[5]>>bit)&1u;
            const bool out=row[3]==0?(a||b):row[3]==1?(a&&b):(a!=b);
            if(out)result|=1u<<bit;
          }
          if(!step(c,bus)||c.pc!=row[0]+row[1]||c.completed!=1)return 1;
          if(c.d[row[4]]!=((input&~mask)|result)||c.d_known!=before.d_known)return 2;
          const unsigned expected=(result&(1u<<(row[2]*8u-1u))?8u:0u)|(result==0?4u:0u);
          if(c.sr!=((before.sr&~15u)|expected)||c.sr_known!=(before.sr_known|15u))return 3;
          if(c.a!=before.a||c.a_known!=before.a_known)return 4;
          for(unsigned r=0;r<8;++r)if(r!=row[4]&&c.d[r]!=before.d[r])return 5;
        }
      }
    }
}
''')

    def test_partial_knownness_against_all_concrete_completions(self):
        source, _ = emit_cpp(logic(1, 1, 0, 0) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
unsigned truth(unsigned a,unsigned b,unsigned kind) {
    unsigned out=0;
    for(unsigned bit=0;bit<8;++bit) {
        const bool x=(a>>bit)&1u,y=(b>>bit)&1u;
        if(kind==0?(x||y):kind==1?(x&&y):(x!=y))out|=1u<<bit;
    }
    return out;
}
int main() {
    CPU initial;reset_from_vectors(initial,0,0);Bus bus;
    if(!step(initial,bus)||initial.d_known[0]!=255u)return 1;
    // Each bit independently ranges over known 0, known 1, unknown: 3^8 states.
    for(unsigned state=0;state<6561;++state) {
      unsigned code=state,known=0,value=0;
      for(unsigned bit=0;bit<8;++bit) {
          const unsigned digit=code%3;code/=3;
          if(digit!=2)known|=1u<<bit;
          if(digit==1)value|=1u<<bit;
      }
      for(unsigned imm:{0u,1u,0x55u,0x80u,0xaau,255u}) {
        for(unsigned kind=0;kind<3;++kind) {
          unsigned all=255u,any=0,n_set=0,z_set=0;
          for(unsigned concrete=0;concrete<256;++concrete) {
              if((concrete&known)!=value)continue;
              const unsigned result=truth(concrete,imm,kind);
              all&=result;any|=result;
              n_set|=result&128u?2u:1u;z_set|=result==0?2u:1u;
          }
          const unsigned expected_known=(~(all^any))&255u;
          for(unsigned payload=0;payload<2;++payload) {
            CPU c;reset_from_vectors(c,0x2000,0);
            c.d[3]=0xabcd0000u|value|(payload?(~known&255u):0u);
            c.d_known[3]=0x98760000u|known;
            c.sr=0x271fu;c.sr_known=0xffefu;const auto before=c;
            if(!logic_immediate_d(c,1,kind,3,imm,4)||c.completed!=1||c.pc!=4)return 2;
            if(c.d_known[3]!=(0x98760000u|expected_known)||
               (c.d[3]&expected_known)!=all||(c.d[3]&0xffffff00u)!=0xabcd0000u)return 3;
            const unsigned flag_known=3u|(n_set!=3?8u:0u)|(z_set!=3?4u:0u);
            const unsigned flag_value=(n_set==2?8u:0u)|(z_set==2?4u:0u);
            if(c.sr_known!=((before.sr_known&~15u)|flag_known)||
               c.sr!=((before.sr&~15u)|flag_value))return 4;
            for(unsigned r=0;r<8;++r)if(r!=3&&(c.d[r]!=before.d[r]||c.d_known[r]!=before.d_known[r]))return 5;
            if(c.a!=before.a||c.a_known!=before.a_known)return 6;
          }
        }
      }
    }
}
''')

    def test_unknown_flags_consumers_and_no_device_bypass(self):
        # ORI.B #$80,D0; BNE +2; illegal; MOVE.B D0,$400001; illegal.
        image = logic(1, 0, 0, 0x80) + words(0x6602, 0xffff, 0x13c0, 0x40, 1, 0xffff)
        source, _ = emit_cpp(image, 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
struct Strict:Bus {unsigned calls=0;void write8(std::uint32_t a,std::uint8_t)override{
    ++calls;throw BusFault(a,true);}};
int main() {
    CPU c;reset_from_vectors(c,0x2000,0);Strict bus;
    if(!step(c,bus)||c.d_known[0]!=0x80||c.sr_known!=0xffef||c.sr!=0x2708)return 1;
    if(!step(c,bus)||c.pc!=8)return 2; // Known-one result proves BNE even with unknown low bits.
    const auto before=c;
    if(step(c,bus)||c.stop!=Stop::undefined_state||bus.calls||c.pc!=before.pc||
       c.completed!=before.completed||c.d!=before.d||c.sr!=before.sr)return 3;
    reset_from_vectors(c,0x2000,0);c.d_known[0]=255u;
    if(!step(c,bus)||!step(c,bus))return 4;
    if(step(c,bus)||c.stop!=Stop::bus_access||bus.calls!=1||c.access_address!=0x400001||
       !c.access_write||c.access_width!=1||c.completed!=2)return 5;
    reset_from_vectors(c,0x2000,0);
    if(!logic_immediate_d(c,1,2,0,0,4)||c.sr_known!=0xffe3)return 6;
    bool result=false;
    if(condition(c,6,result)||c.stop!=Stop::undefined_state)return 7;
    reset_from_vectors(c,0x2000,0);
    if(!logic_immediate_d(c,4,1,0,0,4)||c.d[0]||c.d_known[0]!=0xffffffffu||c.sr!=0x2704)return 8;
}
''')

    def test_wide_partial_results_against_two_possible_inputs(self):
        source, _ = emit_cpp(logic(4, 0, 0, 0xffffffff) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
unsigned calculate(unsigned a,unsigned b,unsigned kind,unsigned bits) {
    unsigned value=0;
    for(unsigned bit=0;bit<bits;++bit) {
        const bool x=(a>>bit)&1u,y=(b>>bit)&1u;
        if(kind==0?(x||y):kind==1?(x&&y):(x!=y))value|=1u<<bit;
    }
    return value;
}
int main() {
    CPU seed;reset_from_vectors(seed,0,0);Bus bus;
    if(!step(seed,bus)||seed.d_known[0]!=0xffffffffu)return 1;
    for(unsigned bytes:{2u,4u}) {
      const unsigned bits=bytes*8u,mask=bytes==4?0xffffffffu:0xffffu,sign=1u<<(bits-1u);
      for(unsigned unknown=0;unknown<bits;++unknown) {
        for(unsigned sample=0;sample<8;++sample) {
          const unsigned input=sample*0x9e3779b9u;
          for(unsigned imm:{0u,1u,sign,0x55555555u,0xaaaaaaaau,0xffffffffu}) {
            for(unsigned kind=0;kind<3;++kind) {
              const unsigned first=calculate(input&~(1u<<unknown),imm,kind,bits);
              const unsigned second=calculate(input|(1u<<unknown),imm,kind,bits);
              const unsigned known=~(first^second)&mask;
              const bool n_known=(first&sign)==(second&sign),z_known=(first==0)==(second==0);
              CPU c;reset_from_vectors(c,0,0);c.d[5]=input;
              c.d_known[5]=(0x87650000u&~mask)|(mask&~(1u<<unknown));
              c.sr=0x271f;c.sr_known=0xfff0;const auto before=c;
              if(!logic_immediate_d(c,bytes,kind,5,imm,4))return 2;
              if(c.d_known[5]!=((before.d_known[5]&~mask)|known)||
                 (c.d[5]&known)!=(first&known)||(c.d[5]&~mask)!=(input&~mask))return 3;
              const unsigned flags=(n_known&&(first&sign)?8u:0u)|(z_known&&first==0?4u:0u);
              if(c.sr!=(0x2710u|flags)||c.sr_known!=(0xfff3u|(n_known?8u:0u)|(z_known?4u:0u)))return 4;
            }
          }
        }
      }
    }
}
''')

    def test_invalid_helper_arguments_and_unsupported_controls_preserve_state(self):
        source, _ = emit_cpp(logic(4, 2, 7, 0x12345678) + words(0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
bool unchanged(const CPU& a,const CPU& b) {
    return a.d==b.d&&a.d_known==b.d_known&&a.a==b.a&&a.a_known==b.a_known&&
           a.pc==b.pc&&a.sr==b.sr&&a.sr_known==b.sr_known&&a.completed==b.completed;
}
int main() {
    for(unsigned bytes:{0u,3u,5u,32u,0xffffffffu}) {
        CPU c;reset_from_vectors(c,0,0);const auto before=c;
        if(logic_immediate_d(c,bytes,0,0,0,4)||c.stop!=Stop::unsupported_instruction||!unchanged(c,before))return 1;
    }
    for(unsigned kind:{3u,32u,0xffffffffu}) {
        CPU c;reset_from_vectors(c,0,0);const auto before=c;
        if(logic_immediate_d(c,1,kind,0,0,4)||!unchanged(c,before))return 2;
    }
    for(unsigned reg:{8u,32u,0xffffffffu}) {
        CPU c;reset_from_vectors(c,0,0);const auto before=c;
        if(logic_immediate_d(c,1,0,reg,0,4)||!unchanged(c,before))return 3;
    }
    Bus bus;CPU c;reset_from_vectors(c,0,0);c.sr=0xa000;const auto before=c;
    if(step(c,bus)||c.stop!=Stop::unsupported_control||!unchanged(c,before))return 4;
    if(step(c,bus)||!unchanged(c,before))return 5;
}
''')


if __name__ == "__main__":
    unittest.main()
