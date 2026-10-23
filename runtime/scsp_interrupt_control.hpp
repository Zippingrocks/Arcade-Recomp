// SCSP sound/main CPU interrupt control register group.
// Sega ST-077-R2-052594 section 4.2.12.
#pragma once
#include <array>
#include <cstdint>

namespace arcaderecomp::scsp {

class InterruptControl final {
    std::array<std::uint16_t,2> enable_{};
    std::array<std::uint16_t,2> enable_known_{};
    std::array<std::uint16_t,2> pending_{};
    std::array<std::uint16_t,2> pending_known_{};
    std::array<std::uint8_t,3> sound_level_{};
    std::array<std::uint8_t,3> sound_level_known_{};
    std::uint64_t writes_=0;

    static constexpr std::uint16_t factors=0x07ffu;
    static bool target_offset(unsigned offset,unsigned base,unsigned& target){
        if(offset==base){target=0;return true;}
        if(offset==base+0x0cu){target=1;return true;}
        return false;
    }
public:
    void invalidate(){*this=InterruptControl{};}
    bool write16(unsigned offset,std::uint16_t value){
        if(value&~factors)return false;
        unsigned target=0;
        if(target_offset(offset,0x1eu,target)){
            enable_[target]=value;enable_known_[target]=factors;++writes_;return true;
        }
        if(target_offset(offset,0x20u,target)){
            if(value&0x20u){pending_[target]|=0x20u;pending_known_[target]|=0x20u;}
            ++writes_;return true;
        }
        if(target_offset(offset,0x22u,target)){
            pending_[target]&=static_cast<std::uint16_t>(~value);
            pending_known_[target]|=value;++writes_;return true;
        }
        if(offset>=0x24u&&offset<=0x28u&&!(offset&1u)){
            if(value&0xff00u)return false;
            sound_level_[(offset-0x24u)>>1u]=static_cast<std::uint8_t>(value);
            sound_level_known_[(offset-0x24u)>>1u]=0xffu;
            ++writes_;return true;
        }
        return false;
    }
    void observe(unsigned factor){
        if(factor>=11u)return;
        const auto bit=static_cast<std::uint16_t>(1u<<factor);
        for(unsigned target=0;target<2u;++target){pending_[target]|=bit;pending_known_[target]|=bit;}
    }
    // The MIDI-input request releases automatically when its FIFO is empty.
    void release_midi_input(){
        for(unsigned target=0;target<2u;++target){
            pending_[target]&=static_cast<std::uint16_t>(~0x08u);
            pending_known_[target]|=0x08u;
        }
    }
    std::uint16_t enable(unsigned target)const{return target<2u?enable_[target]:0u;}
    std::uint16_t enable_known_mask(unsigned target)const{return target<2u?enable_known_[target]:0u;}
    std::uint16_t pending(unsigned target)const{return target<2u?pending_[target]:0u;}
    std::uint16_t pending_known_mask(unsigned target)const{return target<2u?pending_known_[target]:0u;}
    std::uint8_t sound_level_bits(unsigned plane)const{return plane<3u?sound_level_[plane]:0u;}
    bool sound_irq_asserted(unsigned factor)const{
        if(factor>=11u)return false;
        const auto bit=static_cast<std::uint16_t>(1u<<factor);
        return (enable_known_[0]&pending_known_[0]&enable_[0]&pending_[0]&bit)!=0;
    }
    bool main_irq_asserted(unsigned factor)const{
        if(factor>=11u)return false;
        const auto bit=static_cast<std::uint16_t>(1u<<factor);
        return (enable_known_[1]&pending_known_[1]&enable_[1]&pending_[1]&bit)!=0;
    }
    unsigned sound_level(unsigned factor)const{
        if(factor>=11u)return 0u;
        const unsigned bit=factor<8u?factor:7u;
        unsigned level=0;
        for(unsigned plane=0;plane<3u;++plane)level|=((sound_level_[plane]>>bit)&1u)<<plane;
        return level;
    }
    bool sound_level_known(unsigned factor)const{
        if(factor>=11u)return false;
        const auto bit=static_cast<std::uint8_t>(1u<<(factor<8u?factor:7u));
        return (sound_level_known_[0]&sound_level_known_[1]&sound_level_known_[2]&bit)!=0;
    }
    bool sound_cpu_interrupt_level(unsigned& result)const{
        result=0;
        for(unsigned factor=0;factor<11u;++factor){
            const auto bit=static_cast<std::uint16_t>(1u<<factor);
            if(!(enable_known_[0]&bit))return false;
            if(!(enable_[0]&bit))continue;
            if(!(pending_known_[0]&bit))return false;
            if(!(pending_[0]&bit))continue;
            if(!sound_level_known(factor))return false;
            const unsigned level=sound_level(factor);
            if(level>result)result=level;
        }
        return true;
    }
    std::uint64_t completed_writes()const{return writes_;}
};

} // namespace arcaderecomp::scsp
