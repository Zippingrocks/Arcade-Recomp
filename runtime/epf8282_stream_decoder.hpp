// Independently authored incremental decoder for the measured EPF8282 profile.
// This implements the already cross-checked serial-record -> SOF-data mapping;
// it is NOT a silicon configuration controller, cryptographic authenticator,
// decoder of header/options, or a source of CONF_DONE/nSTATUS/Sega RX replies.
// See docs/EPF8282_STREAMING_DECODER.md for specification/evidence boundaries.
#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp_flex8000 {

struct StreamEnvelope {
    // Opaque expected bytes supplied explicitly by the caller. They are matched,
    // not interpreted as device mode/options or authenticated by the frame check.
    std::array<std::uint8_t, 31> prefix;
    std::uint8_t suffix;
};
enum class StreamState { idle, receiving, failed, profile_complete };
enum class StreamError { none, prefix_mismatch, fixed_bit_mismatch,
                         record_check_mismatch, suffix_mismatch,
                         truncated, extra_bits };

class EPF8282StreamDecoder final {
public:
    static constexpr std::size_t kRecords = 212, kRecordBits = 192;
    static constexpr std::size_t kDataPerRecord = 177;
    static constexpr std::size_t kDataBits = kRecords * kDataPerRecord;
    static constexpr std::size_t kPackedBytes = (kDataBits + 7) / 8;
    static constexpr std::size_t kPrefixBits = 31 * 8;
    static constexpr std::size_t kStreamBits = kPrefixBits + kRecords*kRecordBits + 8;
    using PackedData = std::array<std::uint8_t, kPackedBytes>;

    explicit EPF8282StreamDecoder(StreamEnvelope envelope) : envelope_(envelope) {}

    void begin() {
        if (state_ != StreamState::idle)
            throw std::logic_error("explicit reset required before another stream");
        state_ = StreamState::receiving;
    }
    void reset() noexcept {
        state_ = StreamState::idle; error_ = StreamError::none;
        bits_seen_ = records_validated_ = failure_bit_ = 0;
        data_.fill(0); frame_.fill(0); remainder_ = 0; power_ = 1;
    }

    // One already qualified decoder-input bit, delivered LSB-first from an
    // upstream input stage. No clocks, elapsed-time guesses or implicit restart.
    // A bad stream latches an error and discards its staged image. It cannot
    // resynchronize in the middle of arbitrary bytes without explicit reset.
    bool push_bit(bool bit) {
        require_receiving();
        const std::size_t position = bits_seen_;
        if (position == kStreamBits) return fail(StreamError::extra_bits, position);
        ++bits_seen_;
        if (position < kPrefixBits) {
            const bool expected = ((envelope_.prefix[position/8] >> (position%8)) & 1u) != 0;
            return bit == expected || fail(StreamError::prefix_mismatch, position);
        }
        const std::size_t relative = position - kPrefixBits;
        if (relative >= kRecords * kRecordBits) {
            const bool expected = ((envelope_.suffix >> (relative-kRecords*kRecordBits)) & 1u) != 0;
            return bit == expected || fail(StreamError::suffix_mismatch, position);
        }
        const std::size_t offset = relative % kRecordBits;
        if (offset == 0) {
            if (bit) return fail(StreamError::fixed_bit_mismatch, position);
        } else if (offset <= 185) {
            // Polynomial evaluation by ascending coefficients, independent of
            // the Python long-division/check-inversion implementation.
            if (bit) remainder_ ^= power_;
            unsigned next = unsigned(power_) << 1u;
            if (next & 0x100u) next ^= 0x111u;
            power_ = static_cast<std::uint8_t>(next);
            if (offset <= kDataPerRecord && bit)
                frame_[(offset-1)/8] |= static_cast<std::uint8_t>(1u << ((offset-1)%8));
            if (offset == 185 && remainder_ != 0xffu)
                return fail(StreamError::record_check_mismatch, position);
        } else if (!bit) {
            return fail(StreamError::fixed_bit_mismatch, position);
        }
        if (offset == kRecordBits-1) {
            // Commit only a fully checked record to the private staging buffer.
            // Reverse all 37,524 data bits globally, not each byte or record.
            for (std::size_t i = 0; i < kDataPerRecord; ++i) {
                const auto target = kDataBits-1-(records_validated_*kDataPerRecord+i);
                if ((frame_[i/8] >> (i%8)) & 1u)
                    data_[target/8] |= static_cast<std::uint8_t>(1u << (target%8));
            }
            ++records_validated_; frame_.fill(0); remainder_ = 0; power_ = 1;
        }
        return true;
    }

    // Explicit end-of-input is required: neither an input-byte count nor a
    // completed record automatically makes a snapshot available.
    bool finish() {
        require_receiving();
        if (bits_seen_ != kStreamBits) return fail(StreamError::truncated, bits_seen_);
        state_ = StreamState::profile_complete;
        return true;
    }

    // Return a value, not a reference into mutable staging memory. A caller
    // retaining this copy owns its lifetime; reset invalidates this decoder,
    // not copies already taken. This is data, not an acceptance token.
    PackedData packed_data() const {
        if (state_ != StreamState::profile_complete)
            throw std::logic_error("no complete checked profile image");
        return data_;
    }
    StreamState state() const noexcept { return state_; }
    StreamError error() const noexcept { return error_; }
    std::size_t bits_seen() const noexcept { return bits_seen_; }
    std::size_t records_validated() const noexcept { return records_validated_; }
    std::size_t failure_bit() const noexcept { return failure_bit_; }

private:
    const StreamEnvelope envelope_;
    StreamState state_ = StreamState::idle;
    StreamError error_ = StreamError::none;
    std::size_t bits_seen_ = 0, records_validated_ = 0, failure_bit_ = 0;
    PackedData data_{};
    std::array<std::uint8_t, (kDataPerRecord+7)/8> frame_{};
    std::uint8_t remainder_ = 0, power_ = 1;

    void require_receiving() const {
        if (state_ != StreamState::receiving)
            throw std::logic_error("no active stream; explicit begin/reset required");
    }
    bool fail(StreamError error, std::size_t position) noexcept {
        state_ = StreamState::failed; error_ = error; failure_bit_ = position;
        data_.fill(0); frame_.fill(0); remainder_ = 0; power_ = 1;
        return false;
    }
};
} // namespace arcaderecomp_flex8000
