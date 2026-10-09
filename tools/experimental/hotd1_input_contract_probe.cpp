// Original ArcadeRecomp research harness. NO physical serial model.
// All receive bytes/status schedules below are SYNTHETIC. Executes isolated
// AOT routines; not a full game boot, input calibration, or hardware proof.
#include <array>
#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include "hotd1_i960.cpp"

namespace {
using namespace arcaderecomp_generated;
constexpr std::uint32_t io = 0x01c00000u;
constexpr std::array<std::uint32_t, 6> outputs = {
    0x0051eef2u,0x0051eef0u,0x0051ef0eu,0x0051ef0cu,0x0051ef08u,0x0051ef24u};
struct Fixture {
    std::array<std::uint8_t,9> replies{};
    std::array<std::uint32_t,6> written{};
    std::array<bool,6> touched{};
    unsigned selected=0, command=0, tx1=0, tx2=0, reads1=0, reads2=0;
    unsigned delay=0, current_polls=0, polls=0, output_count=0, noise=0;
    bool new_selection=false, active=false, rx1_read=false, ready_seen=false;
    void check(bool value,const char* why) const {if(!value)throw std::runtime_error(why);}
    void output(std::uint32_t address,unsigned width,std::uint32_t value) {
        check(output_count<outputs.size(),"unexpected extra output");
        check(address==outputs[output_count],"output address/order changed");
        check(width==(output_count<4?2u:1u),"output width changed");
        touched[output_count]=true;written[output_count]=value;++output_count;
    }
    static void write8(void* p,std::uint32_t address,std::uint8_t value) {
        auto& f=*static_cast<Fixture*>(p);
        if(address==io+0x14) {
            f.check(!f.active&&!f.new_selection,"selection before prior transaction completes");
            f.check(value<9,"unexpected selection");
            f.selected=value;f.new_selection=true;++f.tx2;return;
        }
        if(address==io+0x12) {
            f.check(!f.active,"overlapping host transaction");
            const unsigned expected_selector=f.tx1/2;
            f.check(f.selected==expected_selector,"selector order changed");
            f.check(value==(f.tx1%2?0x87u:0u),"command order changed");
            f.check(f.new_selection==(f.tx1%2==0),"new/reused selection changed");
            f.command=value;f.active=true;f.rx1_read=false;f.ready_seen=false;
            f.current_polls=0;f.new_selection=false;++f.tx1;return;
        }
        f.output(address,1,value);
    }
    static void write16(void* p,std::uint32_t address,std::uint16_t value) {
        static_cast<Fixture*>(p)->output(address,2,value);
    }
    static std::uint8_t read8(void* p,std::uint32_t address) {
        auto& f=*static_cast<Fixture*>(p);
        f.check(f.active,"read without active transaction");
        if(address==io+0x1a) {
            ++f.current_polls;++f.polls;
            const bool ready=f.current_polls>f.delay;
            f.ready_seen=ready;
            // Unrelated status bits varied; receive-ready bits are artificial.
            return std::uint8_t((f.noise&0xf3u)|(ready?0x0cu:(f.current_polls%2?4u:8u)));
        }
        f.check(f.ready_seen,"RX read before synthetic readiness");
        if(address==io+0x16) {
            f.check(!f.rx1_read,"duplicate RX1");f.rx1_read=true;++f.reads1;
            return std::uint8_t(f.noise^(37u*f.tx1));
        }
        f.check(address==io+0x18&&f.rx1_read,"invalid/out-of-order RX2");
        ++f.reads2;f.active=false;
        // Acknowledgement replies are deliberately unrelated to data replies.
        return f.command==0x87 ? f.replies[f.selected] : std::uint8_t(f.noise^(91u*f.tx1));
    }
};
struct Measurement {unsigned steps, polls;};
Measurement execute(Fixture& f,std::uint32_t entry,std::uint32_t ret,unsigned transactions) {
    CPU cpu{};
    if(!frame_init(cpu,0x00510400u,entry))throw std::runtime_error("frame init");
    cpu.r[16]=0;cpu.r[17]=1; // Two selector arguments for isolated pair helper.
    Bus bus{};bus.ctx=&f;bus.read8=&Fixture::read8;
    bus.write8=&Fixture::write8;bus.write16=&Fixture::write16;
    unsigned steps=0;
    while(steps<4096 && step(cpu,bus)) ++steps;
    f.check(steps<4096&&cpu.ip==ret&&cpu.stop_code==StopCode::return_without_caller,
            "isolated routine did not reach its root return");
    f.check(!f.active&&!f.new_selection&&f.tx1==transactions&&f.tx2==transactions/2,
            "transaction/selection count changed");
    f.check(f.reads1==transactions&&f.reads2==transactions,"RX count changed");
    f.check(f.polls==transactions*(1+f.delay),"polling schedule changed");
    if(entry==0xa3980u) {
        f.check(f.output_count==0,"pair helper unexpectedly wrote RAM");
        f.check(cpu.r[16]==(unsigned(f.replies[0])|(unsigned(f.replies[1]&3u)<<8)),
                "10-bit pair decoding changed");
    } else {
        f.check(f.output_count==6,"full snapshot missing outputs");
        for(unsigned i=0;i<4;++i)
            f.check(f.written[i]==(unsigned(f.replies[i*2])|(unsigned(f.replies[i*2+1]&3u)<<8)),
                    "snapshot pair decoding changed");
        f.check(f.written[4]==((f.replies[8]^3u)&1u),"flag0 changed");
        f.check(f.written[5]==(((f.replies[8]^3u)>>1)&1u),"flag1 changed");
    }
    return {steps,f.polls};
}
}
int main() {
    std::cerr<<"ISOLATED HOST INPUT CONTRACT: SYNTHETIC REPLIES, NOT CABINET VALIDATION\n";
    try {
        unsigned pair_cases=0,full_cases=0,min_steps=std::numeric_limits<unsigned>::max(),max_steps=0;
        // All 65,536 low/high byte combinations, two distractor RX1/ACK cases.
        for(unsigned noise: {0u,255u})for(unsigned hi=0;hi<256;++hi)for(unsigned lo=0;lo<256;++lo) {
            Fixture f{};f.noise=noise;f.replies[0]=lo;f.replies[1]=hi;
            execute(f,0xa3980u,0xa39f0u,4);++pair_cases;
        }
        // Each of four raw words visits all 1,024 values; all 256 flag reply
        // bytes occur. Upper six bits of high bytes and status schedules vary.
        for(unsigned value=0;value<1024;++value)for(unsigned flags=0;flags<4;++flags) {
            Fixture f{};f.noise=(value*29u+flags)&255u;f.delay=std::array<unsigned,4>{0,1,3,7}[flags];
            std::array<unsigned,4> samples={value,1023u-value,(value*37u)&1023u,value^0x155u};
            for(unsigned i=0;i<4;++i) {
                f.replies[i*2]=samples[i]&255u;
                f.replies[i*2+1]=(samples[i]>>8)|((value*13u+i*44u)&0xfcu);
            }
            f.replies[8]=(value&0xfcu)|flags;
            auto measured=execute(f,0xa38c0u,0xa3974u,18);
            if(measured.steps<min_steps)min_steps=measured.steps;
            if(measured.steps>max_steps)max_steps=measured.steps;
            ++full_cases;
        }
        std::cout<<"{\"synthetic_inputs\":true,\"pair_cases\":"<<pair_cases
                 <<",\"snapshot_cases\":"<<full_cases<<",\"pair_byte_domain\":65536"
                 <<",\"pair_distractor_patterns\":2,\"raw_values_per_slot\":1024"
                 <<",\"flag_reply_values\":256,\"snapshot_transactions\":18"
                 <<",\"snapshot_selections\":9,\"snapshot_outputs\":6"
                 <<",\"step_min\":"<<min_steps<<",\"step_max\":"<<max_steps
                 <<",\"all_contracts_passed\":true}\n";
    } catch(const std::exception& e) {
        std::cerr<<"Input contract failed: "<<e.what()<<'\n';return 2;
    }
    return 0;
}
