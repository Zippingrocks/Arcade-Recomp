// Original ArcadeRecomp event-backed serial buffer model.
// Register identities: documented 315-5649 TX1/TX2, RX1/RX2 and status.
// This is NOT a verified Sega baud-rate, gun-sensor or channel-1 responder.
// Events and initial idle observation MUST come from an explicit provider.
// No status-ready constants, invented responses or implicit clock advance.
#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp_model2c {
class SerialEventState final {
public:
    struct TX { std::uint64_t token; unsigned channel; std::uint8_t byte; };
    bool initialized() const { return initialized_; }
    std::uint64_t tick() const { return tick_; }

    // A caller-observed idle snapshot, NOT an assumed chip power-on value.
    // Only an explicit initial idle snapshot is supported by this model.
    void observe_idle(std::uint64_t tick) {
        if (initialized_) throw std::logic_error("serial already initialized; use a new capture session");
        tick_=tick; initialized_=true;
    }
    void advance_to(std::uint64_t tick) {
        require(); check_time(tick); tick_=tick;
    }
    TX transmit(unsigned channel, std::uint8_t byte) {
        require(); auto& c=get(channel);
        if (c.tx_full) throw std::logic_error("unverified TX-full overwrite behavior");
        if (next_token_ == UINT64_MAX) throw std::overflow_error("serial event token exhausted");
        c.tx_full=true; c.token=++next_token_;
        return {c.token,channel,byte};
    }
    void complete_transmit(unsigned channel, std::uint64_t token, std::uint64_t tick) {
        require(); auto& c=get(channel); check_time(tick);
        if (!c.tx_full || c.token!=token) throw std::logic_error("stale or unmatched TX completion");
        c.tx_full=false; tick_=tick;
    }
    void receive(unsigned channel, std::uint8_t byte, std::uint64_t tick) {
        require(); auto& c=get(channel); check_time(tick);
        // Actual overrun policy is not established: stop, do not lose bytes.
        if (c.rx_full) throw std::logic_error("unverified RX-overrun behavior");
        c.rx_byte=byte; c.rx_full=true; tick_=tick;
    }
    void observe_error_bits(std::uint8_t high_nibble, std::uint64_t tick) {
        require(); check_time(tick);
        if (high_nibble & 0x0fu) throw std::invalid_argument("errors cannot impersonate ready flags");
        errors_=high_nibble; tick_=tick;
    }
    std::uint8_t status() const {
        require();
        return errors_ | (channels_[0].tx_full?1u:0u) | (channels_[1].tx_full?2u:0u)
            | (channels_[0].rx_full?4u:0u) | (channels_[1].rx_full?8u:0u);
    }
    std::uint8_t read_receive(unsigned channel) {
        require(); auto& c=get(channel);
        if(!c.rx_full)throw std::logic_error("serial receive buffer empty; no fabricated byte");
        const auto byte=c.rx_byte; c.rx_full=false; return byte;
    }
    std::uint64_t outstanding_token(unsigned channel) const {
        require(); const auto& c=get(channel);
        if(!c.tx_full)throw std::logic_error("no outstanding serial TX");
        return c.token;
    }
private:
    struct Channel { bool tx_full=false, rx_full=false; std::uint8_t rx_byte=0; std::uint64_t token=0; };
    std::array<Channel,2> channels_{};
    bool initialized_=false;
    std::uint8_t errors_=0;
    std::uint64_t tick_=0,next_token_=0;
    void require() const {
        if(!initialized_)throw std::logic_error("serial initial state has not been observed");
    }
    void check_time(std::uint64_t tick) const {
        if(tick<tick_)throw std::logic_error("serial capture time moved backwards");
    }
    Channel& get(unsigned c) {
        if(c<1||c>2)throw std::out_of_range("serial channel must be 1 or 2");
        return channels_[c-1];
    }
    const Channel& get(unsigned c) const {
        if(c<1||c>2)throw std::out_of_range("serial channel must be 1 or 2");
        return channels_[c-1];
    }
};
} // namespace arcaderecomp_model2c
