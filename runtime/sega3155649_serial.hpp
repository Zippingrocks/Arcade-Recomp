// ArcadeRecomp: independently authored partial Sega 315-5649 I/O interface.
//
// Source of *register identities* (not implementation code):
//   Sega's Model 2C CPU memory map, Sega ST-V board service documentation,
//   and observed original House of the Dead i960 serial initialization.
// See docs/SEGA_IO3155649.md for each claim and its confidence level.
//
// Intentional constraints:
// - only documented 8-bit serial TX1/TX2 writes and explicitly injected
//   RX1/RX2 reads are presently supported;
// - no fake status (the observed "always ready" emulator shortcut is rejected);
// - no speculative gun coordinates, trigger state, calibration, port defaults
//   or other undocumented peripheral responses;
// - unsupported registers/lane widths throw before mutating state.
//
// This isn't a full chip, a lightgun emulator, or a complete Model 2C runtime.
#pragma once
#include "sega3155649_events.hpp"

#include <cstdint>
#include <functional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace arcaderecomp_model2c {

class IO3155649 final {
public:
    // 32-bit i960 byte-lane wiring: the 8-bit I/O chip occupies the
    // low and third byte lane of successive 32-bit words (0x00ff00ff).
    // Each device register is thus located at (2 * register_number).
    static constexpr std::uint32_t BASE = 0x01c00000u;
    static constexpr unsigned SERIAL_TX1 = 0x09;
    static constexpr unsigned SERIAL_TX2 = 0x0a;
    static constexpr unsigned SERIAL_RX1 = 0x0b;
    static constexpr unsigned SERIAL_RX2 = 0x0c;
    static constexpr unsigned SERIAL_STATUS = 0x0d;

    struct TXEvent {
        unsigned channel;
        std::uint8_t byte;
        std::uint64_t sequence;
        std::uint32_t address;
    };

    struct Unsupported : std::runtime_error {
        std::uint32_t address;
        bool write;
        Unsupported(std::uint32_t addr, bool wr, const char* reason)
            : std::runtime_error(std::string(wr ? "315-5649 write: " : "315-5649 read: ") + reason),
              address(addr), write(wr) {}
    };

    using SerialRead = std::function<std::uint8_t(std::uint8_t last_mux, unsigned channel)>;
    using SerialWrite = std::function<void(std::uint8_t value, unsigned channel)>;
    using StatusRead = std::function<std::uint8_t()>;

    // RX needs a real hardware trace, explicit user/controller input, or a
    // trusted deterministic test fixture. By default it refuses to respond.
    // Mutually exclusive backend: observed buffer events OR legacy providers.
    // Merely selecting this backend does NOT declare a power-on state.
    SerialEventState& use_observed_events() {
        if (serial_rx_ || status_source_ || !events_.empty())
            throw std::logic_error("cannot mix serial providers or change backend midstream");
        observed_events_enabled_ = true;
        return observed_events_;
    }
    SerialEventState& observed_events() {
        if (!observed_events_enabled_) throw std::logic_error("event backend disabled");
        return observed_events_;
    }
    void set_serial_rx(SerialRead callback) {
        if (observed_events_enabled_) throw std::logic_error("event backend owns serial receive data");
        serial_rx_ = std::move(callback);
    }
    void set_serial_tx_observer(SerialWrite callback) { serial_tx_ = std::move(callback); }

    // Status is externally supplied by a hardware link or an explicitly
    // labeled test fixture. Never fabricate the historically common 0x0c
    // "always receive-ready" value.
    void set_serial_status_source(StatusRead callback) {
        if (observed_events_enabled_) throw std::logic_error("event backend owns status");
        status_source_ = std::move(callback);
    }

    void write_bus_byte(std::uint32_t absolute_address, std::uint8_t value) {
        unsigned reg = resolve_register(absolute_address, true);
        if (reg != SERIAL_TX1 && reg != SERIAL_TX2)
            throw Unsupported(absolute_address, true, "device register write not implemented");
        const unsigned channel = (reg == SERIAL_TX1) ? 1u : 2u;
        // HOTD1 uses channel 2 for a lightgun mux command. We preserve the
        // transmitted byte; its detailed effect is external to this chip.
        if (observed_events_enabled_) {
            try { observed_events_.transmit(channel, value); }
            catch (const std::logic_error& e) { throw Unsupported(absolute_address, true, e.what()); }
        }
        last_tx_[channel - 1u] = value;
        events_.push_back({channel, value, ++sequence_, absolute_address});
        if (serial_tx_) serial_tx_(value, channel);
    }

    std::uint8_t read_bus_byte(std::uint32_t absolute_address) const {
        unsigned reg = resolve_register(absolute_address, false);
        if (reg == SERIAL_STATUS) {
            if (observed_events_enabled_) {
                try { return observed_events_.status(); }
                catch (const std::logic_error& e) { throw Unsupported(absolute_address, false, e.what()); }
            }
            if (!status_source_)
                throw Unsupported(absolute_address, false, "serial status source not configured");
            return status_source_();
        }
        if (reg != SERIAL_RX1 && reg != SERIAL_RX2)
            throw Unsupported(absolute_address, false, "device status/port read not implemented");
        const unsigned channel = (reg == SERIAL_RX1) ? 1u : 2u;
        if (observed_events_enabled_) {
            try { return observed_events_.read_receive(channel); }
            catch (const std::logic_error& e) { throw Unsupported(absolute_address, false, e.what()); }
        }
        if (!serial_rx_)
            throw Unsupported(absolute_address, false, "serial receive source not configured");
        // Channel 2 mux selection was provided by its own TX last byte.
        // Channel 1 likewise owns independent selection state.
        return serial_rx_(last_tx_[channel - 1u], channel);
    }

    const std::vector<TXEvent>& transmissions() const { return events_; }
    std::uint8_t last_tx(unsigned channel) const {
        if (channel < 1u || channel > 2u)
            throw std::out_of_range("315-5649 serial channel must be 1 or 2");
        return last_tx_[channel - 1u];
    }
    std::uint64_t transaction_count() const { return sequence_; }

private:
    std::uint8_t last_tx_[2]{0u, 0u};
    std::uint64_t sequence_ = 0;
    std::vector<TXEvent> events_;
    SerialRead serial_rx_{};
    SerialWrite serial_tx_{};
    StatusRead status_source_{};
    bool observed_events_enabled_ = false;
    mutable SerialEventState observed_events_{}; // Reading RX consumes a byte.

    static unsigned resolve_register(std::uint32_t absolute_address, bool write) {
        if (absolute_address < BASE || absolute_address >= BASE + 0x20u)
            throw Unsupported(absolute_address, write, "outside documented chip aperture");
        const std::uint32_t offset = absolute_address - BASE;
        if (offset & 1u)
            throw Unsupported(absolute_address, write, "unsupported 8-bit CPU bus lane");
        return static_cast<unsigned>(offset >> 1);
    }
};

} // namespace arcaderecomp_model2c
