// Original ArcadeRecomp functional FLEX 8000 configuration input stage.
// Specification: Altera AN33, Configuring FLEX 8000 Devices, June 2000 v3.03,
// printed pp. 45-50, 54-55, 64-66. See docs/FLEX8000_CONFIGURATION_INGRESS.md.
//
// This stage starts ONLY after the enclosing configuration controller has
// established an enabled loading window. It is not that controller: no
// nCONFIG/nSTATUS reset timing, CONF_DONE, CRC checker, initialization clock,
// routing, or user circuit is implemented. It is NOT connected to Sega MMIO.
// Clock events, not guessed wall-clock delays, advance serialization.
#pragma once
#include <cstdint>
#include <optional>
#include <stdexcept>

namespace arcaderecomp_flex8000 {

enum class LoadingMode { passive_serial, passive_parallel_sync,
                         passive_parallel_async };

struct ParallelPins {
    std::uint8_t data = 0;
    bool cs = false;
    bool ncs = true;
    bool nws = true;
    bool nrs = true;
};

// Only driven bits are meaningful. In particular, an undriven DATA7 is NOT 0.
struct BusDrive {
    std::uint8_t mask = 0;
    std::uint8_t value = 0;
};

class ConfigIngress final {
public:
    explicit ConfigIngress(LoadingMode mode) : mode_(mode) {
        if (mode != LoadingMode::passive_serial &&
            mode != LoadingMode::passive_parallel_sync &&
            mode != LoadingMode::passive_parallel_async)
            throw std::invalid_argument("unsupported FLEX configuration input mode");
    }

    // Explicit integration contract: the parent has completed reset/preparation
    // and the relevant clock is low, with inactive parallel read/write strobes.
    // This does not infer that contract from a Sega command or elapsed time.
    void begin_loading() {
        if (active_) throw std::logic_error("loading window already active");
        pins_ = ParallelPins{};
        clock_high_ = false;
        bits_left_ = 0;
        shift_ = 0;
        active_ = true;
    }

    // Parent reset/error may abort even a partial byte. This does not roll back
    // already delivered bits: the parent must discard/reset its own decoder too.
    void abort_loading() noexcept {
        active_ = false;
        bits_left_ = 0;
        shift_ = 0;
        clock_high_ = false;
        pins_ = ParallelPins{};
    }
    bool loading() const noexcept { return active_; }
    unsigned pending_bits() const noexcept { return bits_left_; }

    // PS: sample DATA0 on each rising DCLK edge. PPS: latch a parallel byte on
    // the first rising edge, serialize on eight falling edges, then latch on
    // the next (ninth) rising edge. Repeated levels are not new clock edges.
    // Return an abstract decoder-input bit, not a claim of an extra output pin.
    std::optional<bool> drive_dclk(bool high, std::uint8_t data) {
        require_active();
        if (mode_ == LoadingMode::passive_parallel_async)
            throw std::logic_error("PPA serialization uses the internal clock, not host DCLK");
        if (high == clock_high_) return std::nullopt;
        clock_high_ = high;
        if (mode_ == LoadingMode::passive_serial)
            return high ? std::optional<bool>((data & 1u) != 0) : std::nullopt;
        if (high) {
            if (!bits_left_) { shift_ = data; bits_left_ = 8; }
            return std::nullopt;
        }
        return shift_one();
    }

    // PPA uses CS=1,nCS=0 and captures DATA[7:0] on the rising nWS edge.
    // Calls describe settled digital levels; setup/hold times and propagation
    // delays are NOT simulated. Invalid transaction sequences are diagnostic
    // refusals, not invented silicon error-pin behavior. Reject before mutation.
    void drive_parallel(ParallelPins next) {
        require_ppa();
        const bool selected = next.cs && !next.ncs;
        const bool rising = !pins_.nws && next.nws;
        const bool falling = pins_.nws && !next.nws;
        if (selected) {
            if (!next.nrs && !next.nws)
                throw std::logic_error("parallel read and write strobes overlap");
            if ((rising || falling) && (!pins_.nrs || !next.nrs))
                throw std::logic_error("parallel read/write turnaround has no intervening inactive phase");
            if ((rising || falling) && bits_left_)
                throw std::logic_error("parallel write attempted while serializer busy");
            if (rising && !(pins_.cs && !pins_.ncs))
                throw std::logic_error("chip select changed at the write sampling edge");
        }
        if (selected && rising) { shift_ = next.data; bits_left_ = 8; }
        pins_ = next;
    }

    // PPA: one explicit falling edge of its INTERNAL serialization clock.
    // Busy is released on the eighth such edge, never by a status read.
    std::optional<bool> internal_falling_edge() {
        require_ppa();
        return shift_one();
    }

    // RDYnBUSY belongs only to PPA loading. Its reset/user-mode value and PS/PPS
    // behavior are outside this component, represented as unknown/unavailable.
    std::optional<bool> ready_nbusy() const noexcept {
        if (!active_ || mode_ != LoadingMode::passive_parallel_async)
            return std::nullopt;
        return bits_left_ == 0;
    }
    BusDrive data_bus_drive() const noexcept {
        if (!active_ || mode_ != LoadingMode::passive_parallel_async ||
            !pins_.cs || pins_.ncs || pins_.nrs || !pins_.nws)
            return {};
        return {0x80u, static_cast<std::uint8_t>(bits_left_ == 0 ? 0x80u : 0u)};
    }

private:
    const LoadingMode mode_;
    bool active_ = false, clock_high_ = false;
    ParallelPins pins_{};
    std::uint8_t shift_ = 0;
    unsigned bits_left_ = 0;
    void require_active() const {
        if (!active_) throw std::logic_error("configuration loading window not established");
    }
    void require_ppa() const {
        require_active();
        if (mode_ != LoadingMode::passive_parallel_async)
            throw std::logic_error("parallel asynchronous operation in another loading mode");
    }
    std::optional<bool> shift_one() noexcept {
        if (!bits_left_) return std::nullopt;
        const bool bit = (shift_ & 1u) != 0;
        shift_ = static_cast<std::uint8_t>(shift_ >> 1u);
        --bits_left_;
        return bit;
    }
};
} // namespace arcaderecomp_flex8000
