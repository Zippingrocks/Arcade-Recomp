#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>

namespace arcaderecomp::m68k {

// Model 2 SCSP sound RAM with explicit byte knownness.  Host allocation is
// never treated as evidence of power-on contents.  Ordinary reads require
// known bytes; side-effect-free discarded reads may precede a write such as
// MC68000 CLR without inventing the discarded value.
class SoundRAM final {
    std::vector<std::uint8_t> data_ = std::vector<std::uint8_t>(0x80000u, 0);
    std::vector<std::uint8_t> known_ = std::vector<std::uint8_t>(0x80000u, 0);
    std::uint32_t known_bytes_ = 0;
public:
    static constexpr std::uint32_t size = 0x80000u;

    void invalidate() {
        std::fill(known_.begin(), known_.end(), 0);
        known_bytes_ = 0;
    }

    bool read8(std::uint32_t offset, std::uint8_t& result) const {
        if (offset >= size || !known_[offset]) return false;
        result = data_[offset];
        return true;
    }

    bool read16(std::uint32_t offset, std::uint16_t& result) const {
        if ((offset & 1u) || offset + 1u >= size || !known_[offset] || !known_[offset + 1u])
            return false;
        result = static_cast<std::uint16_t>((std::uint16_t(data_[offset]) << 8u) |
                                            data_[offset + 1u]);
        return true;
    }

    bool read8_discard(std::uint32_t offset) const { return offset < size; }
    bool read16_discard(std::uint32_t offset) const {
        return !(offset & 1u) && offset + 1u < size;
    }

    bool write8(std::uint32_t offset, std::uint8_t value) {
        if (offset >= size) return false;
        data_[offset] = value;
        if (!known_[offset]) { known_[offset] = 1; ++known_bytes_; }
        return true;
    }

    bool write16(std::uint32_t offset, std::uint16_t value) {
        if ((offset & 1u) || offset + 1u >= size) return false;
        return write8(offset, static_cast<std::uint8_t>(value >> 8u)) &&
               write8(offset + 1u, static_cast<std::uint8_t>(value));
    }

    std::uint32_t known_bytes() const { return known_bytes_; }
};

}
