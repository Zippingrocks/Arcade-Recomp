// ARCADERECOMP EXPERIMENTAL DIAGNOSTIC — NOT ACCURATE SEGA SERIAL HARDWARE.
//
// Uses the actual user-supplied original HOTD1 i960 program ONLY if the user
// locally generated it from their own ROM. Serial read and status bytes below
// are intentionally FICTIONAL and can NEVER establish arcade boot fidelity.
// This program must not become a game release runtime.
//
// It exercises the native i960 IAC-0x93 transition, then stops at the next
// unmapped Model 2C address. No Sega ROM bytes or game assets are embedded.
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

#include "model2c_bus.hpp"
#include "hotd1_i960.cpp"

static std::uint32_t le32(const std::vector<std::uint8_t>& image,
                          std::size_t offset) {
    if (offset > image.size() || image.size() - offset < 4u)
        throw std::runtime_error("Boot or PRCB pointer lies outside ROM");
    return std::uint32_t(image[offset]) |
           std::uint32_t(image[offset + 1]) << 8u |
           std::uint32_t(image[offset + 2]) << 16u |
           std::uint32_t(image[offset + 3]) << 24u;
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "USAGE: hotd1_fake_serial_reinit PRIVATE/maincpu.bin\n";
        return 2;
    }
    std::cerr << "WARNING: ARTIFICIAL SERIAL RESPONSE FIXTURE! "
                 "NOT A REAL MODEL 2C ARCADE BOOT.\n";
    try {
        std::ifstream stream(argv[1], std::ios::binary);
        if (!stream) return 2;
        std::vector<std::uint8_t> image(
            std::istreambuf_iterator<char>{stream},
            std::istreambuf_iterator<char>{});
        const std::uint32_t prcb = le32(image, 4);
        const std::uint32_t ip = le32(image, 12);
        const std::uint32_t fp = le32(image, prcb + 24u);

        arcaderecomp_model2c::StrictBus board(std::move(image));
        board.enable_partial_serial_io(true);
        unsigned status_reads = 0;
        unsigned receive_reads = 0;
        board.serial_device().set_serial_status_source([&]() -> std::uint8_t {
            ++status_reads;
            // PURE FICTION for control-flow research. These values do NOT
            // reflect actual Sega receiver state or timing.
            if (status_reads == 1) return 0x00u;
            if (status_reads == 2) return 0x04u;
            return 0x0cu;
        });
        board.serial_device().set_serial_rx(
            [&](std::uint8_t, unsigned channel) -> std::uint8_t {
                ++receive_reads;
                return channel == 1u ? 0x55u : 0xaau;
            });
        arcaderecomp_generated::CPU cpu{};
        cpu.allow_iac_93_reinitialize = true;
        if (!arcaderecomp_generated::frame_init(cpu, fp, ip)) return 2;
        const auto bus = board.callbacks();
        constexpr unsigned kStepLimit = 200000u;
        unsigned steps = 0;

        for (; steps < kStepLimit; ++steps) {
            try {
                if (!arcaderecomp_generated::step(cpu, bus)) {
                    std::cout << "HALT: native opcode not supported; IP=0x"
                              << std::hex << cpu.ip << std::dec
                              << " stop=" << static_cast<unsigned>(cpu.stop_code)
                              << " steps=" << steps
                              << " reinit_count=" << cpu.reinitialize_count << "\n";
                    return 4;
                }
            } catch (const arcaderecomp_model2c::DeviceAccessFault& fault) {
                std::cout << "HALT: unimplemented Model 2C device: " << fault.what() << "\n"
                          << "steps=" << steps
                          << " ip=0x" << std::hex << cpu.ip
                          << " PRCB=0x" << cpu.prcb_address << std::dec
                          << " reinit_count=" << cpu.reinitialize_count
                          << " synthetic_status_reads=" << status_reads
                          << " synthetic_RX_reads=" << receive_reads << "\n";
                return 3;
            }
        }
        std::cout << "HALT: artificial step limit reached, steps=" << steps << "\n";
        return 5;
    } catch (const std::exception& error) {
        std::cerr << "Diagnostic failed: " << error.what() << "\n";
        return 2;
    }
}
