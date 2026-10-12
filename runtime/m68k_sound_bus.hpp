#pragma once
#include "m68k_runtime.hpp"
#include <utility>
#include <vector>

namespace arcaderecomp::m68k {
// Published sound-program ROM aperture only. RAM power-on state, SCSP,
// sample banking and the cabinet's reset-vector wiring remain unsupported.
class SoundROMBus final : public Bus {
    std::vector<std::uint8_t> rom_;
public:
    explicit SoundROMBus(std::vector<std::uint8_t> rom) : rom_(std::move(rom)) {
        if (rom_.size() != 0x80000u) throw std::invalid_argument("sound ROM must be 512 KiB");
    }
    std::uint8_t read8(std::uint32_t address) override {
        address &= 0xffffffu;
        if (address >= 0x600000u && address < 0x680000u) return rom_[address - 0x600000u];
        throw BusFault(address, false);
    }
    void write8(std::uint32_t address, std::uint8_t) override {
        throw BusFault(address & 0xffffffu, true);
    }
};
}
