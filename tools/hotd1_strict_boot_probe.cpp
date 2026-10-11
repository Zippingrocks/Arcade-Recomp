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
            std::size_t executed, bool geometry_trace_enabled) {
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
    for (const auto& access : board.serial_access_trace()) {
        std::cout << "serial_access ordinal=" << access.ordinal
                  << " direction=" << (access.write ? "write" : "read")
                  << " address=0x" << std::hex << access.address << std::dec
                  << " width=" << access.width
                  << " completed=" << (access.completed ? "yes" : "no");
        if (access.value_known)
            std::cout << " value=0x" << std::hex << access.value << std::dec;
        else
            std::cout << " value=UNOBSERVED";
        std::cout << "\n";
    }
    std::cout << "serial_trace_summary total=" << board.serial_access_trace_total()
              << " retained=" << board.serial_access_trace().size()
              << " dropped=" << board.serial_access_trace_dropped()
              << " truncated=" << (board.serial_access_trace_truncated() ? "yes" : "no")
              << " limit=" << board.serial_access_trace_limit() << "\n";
    if (geometry_trace_enabled) {
        for (const auto& access : board.geometry_access_trace()) {
            std::cout << "geometry_access ordinal=" << access.ordinal
                      << " direction=" << (access.write ? "write" : "read")
                      << " address=0x" << std::hex << access.address << std::dec
                      << " width=" << access.width
                      << " region_id=" << static_cast<unsigned>(access.region)
                      << " completed=" << (access.completed ? "yes" : "no");
            if (access.value_known)
                std::cout << " value=0x" << std::hex << access.value << std::dec;
            else
                std::cout << " value=UNOBSERVED";
            std::cout << "\n";
        }
        std::cout << "geometry_trace_summary total="
                  << board.geometry_access_trace_total()
                  << " retained=" << board.geometry_access_trace().size()
                  << " dropped=" << board.geometry_access_trace_dropped()
                  << " truncated=" << (board.geometry_access_trace_truncated()
                                       ? "yes" : "no")
                  << " limit=" << board.geometry_access_trace_limit() << "\n";
    }
}

} // namespace

int main(int argc, char** argv) {
    if (argc < 2 || argc > 6) {
        std::cerr << "Usage: strict_boot_probe <PRIVATE maincpu.bin> "
                  << "[steps=10000] [optional PRIVATE main_data.bin] "
                  << "[--serial-tx] [--geometry-trace]\n"
                  << "   --serial-tx: documented TX only, never fake RX\n"
                  << "   --geometry-trace: refused access attempts ONLY\n";
        return 2;
    }
    try {
        std::size_t limit = 10000u;
        bool partial_serial = false;
        bool geometry_trace = false;
        std::vector<std::string> positional;
        for (int i = 2; i < argc; ++i) {
            const std::string arg(argv[i]);
            if (arg == "--serial-tx") {
                if (partial_serial)
                    throw std::runtime_error("duplicate --serial-tx");
                partial_serial = true;
            } else if (arg == "--geometry-trace") {
                if (geometry_trace)
                    throw std::runtime_error("duplicate --geometry-trace");
                geometry_trace = true;
            } else if (arg.rfind("--", 0) == 0) {
                throw std::runtime_error("unknown probe option");
            } else {
                positional.push_back(arg);
            }
        }
        if (positional.size() > 2u)
            throw std::runtime_error("too many positional arguments");
        if (!positional.empty()) {
            std::size_t consumed = 0;
            const auto parsed = std::stoull(positional[0], &consumed, 10);
            if (consumed != positional[0].size() ||
                parsed == 0u || parsed > 1000000u)
                throw std::runtime_error("Step limit outside 1..1000000");
            limit = static_cast<std::size_t>(parsed);
        }
        auto program = read_binary(argv[1]);
        const std::uint32_t prcb = little32(program, 4);
        const std::uint32_t initial_ip = little32(program, 12);
        if (prcb > program.size() || program.size() - prcb < 28u)
            throw std::runtime_error("Invalid ROM bootstrap PRCB offset");
        const std::uint32_t initial_fp = little32(program, prcb + 24u);
        std::vector<std::uint8_t> data;
        if (positional.size() == 2u)
            data = read_binary(positional[1].c_str());
        arcaderecomp_model2c::StrictBus board(std::move(program), std::move(data));
        board.enable_partial_serial_io(partial_serial);
        board.enable_serial_access_trace(partial_serial);
        board.enable_geometry_access_trace(geometry_trace);
        auto bus = board.callbacks();
        arcaderecomp_generated::CPU cpu{};
        if (!arcaderecomp_generated::frame_init(cpu, initial_fp, initial_ip)) {
            report(cpu, board, 0, geometry_trace);
            std::cerr << "CPU initial frame invalid\n";
            return 2;
        }
        std::size_t executed = 0;
        try {
            while (executed < limit) {
                if (!arcaderecomp_generated::step(cpu, bus)) {
                    report(cpu, board, executed, geometry_trace);
                    std::cerr << "STOP: unsupported i960 instruction / frame state, code="
                              << static_cast<unsigned>(cpu.stop_code) << "\n";
                    return 4;
                }
                ++executed;
            }
            report(cpu, board, executed, geometry_trace);
            std::cerr << "STOP: diagnostic instruction limit reached\n";
            return 5;
        } catch (const arcaderecomp_model2c::DeviceAccessFault& fault) {
            report(cpu, board, executed, geometry_trace);
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
