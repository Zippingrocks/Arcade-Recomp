#pragma once
#include "m68k_runtime.hpp"
#include "model2_sound_control.hpp"
#include "scsp_common_control.hpp"
#include <utility>
#include <vector>

namespace arcaderecomp::m68k {
// Published sound-program ROM aperture and opt-in control research.
// SCSP synthesis, RAM and cabinet reset wiring are unsupported.
class SoundROMBus final : public Bus {
    std::vector<std::uint8_t> rom_;
    bool common_control_enabled_ = false;
    bool hotd_sound_control_enabled_ = false;
    arcaderecomp::scsp::CommonControl common_control_;
    arcaderecomp::model2::HotdSoundControl hotd_sound_control_;
public:
    explicit SoundROMBus(std::vector<std::uint8_t> rom) : rom_(std::move(rom)) {
        if (rom_.size() != 0x80000u) throw std::invalid_argument("sound ROM must be 512 KiB");
    }
    std::uint8_t read8(std::uint32_t address) override {
        address &= 0xffffffu;
        if (address >= 0x600000u && address < 0x680000u) return rom_[address - 0x600000u];
        std::uint8_t value = 0;
        if (common_control_enabled_ && address >= 0x100400u && address <= 0x100401u &&
                common_control_.read8(address - 0x100400u, value)) return value;
        throw BusFault(address, false);
    }
    void read8_discard(std::uint32_t address) override {
        address &= 0xffffffu;
        if (common_control_enabled_ && address >= 0x100400u && address <= 0x100401u &&
                common_control_.read8_discard(address - 0x100400u)) return;
        (void)read8(address);
    }
    std::uint16_t read16(std::uint32_t address) override {
        address &= 0xffffffu;
        if (!(address & 1u) && address >= 0x600000u && address < 0x680000u)
            return static_cast<std::uint16_t>((std::uint16_t(rom_[address - 0x600000u]) << 8) |
                                             rom_[address - 0x600000u + 1u]);
        // Reserved high-byte bits have no documented readback; no guessed word.
        throw BusFault(address, false, 2u);
    }
    void write8(std::uint32_t address, std::uint8_t value) override {
        address &= 0xffffffu;
        if (common_control_enabled_ && address >= 0x100400u && address <= 0x100401u &&
                common_control_.write8(address - 0x100400u, value)) return;
        if (hotd_sound_control_enabled_ && address == 0x400001u &&
                hotd_sound_control_.write8(1u, value)) return;
        throw BusFault(address, true);
    }
    void write16(std::uint32_t address, std::uint16_t value) override {
        address &= 0xffffffu;
        if (common_control_enabled_ && address == 0x100400u && common_control_.write16(value)) return;
        if (hotd_sound_control_enabled_ && address == 0x400000u &&
                hotd_sound_control_.write16(value)) return;
        throw BusFault(address, true, 2u);
    }
    // Caller opts into bounded architectural register semantics, NOT evidence
    // of physical reset completion or a working/timed SCSP audio device.
    void enable_common_control_research(bool enabled) { common_control_enabled_ = enabled; }
    void enable_hotd_sound_control_research(bool enabled) {
        hotd_sound_control_enabled_ = enabled;
    }
    const arcaderecomp::scsp::CommonControl& common_control() const { return common_control_; }
    const arcaderecomp::model2::HotdSoundControl& hotd_sound_control() const {
        return hotd_sound_control_;
    }
    bool establish_scsp_version(unsigned version) { return common_control_.establish_version(version); }
};
}
