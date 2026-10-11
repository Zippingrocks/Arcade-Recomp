"""Synthetic, ROM-free Model 2C geometry aperture decode regression tests.

Published CPU-visible addresses are not evidence of real buffer contents,
MB86235 upload semantics, FIFO readiness, or any video timing behavior.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def native(body):
    compilers = [c for n in ("g++", "clang++") if (c := shutil.which(n))]
    if not compilers:
        raise unittest.SkipTest("A C++17 compiler is required")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-model2c-geo-") as tmp:
            path = Path(tmp)
            source, exe = path / "geo.cpp", path / "geo"
            source.write_text('#include "model2c_bus.hpp"\n'
                              'using namespace arcaderecomp_model2c;\n' + body,
                              encoding="utf-8")
            build = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT / "runtime"), str(source), "-o", str(exe)
            ], capture_output=True, text=True, timeout=45)
            if build.returncode:
                raise AssertionError(compiler + ": " + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True,
                                 text=True, timeout=25)
            if run.returncode:
                raise AssertionError(compiler + ": exit " +
                                     str(run.returncode) + ": " + run.stderr)


class Model2CGeometryApertures(unittest.TestCase):
    def test_published_regions_exact_boundaries_no_extra_registers(self):
        native(r"""
int main() {
    StrictBus bus(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0u));
    struct Aperture {std::uint32_t lo, hi; Region region;};
    const Aperture known[] = {
        {0x00800000u, 0x00803fffu, Region::geometry_interface},
        {0x00804000u, 0x00807fffu, Region::geometry_program_port},
        {0x00880000u, 0x00883fffu, Region::coprocessor_function_port},
        {0x00884000u, 0x00887fffu, Region::coprocessor_fifo_port},
        {0x00900000u, 0x0097ffffu, Region::geometry_buffer},
        {0x00980000u, 0x00980003u, Region::coprocessor_control},
        {0x00980004u, 0x00980007u, Region::geometry_fifo_status},
        {0x00980008u, 0x0098000bu, Region::geometry_control},
        {0x0098000cu, 0x0098000fu, Region::video_control},
        {0x00980014u, 0x00980017u, Region::coprocessor_status}
    };
    for (const auto& k : known) {
        if (bus.classify(k.lo) != k.region ||
            bus.classify(k.hi) != k.region) return 1;
        for (unsigned width : {1u, 2u, 4u}) {
            try {(void)bus.read(k.lo, width); return 2;}
            catch (const DeviceAccessFault& e) {
                if (e.region != k.region || e.address != k.lo ||
                    e.width != width || e.write) return 3;
            }
            try {bus.write(k.lo, width, 0x12345678u); return 4;}
            catch (const DeviceAccessFault& e) {
                if (e.region != k.region || e.address != k.lo ||
                    e.width != width || !e.write) return 5;
            }
        }
    }
    for (const auto gap : {0x007fffffu, 0x00808000u, 0x0087ffffu,
                           0x00888000u, 0x008fffffu, 0x00980010u,
                           0x00980018u, 0x00a00000u}) {
        if (bus.classify(gap) != Region::unmapped) return 6;
    }
    if (!bus.writes().empty() || bus.pending_timing_writes()) return 7;
    bus.write(0x00500100u, 4u, 0xdeadbeefu);
    if (bus.read(0x00500100u, 4u) != 0xdeadbeefu ||
        bus.writes().size() != 1u) return 8;
    return 0;
}
""")

    def test_native_callbacks_and_sync_read_do_not_invent_geometry_data(self):
        native(r"""
int main() {
    StrictBus bus(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0u));
    auto cb = bus.callbacks();
    for (const auto address : {0x00800000u, 0x00804000u,
                               0x00880000u, 0x00884000u,
                               0x00900000u, 0x00980000u,
                               0x00980004u, 0x00980008u,
                               0x0098000cu, 0x00980014u}) {
        std::uint32_t dst = 0xfeedbeefu;
        if (cb.read32_sync(cb.ctx, address, &dst) || dst != 0xfeedbeefu)
            return 1;
        try {(void)cb.read32(cb.ctx, address); return 2;}
        catch (const DeviceAccessFault& e) {
            if (e.address != address || e.write || e.width != 4u)
                return 3;
        }
        try {cb.write32(cb.ctx, address, 0xa5a5a5a5u); return 4;}
        catch (const DeviceAccessFault& e) {
            if (e.address != address || !e.write || e.width != 4u)
                return 5;
        }
    }
    if (!bus.writes().empty() || bus.pending_timing_writes()) return 6;
    return 0;
}
""")


    def test_native_tgpx4_upload_ports_fault_without_writing_program(self):
        native(r"""
int main() {
    StrictBus bus(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0u));
    const auto native = bus.callbacks();
    const std::uint32_t controls[] = {0x80000000u, 0x00000000u};
    for (auto control : controls) {
        try {native.write32(native.ctx, 0x00980000u, control); return 1;}
        catch(const DeviceAccessFault& e) {
            if (!e.write || e.region != Region::coprocessor_control ||
                e.address != 0x00980000u || e.width != 4u) return 2;
        }
    }
    for (std::uint32_t value : {0x12345678u, 0xdeadbeefu}) {
        try {native.write32(native.ctx, 0x00884000u, value); return 3;}
        catch(const DeviceAccessFault& e) {
            if (!e.write || e.region != Region::coprocessor_fifo_port ||
                e.address != 0x00884000u || e.width != 4u) return 4;
        }
    }
    // A documented aperture is NOT an accepted upload or copro execution.
    if (!bus.writes().empty() || bus.pending_timing_writes()) return 5;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
