// SCSP per-slot loop/key control and the cross-slot KEY_ON execution command.
// Sega ST-077-R2-052594 section 4.2.1: KYONEX is write-only; writing one
// executes the registered KYONB state of all 32 slots simultaneously.
#pragma once
#include <array>
#include <cstdint>

namespace arcaderecomp::scsp {

class SlotLoopKeyControl final {
    std::array<std::uint16_t,32> value_{};
    std::array<std::uint16_t,32> known_{};
    std::array<bool,32> key_active_{};
    std::array<bool,32> key_active_known_{};
    std::uint64_t writes_=0;
    std::uint64_t executions_=0;

    static bool decode(unsigned offset,unsigned& slot,unsigned& lane){
        if(offset>=0x400u)return false;
        slot=offset>>5u;const unsigned within=offset&0x1fu;
        if(within!=0u&&within!=1u)return false;
        lane=within;return true;
    }
    void execute(){
        for(unsigned slot=0;slot<32u;++slot){
            if(known_[slot]&key_on_bit){
                key_active_known_[slot]=true;
                key_active_[slot]=(value_[slot]&key_on_bit)!=0;
            }else{
                key_active_known_[slot]=false;
                key_active_[slot]=false;
            }
        }
        ++executions_;
    }
public:
    static constexpr unsigned slots=32u;
    static constexpr std::uint16_t execution_bit=0x1000u;
    static constexpr std::uint16_t key_on_bit=0x0800u;
    static constexpr std::uint16_t field_mask=0x1fffu;
    static constexpr std::uint16_t stored_mask=0x0fffu;

    void invalidate(){*this=SlotLoopKeyControl{};}
    bool read8(unsigned offset,std::uint8_t& result)const{
        unsigned slot=0,lane=0;if(!decode(offset,slot,lane))return false;
        // The upper lane contains write-only KYONEX and has no exact readback.
        if(!lane||((known_[slot]&0x00ffu)!=0x00ffu))return false;
        result=static_cast<std::uint8_t>(value_[slot]);return true;
    }
    bool read16(unsigned,std::uint16_t&)const{return false;}
    bool write8(unsigned offset,std::uint8_t byte){
        unsigned slot=0,lane=0;if(!decode(offset,slot,lane))return false;
        const unsigned shift=lane?0u:8u;const auto bits=std::uint16_t(byte)<<shift;
        if(bits&~field_mask)return false;
        const auto mask=static_cast<std::uint16_t>(stored_mask&(0xffu<<shift));
        value_[slot]=static_cast<std::uint16_t>((value_[slot]&~mask)|(bits&stored_mask));
        known_[slot]|=mask;++writes_;
        if(bits&execution_bit)execute();
        return true;
    }
    bool write16(unsigned offset,std::uint16_t word){
        unsigned slot=0,lane=0;if(!decode(offset,slot,lane)||lane||(word&~field_mask))return false;
        value_[slot]=word&stored_mask;known_[slot]=stored_mask;++writes_;
        if(word&execution_bit)execute();
        return true;
    }
    std::uint16_t value(unsigned slot)const{return slot<slots?value_[slot]:0u;}
    std::uint16_t known_mask(unsigned slot)const{return slot<slots?known_[slot]:0u;}
    bool key_active(unsigned slot)const{return slot<slots&&key_active_[slot];}
    bool key_active_known(unsigned slot)const{return slot<slots&&key_active_known_[slot];}
    std::uint64_t completed_writes()const{return writes_;}
    std::uint64_t completed_executions()const{return executions_;}
};

} // namespace arcaderecomp::scsp
