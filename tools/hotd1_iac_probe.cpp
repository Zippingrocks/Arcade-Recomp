// An ISOLATED original-HOTD1 instruction proof. Does not emulate serial input
// or execute the original startup path through Sega I/O. The game binary is
// supplied privately and is never distributed by this repository.
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
#include "model2c_bus.hpp"
#include "hotd1_i960.cpp"

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "Usage: hotd1_iac_probe PRIVATE/maincpu.bin\n";
        return 2;
    }
    std::ifstream input(argv[1], std::ios::binary);
    if (!input) return 2;
    std::vector<std::uint8_t> image(
        std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{});
    try {
        arcaderecomp_model2c::StrictBus board(std::move(image));
        arcaderecomp_generated::CPU cpu{};
        // Register values are independently observed inputs at the original
        // 0x6a0 site; the preceding real-ROM serial handshake is NOT executed.
        cpu.ip = 0x000006a0u;
        cpu.r[16] = 0xff000010u; // g0 = local processor IAC address
        cpu.r[17] = 0x00000560u; // g1 = pointer to original message in ROM
        bool continued = arcaderecomp_generated::step(cpu, board.callbacks());
        const bool pending = cpu.pending_iac_valid &&
            cpu.stop_code == arcaderecomp_generated::StopCode::iac_reinitialize_pending;
        std::cout << "ISOLATED ORIGINAL I960 INSTRUCTION, NOT AN ARCADE BOOT\n";
        if (!continued && pending) {
            std::cout << "pending_message=0x" << std::hex << cpu.pending_iac[0]
                      << " sat=0x" << cpu.pending_iac[1]
                      << " prcb=0x" << cpu.pending_iac[2]
                      << " requested_next_ip=0x" << cpu.pending_iac[3] << "\n";
            return 0;
        }
        std::cerr << "The instruction did not reach the expected IAC reinitialize boundary\n";
        return 3;
    } catch (const std::exception& error) {
        std::cerr << "Cannot inspect original ROM: " << error.what() << "\n";
        return 4;
    }
}
