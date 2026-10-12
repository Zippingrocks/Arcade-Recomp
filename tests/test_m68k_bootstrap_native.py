"""ROM-free MC68000 native bootstrap and instruction semantics regression."""
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from arcaderecomp.m68k import decode, discover
from arcaderecomp.m68k_cpp import emit_cpp

ROOT = Path(__file__).resolve().parents[1]


def words(*values):
    return struct.pack(">" + "H" * len(values), *values)


def native(source, body):
    compilers = [p for name in ("g++", "clang++") if (p := shutil.which(name))]
    if not compilers:
        raise unittest.SkipTest("C++17 compiler required")
    for compiler in compilers:
        with tempfile.TemporaryDirectory(prefix="arcade-m68k-") as directory:
            cpp, exe = Path(directory) / "test.cpp", Path(directory) / "test"
            cpp.write_text(source + "\n" + body, encoding="utf-8")
            build = subprocess.run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra",
                "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all", "-I",
                str(ROOT / "runtime"), str(cpp), "-o", str(exe)], capture_output=True,
                text=True, timeout=90)
            if build.returncode:
                raise AssertionError(compiler + ": " + build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            if run.returncode:
                raise AssertionError(compiler + " exit " + str(run.returncode) + ": " + run.stderr)


class M68kBootstrapTests(unittest.TestCase):
    def test_decoder_mc68000_only_and_truncation(self):
        self.assertEqual(decode(words(0x70ff), 0).operands, (0, -1))
        self.assertEqual(decode(words(0x71ff), 0).mnemonic, "unsupported")
        ins = decode(words(0x60ff, 0x1234, 0x5678), 0)
        self.assertEqual((ins.size, ins.target), (2, 1))
        self.assertEqual(decode(words(0x6000, 0xfffc), 0x100, 0x100).target, 0xfe)
        self.assertEqual(decode(words(0x51cf, 0xfffe), 0).target, 0)
        self.assertEqual(decode(words(0x6100, 0x1234), 0).mnemonic, "bsr")
        for data in (b"", b"\x4e", words(0x46fc), words(0x41f9, 0x1234),
                     words(0x6000), words(0x50c8), words(0x4228)):
            with self.assertRaises(ValueError):
                decode(data, 0)
        for pc in (-2, 1, 0x100000000):
            with self.assertRaises(ValueError):
                decode(words(0x4e71), pc)
        with self.assertRaises(ValueError):
            discover(words(0x4e71), 0, limit=True)
        with self.assertRaises(ValueError):
            discover(words(0x4e71), 0, base=0xffffffff)
        found, limited = discover(words(0xffff, 0x4e71), 0)
        self.assertEqual(len(found), 1)
        self.assertFalse(limited)
        found, limited = discover(words(0x4e71, 0x4e71), 0, limit=1)
        self.assertTrue(limited)
        self.assertEqual(len(found), 1)
        found, limited = discover(words(0x6004), 0)
        self.assertEqual([(i.pc, i.mnemonic) for i in found], [(0, "bcc"), (6, "invalid_fetch")])
        found, limited = discover(words(0x60ff), 0)
        self.assertEqual([(i.pc, i.mnemonic) for i in found], [(0, "bcc"), (1, "invalid_fetch")])
        self.assertFalse(limited)

    def test_private_probe_rejects_wrong_chip_and_output_escape(self):
        tool = ROOT / "tools/experimental/hotdo_sound_bootstrap_probe.py"
        with tempfile.TemporaryDirectory(prefix="arcade-m68k-input-") as directory:
            path = Path(directory) / "synthetic-chip.bin"
            path.write_bytes(bytes(32))
            run = subprocess.run([sys.executable, str(tool), "--chip", str(path),
                                  "--compiler", "unneeded-compiler"], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("not the authenticated original HOTD1 sound chip", run.stderr)
            run = subprocess.run([sys.executable, str(tool), "--chip", str(path),
                                  "--compiler", "unneeded-compiler", "--work-dir", directory],
                                 capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("ignored build/", run.stderr)
            self.assertEqual(path.read_bytes(), bytes(32))

    def test_native_moveq_clr_movea_and_lea(self):
        image = bytearray()
        rows = []
        for immediate in range(256):
            reg = immediate % 8
            rows.append((len(image), 0, reg, immediate, 0))
            image += words(0x7000 | reg << 9 | immediate)
        for size in range(3):
            for reg in range(8):
                rows.append((len(image), 1, reg, (1, 2, 4)[size], 0))
                image += words(0x4200 | size << 6 | reg)
        for size in (2, 4):
            for source in range(8):
                for dest in range(8):
                    rows.append((len(image), 2, source, size, dest))
                    image += words((0x3040 if size == 2 else 0x2040) | dest << 9 | source)
        for reg in range(8):
            address = (0x80000000 + reg * 0x10001) & 0xffffffff
            rows.append((len(image), 3, reg, address, 0))
            image += words(0x41f9 | reg << 9, address >> 16, address & 0xffff)
        image += words(0xffff)
        source, report = emit_cpp(bytes(image), 0)
        self.assertEqual(report.translated, len(rows))
        table = "static const unsigned rows[][5]={" + ",".join(
            "{" + ",".join(f"{v}u" for v in row) + "}" for row in rows) + "};\n"
        native(source, table + r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus bus;
    for (const auto& row : rows) for (unsigned x = 0; x < 2; ++x) {
        CPU cpu; reset_from_vectors(cpu, 0x2000, row[0]);
        for (unsigned i=0; i<8; ++i) { cpu.d[i]=0xa55a8001u+i; cpu.d_known[i]=0xffffffffu; }
        cpu.sr=static_cast<std::uint16_t>(0x270fu|(x<<4)); cpu.sr_known=0xffffu;
        const unsigned old=cpu.d[row[2]];
        if (!step(cpu,bus) || cpu.completed!=1 || cpu.stop!=Stop::none) return 1;
        if (row[1]==0) {
            const auto value = row[3] < 128 ? row[3] : 0xffffff00u | row[3];
            const auto flags = (value==0 ? 4u : 0u) | (row[3]>=128 ? 8u : 0u);
            if (cpu.d[row[2]]!=value || (cpu.sr&15u)!=flags) return 2;
        } else if (row[1]==1) {
            const unsigned mask=row[3]==4 ? 0xffffffffu : (1u<<(8u*row[3]))-1u;
            if (cpu.d[row[2]]!=(old&~mask) || (cpu.sr&15u)!=4u) return 3;
        } else if (row[1]==2) {
            const unsigned expected=row[3]==4 ? old : (0xffff0000u|(old&0xffffu));
            if (cpu.a[row[4]]!=expected || !cpu.a_known[row[4]] || (cpu.sr&15u)!=15u) return 4;
        } else if (cpu.a[row[2]]!=row[3] || !cpu.a_known[row[2]] || (cpu.sr&15u)!=15u) return 5;
        if ((cpu.sr&16u)!=(x<<4) || cpu.sr_known!=0xffffu) return 6;
    }
    return 0;
}
''')

    def test_native_conditions_branches_and_dbcc(self):
        sources = []
        for cc in range(16):
            opcode = 0x6004 | cc << 8 if cc != 1 else 0x4e71
            source, _ = emit_cpp(words(opcode, 0xffff, 0xffff, 0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"branch_{cc}"))
            source, _ = emit_cpp(words(0x50cb | cc << 8, 4, 0xffff, 0xffff), 0)
            sources.append(source.replace("arcaderecomp_m68k_generated", f"db_{cc}"))
        branches = ",".join(f"branch_{cc}::step" for cc in range(16))
        dbs = ",".join(f"db_{cc}::step" for cc in range(16))
        native("\n".join(sources), r'''
using namespace arcaderecomp::m68k;
using Step = bool(*)(CPU&,Bus&);
''' + f"Step branches[]={{{branches}}};\nStep dbs[]={{{dbs}}};\n" + r'''
int main() {
    Bus bus;
    const unsigned masks[]={0,0,5,5,1,1,4,4,2,2,8,8,10,10,14,14};
    for(unsigned bits=0; bits<16; ++bits) {
        const bool c=bits&1,v=bits&2,z=bits&4,n=bits&8;
        const bool expected[]={true,false,!c&&!z,c||z,!c,c,!z,z,!v,v,!n,n,n==v,n!=v,!z&&n==v,z||n!=v};
        for(unsigned cc=0; cc<16; ++cc) {
            CPU cpu; reset_from_vectors(cpu,0x2000,0);cpu.sr|=bits;cpu.sr_known=0xffffu;
            if(cc!=1) {
                if(!branches[cc](cpu,bus) || cpu.pc!=(expected[cc]?6u:2u))return 1;
                for(unsigned bit=1;bit<=8;bit<<=1) {
                    reset_from_vectors(cpu,0x2000,0);cpu.sr_known=static_cast<std::uint16_t>(0xffffu&~bit);
                    const bool ok=branches[cc](cpu,bus);
                    if(ok==bool(masks[cc]&bit))return 2;
                    if(!ok&&(cpu.pc!=0||cpu.completed!=0||cpu.stop!=Stop::undefined_state))return 3;
                }
            }
            for(unsigned count: {0u,1u,0xffffu}) {
                reset_from_vectors(cpu,0x2000,0);cpu.sr|=bits;cpu.sr_known=0xffffu;
                cpu.d[3]=0xabcd0000u|count;cpu.d_known[3]=0xffffffffu;
                if(!dbs[cc](cpu,bus))return 4;
                const auto remaining=expected[cc]?count:((count-1u)&0xffffu);
                if(cpu.d[3]!=(0xabcd0000u|remaining) || cpu.pc!=(!expected[cc]&&remaining!=0xffffu?6u:4u))return 5;
                if(cpu.sr!=(0x2700u|bits)||cpu.sr_known!=0xffffu)return 6;
            }
        }
    }
    CPU cpu; reset_from_vectors(cpu,0x2000,0);cpu.sr_known=0xffe0u;
    if(!dbs[0](cpu,bus)||cpu.pc!=4u)return 7; // DBT needs neither counter nor flags.
    reset_from_vectors(cpu,0x2000,0);
    if(dbs[1](cpu,bus)||cpu.stop!=Stop::undefined_state)return 8;
    return 0;
}
''')

    def test_memory_clear_read_before_write_and_strict_rom_bus(self):
        source, _ = emit_cpp(words(0x422a, 0xfffd, 0xffff), 0)
        native(source, r'''
#include "m68k_sound_bus.hpp"
using namespace arcaderecomp_m68k_generated;
struct ObservedBus:Bus {
    unsigned reads=0,writes=0,address=0;bool deny_read=false,deny_write=false;
    std::uint8_t read8(std::uint32_t a) override {
        ++reads;address=a;if(deny_read)throw BusFault(a,false);return 0xa5;
    }
    void write8(std::uint32_t a,std::uint8_t value) override {
        if(reads!=1||value!=0||a!=address)throw std::runtime_error("bad clear order");
        ++writes;if(deny_write)throw BusFault(a,true);
    }
};
int main() {
    for(unsigned denial=0;denial<3;++denial) {
        CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.a[2]=0x01000002u;cpu.a_known[2]=true;
        cpu.sr=0x271fu;cpu.sr_known=0xffffu;
        ObservedBus bus;bus.deny_read=denial==1;bus.deny_write=denial==2;
        const bool ok=step(cpu,bus);
        if(ok!=(denial==0)||bus.reads!=1||bus.address!=0xffffffu||bus.writes!=(denial==1?0u:1u))return 1;
        if(ok) {if(cpu.pc!=4||cpu.sr!=0x2714||cpu.completed!=1)return 2;}
        else if(cpu.pc!=0||cpu.sr!=0x271f||cpu.completed!=0||cpu.stop!=Stop::bus_access||
                cpu.access_address!=0xffffffu||cpu.access_write!=(denial==2))return 3;
    }
    CPU cpu;reset_from_vectors(cpu,0x2000,0);ObservedBus bus;
    if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||bus.reads||bus.writes)return 4;
    std::vector<std::uint8_t> bytes(0x80000,0);bytes.front()=0x12;bytes.back()=0x34;
    SoundROMBus rom(std::move(bytes));
    if(rom.read8(0x600000)!=0x12||rom.read8(0x167ffff)!=0x34)return 5;
    for(unsigned address:{0u,0x100401u,0x5fffffu,0x680000u}) {
        try {(void)rom.read8(address);return 6;}catch(const BusFault& e){if(e.write||e.address!=address)return 7;}
    }
    try{rom.write8(0x600000,0);return 8;}catch(const BusFault& e){if(!e.write)return 9;}
    return 0;
}
''')

    def test_partial_register_definedness_and_movea_word_extension(self):
        source, _ = emit_cpp(words(0x3443, 0x4203, 0x4243, 0x4283, 0x7000, 0xffff), 0)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus bus;
    for(unsigned low : {0u,1u,0x7fffu,0x8000u,0xffffu}) {
        CPU cpu;reset_from_vectors(cpu,0x2000,0);
        cpu.d[3]=0xdead0000u|low;cpu.d_known[3]=0xffffu;
        if(!step(cpu,bus)||cpu.a[2]!=(low>=0x8000u?0xffff0000u|low:low)||!cpu.a_known[2])return 1;
        if(cpu.sr!=0x2700u||cpu.sr_known!=0xffe0u)return 2;
    }
    CPU cpu;reset_from_vectors(cpu,0x2000,0);cpu.d_known[3]=0xfffeu;cpu.a[2]=0x12345678;
    if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.a[2]!=0x12345678)return 3;
    reset_from_vectors(cpu,0x2000,2);cpu.d[3]=0xdeadbeef;
    if(!step(cpu,bus)||cpu.d[3]!=0xdeadbe00||cpu.d_known[3]!=255||cpu.sr_known!=0xffef)return 4;
    if(!step(cpu,bus)||cpu.d[3]!=0xdead0000||cpu.d_known[3]!=65535||cpu.sr_known!=0xffef)return 5;
    if(!step(cpu,bus)||cpu.d[3]!=0||cpu.d_known[3]!=0xffffffffu||cpu.sr_known!=0xffef)return 6;
    if(!step(cpu,bus)||cpu.d[0]!=0||cpu.d_known[0]!=0xffffffffu||cpu.sr_known!=0xffef)return 7;
    return 0;
}
''')

    def test_definedness_control_stops_and_synthetic_bootstrap(self):
        source, _ = emit_cpp(words(0x46fc, 0x2710, 0x7401, 0x2242, 0x47f9, 0x0010,
                                  0x0020, 0x422b, 4, 0xffff), 0x600100, 0x600100)
        native(source, r'''
using namespace arcaderecomp_m68k_generated;
int main() {
    Bus bus;CPU cpu;reset_from_vectors(cpu,0x3456,0x600100);
    if(cpu.sr_known!=0xffe0u||cpu.d_known[0]||cpu.a_known[0]||!cpu.a_known[7])return 1;
    for(unsigned i=0;i<4;++i)if(!step(cpu,bus))return 2;
    if(cpu.completed!=4||cpu.pc!=0x60010e||cpu.a[1]!=1||cpu.a[3]!=0x100020)return 3;
    if(step(cpu,bus)||cpu.stop!=Stop::bus_access||cpu.access_address!=0x100024||cpu.access_write)return 4;
    if(cpu.pc!=0x60010e||cpu.completed!=4||cpu.sr!=0x2710)return 5;
    if(step(cpu,bus)||cpu.completed!=4)return 6;
    reset_from_vectors(cpu,0x3456,0x600106);cpu.a[1]=0xdeadbeef;
    if(step(cpu,bus)||cpu.stop!=Stop::undefined_state||cpu.a[1]!=0xdeadbeef||cpu.pc!=0x600106)return 7;
    reset_from_vectors(cpu,0x3456,0x600100);cpu.sr|=0x8000;
    if(step(cpu,bus)||cpu.stop!=Stop::unsupported_control||cpu.completed)return 8;
    reset_from_vectors(cpu,0x3456,0x600100);cpu.pc|=1;
    if(step(cpu,bus)||cpu.stop!=Stop::instruction_address)return 9;
    reset_from_vectors(cpu,0x3456,0x600100);
    if(!move_sr(cpu,0x2000,0x600104)||cpu.sr!=0x2000||cpu.pc!=0x600104)return 10;
    reset_from_vectors(cpu,0x3456,0x600100);cpu.sr=0;
    if(move_sr(cpu,0x2700,0x600104)||cpu.stop!=Stop::privilege)return 11;
    reset_from_vectors(cpu,0x3456,0x600112);
    if(step(cpu,bus)||cpu.stop!=Stop::unsupported_instruction)return 12;
    reset_from_vectors(cpu,0x3456,0x700000);
    if(step(cpu,bus)||cpu.stop!=Stop::untranslated_pc)return 13;
    return 0;
}
''')


if __name__ == "__main__":
    unittest.main()
