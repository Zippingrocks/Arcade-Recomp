// Independent Intel 80960KB CPYSRE/CPYRSRE, canonical normal subset.
// Intel KB manual (Mar 1988), pp. 11-48 and 12-20. Source1 supplies
// magnitude, source2 supplies sign. No host floating arithmetic.
#pragma once
#include "i960_frame_runtime.hpp"
#include <cstdint>

namespace arcaderecomp_generated {
static inline bool copy_sign_extended_normal(CPU& cpu,
    unsigned magnitude_source, bool magnitude_fp,
    unsigned sign_source, bool sign_fp,
    unsigned destination, bool destination_fp, bool reverse) {
    const auto valid = [](unsigned i, bool fp) {
        return fp ? i < 4u : i < 32u && (i & 3u) == 0u;
    };
    if (!(magnitude_fp || sign_fp || destination_fp) ||
        !valid(magnitude_source,magnitude_fp) || !valid(sign_source,sign_fp) ||
        !valid(destination,destination_fp))
        return stop(cpu,StopCode::untranslated);
    if ((magnitude_fp && !cpu.fp_defined[magnitude_source]) ||
        (sign_fp && !cpu.fp_defined[sign_source]))
        return stop(cpu,StopCode::undefined_floating_point_register);
    const auto read = [&cpu](unsigned i,bool fp) {
        return fp ? cpu.fp[i] : ExtendedReal{cpu.r[i],cpu.r[i+1u],
            static_cast<std::uint16_t>(cpu.r[i+2u] & 0xffffu)};
    };
    // Gather both sources before any destination write, including aliases.
    ExtendedReal magnitude = read(magnitude_source,magnitude_fp);
    const ExtendedReal sign = read(sign_source,sign_fp);
    const auto normal = [](const ExtendedReal& v) {
        const auto exponent = v.high & 0x7fffu;
        return exponent != 0u && exponent != 0x7fffu &&
               (v.middle & 0x80000000u) != 0u;
    };
    // Chapter 11's reserved-encoding entry and Chapter 12's nonarithmetic
    // discussion differ for denormals. Do not resolve that ambiguity by
    // guessing normalization/fault behavior; keep this subset normal-only.
    if (!normal(magnitude) || !normal(sign))
        return stop(cpu,StopCode::unsupported_floating_format);
    const std::uint16_t sign_bit = static_cast<std::uint16_t>(
        (sign.high ^ (reverse ? 0x8000u : 0u)) & 0x8000u);
    magnitude.high = static_cast<std::uint16_t>((magnitude.high & 0x7fffu) | sign_bit);
    if (destination_fp) {
        cpu.fp[destination] = magnitude;
        cpu.fp_defined[destination] = true;
    } else {
        cpu.r[destination] = magnitude.low;
        cpu.r[destination+1u] = magnitude.middle;
        cpu.r[destination+2u] = magnitude.high;
    }
    return true;
}
} // namespace arcaderecomp_generated
