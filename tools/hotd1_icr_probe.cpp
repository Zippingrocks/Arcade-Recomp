// ArcadeRecomp: isolated Intel 80960KB SYNMOV-to-ICR check.
//
// The user provides their OWN original verified 2-MiB HOTD1 i960 ROM image
// and PRIVATE AOT output built with --extra-entry 0x6d4.
// This isolates a single original instruction. It is neither an arcade
// boot nor a bypass of the currently unknown 0x00F80000 hardware register.
// No game ROM bytes or generated game-specific code are published here.
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

#include "model2c_bus.hpp"
#include "hotd1_i960.cpp"

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: hotd1_icr_probe PRIVATE/maincpu.bin\n";
        return 2;
    }
    try {
        std::ifstream input(argv[1], std::ios::binary);
        if (!input) return 2;
        std::vector<std::uint8_t> image(
            std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{});
        arcaderecomp_model2c::StrictBus board(std::move(image));
        constexpr std::uint32_t source = 0x000006a8u;
        constexpr std::uint32_t instruction = 0x000006d4u;
        constexpr std::uint32_t next = 0x000006d8u;
        constexpr std::uint32_t expected_icr = 0x0f0e0d0cu;
        if (board.read(source, 4) != expected_icr) {
            std::cerr << "Wrong source word: verify this is the original HOTD1 program\n";
            return 2;
        }
        arcaderecomp_generated::CPU cpu{};
        if (!arcaderecomp_generated::frame_init(cpu, 0x00510400u, instruction))
            return 2;
        cpu.r[20] = 0xff000004u;  // g4 -> internal Intel KB ICR
        cpu.r[21] = source;       // g5 -> original RAM/ROM source word

        const std::uint32_t before = cpu.interrupt_control_register;
        const bool success = arcaderecomp_generated::step(cpu, board.callbacks());
        std::cout << "ISOLATED ORIGINAL ICR INSTRUCTION, NOT FULL ARCADE BOOT\n"
                  << "success=" << success << " source=0x" << std::hex << source
                  << " instruction=0x" << instruction
                  << " old_icr=0x" << before
                  << " new_icr=0x" << cpu.interrupt_control_register
                  << " next_ip=0x" << cpu.ip << std::dec
                  << " cc=" << cpu.cc << "\n";
        if (!success || cpu.ip != next ||
            cpu.interrupt_control_register != expected_icr ||
            cpu.cc != 2 || !cpu.cc_defined) {
            std::cerr << "Original ICR SYNMOV verification FAILED\n";
            return 3;
        }
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "Private ROM ICR verification failed: " << error.what() << "\n";
        return 4;
    }
}
