// SCSP DSP register files only; no DSP execution or audio timing.
// Sega ST-077-R2-052594: COEF, MADRS and MPRO bus-visible storage.
#pragma once
#include <array>
#include <cstdint>

namespace arcaderecomp::scsp {

class DspCoefficients final {
    std::array<std::uint16_t,64> value_{};
    std::array<std::uint16_t,64> known_{};
    std::uint64_t writes_ = 0;
    std::uint64_t discarded_reads_ = 0;
public:
    static constexpr unsigned bytes = 0x80u;
    static constexpr std::uint16_t field_mask = 0x1fffu;

    void invalidate() { *this = DspCoefficients{}; }

    bool read8(unsigned offset, std::uint8_t& result) const {
        if (offset >= bytes) return false;
        const unsigned index=offset>>1u,shift=(offset&1u)?0u:8u;
        const unsigned requested=0xffu<<shift;
        if ((known_[index]&requested)!=requested) return false;
        result=static_cast<std::uint8_t>(value_[index]>>shift);
        return true;
    }
    bool read16(unsigned offset, std::uint16_t& result) const {
        if (offset>=bytes||(offset&1u)||known_[offset>>1u]!=0xffffu) return false;
        result=value_[offset>>1u];return true;
    }
    bool read8_discard(unsigned offset) {
        if (offset>=bytes) return false;
        ++discarded_reads_;return true;
    }
    bool read16_discard(unsigned offset) {
        if (offset>=bytes||(offset&1u)) return false;
        ++discarded_reads_;return true;
    }
    bool write8(unsigned offset,std::uint8_t value) {
        if (offset>=bytes) return false;
        const unsigned index=offset>>1u,shift=(offset&1u)?0u:8u;
        const auto bits=static_cast<std::uint16_t>(std::uint16_t(value)<<shift);
        if (bits&~field_mask) return false;
        const auto mask=static_cast<std::uint16_t>(field_mask&(0xffu<<shift));
        value_[index]=static_cast<std::uint16_t>((value_[index]&~mask)|bits);
        known_[index]|=mask;++writes_;return true;
    }
    bool write16(unsigned offset,std::uint16_t value) {
        if (offset>=bytes||(offset&1u)||(value&~field_mask)) return false;
        value_[offset>>1u]=value;known_[offset>>1u]=field_mask;++writes_;return true;
    }
    std::uint16_t value(unsigned index) const { return index<64u?value_[index]:0u; }
    std::uint16_t known_mask(unsigned index) const { return index<64u?known_[index]:0u; }
    std::uint64_t completed_writes() const { return writes_; }
    std::uint64_t completed_discarded_reads() const { return discarded_reads_; }
};

// 32 R/W MADRS[16:1] words at 0x100780..0x1007bf. All 16 register bits
// carry the documented address field; address bit zero is implicitly absent.
class DspMemoryAddresses final {
    std::array<std::uint16_t,32> value_{};
    std::array<std::uint16_t,32> known_{};
    std::uint64_t writes_ = 0;
    std::uint64_t discarded_reads_ = 0;
public:
    static constexpr unsigned bytes = 0x40u;
    void invalidate() { *this = DspMemoryAddresses{}; }
    bool read8(unsigned offset,std::uint8_t& result) const {
        if(offset>=bytes)return false;
        const unsigned i=offset>>1u,s=(offset&1u)?0u:8u;
        if(((known_[i]>>s)&0xffu)!=0xffu)return false;
        result=static_cast<std::uint8_t>(value_[i]>>s);
        return true;
    }
    bool read16(unsigned offset,std::uint16_t& result) const {
        if(offset>=bytes||(offset&1u)||known_[offset>>1u]!=0xffffu)return false;
        result=value_[offset>>1u];
        return true;
    }
    bool read8_discard(unsigned offset){if(offset>=bytes)return false;++discarded_reads_;return true;}
    bool read16_discard(unsigned offset){if(offset>=bytes||(offset&1u))return false;++discarded_reads_;return true;}
    bool write8(unsigned offset,std::uint8_t value){
        if(offset>=bytes)return false;
        const unsigned i=offset>>1u,s=(offset&1u)?0u:8u;
        const auto mask=static_cast<std::uint16_t>(0xffu<<s);
        value_[i]=static_cast<std::uint16_t>((value_[i]&~mask)|(std::uint16_t(value)<<s));
        known_[i]|=mask;++writes_;return true;
    }
    bool write16(unsigned offset,std::uint16_t value){
        if(offset>=bytes||(offset&1u))return false;
        value_[offset>>1u]=value;
        known_[offset>>1u]=0xffffu;++writes_;return true;
    }
    std::uint16_t value(unsigned i)const{return i<32u?value_[i]:0u;}
    std::uint16_t known_mask(unsigned i)const{return i<32u?known_[i]:0u;}
    std::uint64_t completed_writes()const{return writes_;}
    std::uint64_t completed_discarded_reads()const{return discarded_reads_;}
};

// 128 R/W 64-bit DSP microinstructions at 0x100800..0x100bff. The MC68000
// bus observes MPRO as 512 big-endian 16-bit words; instruction decoding and
// DSP execution are deliberately separate concerns.
class DspMicroprogram final {
    std::array<std::uint16_t,512> value_{};
    std::array<std::uint16_t,512> known_{};
    std::uint64_t writes_ = 0;
    std::uint64_t discarded_reads_ = 0;
public:
    static constexpr unsigned bytes = 0x400u;
    static constexpr unsigned words = 512u;

    void invalidate() { *this = DspMicroprogram{}; }
    bool read8(unsigned offset,std::uint8_t& result) const {
        if(offset>=bytes)return false;
        const unsigned i=offset>>1u,s=(offset&1u)?0u:8u;
        if(((known_[i]>>s)&0xffu)!=0xffu)return false;
        result=static_cast<std::uint8_t>(value_[i]>>s);
        return true;
    }
    bool read16(unsigned offset,std::uint16_t& result) const {
        if(offset>=bytes||(offset&1u)||known_[offset>>1u]!=0xffffu)return false;
        result=value_[offset>>1u];
        return true;
    }
    bool read8_discard(unsigned offset){
        if(offset>=bytes)return false;
        ++discarded_reads_;return true;
    }
    bool read16_discard(unsigned offset){
        if(offset>=bytes||(offset&1u))return false;
        ++discarded_reads_;return true;
    }
    bool write8(unsigned offset,std::uint8_t value){
        if(offset>=bytes)return false;
        const unsigned i=offset>>1u,s=(offset&1u)?0u:8u;
        const auto mask=static_cast<std::uint16_t>(0xffu<<s);
        value_[i]=static_cast<std::uint16_t>((value_[i]&~mask)|(std::uint16_t(value)<<s));
        known_[i]|=mask;++writes_;return true;
    }
    bool write16(unsigned offset,std::uint16_t value){
        if(offset>=bytes||(offset&1u))return false;
        value_[offset>>1u]=value;known_[offset>>1u]=0xffffu;++writes_;return true;
    }
    std::uint16_t value(unsigned i)const{return i<words?value_[i]:0u;}
    std::uint16_t known_mask(unsigned i)const{return i<words?known_[i]:0u;}
    std::uint64_t completed_writes()const{return writes_;}
    std::uint64_t completed_discarded_reads()const{return discarded_reads_;}
};

} // namespace arcaderecomp::scsp
