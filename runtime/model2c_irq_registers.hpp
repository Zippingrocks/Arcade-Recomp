// ArcadeRecomp: provisional opt-in Sega Model 2C interrupt registers.
// Physical addresses and observed register semantics are documented in
// docs/MODEL2C_INTERRUPT_REGISTER_RESEARCH.md. Hardware behavior, timing
// and CPU exception delivery have NOT been verified on an original cabinet.
// No interrupt event sources exist by default.
#pragma once
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp_model2c {
class PartialIRQRegisters final {
public:
    static constexpr std::uint32_t REQUEST = 0x00e80000u;
    static constexpr std::uint32_t ENABLE = 0x00e80004u;
    static constexpr unsigned ENABLE_DELAY_CYCLES = 2u;

    std::uint32_t request() const { return request_; }
    std::uint32_t enable() const { return enable_; }
    unsigned pending_enable_cycles() const { return pending_cycles_; }

    // Retention-mask ACK: writing zero clears all request bits.
    void acknowledge(std::uint32_t retained_bits) {
        request_ &= retained_bits;
    }

    // The public Model 2C device mapping describes a two-CPU-cycle delay.
    // No cycles advance spontaneously without a scheduler.
    void request_enable_update(std::uint32_t value) {
        queued_enable_ = value;
        pending_cycles_ = ENABLE_DELAY_CYCLES;
    }
    void advance_cpu_cycles(unsigned count) {
        if (!pending_cycles_) return;
        if (count < pending_cycles_) {
            pending_cycles_ -= count;
            return;
        }
        enable_ = queued_enable_;
        pending_cycles_ = 0u;
    }

    // Synthetic test hook. NOT wired to real Model 2C interrupt sources.
    void inject_enabled_source_for_test(unsigned bit) {
        if (bit >= 12u)
            throw std::out_of_range("Unidentified Model 2C IRQ source bit");
        const auto mask = std::uint32_t(1u) << bit;
        if (enable_ & mask) request_ |= mask;
    }

    // Observed IRQ0..3 line groups. Does not enter a CPU interrupt frame.
    bool line_level(unsigned pin) const {
        if (pin >= 4u) throw std::out_of_range("i960 has four IRQ pins");
        static constexpr std::uint32_t PIN_MASKS[4] = {
            0x0001u, 0x0002u, 0x03fcu, 0x0c00u
        };
        return (request_ & PIN_MASKS[pin]) != 0u;
    }
private:
    std::uint32_t request_ = 0;
    std::uint32_t enable_ = 0;
    std::uint32_t queued_enable_ = 0;
    unsigned pending_cycles_ = 0;
};
} // namespace arcaderecomp_model2c
