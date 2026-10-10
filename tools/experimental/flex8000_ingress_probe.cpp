// Original diagnostic: feed caller-supplied bytes through three deliberately
// selected FPGA loading modes. Host pin/clock stimulus is SYNTHETIC. This
// proves neither Sega's mode selection nor serial transport wiring. No bytes
// are emitted, and no CONF_DONE/user-mode success is reported.
#include "flex8000_config_ingress.hpp"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>

using namespace arcaderecomp_flex8000;

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: ingress_probe PRIVATE_STREAM (1..65536 bytes)\n";
        return 2;
    }
    try {
        std::ifstream in(argv[1], std::ios::binary | std::ios::ate);
        if (!in || in.tellg() <= 0 || in.tellg() > 65536)
            throw std::runtime_error("invalid input size");
        in.seekg(0);
        std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)), {});
        if (bytes.empty() || bytes.size() > 65536 || in.bad())
            throw std::runtime_error("failed stream read");
        const LoadingMode modes[] = {LoadingMode::passive_serial,
            LoadingMode::passive_parallel_sync, LoadingMode::passive_parallel_async};
        const char* names[] = {"PS", "PPS", "PPA"};
        std::size_t counts[3]{}, busy_observations = 0, readbacks = 0;
        for (unsigned m = 0; m < 3; ++m) {
            ConfigIngress receiver(modes[m]); receiver.begin_loading();
            ParallelPins pins{}; pins.cs = true; pins.ncs = false;
            auto accept = [&](std::optional<bool> result) {
                if (!result) return;
                const auto bit = counts[m]++;
                if (bit >= bytes.size()*8 ||
                    *result != (((bytes[bit/8] >> (bit%8)) & 1u) != 0))
                    throw std::runtime_error("serialized data mismatch");
            };
            for (auto byte : bytes) {
                if (m == 2) {
                    pins.data = byte; receiver.drive_parallel(pins);
                    pins.nws = false; receiver.drive_parallel(pins);
                    pins.nws = true; receiver.drive_parallel(pins);
                }
                for (unsigned bit = 0; bit < 8; ++bit) {
                    if (m < 2) {
                        const auto data = static_cast<std::uint8_t>(m == 0 ? byte >> bit :
                            (bit == 0 ? byte : byte ^ 0xffu));
                        accept(receiver.drive_dclk(true, data));
                        accept(receiver.drive_dclk(true, data)); // same level: no second edge
                        accept(receiver.drive_dclk(false, static_cast<std::uint8_t>(data ^ 0xffu)));
                    } else {
                        if (receiver.ready_nbusy() != std::optional<bool>(false))
                            throw std::runtime_error("premature ready");
                        ++busy_observations;
                        pins.nrs = false; receiver.drive_parallel(pins);
                        const auto before = receiver.pending_bits();
                        for (unsigned poll = 0; poll < 3; ++poll) {
                            const auto drive = receiver.data_bus_drive();
                            if (drive.mask != 0x80u || drive.value != 0u ||
                                receiver.pending_bits() != before)
                                throw std::runtime_error("poll changed busy state or fabricated bus bits");
                            ++readbacks;
                        }
                        pins.nrs = true; receiver.drive_parallel(pins);
                        accept(receiver.internal_falling_edge());
                    }
                }
                if (m == 2 && receiver.ready_nbusy() != std::optional<bool>(true))
                    throw std::runtime_error("ready missing after eight edges");
            }
            if (counts[m] != bytes.size()*8 || receiver.pending_bits())
                throw std::runtime_error("incomplete input-stage stream");
            receiver.abort_loading();
            if (receiver.ready_nbusy() || receiver.data_bus_drive().mask)
                throw std::runtime_error("inactive outputs became claimed hardware values");
        }
        // Emit a single complete result only after all modes pass.
        std::cout << "{\"schema_version\":1,\"synthetic_pin_stimulus\":true,"
                  << "\"board_mode_identified\":false,\"configuration_completed\":false,"
                  << "\"stream_bytes\":" << bytes.size() << ",\"modes\":[";
        for (unsigned m = 0; m < 3; ++m) {
            if (m) std::cout << ',';
            std::cout << "{\"mode\":\"" << names[m] << "\",\"accepted_bits\":"
                      << counts[m] << ",\"matches_input_lsb_first\":true}";
        }
        std::cout << "],\"ppa_busy_observations\":" << busy_observations
                  << ",\"ppa_masked_status_reads\":" << readbacks << "}\n";
    } catch (const std::exception& error) {
        std::cerr << "Ingress probe failed: " << error.what() << '\n'; return 2;
    }
    return 0;
}
