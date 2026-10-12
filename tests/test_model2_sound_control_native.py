"""ROM-free tests for the bounded original-HOTD sound-control aperture."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class Model2SoundControlTests(unittest.TestCase):
    def test_all_values_and_explicit_transaction_metadata(self):
        native('#include "model2_sound_control.hpp"\n', r'''
using arcaderecomp::model2::HotdSoundControl;
int main() {
    static_assert(HotdSoundControl::sample_region_bytes == 0x800000u);
    static_assert(!HotdSoundControl::sample_bank_changed());
    for (unsigned value=0; value<256u; ++value) {
        HotdSoundControl control;
        if (control.write8(0u, static_cast<std::uint8_t>(value))) return 1;
        if (!control.write8(1u, static_cast<std::uint8_t>(value))) return 2;
        if (control.completed_writes()!=1u || control.last_transaction_data()!=value ||
                control.last_transaction_known_mask()!=0x00ffu) return 3;
    }
    for (unsigned value=0; value<65536u; ++value) {
        HotdSoundControl control;
        if (!control.write16(static_cast<std::uint16_t>(value))) return 4;
        if (control.completed_writes()!=1u || control.last_transaction_data()!=value ||
                control.last_transaction_known_mask()!=0xffffu) return 5;
        if (!control.write8(1u, 0xa5u) ||
                control.last_transaction_data()!=((value&0xff00u)|0xa5u) ||
                control.last_transaction_known_mask()!=0xffffu || control.completed_writes()!=2u) return 6;
    }
    return 0;
}
''')

    def test_sound_bus_is_strict_by_default_and_keeps_reads_unknown(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main() {
    SoundROMBus bus(std::vector<std::uint8_t>(0x80000u, 0));
    try { bus.write8(0x400001u, 0); return 1; } catch (const BusFault&) {}
    bus.enable_hotd_sound_control_research(true);
    bus.write8(0x400001u, 0);
    bus.write8(0x1400001u, 0x20u);
    bus.write16(0x400000u, 0x1234u);
    const auto& control=bus.hotd_sound_control();
    if (control.completed_writes()!=3u || control.last_transaction_data()!=0x1234u ||
            control.last_transaction_known_mask()!=0xffffu || control.sample_bank_changed()) return 2;
    for (unsigned address: {0x3fffffu,0x400000u,0x400002u}) {
        try { bus.write8(address, 0); return 3; } catch (const BusFault& e) {
            if (!e.write || e.width!=1u) return 4;
        }
    }
    for (unsigned address: {0x3ffffeu,0x400001u,0x400002u}) {
        try { bus.write16(address, 0); return 5; } catch (const BusFault& e) {
            if (!e.write || e.width!=2u) return 6;
        }
    }
    for (unsigned address: {0x400000u,0x400001u}) {
        try { (void)bus.read8(address); return 7; } catch (const BusFault& e) {
            if (e.write) return 8;
        }
    }
    return 0;
}
''')

    def test_generated_original_form_advances_only_with_opt_in(self):
        # MOVE.B #0,$400001; MOVE.W #$300,$100400; MOVE.W #$138,$100402.
        source, report = emit_cpp(words(0x13fc, 0, 0x0040, 1,
                                        0x33fc, 0x0300, 0x0010, 0x0400,
                                        0x33fc, 0x0138, 0x0010, 0x0402,
                                        0xffff), 0)
        self.assertEqual(report.translated, 3)
        native(source, r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main() {
    for (unsigned enable=0; enable<2; ++enable) {
        CPU cpu; reset_from_vectors(cpu, 0x2000u, 0);
        SoundROMBus bus(std::vector<std::uint8_t>(0x80000u, 0));
        bus.enable_common_control_research(true);
        bus.enable_hotd_sound_control_research(enable!=0);
        const bool first=step(cpu,bus);
        if (first!=(enable!=0)) return 1;
        if (!enable) {
            if (cpu.completed || cpu.pc || cpu.access_address!=0x400001u ||
                    !cpu.access_write || cpu.access_width!=1u) return 2;
            continue;
        }
        if (cpu.completed!=1u || cpu.pc!=8u || bus.hotd_sound_control().completed_writes()!=1u) return 3;
        if (!step(cpu,bus) || cpu.completed!=2u || cpu.pc!=16u ||
                bus.common_control().written_fields()!=0x0300u) return 4;
        if (step(cpu,bus) || cpu.completed!=2u || cpu.pc!=16u ||
                cpu.access_address!=0x100402u || !cpu.access_write || cpu.access_width!=2u) return 5;
    }
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
