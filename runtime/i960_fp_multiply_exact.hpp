// ArcadeRecomp — Intel 80960KB MULR (78Ch), exact IEEE real32 subset.
// Implemented from Intel KB arithmetic documentation, NOT Sega game code.
// Signed zeros and normal finite products that are exactly representable
// are supported. Special operands, subnormals, over/underflow and inexact
// results stop BEFORE writing destination because the Intel AC precision,
// exception flags and fault delivery are not yet modeled.
// All calculations use bounded unsigned integer operations, never host FP.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {
static inline bool multiply_real32_exact(CPU& cpu, std::uint32_t a,
                                         std::uint32_t b,
                                         unsigned destination) {
    if (destination >= 32u)
        return stop(cpu, StopCode::untranslated);
    const std::uint32_t ae = (a >> 23u) & 0xffu;
    const std::uint32_t be = (b >> 23u) & 0xffu;
    const std::uint32_t af = a & 0x7fffffu;
    const std::uint32_t bf = b & 0x7fffffu;
    const bool az = (ae == 0u && af == 0u);
    const bool bz = (be == 0u && bf == 0u);
    const std::uint32_t sign = (a ^ b) & 0x80000000u;
    if (ae == 0xffu || be == 0xffu ||
        (ae == 0u && !az) || (be == 0u && !bz))
        return stop(cpu, StopCode::unsupported_floating_format);
    // Exactly signed zero, even if both operands are zero. Sign comes
    // from the product of their signs, not the ambient rounding mode.
    if (az || bz) {
        cpu.r[destination] = sign;
        return true;
    }
    const std::uint64_t product =
        static_cast<std::uint64_t>(0x800000u | af) *
        static_cast<std::uint64_t>(0x800000u | bf);
    // Each input has a 24-bit significand; product is in [2^46, 2^48).
    const bool high = (product & (std::uint64_t{1} << 47u)) != 0u;
    const unsigned discarded_bits = high ? 24u : 23u;
    const std::int32_t biased = static_cast<std::int32_t>(ae) +
        static_cast<std::int32_t>(be) - 127 + (high ? 1 : 0);
    if (biased < 1 || biased > 254)
        return stop(cpu, StopCode::unsupported_floating_format);
    // Requiring every discarded bit to be zero means the binary32
    // result is exact; no AC rounding direction or inexact flag needed.
    if ((product & ((std::uint64_t{1} << discarded_bits) - 1u)) != 0u)
        return stop(cpu, StopCode::unsupported_floating_rounding);
    const std::uint32_t significand =
        static_cast<std::uint32_t>(product >> discarded_bits);
    cpu.r[destination] = sign | (static_cast<std::uint32_t>(biased) << 23u) |
        (significand & 0x7fffffu);
    return true;
}
} // namespace arcaderecomp_generated
