// Intel 80960KB DIVR 78Bh, exact IEEE binary32 GPR subset.
// Numerator is src2; divisor is src1. All computation is integer-only.
// Exceptional/inexact forms halt without changing destination or AC.
// These stops are diagnostics, NOT modeled architected fault delivery.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>
namespace arcaderecomp_generated {
static inline bool divide_real32_exact(CPU& cpu, std::uint32_t denominator,
                                       std::uint32_t numerator,
                                       unsigned dst) {
    if (dst >= 32u) return stop(cpu, StopCode::untranslated);
    const unsigned de=(denominator>>23u)&255u, ne=(numerator>>23u)&255u;
    const unsigned df=denominator&0x7fffffu, nf=numerator&0x7fffffu;
    const bool dz=de==0u && df==0u, nz=ne==0u && nf==0u;
    if (de==255u || ne==255u || (de==0u && !dz) || (ne==0u && !nz))
        return stop(cpu,StopCode::unsupported_floating_format);
    if (dz) // 0/0 and nonzero/0 need unimplemented FP fault handling.
        return stop(cpu,StopCode::unsupported_floating_division_fault);
    const std::uint32_t sign=(denominator^numerator)&0x80000000u;
    if (nz) { cpu.r[dst]=sign; return true; }
    const std::uint32_t d=0x800000u|df, n=0x800000u|nf;
    const bool less=n<d;
    const std::int32_t biased=static_cast<std::int32_t>(ne)-
        static_cast<std::int32_t>(de)+127-(less?1:0);
    if (biased<1 || biased>254)
        return stop(cpu,StopCode::unsupported_floating_format);
    const std::uint64_t scaled=static_cast<std::uint64_t>(n) <<
        (less?24u:23u);
    if (scaled%d!=0u)
        return stop(cpu,StopCode::unsupported_floating_rounding);
    const std::uint64_t quotient=scaled/d;
    if (quotient<0x800000u || quotient>=0x1000000u)
        return stop(cpu,StopCode::unsupported_floating_format);
    cpu.r[dst]=sign|(static_cast<std::uint32_t>(biased)<<23u)|
        (static_cast<std::uint32_t>(quotient)&0x7fffffu);
    return true;
}
} // namespace arcaderecomp_generated
