// Selected SCSP per-slot control words; no synthesis, key execution or timing.
// Sega ST-077-R2-052594, individual slot register words +0x0a..0x16.
#pragma once
#include <array>
#include <cstdint>

namespace arcaderecomp::scsp {

class SlotEnvelopeReleaseControl final {
    std::array<std::uint16_t,32> value_{};
    std::array<std::uint16_t,32> known_{};
    std::uint64_t writes_=0;
    static bool decode(unsigned offset,unsigned& slot,unsigned& lane){
        if(offset>=0x400u)return false;
        slot=offset>>5u;
        const unsigned within=offset&0x1fu;if(within!=0x0au&&within!=0x0bu)return false;
        lane=within-0x0au;return true;
    }
public:
    static constexpr unsigned slots=32u;
    static constexpr std::uint16_t field_mask=0x7fffu;
    void invalidate(){*this=SlotEnvelopeReleaseControl{};}
    bool read8(unsigned offset,std::uint8_t& result)const{
        unsigned s=0,l=0;if(!decode(offset,s,l))return false;const unsigned shift=l?0u:8u;
        if(((known_[s]>>shift)&0xffu)!=0xffu)return false;
        result=static_cast<std::uint8_t>(value_[s]>>shift);return true;
    }
    bool read16(unsigned offset,std::uint16_t& result)const{
        unsigned s=0,l=0;if(!decode(offset,s,l)||l||known_[s]!=0xffffu)return false;
        result=value_[s];return true;
    }
    bool write8(unsigned offset,std::uint8_t value){
        unsigned s=0,l=0;if(!decode(offset,s,l))return false;const unsigned shift=l?0u:8u;
        const auto bits=std::uint16_t(value)<<shift;if(bits&~field_mask)return false;
        const auto mask=static_cast<std::uint16_t>(field_mask&(0xffu<<shift));
        value_[s]=static_cast<std::uint16_t>((value_[s]&~mask)|bits);known_[s]|=mask;++writes_;return true;
    }
    bool write16(unsigned offset,std::uint16_t value){
        unsigned s=0,l=0;if(!decode(offset,s,l)||l||(value&~field_mask))return false;
        value_[s]=value;known_[s]=field_mask;++writes_;return true;
    }
    std::uint16_t value(unsigned s)const{return s<slots?value_[s]:0u;}
    std::uint16_t known_mask(unsigned s)const{return s<slots?known_[s]:0u;}
    std::uint64_t completed_writes()const{return writes_;}
};

class SlotLfoControl final {
    std::array<std::uint16_t,32> value_{};
    std::array<std::uint16_t,32> known_{};
    std::uint64_t writes_=0,discarded_reads_=0;
    static bool decode(unsigned offset,unsigned& slot,unsigned& lane){
        if(offset>=0x400u)return false;
        slot=offset>>5u;
        const unsigned within=offset&0x1fu;if(within!=0x12u&&within!=0x13u)return false;
        lane=within-0x12u;return true;
    }
public:
    static constexpr unsigned slots=32u;
    void invalidate(){*this=SlotLfoControl{};}
    bool read8(unsigned offset,std::uint8_t& result)const{
        unsigned s=0,l=0;if(!decode(offset,s,l))return false;const unsigned shift=l?0u:8u;
        if(((known_[s]>>shift)&0xffu)!=0xffu)return false;
        result=static_cast<std::uint8_t>(value_[s]>>shift);return true;
    }
    bool read16(unsigned offset,std::uint16_t& result)const{
        unsigned s=0,l=0;if(!decode(offset,s,l)||l||known_[s]!=0xffffu)return false;
        result=value_[s];return true;
    }
    bool read8_discard(unsigned offset){unsigned s=0,l=0;if(!decode(offset,s,l))return false;++discarded_reads_;return true;}
    bool read16_discard(unsigned offset){unsigned s=0,l=0;if(!decode(offset,s,l)||l)return false;++discarded_reads_;return true;}
    bool write8(unsigned offset,std::uint8_t value){
        unsigned s=0,l=0;if(!decode(offset,s,l))return false;const unsigned shift=l?0u:8u;
        const auto mask=static_cast<std::uint16_t>(0xffu<<shift);
        value_[s]=static_cast<std::uint16_t>((value_[s]&~mask)|(std::uint16_t(value)<<shift));
        known_[s]|=mask;++writes_;return true;
    }
    bool write16(unsigned offset,std::uint16_t value){
        unsigned s=0,l=0;if(!decode(offset,s,l)||l)return false;
        value_[s]=value;known_[s]=0xffffu;++writes_;return true;
    }
    std::uint16_t value(unsigned s)const{return s<slots?value_[s]:0u;}
    std::uint16_t known_mask(unsigned s)const{return s<slots?known_[s]:0u;}
    std::uint64_t completed_writes()const{return writes_;}
    std::uint64_t completed_discarded_reads()const{return discarded_reads_;}
};

class SlotVolumeModulationControl final {
    std::array<std::array<std::uint16_t,2>,32> value_{};
    std::array<std::array<std::uint16_t,2>,32> known_{};
    std::uint64_t writes_ = 0;
    std::uint64_t discarded_reads_ = 0;

    static bool decode(unsigned offset,unsigned& slot,unsigned& word,unsigned& lane){
        if(offset>=0x400u)return false;
        slot=offset>>5u;const unsigned within=offset&0x1fu;
        if(within<0x0cu||within>0x0fu)return false;
        word=(within-0x0cu)>>1u;lane=within&1u;return true;
    }
    static constexpr std::uint16_t mask(unsigned word){return word?0xffffu:0x03ffu;}
public:
    static constexpr unsigned slots=32u;
    void invalidate(){*this=SlotVolumeModulationControl{};}
    bool read8(unsigned offset,std::uint8_t& result)const{
        unsigned slot=0,word=0,lane=0;if(!decode(offset,slot,word,lane))return false;
        const unsigned shift=lane?0u:8u,requested=0xffu<<shift;
        if((known_[slot][word]&requested)!=requested)return false;
        result=static_cast<std::uint8_t>(value_[slot][word]>>shift);return true;
    }
    bool read16(unsigned offset,std::uint16_t& result)const{
        unsigned slot=0,word=0,lane=0;
        if(!decode(offset,slot,word,lane)||lane||known_[slot][word]!=0xffffu)return false;
        result=value_[slot][word];return true;
    }
    bool read8_discard(unsigned offset){
        unsigned slot=0,word=0,lane=0;if(!decode(offset,slot,word,lane))return false;
        ++discarded_reads_;return true;
    }
    bool read16_discard(unsigned offset){
        unsigned slot=0,word=0,lane=0;if(!decode(offset,slot,word,lane)||lane)return false;
        ++discarded_reads_;return true;
    }
    bool write8(unsigned offset,std::uint8_t value){
        unsigned slot=0,word=0,lane=0;if(!decode(offset,slot,word,lane))return false;
        const unsigned shift=lane?0u:8u;const auto bits=std::uint16_t(value)<<shift;
        if(bits&~mask(word))return false;
        const auto lane_mask=static_cast<std::uint16_t>(mask(word)&(0xffu<<shift));
        value_[slot][word]=static_cast<std::uint16_t>((value_[slot][word]&~lane_mask)|bits);
        known_[slot][word]|=lane_mask;++writes_;return true;
    }
    bool write16(unsigned offset,std::uint16_t value){
        unsigned slot=0,word=0,lane=0;
        if(!decode(offset,slot,word,lane)||lane||(value&~mask(word)))return false;
        value_[slot][word]=value;known_[slot][word]=mask(word);++writes_;return true;
    }
    std::uint16_t value(unsigned slot,unsigned word)const{
        return slot<slots&&word<2u?value_[slot][word]:0u;
    }
    std::uint16_t known_mask(unsigned slot,unsigned word)const{
        return slot<slots&&word<2u?known_[slot][word]:0u;
    }
    std::uint64_t completed_writes()const{return writes_;}
    std::uint64_t completed_discarded_reads()const{return discarded_reads_;}
};

class SlotInputMixerControl final {
    std::array<std::uint16_t,32> value_{};
    std::array<std::uint16_t,32> known_{};
    std::uint64_t writes_ = 0;
    std::uint64_t discarded_reads_ = 0;

    static bool decode(unsigned offset,unsigned& slot,unsigned& lane) {
        if(offset>=0x400u)return false;
        slot=offset>>5u;
        const unsigned within=offset&0x1fu;
        if(within!=0x14u&&within!=0x15u)return false;
        lane=within-0x14u;return true;
    }
public:
    static constexpr unsigned slots=32u;
    static constexpr std::uint16_t field_mask=0x007fu;

    void invalidate(){*this=SlotInputMixerControl{};}
    bool read8(unsigned offset,std::uint8_t& result)const{
        unsigned slot=0,lane=0;if(!decode(offset,slot,lane))return false;
        const unsigned shift=lane?0u:8u,requested=0xffu<<shift;
        if((known_[slot]&requested)!=requested)return false;
        result=static_cast<std::uint8_t>(value_[slot]>>shift);return true;
    }
    bool read16(unsigned offset,std::uint16_t& result)const{
        unsigned slot=0,lane=0;
        if(!decode(offset,slot,lane)||lane||known_[slot]!=0xffffu)return false;
        result=value_[slot];return true;
    }
    bool read8_discard(unsigned offset){
        unsigned slot=0,lane=0;if(!decode(offset,slot,lane))return false;
        ++discarded_reads_;return true;
    }
    bool read16_discard(unsigned offset){
        unsigned slot=0,lane=0;if(!decode(offset,slot,lane)||lane)return false;
        ++discarded_reads_;return true;
    }
    bool write8(unsigned offset,std::uint8_t value){
        unsigned slot=0,lane=0;if(!decode(offset,slot,lane)||!lane||(value&0x80u))return false;
        value_[slot]=static_cast<std::uint16_t>((value_[slot]&~field_mask)|value);
        known_[slot]|=field_mask;++writes_;return true;
    }
    bool write16(unsigned offset,std::uint16_t value){
        unsigned slot=0,lane=0;
        if(!decode(offset,slot,lane)||lane||(value&~field_mask))return false;
        value_[slot]=value;known_[slot]=field_mask;++writes_;return true;
    }
    std::uint16_t value(unsigned slot)const{return slot<slots?value_[slot]:0u;}
    std::uint16_t known_mask(unsigned slot)const{return slot<slots?known_[slot]:0u;}
    std::uint64_t completed_writes()const{return writes_;}
    std::uint64_t completed_discarded_reads()const{return discarded_reads_;}
};

class SlotMixerControl final {
    std::array<std::uint16_t,32> value_{};
    std::array<std::uint16_t,32> known_{};
    std::uint64_t writes_ = 0;
    std::uint64_t discarded_reads_ = 0;

    static bool decode(unsigned offset, unsigned& slot, unsigned& lane) {
        if (offset >= 0x400u) return false;
        slot = offset >> 5u;
        const unsigned within = offset & 0x1fu;
        if (within != 0x16u && within != 0x17u) return false;
        lane = within - 0x16u;
        return true;
    }
public:
    static constexpr unsigned slots = 32;

    void invalidate() { *this = SlotMixerControl{}; }

    bool read8(unsigned offset, std::uint8_t& result) const {
        unsigned slot=0,lane=0;
        if (!decode(offset,slot,lane)) return false;
        const unsigned shift = lane ? 0u : 8u;
        if (((known_[slot] >> shift) & 0xffu) != 0xffu) return false;
        result = static_cast<std::uint8_t>(value_[slot] >> shift);
        return true;
    }

    bool read16(unsigned offset, std::uint16_t& result) const {
        unsigned slot=0,lane=0;
        if (!decode(offset,slot,lane) || lane || known_[slot] != 0xffffu) return false;
        result = value_[slot];
        return true;
    }

    // The manual assigns no read side effect to this mixer word. CLR may
    // perform its required read without inventing the discarded reset value.
    bool read8_discard(unsigned offset) {
        unsigned slot=0,lane=0;
        if (!decode(offset,slot,lane)) return false;
        ++discarded_reads_;
        return true;
    }
    bool read16_discard(unsigned offset) {
        unsigned slot=0,lane=0;
        if (!decode(offset,slot,lane) || lane) return false;
        ++discarded_reads_;
        return true;
    }

    bool write8(unsigned offset, std::uint8_t value) {
        unsigned slot=0,lane=0;
        if (!decode(offset,slot,lane)) return false;
        const unsigned shift = lane ? 0u : 8u;
        const auto mask = static_cast<std::uint16_t>(0xffu << shift);
        value_[slot] = static_cast<std::uint16_t>((value_[slot] & ~mask) |
                                                  (std::uint16_t(value) << shift));
        known_[slot] |= mask;
        ++writes_;
        return true;
    }

    bool write16(unsigned offset, std::uint16_t value) {
        unsigned slot=0,lane=0;
        if (!decode(offset,slot,lane) || lane) return false;
        value_[slot] = value;
        known_[slot] = 0xffffu;
        ++writes_;
        return true;
    }

    std::uint16_t value(unsigned slot) const { return slot < slots ? value_[slot] : 0; }
    std::uint16_t known_mask(unsigned slot) const { return slot < slots ? known_[slot] : 0; }
    std::uint64_t completed_writes() const { return writes_; }
    std::uint64_t completed_discarded_reads() const { return discarded_reads_; }
};

} // namespace arcaderecomp::scsp
