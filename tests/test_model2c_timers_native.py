"""ROM-free native Model 2C opt-in timer tests (GCC/Clang + UBSan).

Every hardware tick and mask is explicitly synthetic. Tests do not establish
original-cabinet reset/IRQ/readback behavior or real i960 interrupt delivery.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def native(body):
    compilers = [x for name in ("g++", "clang++") if (x := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("A C++17 compiler is required")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-timer-native-") as tmp:
            source = Path(tmp) / "timer.cpp"
            binary = Path(tmp) / "timer"
            source.write_text(
                '#include "model2c_bus.hpp"\n'
                'using namespace arcaderecomp_model2c;\n' + body,
                encoding="utf-8")
            built = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT / "runtime"), str(source), "-o", str(binary)],
                capture_output=True, text=True, timeout=45)
            if built.returncode:
                raise AssertionError(compiler + ": " + built.stderr)
            run = subprocess.run([str(binary)], capture_output=True,
                                 text=True, timeout=25)
            if run.returncode:
                raise AssertionError(
                    compiler + f": exit {run.returncode}: " + run.stderr)


class PartialModel2CTimerTests(unittest.TestCase):
    def test_countdowns_and_explicit_irq(self):
        native(r"""
int main() {
    StrictBus b(std::vector<std::uint8_t>(StrictBus::kProgramSize, 0u));
    if(b.classify(0x00f00000u)!=Region::timer_registers ||
       b.classify(0x00f0000cu)!=Region::timer_registers ||
       b.classify(0x00f00010u)!=Region::unmapped)return 1;
    try {b.write(0x00f00000u,4u,5u);return 2;}
    catch(const DeviceAccessFault& e) {
        if(e.region!=Region::timer_registers)return 3;
    }
    b.enable_partial_timers();
    b.enable_partial_irq_registers();
    for(unsigned i=0u;i<4u;++i) {
        try{(void)b.read(0x00f00000u+i*4u,4u);return 4;}
        catch(const DeviceAccessFault& e) {
            if(e.region!=Region::timer_registers)return 5;
        }
    }
    b.write(0x00e80004u,4u,0x3cu);
    b.irq_registers().advance_cpu_cycles(2u);
    b.write(0x00f00000u,4u,5u);
    b.write(0x00f00004u,4u,2u);
    b.write(0x00f00008u,4u,10u);
    b.write(0x00f0000cu,4u,100u);
    if(b.read(0x00f00000u,4u)!=5u||
       b.read(0x00f00004u,4u)!=2u||
       b.read(0x00f00008u,4u)!=10u||
       b.read(0x00f0000cu,4u)!=100u)return 6;
    b.advance_external_timer_ticks(1u);
    if(b.read(0x00f00000u,4u)!=4u||
       b.read(0x00f00004u,4u)!=1u||
       b.irq_registers().request()!=0u)return 7;
    b.advance_external_timer_ticks(1u);
    if(b.irq_registers().request()!=8u||
       !b.irq_registers().line_level(2u)||
       b.read(0x00f00008u,4u)!=8u)return 8;
    try{(void)b.read(0x00f00004u,4u);return 9;}
    catch(const DeviceAccessFault&){}
    if(b.timer_registers().channel(1u).expirations!=1u)return 10;
    b.write(0x00f00004u,4u,3u);
    b.advance_external_timer_ticks(3u);
    if(b.irq_registers().request()!=12u||
       b.timer_registers().channel(0u).expirations!=1u||
       b.timer_registers().channel(1u).expirations!=2u||
       b.read(0x00f00008u,4u)!=5u||
       b.read(0x00f0000cu,4u)!=95u)return 11;
    b.write(0x00e80000u,4u,~12u);
    if(b.irq_registers().request()!=0u||b.writes().size()!=7u)
        return 12;
    return 0;
}
""")

    def test_strict_invalid_reset_zero_and_widths(self):
        native(r"""
int main() {
    StrictBus b(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    b.enable_partial_timers();
    for(unsigned width : {1u,2u}) {
        try{b.write(0x00f00000u,width,1u);return 1;}
        catch(const DeviceAccessFault& e){
            if(e.region!=Region::timer_registers)return 2;
        }
        try{(void)b.read(0x00f00000u,width);return 3;}
        catch(const DeviceAccessFault&){}
    }
    try{b.write(0x00f00002u,4u,3u);return 4;}
    catch(const DeviceAccessFault&){}
    try{b.write(0x00f00000u,4u,0u);return 5;}
    catch(const DeviceAccessFault& e){
        if(!e.write||e.region!=Region::timer_registers)return 6;
    }
    if(b.timer_registers().channel(0u).running||!b.writes().empty())
        return 7;
    try{(void)b.read(0x00f00000u,4u);return 8;}
    catch(const DeviceAccessFault&){}
    try{(void)b.timer_registers().channel(4u);return 9;}
    catch(const std::out_of_range&){}
    b.advance_external_timer_ticks(2u);
    if(b.irq_registers().request()!=0u)return 10;
    return 0;
}
""")

    def test_huge_explicit_ticks_no_implicit_hardware(self):
        native(r"""
int main() {
    StrictBus b(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    b.enable_partial_timers();
    b.write(0x00f0000cu,4u,0xffffffffu);
    b.advance_external_timer_ticks(0u);
    if(b.read(0x00f0000cu,4u)!=0xffffffffu)return 1;
    b.advance_external_timer_ticks(0x100000001ull);
    if(b.timer_registers().channel(3u).expirations!=1u||
       b.timer_registers().channel(3u).running||
       b.irq_registers().request())return 2;
    try{(void)b.read(0x00f0000cu,4u);return 3;}
    catch(const DeviceAccessFault&){}
    b.write(0x00f0000cu,4u,8u);
    b.enable_partial_irq_registers();
    b.write(0x00e80004u,4u,1u<<5u);
    b.irq_registers().advance_cpu_cycles(2u);
    b.advance_external_timer_ticks(7u);
    if(b.read(0x00f0000cu,4u)!=1u||
       b.irq_registers().request()!=0u)return 4;
    b.advance_external_timer_ticks(1u);
    if(b.timer_registers().channel(3u).expirations!=2u||
       b.irq_registers().request()!=(1u<<5u)||
       !b.irq_registers().line_level(2u))return 5;
    b.enable_partial_timers(false);
    try{b.advance_external_timer_ticks(1u);return 6;}
    catch(const std::logic_error&){}
    try{b.read(0x00f0000cu,4u);return 7;}
    catch(const DeviceAccessFault&){}
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
