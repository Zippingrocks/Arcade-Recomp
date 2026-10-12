"""ROM-free native checks for bounded SCSP interrupt control."""
import unittest

from test_m68k_bootstrap_native import native


class SCSPInterruptControlTests(unittest.TestCase):
    def test_register_masks_commands_levels_and_targets(self):
        native('#include "scsp_interrupt_control.hpp"\n', r'''
using arcaderecomp::scsp::InterruptControl;
int main(){
 for(unsigned value=0;value<65536u;++value){InterruptControl c;
  const bool ok=c.write16(0x1eu,static_cast<std::uint16_t>(value));
  if(ok!=(value<=0x07ffu)||c.completed_writes()!=(ok?1u:0u))return 1;
 }
 InterruptControl c;if(c.sound_level_known(0u))return 12;
 if(!c.write16(0x1eu,0x07ffu)||!c.write16(0x2au,0x0040u)||
    c.enable(0)!=0x07ffu||c.enable(1)!=0x0040u||
    c.enable_known_mask(0)!=0x07ffu||c.enable_known_mask(1)!=0x07ffu)return 2;
 if(!c.write16(0x20u,0u)||c.pending_known_mask(0)!=0u||
    !c.write16(0x20u,0x20u)||c.pending(0)!=0x20u||c.pending_known_mask(0)!=0x20u)return 3;
 c.observe(6u);if(c.pending(0)!=0x60u||c.pending(1)!=0x40u||
    !c.sound_irq_asserted(6u)||!c.main_irq_asserted(6u))return 4;
 if(!c.write16(0x22u,0x40u)||c.pending(0)!=0x20u||c.sound_irq_asserted(6u)||
    c.pending(1)!=0x40u||!c.main_irq_asserted(6u))return 5;
 if(!c.write16(0x2eu,0x40u)||c.pending(1)!=0u||c.main_irq_asserted(6u))return 6;
 if(!c.write16(0x24u,0x55u)||!c.write16(0x26u,0xaau)||!c.write16(0x28u,0xf0u))return 7;
 for(unsigned factor=0;factor<11u;++factor){const unsigned bit=factor<8u?factor:7u;
  unsigned expected=((0x55u>>bit)&1u)|(((0xaau>>bit)&1u)<<1u)|(((0xf0u>>bit)&1u)<<2u);
  if(!c.sound_level_known(factor)||c.sound_level(factor)!=expected)return 8;}
 for(unsigned o:{0x1cu,0x21u,0x30u})if(c.write16(o,0))return 9;
 if(c.write16(0x24u,0x100u)||c.write16(0x1eu,0x800u))return 10;
 c.invalidate();if(c.completed_writes()||c.pending_known_mask(0))return 11;
 return 0;}
''')

    def test_bus_startup_words_and_timer_request_integration(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main(){SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));
 bus.enable_common_control_research(true);
 for(unsigned a=0x10041eu;a<=0x10042eu;a+=2u)bus.write16(a,0u);
 if(bus.interrupt_control().completed_writes()!=9u)return 1;
 bus.write16(0x10041eu,0x0040u);bus.write16(0x10042au,0x0040u);
 bus.write16(0x100418u,0x00feu);
 if(!bus.tick_scsp_sample_research())return 2;
 const auto& irq=bus.interrupt_control();
 if(irq.pending(0)!=0x40u||irq.pending(1)!=0x40u||
    !irq.sound_irq_asserted(6u)||!irq.main_irq_asserted(6u))return 3;
 bus.write16(0x100422u,0x0040u);if(irq.pending(0)||irq.sound_irq_asserted(6u))return 4;
 return 0;}
''')


if __name__ == "__main__":
    unittest.main()
