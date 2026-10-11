"""ROM-free GCC/Clang UBSan tests for strict Model 2C geometry access telemetry."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def native(body):
    compilers = [p for name in ("g++", "clang++") if (p := shutil.which(name)]
    if not compilers:
        raise unittest.SkipTest("C++17 host compiler unavailable")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-geo-trace-") as d:
            folder = Path(d)
            src, out = folder / "test.cpp", folder / "test"
            src.write_text('#include "model2c_bus.hpp"\n'
                           'using namespace arcaderecomp_model2c;\n' + body)
            cmd = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                   "-Werror", "-fsanitize=undefined",
                   "-fno-sanitize-recover=all", "-I",
                   str(ROOT / "runtime"), str(src), "-o", str(out)]
            built = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=45)
            if built.returncode:
                raise AssertionError(compiler + ": " + built.stderr)
            result = subprocess.run([str(out)], capture_output=True, text=True,
                                    timeout=25)
            if result.returncode:
                raise AssertionError(compiler + ": exit " +
                                     str(result.returncode) + ": " + result.stderr)


class GeometryAccessTraceTests(unittest.TestCase):
    def test_refused_writes_reads_never_look_like_executed_program(self):
        native(r"""
int main() {
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    if (!board.geometry_access_trace().empty() ||
        board.geometry_access_trace_total() != 0u) return 1;
    try {board.write(0x00980000u,4u,0x80000000u);return 2;}
    catch (const DeviceAccessFault& e) {
        if (e.region!=Region::coprocessor_control||!e.write)return 3;
    }
    if (!board.geometry_access_trace().empty())return 4; // disabled by default
    board.enable_geometry_access_trace();
    auto cb=board.callbacks();
    try {cb.write32(cb.ctx,0x00980000u,0x80000000u);return 5;}
    catch (const DeviceAccessFault& e) {
        if(e.address!=0x00980000u||!e.write)return 6;
    }
    try {cb.write32(cb.ctx,0x00884000u,0xdeadbeefu);return 7;}
    catch(const DeviceAccessFault& e) {
        if(e.region!=Region::coprocessor_fifo_port||!e.write)return 8;
    }
    try {(void)cb.read32(cb.ctx,0x00980014u);return 9;}
    catch(const DeviceAccessFault& e) {
        if(e.region!=Region::coprocessor_status||e.write)return 10;
    }
    const auto& t=board.geometry_access_trace();
    if(t.size()!=3u||board.geometry_access_trace_total()!=3u)return 11;
    for(unsigned i=0;i<3u;++i)
        if(t[i].ordinal!=i+1u||t[i].completed)return 12;
    if(!t[0].write||!t[0].value_known||t[0].value!=0x80000000u||
       t[0].address!=0x00980000u)return 13;
    if(!t[1].write||!t[1].value_known||t[1].value!=0xdeadbeefu||
       t[1].address!=0x00884000u)return 14;
    if(t[2].write||t[2].value_known||
       t[2].region!=Region::coprocessor_status)return 15;
    std::uint32_t out=0xfeedfaceu;
    if(cb.read32_sync(cb.ctx,0x00980014u,&out)||
       out!=0xfeedfaceu||t.size()!=3u)return 16;
    if(!board.writes().empty()||board.pending_timing_writes())return 17;
    return 0;
}
""")

    def test_bounded_prefix_loss_disable_reenable_clear_and_ram_isolation(self):
        native(r"""
int main() {
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    if(board.geometry_access_trace_limit()!=4096u)return 1;
    board.enable_geometry_access_trace();
    board.set_geometry_access_trace_limit(2u);
    for(unsigned i=0;i<100u;++i) {
        try{board.write(0x00884000u,4u,i);return 2;}
        catch(const DeviceAccessFault& e) {
            if(e.region!=Region::coprocessor_fifo_port)return 3;
        }
    }
    const auto& t=board.geometry_access_trace();
    if(t.size()!=2u||board.geometry_access_trace_total()!=100u||
       board.geometry_access_trace_dropped()!=98u||
       !board.geometry_access_trace_truncated()||
       t[0].ordinal!=1u||t[0].value!=0u||
       t[1].ordinal!=2u||t[1].value!=1u)return 4;
    try{board.set_geometry_access_trace_limit(1u);return 5;}
    catch(const std::invalid_argument&){}
    board.enable_geometry_access_trace(false);
    try{(void)board.read(0x00980004u,4u);return 6;}
    catch(const DeviceAccessFault&){}
    if(board.geometry_access_trace_total()!=100u)return 7;
    board.clear_geometry_access_trace();
    if(!t.empty()||board.geometry_access_trace_total()!=0u||
       board.geometry_access_trace_truncated())return 8;
    board.set_geometry_access_trace_limit(0u);
    board.enable_geometry_access_trace();
    try{board.write(0x00980000u,4u,7u);return 9;}
    catch(const DeviceAccessFault&){}
    if(!t.empty()||board.geometry_access_trace_total()!=1u||
       board.geometry_access_trace_dropped()!=1u)return 10;
    board.set_geometry_access_trace_limit(4u);
    try{board.write(0x00980000u,4u,8u);return 11;}
    catch(const DeviceAccessFault&){}
    if(t.size()!=1u||t[0].ordinal!=2u||t[0].value!=8u)return 12;
    board.write(0x00500100u,4u,0x12345678u);
    if(board.read(0x00500100u,4u)!=0x12345678u||
       board.writes().size()!=1u||t.size()!=1u)return 13;
    return 0;
}
""")

    def test_synthetic_strict_boot_probe_observes_refusal_only(self):
        compilers = [p for name in ("g++", "clang++") if (p := shutil.which(name)]
        if not compilers:
            raise unittest.SkipTest("C++17 host compiler unavailable")
        for compiler in compilers:
            with self.subTest(compiler=compiler):
                with tempfile.TemporaryDirectory(prefix="arcade-geo-probe-") as d:
                    root = Path(d)
                    program = bytearray(0x200000)
                    struct.pack_into("<I", program, 4, 0x100)
                    struct.pack_into("<I", program, 12, 0x20)
                    struct.pack_into("<I", program, 0x100+24, 0x00510400)
                    binary = root / "synthetic.bin"
                    binary.write_bytes(program)
                    (root / "hotd1_i960.cpp").write_text(
                        '#include "i960_frame_runtime.hpp"\n'
                        'namespace arcaderecomp_generated {\n'
                        'bool step(CPU& cpu, const Bus& bus) {\n'
                        '  if (cpu.ip == 0x20u) {\n'
                        '    bus.write32(bus.ctx,0x00884000u,0x12345678u);\n'
                        '    cpu.ip = 0x24u; return true;\n'
                        '  }\n'
                        '  return false;\n'
                        '}}\n')
                    exe = root / "probe"
                    built = subprocess.run([
                        compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                        "-Werror", "-fsanitize=undefined",
                        "-fno-sanitize-recover=all", "-I", str(root),
                        "-I", str(ROOT / "runtime"),
                        str(ROOT / "tools" / "hotd1_strict_boot_probe.cpp"),
                        "-o", str(exe)],
                        capture_output=True, text=True, timeout=45)
                    if built.returncode:
                        raise AssertionError(compiler + ": " + built.stderr)
                    tracked = subprocess.run([str(exe), str(binary), "5",
                                              "--geometry-trace"],
                                             capture_output=True, text=True,
                                             timeout=25)
                    self.assertEqual(tracked.returncode, 3, tracked.stderr)
                    self.assertIn("geometry_access ordinal=1 direction=write",
                                  tracked.stdout)
                    self.assertIn("address=0x884000", tracked.stdout)
                    self.assertIn("completed=no value=0x12345678",
                                  tracked.stdout)
                    self.assertIn(
                        "geometry_trace_summary total=1 retained=1 dropped=0 "
                        "truncated=no limit=4096", tracked.stdout)
                    self.assertIn("mapped_writes=0", tracked.stdout)
                    regular = subprocess.run([str(exe), str(binary), "5"],
                                             capture_output=True, text=True,
                                             timeout=25)
                    self.assertEqual(regular.returncode, 3, regular.stderr)
                    self.assertNotIn("geometry_access", regular.stdout)
                    duplicate = subprocess.run(
                        [str(exe), str(binary),
                         "--geometry-trace", "--geometry-trace"],
                        capture_output=True, text=True, timeout=25)
                    self.assertEqual(duplicate.returncode, 2)


if __name__ == "__main__":
    unittest.main()
