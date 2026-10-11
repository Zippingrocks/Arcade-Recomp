"""ROM-free i960KB diagnostic RET guard: invalid caller RIP cannot corrupt frame.

Validates fail-closed synthetic behavior only, NOT original Intel fault delivery,
cycle accuracy, arcade-cabinet or original ROM execution evidence.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

NATIVE_HEADER = r"""
#include "i960_frame_runtime.hpp"
#include <cstdint>
#include <unordered_map>
using namespace arcaderecomp_generated;

struct Memory {
    std::unordered_map<std::uint32_t,std::uint32_t> words;
    unsigned reads = 0u;
    unsigned writes = 0u;
};
inline std::uint32_t read32(void* context,std::uint32_t addr) {
    auto& memory = *static_cast<Memory*>(context);
    ++memory.reads;
    const auto it=memory.words.find(addr);
    return it==memory.words.end()?0u:it->second;
}
inline void write32(void* context,std::uint32_t addr,std::uint32_t value) {
    auto& memory = *static_cast<Memory*>(context);
    ++memory.writes;
    memory.words[addr]=value;
}
"""


def run_native(body):
    cc = [p for name in ("g++", "clang++") if (p := shutil.which(name))]
    if not cc:
        raise unittest.SkipTest("C++17 compiler unavailable")
    for compiler in cc:
        with tempfile.TemporaryDirectory(prefix="arcade-i960-ret-guard-") as d:
            root=Path(d)
            src,exe=root/"test.cpp",root/"test"
            src.write_text(NATIVE_HEADER+body)
            build=subprocess.run(
                [compiler,"-std=c++17","-O2","-Wall","-Wextra","-Werror",
                 "-fsanitize=undefined","-fno-sanitize-recover=all",
                 "-I",str(ROOT/"runtime"),str(src),"-o",str(exe)],
                capture_output=True,text=True,timeout=45)
            if build.returncode:
                raise AssertionError(compiler+" compile: "+build.stderr)
            result=subprocess.run([str(exe)],capture_output=True,text=True,
                                  timeout=25)
            if result.returncode:
                raise AssertionError(
                    compiler+" native exit "+str(result.returncode)+": "+result.stderr)


class I960RetGuardTests(unittest.TestCase):
    def test_cached_caller_bad_rip_preserves_live_cpu_and_retry(self):
        run_native(r"""
int main() {
    CPU cpu{};
    Bus bus{};
    if(!frame_init(cpu,0x00510400u,0x100u))return 1;
    cpu.r[3]=0xbeefu;
    if(!frame_call(cpu,bus,0x200u,0x104u))return 2;
    const auto callee_fp=cpu.r[31];
    cpu.saved_local[0][2]=0x105u; // synthetic corruption of cached RIP
    if(frame_return(cpu,bus))return 3;
    if(cpu.stop_code!=StopCode::bad_instruction_pointer ||
       cpu.stop_ip!=0x200u || cpu.ip!=0x200u ||
       cpu.frame_depth!=1u || cpu.r[31]!=callee_fp ||
       cpu.r[0]!=0x00510400u || !cpu.saved_valid[0] ||
       cpu.frame_reloads!=0u)return 4;
    cpu.saved_local[0][2]=0x104u;
    if(!frame_return(cpu,bus))return 5;
    if(cpu.ip!=0x104u || cpu.frame_depth!=0u ||
       cpu.r[31]!=0x00510400u ||
       cpu.r[3]!=0xbeefu)return 6;
    return 0;
}
""")

    def test_spilled_caller_bad_rip_preserves_live_cpu_and_reload_count(self):
        run_native(r"""
int main() {
    CPU cpu{};
    Memory memory{};
    Bus bus{};
    bus.ctx=&memory;
    bus.read32=&read32;
    bus.write32=&write32;
    constexpr std::uint32_t BASE=0x00510400u;
    if(!frame_init(cpu,BASE,0x100u))return 1;
    for(unsigned i=0u;i<4u;++i) {
        if(!frame_call(cpu,bus,0x200u+4u*i,0x100u+4u*i))
            return 2;
    }
    if(cpu.frame_depth!=4u || cpu.frame_spills!=1u ||
       memory.writes!=16u || cpu.saved_valid[0])return 3;
    for(unsigned i=0u;i<3u;++i)
        if(!frame_return(cpu,bus))return 4;
    if(cpu.frame_depth!=1u)return 5;
    const auto live_ip=cpu.ip;
    const auto live_fp=cpu.r[31];
    memory.words[BASE+8u]=0x105u; // corrupted spilled caller RIP
    if(frame_return(cpu,bus))return 6;
    if(cpu.stop_code!=StopCode::bad_instruction_pointer ||
       cpu.stop_ip!=live_ip || cpu.ip!=live_ip ||
       cpu.frame_depth!=1u || cpu.r[31]!=live_fp ||
       cpu.r[0]!=BASE || cpu.frame_reloads!=0u)return 7;
    memory.words[BASE+8u]=0x100u; // corrected externally supplied RAM
    if(!frame_return(cpu,bus))return 8;
    if(cpu.ip!=0x100u || cpu.frame_depth!=0u ||
       cpu.r[31]!=BASE || cpu.frame_reloads!=1u)return 9;
    if(memory.reads!=32u)return 10;
    return 0;
}
""")


if __name__=="__main__":
    unittest.main()
