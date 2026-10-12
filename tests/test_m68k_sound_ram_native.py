"""ROM-free native checks for strict Model 2 sound-RAM knownness."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class M68kSoundRAMTests(unittest.TestCase):
    def test_direct_ram_bounds_endian_knownness_and_invalidation(self):
        native('#include "m68k_sound_ram.hpp"\n', r'''
using arcaderecomp::m68k::SoundRAM;
int main() {
    SoundRAM ram; std::uint8_t byte=0x5a; std::uint16_t word=0x5aa5;
    if (ram.known_bytes() || ram.read8(0,byte) || byte!=0x5a || ram.read16(0,word) ||
            word!=0x5aa5 || !ram.read8_discard(0) || !ram.read16_discard(0)) return 1;
    if (!ram.write8(0,0x12) || ram.known_bytes()!=1u || !ram.read8(0,byte) || byte!=0x12 ||
            ram.read16(0,word)) return 2;
    if (!ram.write8(1,0x34) || ram.known_bytes()!=2u || !ram.read16(0,word) || word!=0x1234u) return 3;
    if (!ram.write16(0x7fffeu,0xabcd) || ram.known_bytes()!=4u ||
            !ram.read16(0x7fffeu,word) || word!=0xabcdu) return 4;
    if (ram.read16(1,word) || ram.read16(0x7ffffu,word) || ram.read8(SoundRAM::size,byte) ||
            ram.read8_discard(SoundRAM::size) || ram.read16_discard(1) ||
            ram.write8(SoundRAM::size,0) || ram.write16(1,0)) return 5;
    ram.invalidate();
    if (ram.known_bytes() || ram.read8(0,byte) || !ram.read8_discard(0)) return 6;
    return 0;
}
''')

    def test_bus_opt_in_physical_mask_and_strict_unknown_reads(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main() {
    SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));
    try { bus.write8(0,1); return 1; } catch (const BusFault&) {}
    bus.enable_sound_ram_research(true);
    try { (void)bus.read8(0); return 2; } catch (const BusFault& e) { if(e.write||e.width!=1u)return 3; }
    bus.write8(0x1000000u,0x12u); // physical 24-bit alias of RAM byte zero
    bus.write8(1,0x34u);
    if (bus.read16(0)!=0x1234u || bus.sound_ram().known_bytes()!=2u) return 4;
    bus.write16(0x7fffeu,0xabcdu);
    if (bus.read8(0x7fffeu)!=0xabu || bus.read8(0x7ffffu)!=0xcdu) return 5;
    for (unsigned address: {0x80000u,0x5fffffu,0x680000u}) {
        try { bus.write8(address,0); return 6; } catch (const BusFault&) {}
    }
    bus.enable_sound_ram_research(false);
    try { (void)bus.read16(0); return 7; } catch (const BusFault&) {}
    return 0;
}
''')

    def test_clear_reads_unknown_ram_without_inventing_consumed_data(self):
        # CLR.B $10; CLR.W $12; CLR.L $14; MOVE.W $18,D0 (still unknown).
        source, report = emit_cpp(words(0x4239,0,0x10, 0x4279,0,0x12,
                                        0x42b9,0,0x14, 0x3039,0,0x18, 0xffff), 0)
        self.assertEqual(report.translated, 4)
        native(source, r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main() {
    CPU cpu; reset_from_vectors(cpu,0x2000,0);
    SoundROMBus bus(std::vector<std::uint8_t>(0x80000u,0));
    bus.enable_sound_ram_research(true);
    if (!step(cpu,bus) || !step(cpu,bus) || !step(cpu,bus) || cpu.completed!=3u ||
            cpu.pc!=18u || bus.sound_ram().known_bytes()!=7u) return 1;
    if (bus.read8(0x10)!=0 || bus.read16(0x12)!=0 || bus.read16(0x14)!=0 ||
            bus.read16(0x16)!=0) return 2;
    if (step(cpu,bus) || cpu.completed!=3u || cpu.pc!=18u || cpu.access_address!=0x18u ||
            cpu.access_write || cpu.access_width!=2u) return 3;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
