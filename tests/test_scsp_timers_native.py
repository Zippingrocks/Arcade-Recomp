"""ROM-free native checks for the three SCSP sample-clock timers."""
import unittest

from test_m68k_bootstrap_native import native


class SCSPTimerTests(unittest.TestCase):
    def test_all_word_values_offsets_and_reserved_bits(self):
        native('#include "scsp_timers.hpp"\n', r'''
using arcaderecomp::scsp::Timers;
int main(){
 for(unsigned value=0;value<65536u;++value){Timers t;
  const bool ok=t.write16(0x18u,static_cast<std::uint16_t>(value));
  if(ok!=(value<=0x07ffu)||t.completed_writes()!=(ok?1u:0u))return 1;
  if(ok&&(t.control(0)!=(value>>8u)||t.count(0)!=(value&0xffu)||!t.running(0)))return 2;
 }
 Timers t;
 for(unsigned timer=0;timer<3u;++timer)
  if(!t.write16(0x18u+timer*2u,static_cast<std::uint16_t>((timer<<8u)|(timer*0x40u)))||
     t.control(timer)!=timer||t.count(timer)!=(timer*0x40u))return 3;
 for(unsigned o:{0x16u,0x19u,0x1du,0x20u,0x418u})if(t.write16(o,0))return 4;
 t.invalidate();if(t.completed_writes()||t.running(0))return 5;
 return 0;}
''')

    def test_explicit_prescalers_requests_and_fail_closed_pending(self):
        native('#include "scsp_timers.hpp"\n', r'''
using arcaderecomp::scsp::Timers;
int main(){Timers t;
 for(unsigned timer=0;timer<3u;++timer)
  if(!t.write16(0x18u+timer*2u,static_cast<std::uint16_t>((timer<<8u)|0xfdu)))return 1;
 if(!t.tick_sample()||t.count(0)!=0xfeu||t.count(1)!=0xfdu||t.count(2)!=0xfdu)return 2;
 if(!t.tick_sample()||t.count(0)!=0xffu||t.count(1)!=0xfeu||t.count(2)!=0xfdu||
    !t.interrupt_request(0)||t.interrupt_request(1)||t.interrupt_request(2))return 3;
 // Timer A would need to advance beyond documented pending/clear behavior;
 // refusal is atomic even though B's prescaler would otherwise advance.
 const auto bphase=t.phase(1);if(t.tick_sample()||t.phase(1)!=bphase)return 4;
 if(!t.write16(0x18u,0x0000u)||t.interrupt_request(0)||t.count(0)!=0u)return 5;
 for(unsigned sample=0;sample<2u;++sample)if(!t.tick_sample())return 6;
 if(t.count(1)!=0xffu||!t.interrupt_request(1)||t.count(2)!=0xfeu)return 7;
 Timers loaded_ff;if(!loaded_ff.write16(0x18u,0x00ffu)||loaded_ff.tick_sample()||
    loaded_ff.count(0)!=0xffu||loaded_ff.interrupt_request(0))return 8;
 return 0;}
''')

    def test_sound_bus_word_only_and_no_implicit_clock(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main(){SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));
 try{bus.write16(0x100418u,0x02feu);return 1;}catch(const BusFault&){}
 bus.enable_common_control_research(true);bus.write16(0x100418u,0x02feu);
 if(bus.timers().completed_writes()!=1u||bus.timers().control(0)!=2u||
    bus.timers().count(0)!=0xfeu||bus.timers().phase(0)!=0u)return 2;
 try{bus.write8(0x100418u,0);return 3;}catch(const BusFault&){}
 if(bus.timers().count(0)!=0xfeu||!bus.timers().tick_sample()||
    bus.timers().count(0)!=0xfeu||bus.timers().phase(0)!=1u)return 4;
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
