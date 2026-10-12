// Independent, bounded SCSP common-control register, not a sound generator.
// Sega ST-077-R2-052594, printed pp. 5, 35, 88-89.
#pragma once
#include <cstdint>

namespace arcaderecomp::scsp {

struct ControlRead {
    std::uint16_t value;
    std::uint16_t known_mask;
};

class CommonControl {
    std::uint16_t written_ = 0;
    std::uint16_t written_known_ = 0;
    std::uint8_t version_ = 0;
    bool version_known_ = false;
    std::uint64_t writes_ = 0;
    std::uint64_t discarded_reads_ = 0;
public:
    static constexpr std::uint16_t writable = 0x030fu;

    // Host zero-initialization is not evidence of power-on register contents.
    void invalidate() { *this = CommonControl{}; }

    // Caller-supplied independently observed silicon version, never a default.
    bool establish_version(unsigned version) {
        if (version > 15u) return false;
        version_ = static_cast<std::uint8_t>(version);
        version_known_ = true;
        return true;
    }

    // Write-only fields read as zero, irrespective of their stored value.
    // Reserved bits remain unknown; the manual does not define their readback.
    ControlRead read_fields() const {
        return {static_cast<std::uint16_t>(version_known_ ? version_ << 4 : 0),
                static_cast<std::uint16_t>(writable | (version_known_ ? 0x00f0u : 0))};
    }

    bool read8(unsigned offset, std::uint8_t& result) const {
        if (offset > 1u) return false;
        const auto bits = read_fields();
        const unsigned shift = offset == 0u ? 8u : 0u;
        if (((bits.known_mask >> shift) & 0xffu) != 0xffu) return false;
        result = static_cast<std::uint8_t>(bits.value >> shift);
        return true;
    }

    // A read transaction still happens, but CLR does not consume its data.
    // This register has no read side effect. Never generalize to MIDI/status.
    bool read8_discard(unsigned offset) {
        if (offset > 1u) return false;
        ++discarded_reads_;
        return true;
    }

    bool write8(unsigned offset, std::uint8_t value) {
        if (offset > 1u) return false;
        const unsigned shift = offset == 0u ? 8u : 0u;
        const auto bits = static_cast<std::uint16_t>(std::uint16_t(value) << shift);
        if ((bits & ~writable) != 0u) return false;
        const auto mask = static_cast<std::uint16_t>(writable & (0xffu << shift));
        written_ = static_cast<std::uint16_t>((written_ & ~mask) | bits);
        written_known_ |= mask;
        ++writes_;
        return true;
    }

    bool write16(std::uint16_t value) {
        if ((value & ~writable) != 0u) return false;
        written_ = value;
        written_known_ = writable;
        ++writes_;
        return true;
    }

    std::uint16_t written_fields() const { return written_; }
    std::uint16_t written_known_mask() const { return written_known_; }
    bool output_muted_known() const { return (written_known_ & 15u) == 15u; }
    bool output_muted() const { return output_muted_known() && (written_ & 15u) == 0u; }
    std::uint64_t completed_writes() const { return writes_; }
    std::uint64_t completed_discarded_reads() const { return discarded_reads_; }
};

// DSP ring-buffer configuration at SCSP common word 0x402.  Both documented
// fields are write-only.  RBL is word bits 8:7 and RBP is bits 6:0; every
// higher bit is reserved and rejected rather than silently discarded.
class DspMemoryControl {
    std::uint16_t written_ = 0;
    std::uint16_t written_known_ = 0;
    std::uint64_t writes_ = 0;
public:
    static constexpr std::uint16_t writable = 0x01ffu;

    void invalidate() { *this = DspMemoryControl{}; }

    bool write8(unsigned offset, std::uint8_t value) {
        if (offset > 1u) return false;
        const unsigned shift = offset == 0u ? 8u : 0u;
        const auto bits = static_cast<std::uint16_t>(std::uint16_t(value) << shift);
        if ((bits & ~writable) != 0u) return false;
        const auto mask = static_cast<std::uint16_t>(writable & (0xffu << shift));
        written_ = static_cast<std::uint16_t>((written_ & ~mask) | bits);
        written_known_ |= mask;
        ++writes_;
        return true;
    }

    bool write16(std::uint16_t value) {
        if ((value & ~writable) != 0u) return false;
        written_ = value;
        written_known_ = writable;
        ++writes_;
        return true;
    }

    std::uint16_t written_fields() const { return written_; }
    std::uint16_t written_known_mask() const { return written_known_; }
    std::uint64_t completed_writes() const { return writes_; }
    bool configuration_known() const { return written_known_ == writable; }

    bool ring_buffer_length_words(std::uint32_t& result) const {
        if (!configuration_known()) return false;
        result = 0x2000u << ((written_ >> 7u) & 3u);
        return true;
    }

    bool ring_buffer_base_byte(std::uint32_t& result) const {
        if (!configuration_known()) return false;
        // RBP names byte-address bits 19:13: one unit is 8 KiB / 4K words.
        result = std::uint32_t(written_ & 0x007fu) << 13u;
        return true;
    }
};

} // namespace arcaderecomp::scsp
