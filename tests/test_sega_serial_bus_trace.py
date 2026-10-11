"""ROM-free native C++ tests for opt-in Model 2C serial bus observations.

This is transaction tracing, not physical Sega status/RX reconstruction.
Both GCC and Clang compile with UndefinedBehaviorSanitizer.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def native(body):
    compilers = [p for name in ("g++", "clang++") if (p := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("C++17 compiler unavailable")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-serial-access-") as tmp:
            source = Path(tmp) / "test.cpp"
            exe = Path(tmp) / "test"
            source.write_text('#include "model2c_bus.hpp"\n'
                              'using namespace arcaderecomp_model2c;\n' + body,
                              encoding="utf-8")
            built = subprocess.run([
                compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=undefined", "-fno-sanitize-recover=all",
                "-I", str(ROOT / "runtime"), str(source), "-o", str(exe)],
                capture_output=True, text=True, timeout=45)
            if built.returncode:
                raise AssertionError(compiler + ": " + built.stderr)
            ran = subprocess.run([str(exe)], capture_output=True,
                                 text=True, timeout=25)
            if ran.returncode:
                raise AssertionError(compiler + ": exit " +
                                     str(ran.returncode) + ": " + ran.stderr)


class SerialBusAccessTraceTests(unittest.TestCase):
    def test_real_zero_vs_unknown_and_successful_tx_order(self):
        native(r"""
int main(){
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    board.enable_partial_serial_io();
    board.enable_serial_access_trace();
    board.write(0x01c00014u,1u,0xffu); // synthetic TX2
    board.write(0x01c00012u,1u,1u);    // synthetic TX1
    try {(void)board.read(0x01c0001au,1u);return 1;}
    catch(const DeviceAccessFault& e){
        if(e.region!=Region::serial_io||e.write)return 2;
    }
    const auto& trace=board.serial_access_trace();
    if(trace.size()!=3u)return 3;
    for(unsigned i=0;i<3u;++i)if(trace[i].ordinal!=i+1u)return 4;
    if(!trace[0].write||!trace[0].completed||!trace[0].value_known||
       trace[0].value!=0xffu||trace[0].address!=0x01c00014u)return 5;
    if(!trace[1].write||!trace[1].completed||trace[1].value!=1u||
       trace[1].address!=0x01c00012u)return 6;
    // A rejected read is NOT an observed 0x00 status value.
    if(trace[2].write||trace[2].completed||trace[2].value_known||
       trace[2].address!=0x01c0001au)return 7;
    board.serial_device().set_serial_status_source([](){return std::uint8_t{0};});
    if(board.read(0x01c0001au,1u)!=0u)return 8;
    if(trace.size()!=4u||!trace[3].completed||!trace[3].value_known||
       trace[3].write||trace[3].value!=0u)return 9;
    if(board.writes().size()!=2u||
       board.serial_device().transmissions().size()!=2u)return 10;
    return 0;
}
""")

    def test_rejected_width_lane_device_state_and_capture_reset(self):
        native(r"""
int main(){
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    // Tracing does not enable partial I/O.
    board.enable_serial_access_trace();
    try{board.write(0x01c00014u,1u,0x90u);return 1;}
    catch(const DeviceAccessFault&){}
    board.enable_partial_serial_io();
    try{board.write(0x01c00015u,1u,0x55u);return 2;}
    catch(const DeviceAccessFault&){}
    try{board.write(0x01c00014u,2u,0x9911u);return 3;}
    catch(const DeviceAccessFault&){}
    try{board.write(0x01c00010u,1u,0x08u);return 4;}
    catch(const DeviceAccessFault&){}
    auto& s=board.serial_device().use_observed_events();
    try{(void)board.read(0x01c0001au,1u);return 5;}
    catch(const DeviceAccessFault&){}
    s.observe_idle(10u);  // Explicit synthetic snapshot, not guessed reset.
    board.write(0x01c00014u,1u,0xf0u);
    try{board.write(0x01c00014u,1u,0x77u);return 6;}
    catch(const DeviceAccessFault&){}
    const auto& trace=board.serial_access_trace();
    if(trace.size()!=7u)return 7;
    for(unsigned i=0;i<7u;++i)
        if(trace[i].ordinal!=i+1u)return 8;
    for(unsigned i=0;i<5u;++i)
        if(trace[i].completed||(i==4u&&trace[i].value_known))return 9;
    if(!trace[5].completed||trace[5].value!=0xf0u||
       trace[6].completed||trace[6].value!=0x77u)return 10;
    if(board.writes().size()!=1u||
       board.serial_device().transmissions().size()!=1u||s.status()!=2u)
        return 11;
    board.clear_serial_access_trace(); // Must not clear hardware state.
    if(!trace.empty()||s.status()!=2u)return 12;
    board.enable_serial_access_trace(false);
    try{(void)board.read(0x01c0001au,2u);return 13;}
    catch(const DeviceAccessFault&){}
    if(!trace.empty())return 14;
    return 0;
}
""")

    def test_failing_legacy_providers_are_unknown_and_recover_only_on_real_values(self):
        # Synthetic callback failures simulate a detached input source.
        # A throw must pass through the DeviceAccessFault boundary instead
        # of being mistaken for a received 0x00 or an unhandled C++ error.
        native(r"""
#include <string>
int main(){
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    board.enable_partial_serial_io();
    board.enable_serial_access_trace();
    board.write(0x01c00012u,1u,0x07u);
    board.write(0x01c00014u,1u,0x42u);
    unsigned status_calls=0,rx_calls=0;
    board.serial_device().set_serial_status_source([&]() -> std::uint8_t {
        ++status_calls;
        if(status_calls==1u)
            throw std::runtime_error("private capture transport went offline");
        return std::uint8_t{0};
    });
    board.serial_device().set_serial_rx(
        [&](std::uint8_t mux,unsigned channel)->std::uint8_t {
            ++rx_calls;
            if(channel!=2u||mux!=0x42u)return 0xfeu;
            if(rx_calls==1u)throw std::runtime_error("external RX disconnected");
            return std::uint8_t{0xa5u};
        });
    try{(void)board.read(0x01c0001au,1u);return 1;}
    catch(const DeviceAccessFault& e){
        const std::string message=e.what();
        if(e.region!=Region::serial_io||e.write||
           message.find("external serial status provider failed")==
               std::string::npos||
           message.find("private capture transport")!=std::string::npos)
            return 2;
    }
    try{(void)board.read(0x01c00018u,1u);return 3;}
    catch(const DeviceAccessFault& e){
        const std::string message=e.what();
        if(e.region!=Region::serial_io||e.write||
           message.find("external serial receive provider failed")==
               std::string::npos||
           message.find("RX disconnected")!=std::string::npos)
            return 4;
    }
    if(status_calls!=1u||rx_calls!=1u||board.serial_access_trace().size()!=4u)
        return 5;
    const auto& trace=board.serial_access_trace();
    for(unsigned i=2u;i<4u;++i) {
        if(trace[i].ordinal!=i+1u||trace[i].write||
           trace[i].completed||trace[i].value_known)return 6;
    }
    // Only explicitly returned bytes now become observed known values.
    if(board.read(0x01c0001au,1u)!=0u)return 7;
    if(board.read(0x01c00018u,1u)!=0xa5u)return 8;
    if(status_calls!=2u||rx_calls!=2u||trace.size()!=6u)return 9;
    if(!trace[4].completed||!trace[4].value_known||
       trace[4].value!=0u||!trace[5].completed||
       trace[5].value!=0xa5u)return 10;
    if(board.serial_device().transmissions().size()!=2u||
       board.writes().size()!=2u)return 11;
    return 0;
}
""")

    def test_translated_i960_provider_failure_does_not_advance_ip(self):
        # Invented i960 LOADBYTE from the real 315-5649 status register.
        # This test must not need the original Sega ROM.
        from arcaderecomp.i960_cpp import emit_cpp
        import struct
        word=(0x80<<24)|(18<<19)|(16<<14)|(4<<10)
        generated,report=emit_cpp(struct.pack("<2I",word,0xffffffff),0,8)
        self.assertEqual(report.translated,1)
        native(generated + r"""
using namespace arcaderecomp_generated;
int main(){
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    board.enable_partial_serial_io();
    board.enable_serial_access_trace();
    board.serial_device().set_serial_status_source(
        []()->std::uint8_t{throw std::runtime_error("unavailable");});
    CPU cpu{};
    cpu.r[16]=0x01c0001au;
    cpu.r[18]=0xdeadbeefu;
    Bus bus=board.callbacks();
    try{(void)step(cpu,bus);return 1;}
    catch(const DeviceAccessFault& e){
        if(e.address!=0x01c0001au||e.write||e.width!=1u)return 2;
    }
    if(cpu.ip!=0u||cpu.r[18]!=0xdeadbeefu)return 3;
    const auto& observations=board.serial_access_trace();
    if(observations.size()!=1u||observations[0].completed||
       observations[0].value_known)return 4;
    board.serial_device().set_serial_status_source(
        []()->std::uint8_t{return std::uint8_t{0x0cu};});
    if(!step(cpu,bus)||cpu.ip!=4u||cpu.r[18]!=0x0cu)return 5;
    if(observations.size()!=2u||!observations[1].completed||
       !observations[1].value_known||observations[1].value!=0x0cu)return 6;
    return 0;
}
""")

    def test_trace_not_enabled_by_default(self):
        native(r"""
int main(){
    StrictBus board(std::vector<std::uint8_t>(StrictBus::kProgramSize,0u));
    board.enable_partial_serial_io();
    board.write(0x01c00014u,1u,0xf1u);
    try{(void)board.read(0x01c0001au,1u);return 1;}
    catch(const DeviceAccessFault&){}
    if(!board.serial_access_trace().empty())return 2;
    board.enable_serial_access_trace();
    try{(void)board.read(0x01c0001au,1u);return 3;}
    catch(const DeviceAccessFault&){}
    if(board.serial_access_trace().size()!=1u ||
       board.serial_access_trace()[0].value_known ||
       board.serial_device().last_tx(2u)!=0xf1u)return 4;
    return 0;
}
""")


if __name__ == "__main__":
    unittest.main()
