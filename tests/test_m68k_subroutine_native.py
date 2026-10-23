"""ROM-free MC68000 BSR/RTS control flow and ordered stack transactions."""
import unittest

from arcaderecomp.m68k import decode, discover
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


BUS = r'''
using namespace arcaderecomp::m68k;
struct Stack:Bus {
    unsigned base=0xfffffeu, attempts=0, accepted=0, deny=0;
    unsigned high=0x1234u, low=0x5678u;
    bool writing=false;
    void access(unsigned a,bool write) {
        const unsigned expected=(base+(attempts%2u)*2u)&0xffffffu;
        ++attempts;
        if(a!=expected||write!=writing)throw std::runtime_error("wrong stack word order");
        if(attempts==deny)throw BusFault(a,write,2);
        ++accepted;
    }
    std::uint16_t read16(std::uint32_t a)override {
        access(a,false);return static_cast<std::uint16_t>(a==base?high:low);
    }
    void write16(std::uint32_t a,std::uint16_t value)override {
        access(a,true);if(a==base)high=value;else low=value;
    }
};
bool unchanged(const CPU& a,const CPU& b) {
    return a.a==b.a&&a.a_known==b.a_known&&a.d==b.d&&a.d_known==b.d_known&&
        a.pc==b.pc&&a.completed==b.completed&&a.sr==b.sr&&a.sr_known==b.sr_known;
}
CPU initial(unsigned pc,unsigned sp,unsigned flags=31,unsigned known=0) {
    CPU c;reset_from_vectors(c,sp,pc);
    for(unsigned r=0;r<8;++r) {
        c.d[r]=0xaabbcc00u+r;c.d_known[r]=0x55550000u+r;
        if(r!=7){c.a[r]=0x12345600u+r;c.a_known[r]=false;}
    }
    c.sr=static_cast<std::uint16_t>(0x2700u|flags);
    c.sr_known=static_cast<std::uint16_t>(0xffe0u|known);
    return c;
}
'''


def variants():
    sources = []
    for name, image, base in (
        ("short_call", words(0x61fe), 0x12340000),
        ("word_call", words(0x6100, 0xfffe), 0x12340000),
        ("wrap_call", words(0x61fe), 0xfffffffe),
        ("wrap_word", words(0x6100, 0xfffe), 0xfffffffc),
        ("ret", words(0x4e75), 0x12340000),
    ):
        source, _ = emit_cpp(image, base, base, limit=1)
        sources.append(source.replace("arcaderecomp_m68k_generated", name))
    return "\n".join(sources)


class M68kSubroutineTests(unittest.TestCase):
    def test_decoder_all_displacements_wrap_and_truncation(self):
        for byte in range(1, 256):
            ins = decode(words(0x6100 | byte), 0x100, 0x100)
            displacement = byte if byte < 128 else byte - 256
            self.assertEqual((ins.mnemonic, ins.size, ins.operands, ins.target, ins.next_pc),
                             ("bsr", 2, (), 0x102 + displacement, 0x102))
        for word in range(65536):
            ins = decode(words(0x6100, word), 0x100, 0x100)
            displacement = word if word < 32768 else word - 65536
            self.assertEqual((ins.mnemonic, ins.size, ins.target, ins.next_pc),
                             ("bsr", 4, (0x102 + displacement) & 0xffffffff, 0x104))
        for data in (words(0x6100), words(0x6100) + b"\x12"):
            with self.assertRaises(ValueError):
                decode(data, 0)
        ins = decode(words(0x61ff), 0xfffffffe, 0xfffffffe)
        self.assertEqual((ins.size, ins.target, ins.next_pc), (2, 0xffffffff, 0))
        ins = decode(words(0x6100, 4), 0xfffffffc, 0xfffffffc)
        self.assertEqual((ins.target, ins.next_pc), (2, 0))
        self.assertEqual(decode(words(0x4e75), 0).mnemonic, "rts")
        self.assertEqual(decode(words(0x4e73), 0).mnemonic, "rte")
        for opcode in (0x4e74, 0x4e77, 0x4e90):
            self.assertEqual(decode(words(opcode, 0), 0).mnemonic, "unsupported")

    def test_discovery_follows_calls_and_continuations_but_never_rts_fallthrough(self):
        # Short call -> word call -> RTS -> RTS; never decode dead words at 6/14.
        data = words(0x6106, 0x4e71, 0xffff, 0xffff, 0x6100, 6, 0x4e75, 0xffff, 0x4e75)
        found, limited = discover(data, 0)
        self.assertFalse(limited)
        self.assertEqual([(i.pc, i.mnemonic) for i in found],
                         [(0, "bsr"), (2, "nop"), (4, "unsupported"), (8, "bsr"),
                          (12, "rts"), (16, "rts")])
        found, limited = discover(words(0x61fe, 0x4e75), 0)
        self.assertEqual([i.pc for i in found], [0, 2])
        self.assertFalse(limited)
        found, limited = discover(words(0x6100, 2, 0x4e75), 0)
        self.assertEqual([i.pc for i in found], [0, 4])
        self.assertFalse(limited)

    def test_native_calls_returns_all_ccr_values_knownness_and_address_wraps(self):
        native(variants(), BUS + r'''
using Step=bool(*)(CPU&,Bus&);
int main() {
    const Step calls[]={short_call::step,word_call::step,wrap_call::step,wrap_word::step};
    const unsigned pcs[]={0x12340000u,0x12340000u,0xfffffffeu,0xfffffffcu};
    const unsigned returns[]={0x12340002u,0x12340004u,0u,0u};
    for(unsigned form=0;form<4;++form)for(unsigned sp:{2u,0x01000002u,0xfffffffeu}) {
      for(unsigned flags=0;flags<32;++flags)for(unsigned known=0;known<32;++known) {
        auto c=initial(pcs[form],sp,flags,known);auto expected=c;
        Stack bus;bus.base=(sp-4u)&0xffffffu;bus.writing=true;
        expected.a[7]-=4u;expected.completed=1;
        if(!calls[form](c,bus)||!unchanged(c,expected)||bus.attempts!=2||bus.accepted!=2||
           bus.high!=(returns[form]>>16u)||bus.low!=(returns[form]&65535u))return 1;
        c.pc=0x12340000u;expected=c;expected.pc=returns[form];expected.a[7]+=4u;++expected.completed;
        bus.writing=false;bus.attempts=bus.accepted=0;
        if(!ret::step(c,bus)||!unchanged(c,expected)||bus.attempts!=2||bus.accepted!=2)return 2;
      }
    }
}
''')

    def test_native_every_word_refusal_unknown_stack_alignment_and_no_byte_fallback(self):
        native(variants(), BUS + r'''
struct ByteOnly:Bus {
    unsigned calls=0;
    std::uint8_t read8(std::uint32_t)override{++calls;return 0;}
    void write8(std::uint32_t,std::uint8_t)override{++calls;}
};
int main() {
    for(bool writing:{false,true})for(unsigned deny=1;deny<=2;++deny) {
        auto c=initial(0x12340000u,writing?2u:0xfffffffeu);const auto before=c;
        Stack bus;bus.writing=writing;bus.deny=deny;bus.high=0xabcd;
        const auto run=writing?word_call::step:ret::step;
        if(run(c,bus)||c.stop!=Stop::bus_access||c.stop_pc!=before.pc||!unchanged(c,before))return 1;
        if(bus.attempts!=deny||bus.accepted!=deny-1u||c.access_width!=2||c.access_write!=writing||
           c.access_address!=(deny==1?0xfffffeu:0u))return 2;
        if(bus.low!=0x5678u||bus.high!=(writing&&deny==2?0x1234u:0xabcdu))return 3;
        if(run(c,bus)||bus.attempts!=deny||!unchanged(c,before))return 4;
    }
    for(bool writing:{false,true}) {
        const auto run=writing?word_call::step:ret::step;
        auto c=initial(0x12340000u,0x01000003u);c.a_known[7]=false;auto before=c;Stack bus;
        if(run(c,bus)||c.stop!=Stop::undefined_state||bus.attempts||!unchanged(c,before))return 5;
        c=initial(0x12340000u,0x01000003u);before=c;
        if(run(c,bus)||c.stop!=Stop::data_address||bus.attempts||!unchanged(c,before)||
           c.access_address!=(writing?0xffffffu:3u)||c.access_write!=writing||c.access_width!=4)return 6;
        c=initial(0x12340000u,writing?2u:0xfffffffeu);before=c;ByteOnly bytes;
        if(run(c,bytes)||c.stop!=Stop::bus_access||bytes.calls||!unchanged(c,before)||
           c.access_address!=0xfffffeu||c.access_width!=2||c.access_write!=writing)return 7;
    }
}
''')

    def test_native_nested_calls_use_only_the_bus_stack(self):
        data = words(0x6106, 0x4e71, 0xffff, 0xffff, 0x6100, 6, 0x4e75, 0xffff, 0x4e75)
        source, _ = emit_cpp(data, 0)
        native(source, r'''
#include <map>
using namespace arcaderecomp_m68k_generated;
struct Memory:Bus {
    std::map<unsigned,std::uint16_t> words;unsigned reads=0,writes=0;
    std::uint16_t read16(std::uint32_t a)override{++reads;return words.at(a);}
    void write16(std::uint32_t a,std::uint16_t v)override{++writes;words[a]=v;}
};
int main() {
    CPU c;reset_from_vectors(c,0x2000,0);Memory bus;
    const unsigned pcs[]={8,16,12,2};const unsigned sps[]={0x1ffc,0x1ff8,0x1ffc,0x2000};
    for(unsigned i=0;i<4;++i)if(!step(c,bus)||c.pc!=pcs[i]||c.a[7]!=sps[i]||c.completed!=i+1)return 1;
    if(bus.reads!=4||bus.writes!=4||bus.words.at(0x1ffe)!=2||bus.words.at(0x1ffa)!=12)return 2;
    // Altering stack data changes the return destination; there is no host call stack.
    reset_from_vectors(c,0x2000,0);if(!step(c,bus)||!step(c,bus))return 3;
    bus.words[0x1ff8]=0x7654;bus.words[0x1ffa]=0x3210;
    if(!step(c,bus)||c.pc!=0x76543210u||c.a[7]!=0x1ffcu)return 4;
    if(step(c,bus)||c.stop!=Stop::untranslated_pc||c.completed!=3||bus.reads!=6)return 5;
}
''')

    def test_native_odd_destinations_and_control_guards_are_explicit_diagnostics(self):
        source, _ = emit_cpp(words(0x61ff, 0x4e75), 0)
        native(source, BUS + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    auto c=initial(0,2);Stack bus;bus.writing=true;
    if(!step(c,bus)||c.pc!=1||c.completed!=1||bus.attempts!=2)return 1;
    if(step(c,bus)||c.stop!=Stop::instruction_address||c.stop_pc!=1||bus.attempts!=2)return 2;
    c=initial(2,0xfffffffeu);bus=Stack{};bus.low=3;
    if(!step(c,bus)||c.pc!=0x12340003u||c.completed!=1||c.a[7]!=2)return 3;
    if(step(c,bus)||c.stop!=Stop::instruction_address||bus.attempts!=2)return 4;
    for(unsigned pc:{0u,2u})for(unsigned mode=0;mode<3;++mode) {
        c=initial(pc,2);bus=Stack{};
        if(mode==0)c.sr_known&=static_cast<std::uint16_t>(~0x2000u);
        if(mode==1)c.sr&=static_cast<std::uint16_t>(~0x2000u);
        if(mode==2)c.sr|=0x8000u;
        const auto before=c;
        if(step(c,bus)||!unchanged(c,before)||bus.attempts||
           c.stop!=(mode==0?Stop::undefined_state:Stop::unsupported_control))return 5;
    }
}
''')


if __name__ == "__main__":
    unittest.main()
