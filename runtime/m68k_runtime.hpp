#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp::m68k {
enum class Stop {
    none, unsupported_instruction, untranslated_pc, instruction_address,
    undefined_state, unsupported_control, privilege, bus_access, data_address
};

struct CPU {
    std::array<std::uint32_t, 8> d{}, a{}, d_known{};
    std::array<bool, 8> a_known{};
    std::uint32_t pc = 0;
    std::uint16_t sr = 0, sr_known = 0;
    Stop stop = Stop::none;
    std::uint32_t stop_pc = 0, access_address = 0;
    bool access_write = false;
    std::uint8_t access_width = 0;
    std::uint64_t completed = 0;
};

struct BusFault : std::runtime_error {
    std::uint32_t address;
    bool write;
    std::uint8_t width;
    BusFault(std::uint32_t a, bool w, std::uint8_t bytes = 1) :
        std::runtime_error("unimplemented 68000 data bus access"),
        address(a), write(w), width(bytes) {}
};

// Providers must throw BusFault for unsupported accesses. A successful read
// followed by a rejected write is observable; this is not an atomic rollback.
struct Bus {
    virtual ~Bus() = default;
    virtual std::uint8_t read8(std::uint32_t address) { throw BusFault(address, false); }
    // CLR performs the transaction but discards its data. An override must
    // reproduce documented read side effects; it must not invent a value for
    // an unknown register. Strict providers retain the normal read boundary.
    virtual void read8_discard(std::uint32_t address) { (void)read8(address); }
    virtual void write8(std::uint32_t address, std::uint8_t) { throw BusFault(address, true); }
    // A word cycle is not silently decomposed into two potentially side-effecting
    // byte accesses. Each board provider must explicitly implement word lanes.
    virtual std::uint16_t read16(std::uint32_t address) { throw BusFault(address, false, 2); }
    virtual void read16_discard(std::uint32_t address) { (void)read16(address); }
    virtual void write16(std::uint32_t address, std::uint16_t) { throw BusFault(address, true, 2); }
};

inline bool stop(CPU& cpu, Stop reason) {
    cpu.stop = reason; cpu.stop_pc = cpu.pc; return false;
}

// Explicit architectural vector input, NOT Model 2C's power-on vector wiring.
// Registers and CCR which reset does not define remain marked unknown.
inline bool reset_from_vectors(CPU& cpu, std::uint32_t ssp, std::uint32_t pc) {
    if (pc & 1u) return stop(cpu, Stop::instruction_address);
    cpu = CPU{};
    cpu.pc = pc; cpu.a[7] = ssp; cpu.a_known[7] = true;
    cpu.sr = 0x2700u; cpu.sr_known = 0xffe0u;
    return true;
}

inline bool execution_allowed(CPU& cpu) {
    if (cpu.stop != Stop::none) return false;
    if (cpu.pc & 1u) return stop(cpu, Stop::instruction_address);
    // No trace exception, stack-bank switch or interrupt acceptance is modeled.
    if ((cpu.sr_known & 0xa700u) != 0xa700u) return stop(cpu, Stop::undefined_state);
    if ((cpu.sr & 0xa700u) != 0x2700u) return stop(cpu, Stop::unsupported_control);
    return true;
}

inline bool finish(CPU& cpu, std::uint32_t next) {
    cpu.pc = next; ++cpu.completed; return true;
}

inline void logical_flags(CPU& cpu, bool negative, bool zero) {
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~15u) | (negative ? 8u : 0u) | (zero ? 4u : 0u));
    cpu.sr_known |= 15u;  // X's value AND definedness are preserved.
}

// Original MC68000 brief indexed effective address. Extension bits 10..8 are
// reserved on this core; later-family scale/full-format encodings fail closed.
inline bool indexed_address(CPU& cpu, unsigned base, std::uint16_t extension,
                            std::uint32_t& address) {
    if (base >= 8u || (extension & 0x0700u))
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned index = (extension >> 12u) & 7u;
    const bool address_index = (extension & 0x8000u) != 0u;
    const bool long_index = (extension & 0x0800u) != 0u;
    if (!cpu.a_known[base] || (address_index && !cpu.a_known[index]))
        return stop(cpu, Stop::undefined_state);
    std::uint32_t value = 0;
    if (address_index) {
        value = cpu.a[index];
    } else {
        const std::uint32_t mask = long_index ? 0xffffffffu : 0xffffu;
        if ((cpu.d_known[index] & mask) != mask)
            return stop(cpu, Stop::undefined_state);
        value = cpu.d[index];
    }
    if (!long_index) {
        value &= 0xffffu;
        if (value & 0x8000u) value |= 0xffff0000u;
    }
    const std::uint32_t displacement =
        (extension & 0x0080u) ? (extension | 0xffffff00u) : (extension & 0x00ffu);
    address = cpu.a[base] + value + displacement;
    return true;
}

inline bool indexed_pc_address(CPU& cpu, std::uint32_t base,
                               std::uint16_t extension,
                               std::uint32_t& address) {
    if (extension & 0x0700u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned index = (extension >> 12u) & 7u;
    const bool address_index = (extension & 0x8000u) != 0u;
    const bool long_index = (extension & 0x0800u) != 0u;
    if (address_index && !cpu.a_known[index])
        return stop(cpu, Stop::undefined_state);
    std::uint32_t value = 0;
    if (address_index) {
        value = cpu.a[index];
    } else {
        const std::uint32_t mask = long_index ? 0xffffffffu : 0xffffu;
        if ((cpu.d_known[index] & mask) != mask)
            return stop(cpu, Stop::undefined_state);
        value = cpu.d[index];
    }
    if (!long_index) {
        value &= 0xffffu;
        if (value & 0x8000u) value |= 0xffff0000u;
    }
    const std::uint32_t displacement =
        (extension & 0x0080u) ? (extension | 0xffffff00u) : (extension & 0x00ffu);
    address = base + value + displacement;
    return true;
}

// Motorola PRM ANDI/ORI/EORI: Dn byte/word writes preserve upper bits, X is
// unchanged, NZ reflect the result and VC clear. Knownness is diagnostic
// metadata, not physical CPU state: masked-away unknown bits need no guess.
// kind: 0 = ORI, 1 = ANDI, 2 = EORI.
inline bool logic_immediate_d(CPU& cpu, unsigned bytes, unsigned kind, unsigned reg,
                              std::uint32_t immediate, std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) || kind > 2u || reg >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << (bytes * 8u)) - 1u;
    const std::uint32_t sign = 1u << (bytes * 8u - 1u);
    immediate &= mask;
    std::uint32_t value = cpu.d[reg] & mask, known = cpu.d_known[reg] & mask;
    if (kind == 0u) { value |= immediate; known |= immediate; }
    else if (kind == 1u) { value &= immediate; known |= ~immediate & mask; }
    else value ^= immediate;
    cpu.d[reg] = (cpu.d[reg] & ~mask) | value;
    cpu.d_known[reg] = (cpu.d_known[reg] & ~mask) | known;
    // Unknown flag payload bits are cleared deterministically, never marked
    // known. Z is already false if any known result bit is one.
    const bool negative_known = (known & sign) != 0;
    const bool known_one = (value & known) != 0;
    const bool zero_known = known_one || known == mask;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~15u) |
        (negative_known && (value & sign) ? 8u : 0u) |
        (zero_known && !known_one ? 4u : 0u));
    cpu.sr_known = static_cast<std::uint16_t>((cpu.sr_known & ~15u) | 3u |
        (negative_known ? 8u : 0u) | (zero_known ? 4u : 0u));
    return finish(cpu, next);
}

// MC68000 non-updating data operand read. A long uses two word transactions,
// high word first; each address reaches the physical 24-bit bus independently.
// Do not roll back a successful first read if the second read is rejected.
inline bool read_operand(CPU& cpu, Bus& bus, std::uint32_t address, unsigned bytes,
                         std::uint32_t& value) {
    if (bytes != 1u && bytes != 2u && bytes != 4u)
        return stop(cpu, Stop::unsupported_instruction);
    address &= 0x00ffffffu;
    if (bytes != 1u && (address & 1u)) {
        cpu.access_address = address;
        cpu.access_width = static_cast<std::uint8_t>(bytes); cpu.access_write = false;
        return stop(cpu, Stop::data_address);
    }
    if (bytes == 1u) value = bus.read8(address);
    else if (bytes == 2u) value = bus.read16(address);
    else {
        const std::uint32_t high = bus.read16(address);
        const std::uint32_t low = bus.read16((address + 2u) & 0x00ffffffu);
        value = (high << 16u) | low;
    }
    return true;
}

// BSR's stack push is HIGH word then LOW word, unlike MOVE.L predecrement.
// Motorola US4325121, Appendix B Sheet E, bsri2/3 and bsrw2/3, columns 193-194.
// SP arithmetic is 32-bit; only the separate physical bus addresses are 24-bit.
// On a provider refusal, CPU state is retained diagnostically while already
// accepted bus effects survive. This is NOT physical BERR/exception microstate.
inline bool branch_subroutine(CPU& cpu, Bus& bus, std::uint32_t target,
                              std::uint32_t return_pc) {
    if (!cpu.a_known[7]) return stop(cpu, Stop::undefined_state);
    const std::uint32_t stack = cpu.a[7] - 4u;
    const std::uint32_t address = stack & 0x00ffffffu;
    if (address & 1u) {
        cpu.access_address = address; cpu.access_width = 4; cpu.access_write = true;
        return stop(cpu, Stop::data_address);
    }
    bus.write16(address, static_cast<std::uint16_t>(return_pc >> 16u));
    bus.write16((address + 2u) & 0x00ffffffu, static_cast<std::uint16_t>(return_pc));
    cpu.a[7] = stack;
    return finish(cpu, target);
}

// RTS obtains its destination from actual bus data, never a host call stack.
// Like other direct branches, an odd or untranslated destination is diagnosed
// at the next generated step. Prefetch and address-error frames are not modeled.
inline bool return_subroutine(CPU& cpu, Bus& bus) {
    if (!cpu.a_known[7]) return stop(cpu, Stop::undefined_state);
    std::uint32_t target = 0;
    if (!read_operand(cpu, bus, cpu.a[7], 4u, target)) return false;
    cpu.a[7] += 4u;
    return finish(cpu, target);
}

inline bool compare_immediate(CPU& cpu, unsigned bytes, std::uint32_t destination,
                              std::uint32_t immediate, std::uint32_t next) {
    if (bytes != 1u && bytes != 2u && bytes != 4u)
        return stop(cpu, Stop::unsupported_instruction);
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << (bytes * 8u)) - 1u;
    const std::uint32_t sign = 1u << (bytes * 8u - 1u);
    destination &= mask; immediate &= mask;
    const std::uint32_t result = (destination - immediate) & mask;
    const bool overflow = ((destination ^ immediate) & (destination ^ result) & sign) != 0;
    // Comparison sets NZVC from destination - immediate; X is not consumed or
    // changed, including its knownness. No destination register/memory write.
    logical_flags(cpu, (result & sign) != 0, result == 0);
    if (overflow) cpu.sr |= 2u;
    if (destination < immediate) cpu.sr |= 1u;
    return finish(cpu, next);
}

// MC68000 CLR reads the destination before clearing it (Motorola PRM 4-74).
// Long operand reads are high word then low word. CLR.L writes are the reverse:
// low word then high word (Atari Hardware Bugs & Warnings, 26-Apr-1995, p.6).
// These are separate data transactions, not TAS's indivisible RMW bus cycle.
// This helper intentionally commits no CPU state on a diagnostic refusal;
// already accepted bus effects survive. It does not model BERR microstate.
inline bool clear_memory(CPU& cpu, Bus& bus, std::uint32_t address, unsigned bytes) {
    if (bytes != 1u && bytes != 2u && bytes != 4u)
        return stop(cpu, Stop::unsupported_instruction);
    address &= 0x00ffffffu;
    if (bytes != 1u && (address & 1u)) {
        cpu.access_address = address;
        cpu.access_width = static_cast<std::uint8_t>(bytes); cpu.access_write = false;
        return stop(cpu, Stop::data_address);
    }
    if (bytes == 1u) {
        bus.read8_discard(address); bus.write8(address, 0);
    } else if (bytes == 2u) {
        bus.read16_discard(address); bus.write16(address, 0);
    } else {
        const std::uint32_t low_address = (address + 2u) & 0x00ffffffu;
        bus.read16_discard(address); bus.read16_discard(low_address);
        bus.write16(low_address, 0); bus.write16(address, 0);
    }
    return true;
}

inline bool write_move(CPU& cpu, Bus& bus, std::uint32_t address, unsigned bytes,
                       std::uint32_t value) {
    address &= 0x00ffffffu;
    if (bytes == 1u) bus.write8(address, static_cast<std::uint8_t>(value));
    else if (bytes == 2u) {
        if (address & 1u) {
            cpu.access_address = address; cpu.access_width = 2; cpu.access_write = true;
            return stop(cpu, Stop::data_address);
        }
        bus.write16(address, static_cast<std::uint16_t>(value));
    } else if (bytes == 4u) {
        if (address & 1u) {
            cpu.access_address = address; cpu.access_width = 4; cpu.access_write = true;
            return stop(cpu, Stop::data_address);
        }
        // Ordinary MOVE.L writes the high word at the lower address first.
        // Predecrement and CLR.L have distinct transaction order and do not use
        // this helper.
        bus.write16(address, static_cast<std::uint16_t>(value >> 16u));
        bus.write16((address + 2u) & 0x00ffffffu,
                    static_cast<std::uint16_t>(value));
    } else return stop(cpu, Stop::unsupported_instruction);
    return true;
}

// MOVE (An)+,(Am)+ evaluates source before destination. Each postincrement is
// committed only after that operand's complete diagnostic bus transfer. Thus a
// refused destination can retain a completed source increment and accepted bus
// effects; this is not an MC68000 BERR exception/restart model.
inline bool move_memory_postincrement(CPU& cpu, Bus& bus, unsigned bytes,
                                      unsigned source, unsigned destination,
                                      std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) ||
        source >= 8u || destination >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    if (!cpu.a_known[source] || !cpu.a_known[destination])
        return stop(cpu, Stop::undefined_state);
    const unsigned source_increment = bytes == 1u && source == 7u ? 2u : bytes;
    const unsigned destination_increment = bytes == 1u && destination == 7u ? 2u : bytes;
    std::uint32_t value = 0;
    if (!read_operand(cpu, bus, cpu.a[source], bytes, value)) return false;
    cpu.a[source] += source_increment;
    if (!write_move(cpu, bus, cpu.a[destination], bytes, value)) return false;
    cpu.a[destination] += destination_increment;
    const std::uint32_t sign = 1u << (bytes * 8u - 1u);
    logical_flags(cpu, (value & sign) != 0, value == 0);
    return finish(cpu, next);
}

// MOVE evaluates and reads its source before evaluating the destination. If
// an address register participates in both operands, the indexed destination
// therefore observes the completed source postincrement.
inline bool move_postincrement_to_indexed(CPU& cpu, Bus& bus, unsigned bytes,
                                          unsigned source, unsigned base,
                                          std::uint16_t extension,
                                          std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) ||
        source >= 8u || base >= 8u || (extension & 0x0700u))
        return stop(cpu, Stop::unsupported_instruction);
    if (!cpu.a_known[source]) return stop(cpu, Stop::undefined_state);
    std::uint32_t value = 0;
    if (!read_operand(cpu, bus, cpu.a[source], bytes, value)) return false;
    cpu.a[source] += bytes == 1u && source == 7u ? 2u : bytes;
    std::uint32_t address = 0;
    if (!indexed_address(cpu, base, extension, address)) return false;
    if (!write_move(cpu, bus, address, bytes, value)) return false;
    const std::uint32_t sign = 1u << (bytes * 8u - 1u);
    logical_flags(cpu, (value & sign) != 0u, value == 0u);
    return finish(cpu, next);
}

inline bool shift_immediate(CPU& cpu, unsigned bytes, unsigned reg, unsigned count,
                            bool left, bool rotate, std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) || reg >= 8u || count < 1u || count > 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    if ((cpu.d_known[reg] & mask) != mask) return stop(cpu, Stop::undefined_state);
    const std::uint32_t sign = 1u << (bits - 1u);
    std::uint32_t value = cpu.d[reg] & mask;
    bool carry = false;
    for (unsigned i = 0; i < count; ++i) {
        carry = (value & (left ? sign : 1u)) != 0;
        value = left ? (value << 1u) & mask : value >> 1u;
        if (rotate && carry) value |= left ? 1u : sign;
    }
    cpu.d[reg] = (cpu.d[reg] & ~mask) | value;
    logical_flags(cpu, (value & sign) != 0, value == 0);
    if (carry) cpu.sr |= 1u;
    if (!rotate) {
        cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~16u) | (carry ? 16u : 0u));
        cpu.sr_known |= 16u;
    }
    return finish(cpu, next);
}

// MC68000 register-count logical shifts use the count register's low six bits.
// A zero count clears C but leaves X (and its knownness) unchanged; a nonzero
// count copies the final shifted-out bit to both C and X.
inline bool logical_shift_register(CPU& cpu, unsigned bytes, unsigned destination,
                                   unsigned count_register, bool left,
                                   std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) ||
        destination >= 8u || count_register >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    if ((cpu.d_known[destination] & mask) != mask ||
        (cpu.d_known[count_register] & 63u) != 63u)
        return stop(cpu, Stop::undefined_state);
    const unsigned count = cpu.d[count_register] & 63u;
    const std::uint32_t sign = 1u << (bits - 1u);
    std::uint32_t value = cpu.d[destination] & mask;
    bool carry = false;
    for (unsigned i = 0; i < count; ++i) {
        carry = (value & (left ? sign : 1u)) != 0u;
        value = left ? (value << 1u) & mask : value >> 1u;
    }
    cpu.d[destination] = (cpu.d[destination] & ~mask) | value;
    cpu.d_known[destination] |= mask;
    const std::uint16_t nz = static_cast<std::uint16_t>(
        (value & sign ? 8u : 0u) | (value == 0u ? 4u : 0u));
    if (count != 0u) {
        cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
            (carry ? 17u : 0u) | nz);
        cpu.sr_known |= 31u;
    } else {
        cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~15u) | nz);
        cpu.sr_known |= 15u;
    }
    return finish(cpu, next);
}

// Motorola ADDQ to Dn: byte/word updates retain the upper register bits, while
// all five arithmetic condition codes describe the sized addition. Unknown
// input bits stop rather than guessing carry or overflow.
inline bool add_quick_data(CPU& cpu, unsigned bytes, unsigned reg,
                           unsigned immediate, std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) || reg >= 8u ||
        immediate < 1u || immediate > 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu :
        (1u << (bytes * 8u)) - 1u;
    if ((cpu.d_known[reg] & mask) != mask)
        return stop(cpu, Stop::undefined_state);
    const std::uint32_t sign = 1u << (bytes * 8u - 1u);
    const std::uint32_t value = cpu.d[reg] & mask;
    const std::uint32_t result = (value + immediate) & mask;
    const bool carry = static_cast<std::uint64_t>(value) + immediate > mask;
    const bool overflow = ((~(value ^ immediate) & (value ^ result) & sign) != 0u);
    cpu.d[reg] = (cpu.d[reg] & ~mask) | result;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
        (carry ? 17u : 0u) | ((result & sign) ? 8u : 0u) |
        (result == 0u ? 4u : 0u) | (overflow ? 2u : 0u));
    cpu.sr_known |= 31u;
    return finish(cpu, next);
}

inline bool add_immediate_data(CPU& cpu, unsigned bytes, unsigned reg,
                               std::uint32_t immediate, std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) || reg >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    if ((cpu.d_known[reg] & mask) != mask)
        return stop(cpu, Stop::undefined_state);
    immediate &= mask;
    const std::uint32_t value = cpu.d[reg] & mask;
    const std::uint32_t result = (value + immediate) & mask;
    const std::uint32_t sign = 1u << (bits - 1u);
    const bool carry = static_cast<std::uint64_t>(value) + immediate > mask;
    const bool overflow = (~(value ^ immediate) & (value ^ result) & sign) != 0u;
    cpu.d[reg] = (cpu.d[reg] & ~mask) | result;
    cpu.d_known[reg] |= mask;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
        (carry ? 17u : 0u) | (result & sign ? 8u : 0u) |
        (result == 0u ? 4u : 0u) | (overflow ? 2u : 0u));
    cpu.sr_known |= 31u;
    return finish(cpu, next);
}

// Motorola SUB Dn,Dn: the sized destination minus source sets all five
// arithmetic condition codes. C and X both represent unsigned borrow.
inline bool subtract_data(CPU& cpu, unsigned bytes, unsigned source,
                          unsigned destination, std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) ||
        source >= 8u || destination >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    if ((cpu.d_known[source] & mask) != mask ||
        (cpu.d_known[destination] & mask) != mask)
        return stop(cpu, Stop::undefined_state);
    const std::uint32_t source_value = cpu.d[source] & mask;
    const std::uint32_t destination_value = cpu.d[destination] & mask;
    const std::uint32_t result = (destination_value - source_value) & mask;
    const std::uint32_t sign = 1u << (bits - 1u);
    const bool borrow = destination_value < source_value;
    const bool overflow = ((destination_value ^ source_value) &
                           (destination_value ^ result) & sign) != 0;
    cpu.d[destination] = (cpu.d[destination] & ~mask) | result;
    cpu.d_known[destination] |= mask;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
        (borrow ? 17u : 0u) | (result & sign ? 8u : 0u) |
        (result == 0u ? 4u : 0u) | (overflow ? 2u : 0u));
    cpu.sr_known |= 31u;
    return finish(cpu, next);
}

inline bool subtract_immediate_data(CPU& cpu, unsigned bytes,
                                    unsigned destination,
                                    std::uint32_t immediate,
                                    std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) || destination >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    if ((cpu.d_known[destination] & mask) != mask)
        return stop(cpu, Stop::undefined_state);
    immediate &= mask;
    const std::uint32_t destination_value = cpu.d[destination] & mask;
    const std::uint32_t result = (destination_value - immediate) & mask;
    const std::uint32_t sign = 1u << (bits - 1u);
    const bool borrow = destination_value < immediate;
    const bool overflow = ((destination_value ^ immediate) &
                           (destination_value ^ result) & sign) != 0u;
    cpu.d[destination] = (cpu.d[destination] & ~mask) | result;
    cpu.d_known[destination] |= mask;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
        (borrow ? 17u : 0u) | (result & sign ? 8u : 0u) |
        (result == 0u ? 4u : 0u) | (overflow ? 2u : 0u));
    cpu.sr_known |= 31u;
    return finish(cpu, next);
}

inline bool subtract_quick_data(CPU& cpu, unsigned bytes, unsigned destination,
                                unsigned immediate, std::uint32_t next) {
    if (immediate < 1u || immediate > 8u)
        return stop(cpu, Stop::unsupported_instruction);
    return subtract_immediate_data(cpu, bytes, destination, immediate, next);
}

inline bool subtract_quick_memory(CPU& cpu, Bus& bus, std::uint32_t address,
                                  unsigned bytes, unsigned immediate,
                                  std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) ||
        immediate < 1u || immediate > 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    std::uint32_t destination = 0;
    if (!read_operand(cpu, bus, address, bytes, destination)) return false;
    const std::uint32_t result = (destination - immediate) & mask;
    const std::uint32_t sign = 1u << (bits - 1u);
    const bool borrow = destination < immediate;
    const bool overflow = ((destination ^ immediate) &
                           (destination ^ result) & sign) != 0u;
    if (!write_move(cpu, bus, address, bytes, result)) return false;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
        (borrow ? 17u : 0u) | (result & sign ? 8u : 0u) |
        (result == 0u ? 4u : 0u) | (overflow ? 2u : 0u));
    cpu.sr_known |= 31u;
    return finish(cpu, next);
}

inline bool add_quick_memory(CPU& cpu, Bus& bus, std::uint32_t address,
                             unsigned bytes, unsigned immediate,
                             std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) ||
        immediate < 1u || immediate > 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    std::uint32_t destination = 0;
    if (!read_operand(cpu, bus, address, bytes, destination)) return false;
    const std::uint32_t result = (destination + immediate) & mask;
    const std::uint32_t sign = 1u << (bits - 1u);
    const bool carry = static_cast<std::uint64_t>(destination) + immediate > mask;
    const bool overflow = (~(destination ^ immediate) &
                           (destination ^ result) & sign) != 0u;
    if (!write_move(cpu, bus, address, bytes, result)) return false;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
        (carry ? 17u : 0u) | (result & sign ? 8u : 0u) |
        (result == 0u ? 4u : 0u) | (overflow ? 2u : 0u));
    cpu.sr_known |= 31u;
    return finish(cpu, next);
}

inline bool bit_set_immediate_memory(CPU& cpu, Bus& bus,
                                     std::uint32_t address, unsigned bit,
                                     std::uint32_t next) {
    std::uint32_t value = 0;
    if (!read_operand(cpu, bus, address, 1u, value)) return false;
    const std::uint32_t mask = 1u << (bit & 7u);
    const bool zero = (value & mask) == 0u;
    if (!write_move(cpu, bus, address, 1u, value | mask)) return false;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~4u) |
                                       (zero ? 4u : 0u));
    cpu.sr_known |= 4u;
    return finish(cpu, next);
}

inline bool multiply_unsigned_word(CPU& cpu, unsigned source,
                                   unsigned destination, std::uint32_t next) {
    if (source >= 8u || destination >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    if ((cpu.d_known[source] & 0xffffu) != 0xffffu ||
        (cpu.d_known[destination] & 0xffffu) != 0xffffu)
        return stop(cpu, Stop::undefined_state);
    const std::uint32_t result = (cpu.d[source] & 0xffffu) *
                                 (cpu.d[destination] & 0xffffu);
    cpu.d[destination] = result;
    cpu.d_known[destination] = 0xffffffffu;
    logical_flags(cpu, (result & 0x80000000u) != 0u, result == 0u);
    return finish(cpu, next);
}

inline bool movem_store(CPU& cpu, Bus& bus, unsigned bytes, unsigned base,
                        std::uint16_t mask, bool predecrement,
                        std::uint32_t next) {
    if ((bytes != 2u && bytes != 4u) || base >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    if (!cpu.a_known[base]) return stop(cpu, Stop::undefined_state);
    for (unsigned bit = 0; bit < 16u; ++bit) {
        if (!(mask & (1u << bit))) continue;
        const bool address = predecrement ? bit < 8u : bit >= 8u;
        const unsigned reg = predecrement ?
            (bit < 8u ? 7u - bit : 15u - bit) :
            (bit < 8u ? bit : bit - 8u);
        if (address) {
            if (!cpu.a_known[reg]) return stop(cpu, Stop::undefined_state);
        } else {
            const std::uint32_t required = bytes == 4u ? 0xffffffffu : 0xffffu;
            if ((cpu.d_known[reg] & required) != required)
                return stop(cpu, Stop::undefined_state);
        }
    }
    const std::uint32_t initial_base = cpu.a[base];
    std::uint32_t address = initial_base;
    for (unsigned bit = 0; bit < 16u; ++bit) {
        if (!(mask & (1u << bit))) continue;
        const bool address_register = predecrement ? bit < 8u : bit >= 8u;
        const unsigned reg = predecrement ?
            (bit < 8u ? 7u - bit : 15u - bit) :
            (bit < 8u ? bit : bit - 8u);
        const std::uint32_t value = address_register ?
            (reg == base ? initial_base : cpu.a[reg]) : cpu.d[reg];
        if (predecrement) address -= bytes;
        if (!write_move(cpu, bus, address, bytes, value)) return false;
        if (predecrement) cpu.a[base] = address;
        else address += bytes;
    }
    return finish(cpu, next);
}

inline bool movem_load_postincrement(CPU& cpu, Bus& bus, unsigned bytes,
                                     unsigned base, std::uint16_t mask,
                                     std::uint32_t next) {
    if ((bytes != 2u && bytes != 4u) || base >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    if (!cpu.a_known[base]) return stop(cpu, Stop::undefined_state);
    std::uint32_t address = cpu.a[base];
    for (unsigned bit = 0; bit < 16u; ++bit) {
        if (!(mask & (1u << bit))) continue;
        std::uint32_t value = 0;
        if (!read_operand(cpu, bus, address, bytes, value)) return false;
        address += bytes;
        if (bit < 8u) {
            if (bytes == 2u && (value & 0x8000u)) value |= 0xffff0000u;
            cpu.d[bit] = value;
            cpu.d_known[bit] = 0xffffffffu;
        } else if (bit - 8u != base) {
            if (bytes == 2u && (value & 0x8000u)) value |= 0xffff0000u;
            cpu.a[bit - 8u] = value;
            cpu.a_known[bit - 8u] = true;
        }
        // Motorola specifies that a listed postincrement base ignores the
        // loaded memory value and retains the postincremented effective address.
        cpu.a[base] = address;
    }
    return finish(cpu, next);
}

// Motorola NEGX supports multi-precision negation: X is an input and C/X
// report the borrow. Z is cumulative, remaining set only when it was already
// set and this sized result is zero. An unknown retained Z remains unknown.
inline bool negate_extend_data(CPU& cpu, unsigned bytes, unsigned reg,
                               std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) || reg >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    if ((cpu.d_known[reg] & mask) != mask || !(cpu.sr_known & 16u))
        return stop(cpu, Stop::undefined_state);
    const std::uint32_t value = cpu.d[reg] & mask;
    const std::uint32_t extend = (cpu.sr & 16u) ? 1u : 0u;
    const std::uint32_t result = (0u - value - extend) & mask;
    const std::uint32_t sign = 1u << (bits - 1u);
    const bool borrow = value != 0u || extend != 0u;
    const bool overflow = (value & sign) != 0u && (result & sign) != 0u;
    const bool zero = result == 0u && (cpu.sr & 4u) != 0u;
    const bool zero_known = result != 0u || (cpu.sr_known & 4u) != 0u;
    cpu.d[reg] = (cpu.d[reg] & ~mask) | result;
    cpu.d_known[reg] |= mask;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
        (borrow ? 17u : 0u) | (result & sign ? 8u : 0u) |
        (zero ? 4u : 0u) | (overflow ? 2u : 0u));
    cpu.sr_known = static_cast<std::uint16_t>((cpu.sr_known & ~31u) | 27u |
        (zero_known ? 4u : 0u));
    return finish(cpu, next);
}

inline bool negate_data(CPU& cpu, unsigned bytes, unsigned reg,
                        std::uint32_t next) {
    if ((bytes != 1u && bytes != 2u && bytes != 4u) || reg >= 8u)
        return stop(cpu, Stop::unsupported_instruction);
    const unsigned bits = bytes * 8u;
    const std::uint32_t mask = bytes == 4u ? 0xffffffffu : (1u << bits) - 1u;
    if ((cpu.d_known[reg] & mask) != mask)
        return stop(cpu, Stop::undefined_state);
    const std::uint32_t value = cpu.d[reg] & mask;
    const std::uint32_t result = (0u - value) & mask;
    const std::uint32_t sign = 1u << (bits - 1u);
    const bool borrow = value != 0u;
    cpu.d[reg] = (cpu.d[reg] & ~mask) | result;
    cpu.d_known[reg] |= mask;
    cpu.sr = static_cast<std::uint16_t>((cpu.sr & ~31u) |
        (borrow ? 17u : 0u) | (result & sign ? 8u : 0u) |
        (result == 0u ? 4u : 0u) | (value == sign ? 2u : 0u));
    cpu.sr_known |= 31u;
    return finish(cpu, next);
}

inline bool swap_data(CPU& cpu, unsigned reg, std::uint32_t next) {
    if (reg >= 8u) return stop(cpu, Stop::unsupported_instruction);
    if (cpu.d_known[reg] != 0xffffffffu)
        return stop(cpu, Stop::undefined_state);
    const std::uint32_t result = (cpu.d[reg] << 16u) | (cpu.d[reg] >> 16u);
    cpu.d[reg] = result;
    logical_flags(cpu, (result & 0x80000000u) != 0u, result == 0u);
    return finish(cpu, next);
}

inline bool move_sr(CPU& cpu, std::uint16_t value, std::uint32_t next) {
    if (!(cpu.sr_known & 0x2000u)) return stop(cpu, Stop::undefined_state);
    if (!(cpu.sr & 0x2000u)) return stop(cpu, Stop::privilege);
    if ((value & 0xffe0u) != 0x2700u) return stop(cpu, Stop::unsupported_control);
    cpu.sr = value; cpu.sr_known = 0xffffu;
    return finish(cpu, next);
}

inline bool condition(CPU& cpu, unsigned cc, bool& result) {
    static constexpr std::uint16_t needed[16] = {0,0,5,5,1,1,4,4,2,2,8,8,10,10,14,14};
    if (cc > 15u) return stop(cpu, Stop::unsupported_instruction);
    if ((cpu.sr_known & needed[cc]) != needed[cc]) return stop(cpu, Stop::undefined_state);
    const bool c = (cpu.sr & 1u) != 0, v = (cpu.sr & 2u) != 0;
    const bool z = (cpu.sr & 4u) != 0, n = (cpu.sr & 8u) != 0;
    switch(cc) {
        case 0: result = true; break;
        case 1: result = false; break;
        case 2: result = !c && !z; break;
        case 3: result = c || z; break;
        case 4: result = !c; break;
        case 5: result = c; break;
        case 6: result = !z; break;
        case 7: result = z; break;
        case 8: result = !v; break;
        case 9: result = v; break;
        case 10: result = !n; break;
        case 11: result = n; break;
        case 12: result = n == v; break;
        case 13: result = n != v; break;
        case 14: result = !z && n == v; break;
        case 15: result = z || n != v; break;
    }
    return true;
}
}  // namespace arcaderecomp::m68k
