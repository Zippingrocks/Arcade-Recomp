"""ROM-free original MC68000 six-byte exception-return transactions."""
import unittest

from arcaderecomp.m68k import decode, discover
from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


FRAME = r'''
using namespace arcaderecomp_m68k_generated;
struct Frame:Bus {
 std::uint32_t stack=0x12340000u,target=0x89abcdefu;
 std::uint16_t saved=0x2200u;
 unsigned attempts=0,accepted=0,fail=99;
 std::uint32_t addresses[3]{};
 std::uint16_t read16(std::uint32_t a)override {
  const unsigned n=attempts++;
  if(n>=3u||n==fail)throw BusFault(a,false,2);
  addresses[n]=a;
  if(a!=((stack+2u*n)&0x00ffffffu))throw BusFault(a,false,2);
  ++accepted;
  return n==0?saved:static_cast<std::uint16_t>(n==1?target>>16u:target);
 }
};
inline CPU initial(std::uint32_t stack) {
 CPU c;reset_from_vectors(c,stack,0);
 for(unsigned i=0;i<8;++i){c.d[i]=0x12345678u+i;c.d_known[i]=0x10203040u+i;}
 for(unsigned i=0;i<7;++i){c.a[i]=0xfedcba98u+i;c.a_known[i]=(i&1u)!=0;}
 return c;
}
inline bool unchanged(const CPU& a,const CPU& b) {
 return a.d==b.d&&a.a==b.a&&a.d_known==b.d_known&&a.a_known==b.a_known&&
        a.sr==b.sr&&a.sr_known==b.sr_known&&a.pc==b.pc&&a.completed==b.completed;
}
'''


class M68kRTETests(unittest.TestCase):
    def test_decode_and_discovery_have_no_guessed_return_or_fallthrough(self):
        ins = decode(words(0x4e73), 0xfffffffe, 0xfffffffe)
        self.assertEqual((ins.mnemonic, ins.size, ins.operands, ins.target,
                          ins.next_pc), ("rte", 2, (), None, 0))
        for data in (b"", b"\x4e"):
            with self.assertRaises(ValueError):
                decode(data, 0)
        for opcode in (0x4e72, 0x4e74, 0x4e77):
            self.assertEqual(decode(words(opcode, 0), 0).mnemonic, "unsupported")
        image = words(0x4e73, 0x4e71, 0xffff)
        graph, limited = discover(image, 0)
        self.assertEqual([(i.pc, i.mnemonic) for i in graph], [(0, "rte")])
        self.assertFalse(limited)
        source, report = emit_cpp(image, 0, additional_entries=(2,))
        self.assertEqual((report.discovered, report.translated, report.unsupported),
                         (3, 2, (4,)))
        self.assertIn("return return_exception(cpu, bus);", source)

    def test_every_restored_sr_and_prior_ccr_knownness(self):
        source, _ = emit_cpp(words(0x4e73), 0)
        native(source, FRAME + r'''
int main(){
 for(unsigned sr=0;sr<=0xffffu;++sr){
  Frame b;b.saved=static_cast<std::uint16_t>(sr);
  auto c=initial(b.stack);const auto before=c;
  const bool supported=(sr&~0x271fu)==0u&&(sr&0x2000u)!=0u;
  if(step(c,b)!=supported)return 1;
  if(!supported){
   if(c.stop!=Stop::unsupported_control||b.accepted!=1u||!unchanged(c,before))return 2;
   if(step(c,b)||b.attempts!=1u)return 3;
  } else if(c.sr!=sr||c.sr_known!=0xffffu||c.pc!=b.target||c.a[7]!=b.stack+6u||
            c.completed!=1u||b.accepted!=3u||c.d!=before.d||c.d_known!=before.d_known||
            c.a_known!=before.a_known)return 4;
 }
 // RTE overwrites every CCR bit, including X; prior CCR value/knownness is irrelevant.
 for(unsigned flags=0;flags<32;++flags)for(unsigned known=0;known<32;++known)
  for(unsigned restored=0;restored<32;++restored){
   Frame b;b.saved=static_cast<std::uint16_t>(0x2500u|restored);
   auto c=initial(b.stack);c.sr=static_cast<std::uint16_t>(0x2700u|flags);
   c.sr_known=static_cast<std::uint16_t>(0xffe0u|known);const auto before=c;
   if(!step(c,b)||c.sr!=b.saved||c.sr_known!=0xffffu||c.completed!=1u)return 5;
   for(unsigned i=0;i<7;++i)if(c.a[i]!=before.a[i])return 6;
  }
 return 0;
}
''')

    def test_word_order_stack_wrap_partial_reads_and_latched_refusal(self):
        source, _ = emit_cpp(words(0x4e73), 0)
        native(source, FRAME + r'''
int main(){
 for(std::uint32_t sp:{0u,0x12340000u,0x00fffffcu,0x00fffffeu,0xfffffffcu,0xfffffffeu}){
  for(unsigned fail=0;fail<4;++fail){
   Frame b;b.stack=sp;b.fail=fail;auto c=initial(sp);const auto before=c;
   if(step(c,b)!=(fail==3u))return 1;
   for(unsigned i=0;i<b.accepted;++i)if(b.addresses[i]!=((sp+2u*i)&0xffffffu))return 2;
   if(fail<3u){
    if(c.stop!=Stop::bus_access||c.stop_pc||c.access_write||c.access_width!=2u||
       c.access_address!=((sp+2u*fail)&0xffffffu)||b.accepted!=fail||
       b.attempts!=fail+1u||!unchanged(c,before))return 3;
    if(step(c,b)||b.attempts!=fail+1u||!unchanged(c,before))return 4;
   } else if(c.a[7]!=sp+6u||c.pc!=b.target||c.sr!=b.saved||
             c.completed!=1u||b.accepted!=3u)return 5;
  }
 }
 // Refusing a word is not satisfied by a byte-only provider.
 struct Bytes:Bus{unsigned reads=0;std::uint8_t read8(std::uint32_t)override{++reads;return 0;}}b;
 auto c=initial(0x1000u);if(step(c,b)||c.stop!=Stop::bus_access||b.reads||
    c.access_address!=0x1000u||c.access_width!=2u||c.completed)return 6;
 return 0;
}
''')

    def test_unknown_odd_and_unsupported_current_control_stops_before_data_reads(self):
        source, _ = emit_cpp(words(0x4e73), 0)
        native(source, FRAME + r'''
int main(){
 for(unsigned mode=0;mode<7;++mode){
  Frame b;auto c=initial(b.stack);Stop expected=Stop::undefined_state;
  if(mode==0)c.a_known[7]=false;
  if(mode==1)c.sr_known&=static_cast<std::uint16_t>(~0x2000u);
  if(mode==2)c.sr_known&=static_cast<std::uint16_t>(~0x8000u);
  if(mode==3)c.sr_known&=static_cast<std::uint16_t>(~0x0100u);
  if(mode==4){c.sr&=static_cast<std::uint16_t>(~0x2000u);expected=Stop::unsupported_control;}
  if(mode==5){c.sr|=0x8000u;expected=Stop::unsupported_control;}
  if(mode==6){++c.a[7];expected=Stop::data_address;}
  const auto before=c;
  if(step(c,b)||c.stop!=expected||b.attempts||!unchanged(c,before))return 1;
  if(mode==6&&(c.access_address!=0x340001u||c.access_width!=2u||c.access_write))return 2;
 }
 // The privileged helper also rejects direct calls from user mode.
 Frame b;auto c=initial(b.stack);c.sr&=static_cast<std::uint16_t>(~0x2000u);
 if(return_exception(c,b)||c.stop!=Stop::privilege||b.attempts)return 3;
 return 0;
}
''')

    def test_dynamic_destination_checked_on_following_step(self):
        source, _ = emit_cpp(words(0x4e73, 0x4e71, 0xffff), 0,
                             additional_entries=(2,))
        native(source, FRAME + r'''
int main(){
 for(std::uint32_t target:{2u,1u,0x12345678u}){
  Frame b;b.target=target;b.saved=0x230fu;auto c=initial(b.stack);
  if(!step(c,b)||c.completed!=1u||c.pc!=target||c.sr!=b.saved)return 1;
  if(target==2u){if(!step(c,b)||c.pc!=4u||c.completed!=2u)return 2;}
  else if(step(c,b)||c.stop!=(target&1u?Stop::instruction_address:Stop::untranslated_pc)||
          c.stop_pc!=target||c.completed!=1u)return 3;
  if(b.attempts!=3u)return 4;
 }
 return 0;
}
''')

    def test_autovector_rte_roundtrip_and_pending_request_after_return(self):
        source, _ = emit_cpp(words(0x4e71, 0xffff, 0x4e73), 0,
                             additional_entries=(4,))
        native(source, r'''
#include <map>
#include <vector>
using namespace arcaderecomp_m68k_generated;
struct Memory:Bus {
 unsigned level=0;std::map<std::uint32_t,std::uint16_t> data;
 std::vector<std::uint32_t> reads,writes;
 bool interrupt_level(unsigned& out)override{out=level;return true;}
 std::uint16_t read16(std::uint32_t a)override{
  const auto it=data.find(a);if(it==data.end())throw BusFault(a,false,2);
  reads.push_back(a);return it->second;
 }
 void write16(std::uint32_t a,std::uint16_t v)override{writes.push_back(a);data[a]=v;}
};
int main(){
 for(unsigned level=1;level<8;++level)for(unsigned mask=0;mask<level;++mask)
  for(unsigned flags=0;flags<32;++flags){
   Memory b;b.level=level;b.data[(24u+level)*4u]=0;b.data[(24u+level)*4u+2u]=4;
   CPU c;reset_from_vectors(c,0x1000u,0);c.sr=static_cast<std::uint16_t>(0x2000u|(mask<<8u)|flags);
   c.sr_known=0xffffu;const auto saved=c.sr;
   if(!step(c,b)||c.completed||c.pc!=4u||c.a[7]!=0xffau)return 1;
   if(!step(c,b)||c.completed!=1u||c.pc||c.a[7]!=0x1000u||c.sr!=saved||
      c.sr_known!=0xffffu)return 2;
   const std::vector<std::uint32_t> expected={(24u+level)*4u,(24u+level)*4u+2u,0xffau,0xffcu,0xffeu};
   if(b.reads!=expected||b.writes!=std::vector<std::uint32_t>({0xffeu,0xffau,0xffcu}))return 3;
   if(flags&1u){
    // A still-asserted request is accepted at the following boundary, not hidden by RTE.
    if(!step(c,b)||c.completed!=1u||c.pc!=4u||c.a[7]!=0xffau)return 4;
    b.level=0;if(!step(c,b)||c.completed!=2u||c.pc)return 5;
   }else b.level=0;
   const auto count=c.completed;
   if(!step(c,b)||c.pc!=2u||c.completed!=count+1u||c.a[7]!=0x1000u)return 6;
  }
 return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
