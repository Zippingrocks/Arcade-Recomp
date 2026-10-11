// ArcadeRecomp: provisional, opt-in Model 2C countdown timers.
//
// Public Model 2C mapping identifies four 32-bit timer registers at
// 0x00F00000..0x00F0000F, driven by 25 MHz timer ticks. These are
// architecture RESEARCH observations, not independently captured
// original-cabinet reset, retrigger, IRQ timing or readback behavior.
// Never advance time implicitly on host wall time, CPU calls, or bus polls.
#pragma once
#include "model2c_irq_registers.hpp"
#include <array>
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp_model2c {

class PartialModel2CTimers final {
public:
    static constexpr std::uint32_t BASE = 0x00f00000u;
    static constexpr unsigned CHANNELS = 4u;
    static constexpr std::uint32_t TICKS_PER_SECOND = 25000000u;

    struct Unverified : std::logic_error {
        using std::logic_error::logic_error;
    };

    // Reset state and post-expiration register readback remain unknown.
    // Do not return zero or 0x000fffff unless independently corroborated.
    struct Channel {
        bool running = false;
        bool readback_known = false;
        std::uint32_t remaining = 0u;
        std::uint64_t expirations = 0u;
    };

    static unsigned index(std::uint32_t address) {
        if (address < BASE || address - BASE >= CHANNELS * 4u ||
            ((address - BASE) & 3u) != 0u)
            throw Unverified("invalid timer register address");
        return (address - BASE) / 4u;
    }

    std::uint32_t read(std::uint32_t address) const {
        const auto& channel = state_[index(address)];
        if (!channel.readback_known)
            throw Unverified("timer reset/expired value not independently verified");
        return channel.remaining;
    }

    void write(std::uint32_t address, std::uint32_t ticks) {
        auto& channel = state_[index(address)];
        // Zero-load behavior is unknown; never manufacture an immediate
        // IRQ or guess whether this disables a channel.
        if (ticks == 0u)
            throw Unverified("zero timer load behavior not verified");
        channel.running = true;
        channel.readback_known = true;
        channel.remaining = ticks;
    }

    // Caller supplies a REAL externally established number of 25-MHz
    // timer ticks. A synthetic fixture may supply them for tests, but
    // without an original clock source this is not physical timing.
    void advance_external_ticks(std::uint64_t ticks,
                                PartialIRQRegisters& irq,
                                bool route_partial_irq) {
        if (ticks == 0u) return;
        for (unsigned i = 0u; i < CHANNELS; ++i) {
            auto& channel = state_[i];
            if (!channel.running) continue;
            if (ticks < channel.remaining) {
                channel.remaining -= static_cast<std::uint32_t>(ticks);
                continue;
            }
            if (channel.expirations == UINT64_MAX)
                throw std::overflow_error("timer expiration counter exhausted");
            channel.running = false;
            channel.readback_known = false;
            channel.remaining = 0u; // internal sentinel, NEVER CPU readback
            ++channel.expirations;
            if (route_partial_irq)
                irq.observe_timer_expiration(i);
        }
    }

    const Channel& channel(unsigned index_value) const {
        if (index_value >= CHANNELS)
            throw std::out_of_range("timer channel outside 0..3");
        return state_[index_value];
    }

private:
    std::array<Channel, CHANNELS> state_{};
};

} // namespace arcaderecomp_model2c
