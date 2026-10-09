// Diagnostic-only ROM bootstrap probe; NOT a Model 2C hardware runtime.
// Requires a locally generated, PRIVATE hotd1_i960.cpp and maincpu.bin.
// Commercial game content is deliberately not included in this repository.

#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <iterator>
#include <string>
#include <unordered_map>
#include <vector>

#include "hotd1_i960.cpp"

namespace {

struct ShadowBus {
    std::vector<std::uint8_t> program;
    std::unordered_map<std::uint32_t, std::uint32_t> shadow;
    std::size_t writes = 0;
    std::size_t reads = 0;

    static std::uint32_t read32(void* context, std::uint32_t address) {
        auto& bus = *static_cast<ShadowBus*>(context);
        ++bus.reads;
        if (address % 4 != 0) {
            std::cerr << "Unaligned diagnostic read: 0x" << std::hex << address << "\n";
            std::abort();
        }
        if (address < bus.program.size() &&
            bus.program.size() - address >= 4) {
            const auto* p = bus.program.data() + address;
            return std::uint32_t(p[0]) | (std::uint32_t(p[1]) << 8) |
                   (std::uint32_t(p[2]) << 16) | (std::uint32_t(p[3]) << 24);
        }
        auto existing = bus.shadow.find(address);
        return existing == bus.shadow.end() ? 0 : existing->second;
    }

    static void write32(void* context, std::uint32_t address, std::uint32_t value) {
        auto& bus = *static_cast<ShadowBus*>(context);
        if (address % 4 != 0) {
            std::cerr << "Unaligned diagnostic write: 0x" << std::hex << address << "\n";
            std::abort();
        }
        if (address < bus.program.size()) {
            std::cerr << "Write to program ROM blocked: 0x" << std::hex << address << "\n";
            std::abort();
        }
        bus.shadow[address] = value;
        ++bus.writes;
    }

    std::uint32_t boot_word(std::size_t offset) const {
        if (offset > program.size() || program.size() - offset < 4)
            throw std::runtime_error("i960 boot record or PRCB outside program image");
        return std::uint32_t(program[offset]) |
               std::uint32_t(program[offset + 1]) << 8 |
               std::uint32_t(program[offset + 2]) << 16 |
               std::uint32_t(program[offset + 3]) << 24;
    }

    std::uint32_t boot_ip() const { return boot_word(12); }
    std::uint32_t boot_prcb() const { return boot_word(4); }
};

} // namespace

int main(int argc, char** argv) {
    if (argc < 2 || argc > 3) {
        std::cerr << "Usage: hotd1_boot_probe <PRIVATE maincpu.bin> [max_steps]\n";
        return 2;
    }
    std::size_t limit = 2000;
    if (argc == 3) {
        try {
            limit = std::stoul(argv[2]);
        } catch (...) {
            std::cerr << "Invalid max_steps\n";
            return 2;
        }
        if (limit < 1 || limit > 1000000) {
            std::cerr << "max_steps must be in the range 1..1000000\n";
            return 2;
        }
    }

    std::ifstream file(argv[1], std::ios::binary);
    if (!file) {
        std::cerr << "Cannot open private CPU program image\n";
        return 2;
    }
    ShadowBus shadow;
    shadow.program.assign(std::istreambuf_iterator<char>(file),
                          std::istreambuf_iterator<char>());
    if (shadow.program.size() > 256u * 1024u * 1024u) {
        std::cerr << "Oversized program image\n";
        return 2;
    }

    arcaderecomp_generated::CPU cpu{};
    try {
        const std::uint32_t prcb = shadow.boot_prcb();
        // Intel 80960KB reset obtains its initial FP from PRCB + 24.
        // No arcade peripheral behavior is emulated by this boot probe.
        if (prcb > shadow.program.size() ||
            shadow.program.size() - prcb < 28) {
            std::cerr << "PRCB frame pointer lies outside program ROM\n";
            return 2;
        }
        const std::uint32_t initial_fp = shadow.boot_word(prcb + 24u);
        if (!arcaderecomp_generated::frame_init(cpu, initial_fp, shadow.boot_ip())) {
            std::cerr << "Failed to initialize i960 local register frame\n";
            return 2;
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << "\n";
        return 2;
    }
    arcaderecomp_generated::Bus bus{&shadow, &ShadowBus::read32,
                                   &ShadowBus::write32};
    std::size_t executed = 0;
    while (executed < limit && arcaderecomp_generated::step(cpu, bus))
        ++executed;

    std::cout << "DIAGNOSTIC SHADOW BUS — NOT MODEL 2C EMULATION\n"
              << "steps_executed=" << std::dec << executed << "\n"
              << "stop_ip=0x" << std::hex << cpu.ip << "\n"
              << "shadow_bus_reads=" << std::dec << shadow.reads << "\n"
              << "shadow_bus_writes=" << shadow.writes << "\n"
              << "limit_reached=" << (executed == limit ? "true" : "false") << "\n"
              << "frame_depth=" << cpu.frame_depth << "\n"
              << "frame_spills=" << cpu.frame_spills << "\n"
              << "frame_reloads=" << cpu.frame_reloads << "\n"
              << "stop_code=" << static_cast<unsigned>(cpu.stop_code) << "\n";
    return 0;
}
