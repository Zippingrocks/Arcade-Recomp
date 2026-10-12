// SCSP per-slot mixer word only; no synthesis, key state, envelope or timing.
// Sega ST-077-R2-052594, individual slot control register word +0x16.
#pragma once
#include <array>
#include <cstdint>

namespace arcaderecomp::scsp {

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
