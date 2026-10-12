#pragma once
#include "m68k_runtime.hpp"
#include "m68k_sound_ram.hpp"
#include "model2_sound_control.hpp"
#include "scsp_common_control.hpp"
#include "scsp_dsp_coefficients.hpp"
#include "scsp_prohibited_window.hpp"
#include "scsp_slot_mixer.hpp"
#include <utility>
#include <vector>

namespace arcaderecomp::m68k {
// Published sound-program ROM aperture and opt-in control research.
// SCSP synthesis, RAM and cabinet reset wiring are unsupported.
class SoundROMBus final : public Bus {
    std::vector<std::uint8_t> rom_;
    bool sound_ram_enabled_ = false;
    bool common_control_enabled_ = false;
    bool slot_mixer_enabled_ = false;
    bool dsp_registers_enabled_ = false;
    bool hotd_sound_control_enabled_ = false;
    arcaderecomp::scsp::CommonControl common_control_;
    arcaderecomp::scsp::DspMemoryControl dsp_memory_control_;
    arcaderecomp::scsp::SlotEnvelopeReleaseControl slot_envelope_release_control_;
    arcaderecomp::scsp::SlotLfoControl slot_lfo_control_;
    arcaderecomp::scsp::SlotVolumeModulationControl slot_volume_modulation_control_;
    arcaderecomp::scsp::SlotInputMixerControl slot_input_mixer_control_;
    arcaderecomp::scsp::SlotMixerControl slot_mixer_control_;
    arcaderecomp::scsp::DspCoefficients dsp_coefficients_;
    arcaderecomp::scsp::DspMemoryAddresses dsp_memory_addresses_;
    arcaderecomp::scsp::DspProhibitedClearWindow dsp_prohibited_clear_window_;
    arcaderecomp::scsp::DspMicroprogram dsp_microprogram_;
    arcaderecomp::model2::HotdSoundControl hotd_sound_control_;
    SoundRAM sound_ram_;
public:
    explicit SoundROMBus(std::vector<std::uint8_t> rom) : rom_(std::move(rom)) {
        if (rom_.size() != 0x80000u) throw std::invalid_argument("sound ROM must be 512 KiB");
    }
    std::uint8_t read8(std::uint32_t address) override {
        address &= 0xffffffu;
        std::uint8_t value = 0;
        if (sound_ram_enabled_ && address < SoundRAM::size && sound_ram_.read8(address, value))
            return value;
        if (address >= 0x600000u && address < 0x680000u) return rom_[address - 0x600000u];
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_envelope_release_control_.read8(address - 0x100000u, value)) return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_lfo_control_.read8(address - 0x100000u, value)) return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_volume_modulation_control_.read8(address - 0x100000u, value)) return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_input_mixer_control_.read8(address - 0x100000u, value)) return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_mixer_control_.read8(address - 0x100000u, value)) return value;
        if (dsp_registers_enabled_ && address >= 0x100700u && address < 0x100780u &&
                dsp_coefficients_.read8(address - 0x100700u, value)) return value;
        if (dsp_registers_enabled_ && address >= 0x100780u && address < 0x1007c0u &&
                dsp_memory_addresses_.read8(address - 0x100780u, value)) return value;
        if (dsp_registers_enabled_ && address >= 0x100800u && address < 0x100c00u &&
                dsp_microprogram_.read8(address - 0x100800u, value)) return value;
        if (common_control_enabled_ && address >= 0x100400u && address <= 0x100401u &&
                common_control_.read8(address - 0x100400u, value)) return value;
        throw BusFault(address, false);
    }
    void read8_discard(std::uint32_t address) override {
        address &= 0xffffffu;
        if (sound_ram_enabled_ && address < SoundRAM::size && sound_ram_.read8_discard(address)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_lfo_control_.read8_discard(address - 0x100000u)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_input_mixer_control_.read8_discard(address - 0x100000u)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_volume_modulation_control_.read8_discard(address - 0x100000u)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_mixer_control_.read8_discard(address - 0x100000u)) return;
        if (dsp_registers_enabled_ && address >= 0x100700u && address < 0x100780u &&
                dsp_coefficients_.read8_discard(address - 0x100700u)) return;
        if (dsp_registers_enabled_ && address >= 0x100780u && address < 0x1007c0u &&
                dsp_memory_addresses_.read8_discard(address - 0x100780u)) return;
        if (dsp_registers_enabled_ && address >= 0x100800u && address < 0x100c00u &&
                dsp_microprogram_.read8_discard(address - 0x100800u)) return;
        if (common_control_enabled_ && address >= 0x100400u && address <= 0x100401u &&
                common_control_.read8_discard(address - 0x100400u)) return;
        (void)read8(address);
    }
    std::uint16_t read16(std::uint32_t address) override {
        address &= 0xffffffu;
        std::uint16_t value = 0;
        if (sound_ram_enabled_ && address < SoundRAM::size && sound_ram_.read16(address, value))
            return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_envelope_release_control_.read16(address - 0x100000u, value)) return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_lfo_control_.read16(address - 0x100000u, value)) return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_volume_modulation_control_.read16(address - 0x100000u, value)) return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_input_mixer_control_.read16(address - 0x100000u, value)) return value;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_mixer_control_.read16(address - 0x100000u, value)) return value;
        if (dsp_registers_enabled_ && address >= 0x100700u && address < 0x100780u &&
                dsp_coefficients_.read16(address - 0x100700u, value)) return value;
        if (dsp_registers_enabled_ && address >= 0x100780u && address < 0x1007c0u &&
                dsp_memory_addresses_.read16(address - 0x100780u, value)) return value;
        if (dsp_registers_enabled_ && address >= 0x100800u && address < 0x100c00u &&
                dsp_microprogram_.read16(address - 0x100800u, value)) return value;
        if (!(address & 1u) && address >= 0x600000u && address < 0x680000u)
            return static_cast<std::uint16_t>((std::uint16_t(rom_[address - 0x600000u]) << 8) |
                                             rom_[address - 0x600000u + 1u]);
        // Reserved high-byte bits have no documented readback; no guessed word.
        throw BusFault(address, false, 2u);
    }
    void read16_discard(std::uint32_t address) override {
        address &= 0xffffffu;
        if (sound_ram_enabled_ && address < SoundRAM::size && sound_ram_.read16_discard(address)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_lfo_control_.read16_discard(address - 0x100000u)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_input_mixer_control_.read16_discard(address - 0x100000u)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_volume_modulation_control_.read16_discard(address - 0x100000u)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_mixer_control_.read16_discard(address - 0x100000u)) return;
        if (dsp_registers_enabled_ && address >= 0x100700u && address < 0x100780u &&
                dsp_coefficients_.read16_discard(address - 0x100700u)) return;
        if (dsp_registers_enabled_ && address >= 0x100780u && address < 0x1007c0u &&
                dsp_memory_addresses_.read16_discard(address - 0x100780u)) return;
        if (dsp_registers_enabled_ && address >= 0x1007c0u && address < 0x100800u &&
                dsp_prohibited_clear_window_.read16_discard(address - 0x1007c0u)) return;
        if (dsp_registers_enabled_ && address >= 0x100800u && address < 0x100c00u &&
                dsp_microprogram_.read16_discard(address - 0x100800u)) return;
        (void)read16(address);
    }
    void write8(std::uint32_t address, std::uint8_t value) override {
        address &= 0xffffffu;
        if (sound_ram_enabled_ && address < SoundRAM::size && sound_ram_.write8(address, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_envelope_release_control_.write8(address - 0x100000u, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_lfo_control_.write8(address - 0x100000u, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_volume_modulation_control_.write8(address - 0x100000u, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_input_mixer_control_.write8(address - 0x100000u, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_mixer_control_.write8(address - 0x100000u, value)) return;
        if (dsp_registers_enabled_ && address >= 0x100700u && address < 0x100780u &&
                dsp_coefficients_.write8(address - 0x100700u, value)) return;
        if (dsp_registers_enabled_ && address >= 0x100780u && address < 0x1007c0u &&
                dsp_memory_addresses_.write8(address - 0x100780u, value)) return;
        if (dsp_registers_enabled_ && address >= 0x100800u && address < 0x100c00u &&
                dsp_microprogram_.write8(address - 0x100800u, value)) return;
        if (common_control_enabled_ && address >= 0x100400u && address <= 0x100401u &&
                common_control_.write8(address - 0x100400u, value)) return;
        if (common_control_enabled_ && address >= 0x100402u && address <= 0x100403u &&
                dsp_memory_control_.write8(address - 0x100402u, value)) return;
        if (hotd_sound_control_enabled_ && address == 0x400001u &&
                hotd_sound_control_.write8(1u, value)) return;
        throw BusFault(address, true);
    }
    void write16(std::uint32_t address, std::uint16_t value) override {
        address &= 0xffffffu;
        if (sound_ram_enabled_ && address < SoundRAM::size && sound_ram_.write16(address, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_envelope_release_control_.write16(address - 0x100000u, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_lfo_control_.write16(address - 0x100000u, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_volume_modulation_control_.write16(address - 0x100000u, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_input_mixer_control_.write16(address - 0x100000u, value)) return;
        if (slot_mixer_enabled_ && address >= 0x100000u && address < 0x100400u &&
                slot_mixer_control_.write16(address - 0x100000u, value)) return;
        if (dsp_registers_enabled_ && address >= 0x100700u && address < 0x100780u &&
                dsp_coefficients_.write16(address - 0x100700u, value)) return;
        if (dsp_registers_enabled_ && address >= 0x100780u && address < 0x1007c0u &&
                dsp_memory_addresses_.write16(address - 0x100780u, value)) return;
        if (dsp_registers_enabled_ && address >= 0x1007c0u && address < 0x100800u &&
                dsp_prohibited_clear_window_.write16(address - 0x1007c0u, value)) return;
        if (dsp_registers_enabled_ && address >= 0x100800u && address < 0x100c00u &&
                dsp_microprogram_.write16(address - 0x100800u, value)) return;
        if (common_control_enabled_ && address == 0x100400u && common_control_.write16(value)) return;
        if (common_control_enabled_ && address == 0x100402u &&
                dsp_memory_control_.write16(value)) return;
        if (hotd_sound_control_enabled_ && address == 0x400000u &&
                hotd_sound_control_.write16(value)) return;
        throw BusFault(address, true, 2u);
    }
    // Caller opts into bounded architectural register semantics, NOT evidence
    // of physical reset completion or a working/timed SCSP audio device.
    void enable_common_control_research(bool enabled) { common_control_enabled_ = enabled; }
    void enable_slot_mixer_research(bool enabled) { slot_mixer_enabled_ = enabled; }
    void enable_dsp_registers_research(bool enabled) { dsp_registers_enabled_ = enabled; }
    void enable_sound_ram_research(bool enabled) { sound_ram_enabled_ = enabled; }
    bool establish_sound_ram_byte_research(std::uint32_t address, std::uint8_t value) {
        address &= 0xffffffu;
        return sound_ram_enabled_ && sound_ram_.establish8(address, value);
    }
    void enable_hotd_sound_control_research(bool enabled) {
        hotd_sound_control_enabled_ = enabled;
    }
    const arcaderecomp::scsp::CommonControl& common_control() const { return common_control_; }
    const arcaderecomp::scsp::DspMemoryControl& dsp_memory_control() const {
        return dsp_memory_control_;
    }
    const arcaderecomp::model2::HotdSoundControl& hotd_sound_control() const {
        return hotd_sound_control_;
    }
    const SoundRAM& sound_ram() const { return sound_ram_; }
    const arcaderecomp::scsp::SlotMixerControl& slot_mixer_control() const {
        return slot_mixer_control_;
    }
    const arcaderecomp::scsp::SlotInputMixerControl& slot_input_mixer_control() const {
        return slot_input_mixer_control_;
    }
    const arcaderecomp::scsp::SlotVolumeModulationControl& slot_volume_modulation_control() const {
        return slot_volume_modulation_control_;
    }
    const arcaderecomp::scsp::SlotLfoControl& slot_lfo_control() const {
        return slot_lfo_control_;
    }
    const arcaderecomp::scsp::SlotEnvelopeReleaseControl& slot_envelope_release_control() const {
        return slot_envelope_release_control_;
    }
    const arcaderecomp::scsp::DspCoefficients& dsp_coefficients() const {
        return dsp_coefficients_;
    }
    const arcaderecomp::scsp::DspMemoryAddresses& dsp_memory_addresses() const {
        return dsp_memory_addresses_;
    }
    const arcaderecomp::scsp::DspMicroprogram& dsp_microprogram() const {
        return dsp_microprogram_;
    }
    const arcaderecomp::scsp::DspProhibitedClearWindow& dsp_prohibited_clear_window() const {
        return dsp_prohibited_clear_window_;
    }
    bool establish_scsp_version(unsigned version) { return common_control_.establish_version(version); }
};
}
