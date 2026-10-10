// Original ArcadeRecomp observation tool; NOT a Sega serial device model.
// External evidence: biggestsonicfan/m2-sdk docs/rs422-serial-protocol.md
// at f952efb0bf7445f2d2cee1c9a6cca93af4194106 (Model 2B report).
// Record a TXD2 data latch followed by a TXD1 command/strobe. No busy flags,
// RX bytes, baud clocks, FPGA pins or configuration success are fabricated.
#pragma once
#include <array>
#include <cstdint>
#include <optional>
#include <stdexcept>

namespace arcaderecomp_model2c {
struct CapturedSerialCommand {
    std::uint8_t command;
    std::optional<std::uint8_t> data;
    std::uint64_t command_sequence;
    std::optional<std::uint64_t> data_sequence;
    bool fresh_data;
};

class SerialTxCapture final {
public:
    static constexpr std::uint32_t TXD1 = 0x01c00012u;
    static constexpr std::uint32_t TXD2 = 0x01c00014u;

    // Sequence is observer ordering, not cycles or elapsed board time.
    // Unknown initial latch stays unknown. A command still gets recorded.
    std::optional<CapturedSerialCommand> observe(std::uint64_t sequence,
                                                 std::uint32_t address,
                                                 std::uint8_t byte) {
        if (address != TXD1 && address != TXD2)
            throw std::invalid_argument("not a serial TX byte register");
        if (last_sequence_ && sequence <= *last_sequence_)
            throw std::invalid_argument("serial write order is not increasing");
        if (address == TXD2) {
            data_ = byte;
            data_sequence_ = sequence;
            fresh_ = true;
            last_sequence_ = sequence;
            return std::nullopt; // A data-latch write alone is NOT a transfer.
        }
        CapturedSerialCommand result{byte, data_, sequence, data_sequence_, fresh_};
        last_sequence_ = sequence;
        fresh_ = false;
        return result;
    }

    // Explicitly discard observation continuity. Not an emulated power-on state.
    void reset_observation() noexcept {
        data_.reset(); data_sequence_.reset(); last_sequence_.reset(); fresh_ = false;
    }

    // The Model 2B report measures the 07/data byte pair on its wire. Other
    // command encodings are deliberately NOT inferred from those measurements.
    // This predicts byte framing only, not transmission timing or peer ACKs.
    static std::array<std::uint8_t, 2> model2b_reported_07_pair(
            const CapturedSerialCommand& event) {
        if (event.command != 7u || !event.data)
            throw std::invalid_argument("wire format unsupported or data latch unknown");
        return {7u, *event.data};
    }
private:
    std::optional<std::uint8_t> data_;
    std::optional<std::uint64_t> data_sequence_, last_sequence_;
    bool fresh_ = false;
};
} // namespace arcaderecomp_model2c
