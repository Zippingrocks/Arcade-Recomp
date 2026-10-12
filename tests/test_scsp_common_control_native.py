"""Synthetic common-control tests; no assumed SCSP version/reset state."""
import unittest

from arcaderecomp.m68k_cpp import emit_cpp
from test_m68k_bootstrap_native import native, words


class SCSPCommonControlTests(unittest.TestCase):
    def test_dsp_memory_control_all_values_lanes_and_derived_boundaries(self):
        native('#include "scsp_common_control.hpp"\n', r'''
using arcaderecomp::scsp::DspMemoryControl;
int main() {
    for (unsigned value=0; value<65536u; ++value) {
        DspMemoryControl reg;
        const bool accepted=reg.write16(static_cast<std::uint16_t>(value));
        if (accepted!=((value&~DspMemoryControl::writable)==0u)) return 1;
        if (reg.completed_writes()!=(accepted?1u:0u) ||
                reg.written_known_mask()!=(accepted?0x01ffu:0u)) return 2;
        std::uint32_t length=0xa5a5a5a5u,base=0xa5a5a5a5u;
        if (reg.ring_buffer_length_words(length)!=accepted ||
                reg.ring_buffer_base_byte(base)!=accepted) return 3;
        if (accepted && (length!=(0x2000u<<((value>>7u)&3u)) ||
                base!=((value&0x7fu)<<13u))) return 4;
    }
    for (unsigned offset=0; offset<2; ++offset) for (unsigned value=0; value<256; ++value) {
        DspMemoryControl reg;
        const bool accepted=reg.write8(offset,static_cast<std::uint8_t>(value));
        const bool expected=offset==0u ? value<=1u : true;
        if (accepted!=expected || reg.completed_writes()!=(accepted?1u:0u)) return 5;
        if (accepted && reg.written_known_mask()!=(offset==0u?0x0100u:0x00ffu)) return 6;
        if (reg.configuration_known()) return 7;
    }
    DspMemoryControl original;
    if (!original.write16(0x0138u) || !original.configuration_known()) return 8;
    std::uint32_t length=0,base=0;
    if (!original.ring_buffer_length_words(length) || length!=0x8000u ||
            !original.ring_buffer_base_byte(base) || base!=0x70000u ||
            base+length*2u!=0x80000u) return 9;
    original.invalidate();
    if (original.configuration_known() || original.completed_writes() ||
            original.written_fields() || original.written_known_mask()) return 10;
    return 0;
}
''')

    def test_all_word_and_byte_writes_and_read_only_fields(self):
        native('#include "scsp_common_control.hpp"\n', r'''
using arcaderecomp::scsp::CommonControl;
int main() {
    for(unsigned value=0; value<65536u; ++value) {
        CommonControl reg;
        if(reg.written_known_mask()!=0 || reg.output_muted_known())return 1;
        if(!reg.write16(0x030fu))return 2;
        const bool ok=reg.write16(static_cast<std::uint16_t>(value));
        if(ok!=((value&~0x030fu)==0u))return 3;
        if(reg.written_fields()!=(ok?value:0x030fu) || reg.written_known_mask()!=0x030fu)return 4;
        if(reg.completed_writes()!=(ok?2u:1u))return 5;
        const auto read=reg.read_fields();
        if(read.value!=0 || read.known_mask!=0x030fu)return 6;
        std::uint8_t output=0x5a;
        if(reg.read8(1,output)||output!=0x5a)return 7;
    }
    for(unsigned offset=0; offset<2; ++offset)for(unsigned value=0; value<256; ++value) {
        CommonControl reg;
        const unsigned mask=offset==0?3u:15u;
        const bool ok=reg.write8(offset,static_cast<std::uint8_t>(value));
        if(ok!=((value&~mask)==0u))return 8;
        const unsigned shift=offset==0?8u:0u;
        if(reg.written_fields()!=(ok?(value<<shift):0u) ||
           reg.written_known_mask()!=(ok?(mask<<shift):0u))return 9;
        if(reg.completed_writes()!=(ok?1u:0u))return 10;
    }
    for(unsigned version=0; version<16; ++version) {
        CommonControl reg;
        if(!reg.establish_version(version)||!reg.write16(0x030fu))return 11;
        std::uint8_t value=0x5a;
        if(!reg.read8(1,value)||value!=(version<<4))return 12;
        if(reg.read8(0,value)||value!=(version<<4))return 13;
        if(reg.read_fields().known_mask!=0x03ffu)return 14;
        if(reg.establish_version(16)||reg.read_fields().value!=(version<<4))return 15;
        if(reg.write8(2,0)||reg.read8(2,value)||reg.read8_discard(2))return 16;
        if(reg.completed_discarded_reads()!=0)return 17;
        if(!reg.read8_discard(1)||reg.completed_discarded_reads()!=1)return 18;
        reg.invalidate();
        if(reg.written_known_mask()||reg.output_muted_known()||reg.completed_writes()||
           reg.completed_discarded_reads()||reg.read_fields().known_mask!=0x030fu)return 19;
        if(!reg.write8(1,0)||!reg.output_muted()||reg.written_known_mask()!=15u)return 20;
        if(!reg.write8(0,3)||!reg.output_muted()||reg.written_fields()!=0x0300u)return 21;
        if(!reg.write8(1,1)||reg.output_muted()||reg.written_fields()!=0x0301u)return 22;
    }
    return 0;
}
''')

    def test_native_clear_opt_in_does_not_materialize_unknown_version(self):
        # Synthetic sequence: LEA common control; CLR.B low lane; MOVE.B to unknown I/O.
        source, _ = emit_cpp(words(0x41f9,0x0010,0x0400,0x4228,1,
                                   0x13fc,5,0x0030,7,0xffff), 0)
        native(source, r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
int main() {
    for(unsigned enable=0;enable<2;++enable) {
        CPU cpu;reset_from_vectors(cpu,0x2000,0);
        SoundROMBus bus(std::vector<std::uint8_t>(0x80000,0));
        bus.enable_common_control_research(enable!=0);
        if(!step(cpu,bus))return 1;
        const bool cleared=step(cpu,bus);
        if(cleared!=(enable!=0))return 2;
        if(!enable) {
            if(cpu.completed!=1||cpu.pc!=6||cpu.access_address!=0x100401||cpu.access_write)return 3;
            if(bus.common_control().completed_writes()||bus.common_control().completed_discarded_reads())return 4;
            continue;
        }
        if(cpu.pc!=10||cpu.completed!=2||!bus.common_control().output_muted())return 5;
        if(bus.common_control().completed_writes()!=1||bus.common_control().completed_discarded_reads()!=1)return 6;
        // Even after a successful CLR, a consuming read must not invent VER.
        try{(void)bus.read8(0x100401);return 7;}catch(const BusFault&){}
        if(step(cpu,bus)||cpu.pc!=10||cpu.completed!=2||cpu.access_address!=0x300007||
           !cpu.access_write||cpu.access_width!=1)return 8;
        for(unsigned address:{0x1003ffu,0x100404u,0x400001u}) {
            try{bus.read8_discard(address);return 9;}catch(const BusFault&){}
        }
        if(bus.common_control().completed_discarded_reads()!=1)return 10;
        if(!bus.establish_scsp_version(11)||bus.read8(0x100401)!=0xb0)return 11;
        bus.enable_common_control_research(false);
        try{bus.write8(0x100401,0);return 12;}catch(const BusFault&){}
        try{bus.read8_discard(0x100401);return 13;}catch(const BusFault&){}
        if(bus.common_control().completed_writes()!=1)return 14;
    }
    return 0;
}
''')

    def test_sound_bus_word_lanes_alignment_and_denied_writes(self):
        native('#include "m68k_sound_bus.hpp"\n', r'''
using namespace arcaderecomp::m68k;
int main() {
    std::vector<std::uint8_t> data(0x80000,0);
    data[0]=0x12;data[1]=0x34;data[0x7fffe]=0xab;data[0x7ffff]=0xcd;
    SoundROMBus bus(std::move(data));
    if(bus.read16(0x600000)!=0x1234||bus.read16(0x167fffe)!=0xabcd)return 1;
    for(unsigned address:{0x600001u,0x67ffffu,0x680000u,0x100400u}) {
        try{(void)bus.read16(address);return 2;}catch(const BusFault& e){if(e.write||e.width!=2)return 3;}
    }
    try{bus.write16(0x100400,0x300);return 4;}catch(const BusFault& e){if(!e.write||e.width!=2)return 5;}
    bus.enable_common_control_research(true);
    bus.write16(0x100400,0x030f);
    if(bus.common_control().written_fields()!=0x030f||bus.common_control().completed_writes()!=1)return 6;
    bus.write16(0x100402,0x0138);
    if(bus.dsp_memory_control().written_fields()!=0x0138u||
       bus.dsp_memory_control().completed_writes()!=1u)return 7;
    for(unsigned address:{0x1003ffu,0x100401u,0x100404u,0x400000u,0x600000u}) {
        try{bus.write16(address,0);return 8;}catch(const BusFault& e){if(!e.write||e.width!=2)return 9;}
    }
    try{bus.write16(0x100400,0x0310);return 10;}catch(const BusFault&){}
    try{bus.write16(0x100402,0x0200);return 11;}catch(const BusFault&){}
    if(bus.common_control().written_fields()!=0x030f||bus.common_control().completed_writes()!=1||
       bus.dsp_memory_control().completed_writes()!=1)return 12;
    bus.write8(0x100401,0);
    if(bus.common_control().written_fields()!=0x0300||!bus.common_control().output_muted())return 13;
    try{(void)bus.read16(0x100400);return 14;}catch(const BusFault&){}
    try{(void)bus.read16(0x100402);return 15;}catch(const BusFault&){}
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
