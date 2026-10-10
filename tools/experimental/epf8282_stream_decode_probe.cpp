// Original diagnostic, not a Sega runtime: compare all three synthetic loading
// paths + incremental record decoding against caller-supplied expected SOF data.
// No payload bytes leave stdout. A full profile match does NOT arm startup.
#include "epf8282_stream_decoder.hpp"
#include "flex8000_config_ingress.hpp"
#include "flex8000_startup.hpp"
#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
using namespace arcaderecomp_flex8000;
namespace {
std::vector<std::uint8_t> read_exact(const char* path, std::size_t count) {
    std::ifstream f(path, std::ios::binary|std::ios::ate);
    if (!f || f.tellg() != static_cast<std::streamoff>(count))
        throw std::runtime_error("incorrect input file size");
    f.seekg(0);
    std::vector<std::uint8_t> data((std::istreambuf_iterator<char>(f)), {});
    if (f.bad() || data.size()!=count) throw std::runtime_error("incomplete file read");
    return data;
}
}
int main(int argc, char** argv) {
    if (argc!=3) {
        std::cerr << "Usage: stream_decode_probe PRIVATE_STREAM PRIVATE_EXPECTED_PACKED_DATA\n";
        return 2;
    }
    try {
        const auto stream = read_exact(argv[1], EPF8282StreamDecoder::kStreamBits/8);
        const auto expected = read_exact(argv[2], EPF8282StreamDecoder::kPackedBytes);
        StreamEnvelope envelope{};
        std::copy_n(stream.begin(), envelope.prefix.size(), envelope.prefix.begin());
        envelope.suffix = stream.back();
        const LoadingMode modes[] = {LoadingMode::passive_serial,
            LoadingMode::passive_parallel_sync, LoadingMode::passive_parallel_async};
        const char* names[] = {"PS", "PPS", "PPA"};
        std::size_t bits[3]{}, records[3]{};
        for (unsigned m=0; m<3; ++m) {
            ConfigIngress ingress(modes[m]); ingress.begin_loading();
            EPF8282StreamDecoder decoder(envelope); decoder.begin();
            // Explicit synthetic options; startup must remain unestablished.
            ConfigStartup startup({StartupClock::internal_oscillator,
                                   StartupClock::internal_oscillator, StartupTimeout::enabled});
            ParallelPins pins{}; pins.cs=true; pins.ncs=false;
            auto receive = [&](std::optional<bool> sample) {
                if (sample && !decoder.push_bit(*sample))
                    throw std::runtime_error("stream profile mismatch at bit " +
                                             std::to_string(decoder.failure_bit()));
            };
            for (auto byte: stream) {
                if (m==2) {
                    pins.data=byte; ingress.drive_parallel(pins);
                    pins.nws=false; ingress.drive_parallel(pins);
                    pins.nws=true; ingress.drive_parallel(pins);
                }
                for (unsigned b=0; b<8; ++b) {
                    if (m<2) {
                        const auto data=static_cast<std::uint8_t>(m==0 ? byte>>b :
                                                               (b==0 ? byte : byte^0xffu));
                        receive(ingress.drive_dclk(true,data));
                        receive(ingress.drive_dclk(true,data)); // no duplicate edge
                        receive(ingress.drive_dclk(false,static_cast<std::uint8_t>(data^0xffu)));
                    } else {
                        pins.nrs=false; ingress.drive_parallel(pins);
                        const auto before=decoder.bits_seen();
                        for (unsigned poll=0;poll<3;++poll) {
                            const auto drive=ingress.data_bus_drive();
                            if (drive.mask!=0x80u || drive.value!=0 || decoder.bits_seen()!=before)
                                throw std::runtime_error("status poll modified data or readiness");
                        }
                        pins.nrs=true; ingress.drive_parallel(pins);
                        receive(ingress.internal_falling_edge());
                    }
                }
            }
            if (ingress.pending_bits() || decoder.state()!=StreamState::receiving)
                throw std::runtime_error("input completion state mismatch");
            bool unavailable=false;
            try { (void)decoder.packed_data(); }
            catch (const std::logic_error&) { unavailable=true; }
            if (!unavailable || !decoder.finish()) throw std::runtime_error("invalid sealing boundary");
            const auto data=decoder.packed_data();
            if (!std::equal(data.begin(),data.end(),expected.begin(),expected.end()))
                throw std::runtime_error("native data differs from independent Python mapping");
            if (startup.phase()!=StartupPhase::unestablished ||
                startup.conf_done_drive()!=DrainDrive::unknown ||
                startup.nstatus_drive()!=DrainDrive::unknown)
                throw std::runtime_error("profile success manufactured startup acceptance");
            bits[m]=decoder.bits_seen(); records[m]=decoder.records_validated();
        }
        std::cout << "{\"schema_version\":1,\"synthetic_pin_stimulus\":true,"
                     "\"opaque_envelope_supplied_from_input\":true,"
                     "\"silicon_configuration_accepted\":false,\"startup_armed\":false,"
                     "\"sega_serial_connected\":false,\"data_bits\":"
                  << EPF8282StreamDecoder::kDataBits << ",\"modes\":[";
        for (unsigned i=0;i<3;++i) {
            if (i) std::cout << ',';
            std::cout << "{\"mode\":\"" << names[i] << "\",\"input_bits\":" << bits[i]
                      << ",\"records_validated\":" << records[i]
                      << ",\"matches_python_data\":true}";
        }
        std::cout << "]}\n";
    } catch (const std::exception& e) {
        std::cerr << "Stream decoding probe failed: " << e.what() << '\n'; return 2;
    }
    return 0;
}
