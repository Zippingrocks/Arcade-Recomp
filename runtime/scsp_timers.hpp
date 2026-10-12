// SCSP timers A/B/C with explicit sample-clock advancement.
// Sega ST-077-R2-052594 section 4.2.11.
#pragma once
#include <array>
#include <cstdint>

namespace arcaderecomp::scsp {

class Timers final {
    std::array<std::uint8_t,3> count_{};
    std::array<std::uint8_t,3> control_{};
    std::array<std::uint8_t,3> phase_{};
    std::array<bool,3> running_{};
    std::array<bool,3> request_{};
    std::uint64_t writes_=0;

    static bool decode(unsigned offset,unsigned& timer){
        if(offset<0x18u||offset>0x1cu||(offset&1u))return false;
        timer=(offset-0x18u)>>1u;return true;
    }
public:
    static constexpr unsigned timer_count=3u;
    static constexpr std::uint16_t field_mask=0x07ffu;

    void invalidate(){*this=Timers{};}
    bool write16(unsigned offset,std::uint16_t value){
        unsigned timer=0;if(!decode(offset,timer)||(value&~field_mask))return false;
        control_[timer]=static_cast<std::uint8_t>((value>>8u)&7u);
        count_[timer]=static_cast<std::uint8_t>(value);
        phase_[timer]=0;running_[timer]=true;request_[timer]=false;++writes_;return true;
    }
    // One explicit 44.1 kHz sample event. No CPU instruction implicitly clocks
    // these timers. Behavior after a pending timer at FF would require the
    // interrupt/clear registers and therefore fails closed without mutation.
    bool tick_sample(){
        for(unsigned timer=0;timer<timer_count;++timer)
            if(running_[timer]&&count_[timer]==0xffu&&
                    phase_[timer]+1u>=(1u<<control_[timer]))return false;
        for(unsigned timer=0;timer<timer_count;++timer){
            if(!running_[timer])continue;
            if(++phase_[timer]<(1u<<control_[timer]))continue;
            phase_[timer]=0;
            if(++count_[timer]==0xffu)request_[timer]=true;
        }
        return true;
    }
    std::uint8_t count(unsigned timer)const{return timer<timer_count?count_[timer]:0u;}
    std::uint8_t control(unsigned timer)const{return timer<timer_count?control_[timer]:0u;}
    std::uint8_t phase(unsigned timer)const{return timer<timer_count?phase_[timer]:0u;}
    bool running(unsigned timer)const{return timer<timer_count&&running_[timer];}
    bool interrupt_request(unsigned timer)const{return timer<timer_count&&request_[timer];}
    std::uint64_t completed_writes()const{return writes_;}
};

} // namespace arcaderecomp::scsp
