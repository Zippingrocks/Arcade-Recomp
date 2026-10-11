"""ROM-free native serial replay: strict observed CPU-side rows, never cabinet proof."""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

CAPTURE = (
    "arcade-serial-cpu-replay-v1\n"
    "count=6 dropped=0 complete=yes provenance=synthetic\n"
    "1 W 0x01c00014 0xff\n"
    "2 W 0x01c00012 0x01\n"
    "3 R 0x01c0001a 0x00\n"
    "4 R 0x01c0001a 0x0c\n"
    "5 R 0x01c00016 0x45\n"
    "6 R 0x01c00018 0x92\n"
    "END\n"
)


def compilers():
    available = [p for name in ("g++", "clang++")
                 if (p := shutil.which(name))]
    if not available:
        raise unittest.SkipTest("C++17 compiler unavailable")
    return available


def native(source):
    for compiler in compilers():
        with tempfile.TemporaryDirectory(prefix="arcade-serial-cpu-replay-") as tmp:
            root = Path(tmp)
            src = root / "replay.cpp"
            exe = root / "replay"
            src.write_text(
                '#include "model2c_bus.hpp"\n'
                '#include "sega3155649_cpu_replay.hpp"\n'
                '#include <sstream>\n'
                '#include <string>\n'
                'using namespace arcaderecomp_model2c;\n' + source)
            build = subprocess.run(
                [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=undefined", "-fno-sanitize-recover=all",
                 "-I", str(ROOT / "runtime"), str(src), "-o", str(exe)],
                capture_output=True, text=True, timeout=45)
            if build.returncode:
                raise AssertionError(compiler + ": " + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True,
                                 timeout=25)
            if run.returncode:
                raise AssertionError(
                    compiler + ": exit " + str(run.returncode) + ": " + run.stderr)


class SerialCPUReplayTests(unittest.TestCase):
    def test_exact_reads_tx_and_exhaustion_refuse_unobserved(self):
        native(r"""
int main() {
    const std::string text =
        "arcade-serial-cpu-replay-v1\n"
        "count=6 dropped=0 complete=yes provenance=synthetic\n"
        "1 W 0x01c00014 0xff\n"
        "2 W 0x01c00012 0x01\n"
        "3 R 0x01c0001a 0x00\n"
        "4 R 0x01c0001a 0x0c\n"
        "5 R 0x01c00016 0x45\n"
        "6 R 0x01c00018 0x92\n"
        "END\n";
    std::istringstream input(text);
    auto replay = SerialCPUReplay::parse(input);
    if(replay.total()!=6u || replay.consumed()!=0u)return 1;
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0));
    board.enable_partial_serial_io();
    board.enable_serial_access_trace();
    replay.bind(board.serial_device());
    auto bus = board.callbacks();
    bus.write8(bus.ctx,0x01c00014u,0xffu);
    bus.write8(bus.ctx,0x01c00012u,0x01u);
    if(bus.read8(bus.ctx,0x01c0001au)!=0u)return 2;
    if(bus.read8(bus.ctx,0x01c0001au)!=0x0cu)return 3;
    if(bus.read8(bus.ctx,0x01c00016u)!=0x45u)return 4;
    if(bus.read8(bus.ctx,0x01c00018u)!=0x92u)return 5;
    if(!replay.exhausted() || replay.remaining()!=0u ||
       replay.consumed()!=6u)return 6;
    try{(void)bus.read8(bus.ctx,0x01c0001au);return 7;}
    catch(const DeviceAccessFault& e) {
       if(e.region!=Region::serial_io || e.write)return 8;
    }
    if(replay.consumed()!=6u || board.writes().size()!=2u ||
       board.serial_device().transmissions().size()!=2u)return 9;
    const auto& trace=board.serial_access_trace();
    if(trace.size()!=7u || trace[2].value!=0u ||
       !trace[2].completed || !trace[3].completed ||
       trace[6].completed || trace[6].value_known)return 10;
    return 0;
}
""")

    def test_divergence_is_atomic_and_does_not_consume_unknown_input(self):
        native(r"""
int main() {
    const std::string text =
      "arcade-serial-cpu-replay-v1\n"
      "count=2 dropped=0 complete=yes provenance=synthetic\n"
      "1 W 0x01c00014 0xff\n"
      "2 R 0x01c0001a 0x00\n"
      "END\n";
    std::istringstream input(text);
    auto replay=SerialCPUReplay::parse(input);
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0));
    board.enable_partial_serial_io();replay.bind(board.serial_device());
    try{board.write(0x01c00014u,1u,0x01u);return 1;}
    catch(const DeviceAccessFault&){}
    if(replay.consumed()!=0u || board.writes().size()!=0u ||
       board.serial_device().transmissions().size()!=0u)return 2;
    try{(void)board.read(0x01c0001au,1u);return 3;}
    catch(const DeviceAccessFault&){}
    if(replay.consumed()!=0u)return 4;
    board.write(0x01c00014u,1u,0xffu);
    if(replay.consumed()!=1u)return 5;
    try{(void)board.read(0x01c00018u,1u);return 6;}
    catch(const DeviceAccessFault&){}
    if(replay.consumed()!=1u)return 7;
    if(board.read(0x01c0001au,1u)!=0u || !replay.exhausted())return 8;
    try{replay.bind(board.serial_device());return 9;}
    catch(const std::logic_error&){}
    return 0;
}
""")

    def test_capture_validation_rejects_truncation_extra_and_spoofed_roles(self):
        native(r"""
static bool rejects(const std::string& text) {
    std::istringstream input(text);
    try{(void)SerialCPUReplay::parse(input);}
    catch(const std::invalid_argument&){return true;}
    return false;
}
int main() {
    const std::string good =
        "arcade-serial-cpu-replay-v1\n"
        "count=2 dropped=0 complete=yes provenance=external_unverified\n"
        "1 W 0x01c00014 0xff\n"
        "2 R 0x01c0001a 0x00\n"
        "END\n";
    if(rejects(good))return 1;
    const std::string bad[]={
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=1 complete=yes provenance=external_unverified\n"
        "1 W 0x01c00014 0xff\n2 R 0x01c0001a 0x00\nEND\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=no provenance=synthetic\n"
        "1 W 0x01c00014 0xff\n2 R 0x01c0001a 0x00\nEND\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=yes provenance=cabinet_verified\n"
        "1 W 0x01c00014 0xff\n2 R 0x01c0001a 0x00\nEND\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=yes provenance=synthetic\n"
        "1 W 0x01c00014 0xff\n3 R 0x01c0001a 0x00\nEND\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=yes provenance=synthetic\n"
        "1 W 0x01c00014 0xff\n2 R 0x01c0001a 0x00\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=yes provenance=synthetic\n"
        "1 W 0x01c00014 0xff\n2 R 0x01c0001a 0x00\nEND\nTRAILING\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=yes provenance=synthetic\n"
        "1 W 0x01c0001a 0xff\n2 R 0x01c0001a 0x00\nEND\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=yes provenance=synthetic\n"
        "1 W 0x01c00014 0xff\n2 R 0x01c00014 0x00\nEND\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=yes provenance=synthetic\n"
        "1 W 0x01c00014 0xff\n2 R 0x01c0001a 0x100\nEND\n",
        "arcade-serial-cpu-replay-v1\ncount=100001 dropped=0 complete=yes provenance=synthetic\nEND\n",
        "arcade-serial-cpu-replay-v1\ncount=2 dropped=0 complete=yes provenance=synthetic\n"
        "1 W 0x01c00014 0xff\n2 R 0x01c0001a 0x00\nEND\n\n"
    };
    for(const auto& wrong:bad)if(!rejects(wrong))return 2;
    return 0;
}
""")

    def test_compiled_strict_probe_opt_in_replay_and_default_strict(self):
        for compiler in compilers():
            with self.subTest(compiler=compiler):
                with tempfile.TemporaryDirectory(prefix="arcade-serial-replay-probe-") as tmp:
                    root = Path(tmp)
                    image = bytearray(0x200000)
                    struct.pack_into("<I", image, 4, 0x100)
                    struct.pack_into("<I", image, 12, 0x20)
                    struct.pack_into("<I", image, 0x118, 0x00510400)
                    rom = root / "synthetic.bin"
                    rom.write_bytes(image)
                    (root / "hotd1_i960.cpp").write_text(
                        '#include "i960_frame_runtime.hpp"\n'
                        'namespace arcaderecomp_generated {\n'
                        'bool step(CPU& cpu,const Bus& bus){\n'
                        '  if(cpu.ip==0x20u){bus.write8(bus.ctx,0x01c00014u,0xffu);'
                        'cpu.ip=0x24u;return true;}\n'
                        '  if(cpu.ip==0x24u){bus.write8(bus.ctx,0x01c00012u,0x01u);'
                        'cpu.ip=0x28u;return true;}\n'
                        '  if(cpu.ip==0x28u){cpu.r[18]=bus.read8(bus.ctx,0x01c0001au);'
                        'cpu.ip=0x2cu;return true;}\n'
                        '  if(cpu.ip==0x2cu){cpu.r[18]=bus.read8(bus.ctx,0x01c0001au);'
                        'cpu.ip=0x30u;return true;}\n'
                        '  return false;}\n}\n')
                    replay = root / "private_replay.txt"
                    replay.write_text(
                        "arcade-serial-cpu-replay-v1\n"
                        "count=4 dropped=0 complete=yes provenance=synthetic\n"
                        "1 W 0x01c00014 0xff\n"
                        "2 W 0x01c00012 0x01\n"
                        "3 R 0x01c0001a 0x00\n"
                        "4 R 0x01c0001a 0x0c\n"
                        "END\n")
                    binary = root / "strict"
                    built = subprocess.run(
                        [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                         "-Werror", "-fsanitize=undefined",
                         "-fno-sanitize-recover=all", "-I", str(root),
                         "-I", str(ROOT / "runtime"),
                         str(ROOT / "tools" / "hotd1_strict_boot_probe.cpp"),
                         "-o", str(binary)],
                        capture_output=True, text=True, timeout=45)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    args = [str(binary), str(rom), "10"]
                    regular = subprocess.run(args, capture_output=True,
                                             text=True, timeout=20)
                    self.assertEqual(regular.returncode, 3)
                    self.assertNotIn("serial_replay_UNVERIFIED", regular.stdout)
                    checked = subprocess.run(
                        args + ["--serial-replay-unverified", str(replay)],
                        capture_output=True, text=True, timeout=20)
                    self.assertEqual(checked.returncode, 4, checked.stderr)
                    self.assertIn("executed=4", checked.stdout)
                    self.assertIn(
                        "serial_replay_UNVERIFIED consumed=4 total=4 remaining=0",
                        checked.stdout)
                    self.assertIn("UNVERIFIED SERIAL REPLAY", checked.stderr)
                    self.assertIn("serial_access ordinal=3 direction=read",
                                  checked.stdout)
                    self.assertIn("completed=yes value=0x0", checked.stdout)
                    altered = replay.read_text().replace(
                        "2 W 0x01c00012 0x01", "2 W 0x01c00012 0xff")
                    replay.write_text(altered)
                    wrong = subprocess.run(
                        args + ["--serial-replay-unverified", str(replay)],
                        capture_output=True, text=True, timeout=20)
                    self.assertEqual(wrong.returncode, 3)
                    self.assertIn(
                        "serial_replay_UNVERIFIED consumed=1 total=4 remaining=3",
                        wrong.stdout)
                    for suffix in (
                        ["--serial-replay-unverified"],
                        ["--serial-tx", "--serial-replay-unverified", str(replay)],
                        ["--serial-replay-unverified", str(replay),
                         "--serial-replay-unverified", str(replay)],
                    ):
                        invalid = subprocess.run(args + suffix, capture_output=True,
                                                 text=True, timeout=20)
                        self.assertEqual(invalid.returncode, 2, invalid.stderr)


if __name__ == "__main__":
    unittest.main()
