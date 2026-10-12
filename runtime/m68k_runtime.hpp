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
    } else return stop(cpu, Stop::unsupported_instruction);
    return true;
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
