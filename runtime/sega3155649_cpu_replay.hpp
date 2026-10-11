// Strict opt-in replay of an externally supplied CPU-side 315-5649 trace.
// NOT verified cabinet hardware, UART timing, or an authentic receiver.
// Read results can only come from an explicit, fully validated input row.
#pragma once
#include "sega3155649_serial.hpp"

#include <cstdint>
#include <istream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace arcaderecomp_model2c {

class SerialCPUReplay final {
public:
    static constexpr std::size_t kMaxRecords = 100000u;
    struct Record {
        std::uint32_t address;
        std::uint8_t value;
        bool write;
    };

    // Text is a *claim* from an external capture producer. Complete=yes and
    // dropped=0 do not authenticate its origin or validate an arcade device.
    static SerialCPUReplay parse(std::istream& input) {
        std::string line;
        if (!next_line(input, line) || line != "arcade-serial-cpu-replay-v1")
            throw std::invalid_argument("incorrect serial replay version");
        if (!next_line(input, line))
            throw std::invalid_argument("missing replay completeness header");
        std::istringstream header(line);
        std::string count, dropped, complete, provenance, extra;
        if (!(header >> count >> dropped >> complete >> provenance) ||
            (header >> extra) ||
            count.rfind("count=", 0) != 0 ||
            dropped != "dropped=0" || complete != "complete=yes" ||
            (provenance != "provenance=synthetic" &&
             provenance != "provenance=external_unverified"))
            throw std::invalid_argument("incomplete or unsupported serial replay header");
        const auto count_value = decimal(count.substr(6));
        if (count_value == 0u || count_value > kMaxRecords)
            throw std::invalid_argument("serial replay length outside safety cap");
        SerialCPUReplay replay;
        replay.records_.reserve(static_cast<std::size_t>(count_value));
        for (std::size_t i = 0; i < count_value; ++i) {
            if (!next_line(input, line))
                throw std::invalid_argument("serial replay missing event");
            std::istringstream row(line);
            std::string seq, dir, addr, value;
            if (!(row >> seq >> dir >> addr >> value) || (row >> extra) ||
                decimal(seq) != i + 1u ||
                (dir != "W" && dir != "R"))
                throw std::invalid_argument("serial replay event ordinal or shape invalid");
            const auto address = hex_address(addr);
            const auto byte = hex_byte(value);
            const bool write = dir == "W";
            if (write ? (address != IO3155649::BASE + 2u * IO3155649::SERIAL_TX1 &&
                         address != IO3155649::BASE + 2u * IO3155649::SERIAL_TX2)
                      : (address != IO3155649::BASE + 2u * IO3155649::SERIAL_RX1 &&
                         address != IO3155649::BASE + 2u * IO3155649::SERIAL_RX2 &&
                         address != IO3155649::BASE + 2u * IO3155649::SERIAL_STATUS))
                throw std::invalid_argument("serial replay address/direction invalid");
            replay.records_.push_back({address, byte, write});
        }
        if (!next_line(input, line) || line != "END" || next_line(input, line))
            throw std::invalid_argument("serial replay lacks exact terminal marker");
        return replay;
    }

    void bind(IO3155649& io) {
        if (bound_)
            throw std::logic_error("serial replay already attached");
        io.set_serial_tx_observer([this](std::uint8_t value, unsigned channel) {
            if (channel != 1u && channel != 2u)
                throw std::logic_error("invalid serial transmit channel");
            consume(IO3155649::BASE + 2u *
                    (channel == 1u ? IO3155649::SERIAL_TX1 : IO3155649::SERIAL_TX2),
                    true, value);
        });
        io.set_serial_status_source([this]() -> std::uint8_t {
            return consume(IO3155649::BASE + 2u * IO3155649::SERIAL_STATUS,
                           false, 0u);
        });
        io.set_serial_rx([this](std::uint8_t, unsigned channel) -> std::uint8_t {
            if (channel != 1u && channel != 2u)
                throw std::logic_error("invalid serial receive channel");
            return consume(IO3155649::BASE + 2u *
                           (channel == 1u ? IO3155649::SERIAL_RX1 : IO3155649::SERIAL_RX2),
                           false, 0u);
        });
        bound_ = true;
    }

    std::size_t consumed() const { return next_; }
    std::size_t total() const { return records_.size(); }
    std::size_t remaining() const { return records_.size() - next_; }
    bool exhausted() const { return next_ == records_.size(); }

private:
    std::vector<Record> records_{};
    std::size_t next_ = 0u;
    bool bound_ = false;

    std::uint8_t consume(std::uint32_t address, bool write, std::uint8_t byte) {
        if (next_ >= records_.size())
            throw std::logic_error("serial replay exhausted; unknown CPU bus response");
        const auto& expected = records_[next_];
        if (expected.address != address || expected.write != write ||
            (write && expected.value != byte))
            throw std::logic_error("serial replay diverged; no substituted response");
        // Advance only on an exact request. TX callbacks are invoked before
        // IO3155649 commits, and its event-backed backend must not be mixed.
        ++next_;
        return expected.value;
    }

    static bool next_line(std::istream& input, std::string& line) {
        if (!std::getline(input, line)) return false;
        if (line.size() > 128u) throw std::invalid_argument("serial replay line too long");
        if (!line.empty() && line.back() == '\r') line.pop_back();
        return true;
    }
    static std::uint64_t decimal(const std::string& value) {
        if (value.empty() || value.size() > 20u)
            throw std::invalid_argument("malformed serial replay decimal");
        std::uint64_t result = 0u;
        for (char c : value) {
            if (c < '0' || c > '9' ||
                result > (UINT64_MAX - static_cast<unsigned>(c - '0')) / 10u)
                throw std::invalid_argument("malformed serial replay decimal");
            result = result * 10u + static_cast<unsigned>(c - '0');
        }
        return result;
    }
    static unsigned digit(char c) {
        if (c >= '0' && c <= '9') return static_cast<unsigned>(c - '0');
        if (c >= 'a' && c <= 'f') return static_cast<unsigned>(c - 'a' + 10);
        if (c >= 'A' && c <= 'F') return static_cast<unsigned>(c - 'A' + 10);
        throw std::invalid_argument("malformed serial replay hexadecimal");
    }
    static std::uint32_t hex_address(const std::string& value) {
        if (value.size() != 10u || value.substr(0, 2) != "0x")
            throw std::invalid_argument("serial replay address must be 8 hex digits");
        std::uint32_t n = 0u;
        for (std::size_t i = 2; i < value.size(); ++i)
            n = (n << 4u) | digit(value[i]);
        return n;
    }
    static std::uint8_t hex_byte(const std::string& value) {
        if (value.size() != 4u || value.substr(0, 2) != "0x")
            throw std::invalid_argument("serial replay value must be 2 hex digits");
        return static_cast<std::uint8_t>((digit(value[2]) << 4u) | digit(value[3]));
    }
};

} // namespace arcaderecomp_model2c
