"""Event-backed serial plumbing. Synthetic inputs are NOT cabinet evidence."""
from pathlib import Path
import unittest
from test_i960_transfer_shift import run_native, memb, regop

PREFIX = r'''
#include "model2c_bus.hpp"
using namespace arcaderecomp_model2c;
using namespace arcaderecomp_generated;
'''

def native(body, words=None):
    # Branch-to-self uses bus-free compiled synthetic code; helpers exercise bus.
    return run_native(words or [0x08000000], PREFIX+body)

class SerialObservedEventTests(unittest.TestCase):
    def test_no_reset_assumption_no_autoreplies_and_channel_separation(self):
        native(r'''
int main(){
 StrictBus bus(std::vector<std::uint8_t>(StrictBus::kProgramSize,0));
 bus.enable_partial_serial_io();auto& s=bus.serial_device().use_observed_events();
 try{bus.read(0x01c0001a,1);return 1;}catch(const DeviceAccessFault&){}
 s.observe_idle(100);if(bus.read(0x01c0001a,1)!=0)return 2;
 bus.write(0x01c00014,1,0xff);auto t2=s.outstanding_token(2);
 bus.write(0x01c00012,1,0x01);auto t1=s.outstanding_token(1);
 if(bus.read(0x01c0001a,1)!=3)return 3;
 s.advance_to(1000000);if(bus.read(0x01c0001a,1)!=3)return 4;
 // Time alone must not manufacture replies or release TX buffers.
 s.complete_transmit(2,t2,1000001);if(bus.read(0x01c0001a,1)!=1)return 5;
 s.receive(2,0xa5,1000002);if(bus.read(0x01c0001a,1)!=9)return 6;
 s.complete_transmit(1,t1,1000003);s.receive(1,0x5a,1000004);
 if(bus.read(0x01c0001a,1)!=12)return 7;
 if(bus.read(0x01c00016,1)!=0x5a||bus.read(0x01c0001a,1)!=8)return 8;
 if(bus.read(0x01c00018,1)!=0xa5||bus.read(0x01c0001a,1)!=0)return 9;
 try{bus.read(0x01c00018,1);return 10;}catch(const DeviceAccessFault&){}
 return 0;
}''')

    def test_reject_stale_completion_clock_reversal_and_unverified_overruns(self):
        native(r'''
int main(){SerialEventState s{};s.observe_idle(10);auto t=s.transmit(1,1);
 try{s.complete_transmit(1,t.token+1,11);return 1;}catch(const std::logic_error&){}
 if(s.status()!=1||s.tick()!=10)return 2;
 try{s.complete_transmit(1,t.token,9);return 3;}catch(const std::logic_error&){}
 try{s.transmit(1,2);return 4;}catch(const std::logic_error&){}
 s.complete_transmit(1,t.token,11);auto t2=s.transmit(1,2);
 if(t2.token==t.token)return 5;
 try{s.complete_transmit(1,t.token,12);return 6;}catch(const std::logic_error&){}
 s.receive(2,0x81,12);
 try{s.receive(2,0x82,13);return 7;}catch(const std::logic_error&){}
 if(s.tick()!=12||s.read_receive(2)!=0x81)return 8;
 try{s.observe_idle(20);return 9;}catch(const std::logic_error&){}
 return 0;
}''')

    def test_explicit_error_bits_and_backend_exclusivity(self):
        native(r'''
int main(){IO3155649 io{};auto& s=io.use_observed_events();s.observe_idle(0);
 try{io.set_serial_rx([](std::uint8_t,unsigned){return 0;});return 1;}catch(const std::logic_error&){}
 try{io.set_serial_status_source([](){return 12;});return 2;}catch(const std::logic_error&){}
 s.observe_error_bits(0x10,1);s.receive(1,0x80,2);
 if(s.status()!=0x14||s.read_receive(1)!=0x80||s.status()!=0x10)return 3;
 try{s.observe_error_bits(0x0c,3);return 4;}catch(const std::invalid_argument&){}
 if(s.status()!=0x10||s.tick()!=2)return 5;
 s.observe_error_bits(0,3);if(s.status()!=0)return 6;
 IO3155649 legacy{};legacy.set_serial_status_source([](){return 0;});
 try{legacy.use_observed_events();return 7;}catch(const std::logic_error&){}
 return 0;
}''')

    def test_native_i960_poll_exits_only_after_two_external_receive_events(self):
        # 0: ldob STATUS(g0),g2; 4: and 12,g2,g2; 8: cmpo 12,g2;
        # 12: bne 0; 16: unknown (stop before this sentinel).
        load=(0x80<<24)|(18<<19)|(16<<14)|(1<<13)|0x1a
        words=[load,regop(0x581,src=12,src2=18,dst=18,literal=True),
               regop(0x5a0,src=12,src2=18,dst=0,literal=True),0x15fffff4,0xffffffff]
        native(r'''
int main(){StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0));
 board.enable_partial_serial_io();auto& s=board.serial_device().use_observed_events();s.observe_idle(0);
 CPU cpu{};Bus bus=board.callbacks();cpu.r[16]=0x01c00000;
 for(int n=0;n<4;++n)if(!step(cpu,bus))return 1;
 if(cpu.ip!=0)return 2;
 s.receive(1,0x77,10);
 for(int n=0;n<4;++n)if(!step(cpu,bus))return 3;
 if(cpu.ip!=0)return 4;
 s.receive(2,0x88,20);
 for(int n=0;n<4;++n)if(!step(cpu,bus))return 5;
 if(cpu.ip!=16||board.read(0x01c0001a,1)!=12)return 6;
 return 0;
}''',words)

    def test_unknown_mode_gpio_and_board_writes_remain_blocked(self):
        native(r'''
int main(){StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0));
 board.enable_partial_serial_io();board.serial_device().use_observed_events().observe_idle(0);
 for(auto a:{0x01c00010u,0x01c0001cu,0x00f80000u}){
  try{board.write(a,a==0x00f80000u?4:1,2);return 1;}catch(const DeviceAccessFault&){}
 }
 if(!board.writes().empty())return 2;
 return 0;
}''')

if __name__=='__main__':unittest.main()
