// Strict original HOTD1 boot diagnostic, NOT a playable emulator or full port.
// User supplies PRIVATE, previously hash-verified ROM-derived images.
// Compile with the independently generated PRIVATE hotd1_i960.cpp.
//
// Device accesses without independent Model 2C implementations are rejected
// and reported. A controlled failure at Sega I/O is useful research evidence.
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

#include "model2c_bus.hpp"
#include "hotd1_i960.cpp"

namespace {

std::vector<std::uint8_t> read_binary(const char* filename) {
    std::ifstream file(filename, std::ios::binary);
    if (!file) throw std::runtime_error(std::string("Cannot read file: ") + filename);
    return {std::istreambuf_iterator<char>(file),
            std::istreambuf_iterator<char>()};
}

std::uint32_t little32(const std::vector<std::uint8_t>& data,
                       std::size_t offset) {
    if (offset > data.size() || data.size() - offset < 4u)
        throw std::runtime_error("i960 bootstrap word outside program ROM");
    return std::uint32_t(data[offset]) |
           (std::uint32_t(data[offset + 1u]) << 8u) |
           (std::uint32_t(data[offset + 2u]) << 16u) |
           (std::uint32_t(data[offset + 3u]) << 24u);
}

void report(const arcaderecomp_generated::CPU& cpu,
            const arcaderecomp_model2c::StrictBus& board,
            std::size_t executed) {
    std::cout << "Original HOTD1 Model 2C STRICT diagnostic — NOT A GAME BOOT\n"
              << "executed=" << std::dec << executed
              << " ip=0x" << std::hex << cpu.ip << std::dec
              << " frame_depth=" << cpu.frame_depth
              << " spills=" << cpu.frame_spills
              << " reloads=" << cpu.frame_reloads
              << " mapped_writes=" << board.writes().size()
              << " CPU_control_writes=" << board.pending_timing_writes()
              << " documented_serial_tx=" << board.serial_device().transmissions().size()
              << "\n";
    for (const auto& tx : board.serial_device().transmissions()) {
        std::cout << "serial_tx channel=" << tx.channel
                  << " byte=0x" << std::hex << static_cast<unsigned>(tx.byte)
                  << " address=0x" << tx.address << std::dec << "\n";
    }
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 2 || argc > 5) {
        std::cerr << "Usage: strict_boot_probe <PRIVATE maincpu.bin> "
                  << "[steps=10000] [optional PRIVATE main_data.bin] [--serial-tx]\n"
                  << "   --serial-tx: opt into documented serial writes ONLY, "
                  << "never fake status/receive bytes\n";
        return 2;
    }
    try {
        std::size_t limit = 10000u;
        if (argc >= 3) {
            limit = std::stoul(argv[2]);
            if (limit == 0u || limit > 1000000u)
                throw std::runtime_error("Step limit outside 1..1000000");
        }
        auto program = read_binary(argv[1]);
        const std::uint32_t prcb = little32(program, 4);
        const std::uint32_t initial_ip = little32(program, 12);
        if (prcb > program.size() || program.size() - prcb < 28u)
            throw std::runtime_error("Invalid ROM bootstrap PRCB offset");
        const std::uint32_t initial_fp = little32(program, prcb + 24u);
        std::vector<std::uint8_t> data;
        bool partial_serial = false;
        if (argc >= 4) {
            if (std::string(argv[3]) == "--serial-tx") partial_serial = true;
            else data = read_binary(argv[3]);
        }
        if (argc >= 5) {
            if (std::string(argv[4]) != "--serial-tx" || partial_serial)
                throw std::runtime_error("Unknown/duplicated command option");
            partial_serial = true;
        }
        arcaderecomp_model2c::StrictBus board(std::move(program), std::move(data));
        board.enable_partial_serial_io(partial_serial);
        auto bus = board.callbacks();
        arcaderecomp_generated::CPU cpu{};
        if (!arcaderecomp_generated::frame_init(cpu, initial_fp, initial_ip)) {
            report(cpu, board, 0);
            std::cerr << "CPU initial frame invalid\n";
            return 2;
        }
        std::size_t executed = 0;
        try {
            while (executed < limit) {
                if (!arcaderecomp_generated::step(cpu, bus)) {
                    report(cpu, board, executed);
                    std::cerr << "STOP: unsupported i960 instruction / frame state, code="
                              << static_cast<unsigned>(cpu.stop_code) << "\n";
                    return 4;
                }
                ++executed;
            }
            report(cpu, board, executed);
            std::cerr << "STOP: diagnostic instruction limit reached\n";
            return 5;
        } catch (const arcaderecomp_model2c::DeviceAccessFault& fault) {
            report(cpu, board, executed);
            std::cerr << "STOP: required hardware not implemented: "
                      << fault.what() << "\n";
            return 3;
        }
    } catch (const std::exception& error) {
        std::cerr << "Cannot initialize original HOTD1 probe: "
                  << error.what() << "\n";
        return 2;
    }
}
