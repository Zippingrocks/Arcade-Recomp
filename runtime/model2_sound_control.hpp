#pragma once
#include <cstdint>

namespace arcaderecomp::model2 {

// Bounded contract for the original HOTD Model 2 sound-control aperture.
// The target has exactly 8 MiB of sample data, so the published Model 2
// reference handler performs no sample-bank change.  This object records bus
// transactions for validation; it does not invent a readable latch.
class HotdSoundControl final {
    std::uint16_t last_transaction_data_ = 0;
    std::uint16_t last_transaction_known_mask_ = 0;
    std::uint64_t completed_writes_ = 0;
public:
    static constexpr std::uint32_t sample_region_bytes = 0x800000u;

    // Only the low byte lane is established by original HOTD stores.  The
    // even/high byte lane remains refused until its strobe semantics are known.
    bool write8(unsigned offset, std::uint8_t value) {
        if (offset != 1u) return false;
        last_transaction_data_ = static_cast<std::uint16_t>(
            (last_transaction_data_ & 0xff00u) | value);
        last_transaction_known_mask_ = static_cast<std::uint16_t>(
            last_transaction_known_mask_ | 0x00ffu);
        ++completed_writes_;
        return true;
    }

    bool write16(std::uint16_t value) {
        last_transaction_data_ = value;
        last_transaction_known_mask_ = 0xffffu;
        ++completed_writes_;
        return true;
    }

    std::uint16_t last_transaction_data() const { return last_transaction_data_; }
    std::uint16_t last_transaction_known_mask() const {
        return last_transaction_known_mask_;
    }
    std::uint64_t completed_writes() const { return completed_writes_; }
    static constexpr bool sample_bank_changed() { return false; }
};

}
