#pragma once
#include <array>
#include <cstdint>
#include <stdexcept>

namespace arcaderecomp::m68k {
enum class Stop {
    none, unsupported_instruction, untranslated_pc, instruction_address,
    undefined_state, unsupported_control, privilege, bus_access
};

struct CPU {
    std::array<std::uint32_t, 8> d{}, a{}, d_known{};
    std::array<bool, 8> a_known{};
    std::uint32_t pc = 0;
    std::uint16_t sr = 0, sr_known = 0;
    Stop stop = Stop::none;
    std::uint32_t stop_pc = 0, access_address = 0;
    bool access_write = false;
    std::uint64_t completed = 0;
};

struct BusFault : std::runtime_error {
    std::uint32_t address;
    bool write;
    BusFault(std::uint32_t a, bool w) : std::runtime_error("unimplemented 68000 data bus access"),
        address(a), write(w) {}
};

// Providers must throw BusFault for unsupported accesses. A successful read
// followed by a rejected write is observable; this is not an atomic rollback.
struct Bus {
    virtual ~Bus() = default;
    virtual std::uint8_t read8(std::uint32_t address) { throw BusFault(address, false); }
    virtual void write8(std::uint32_t address, std::uint8_t) { throw BusFault(address, true); }
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
