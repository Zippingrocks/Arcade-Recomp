"""Compiled synthetic configuration-stage tests. No original game data in CI."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from arcaderecomp.config_ingress_probe import run_probe, validate_report

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r'''
#include "flex8000_config_ingress.hpp"
#include <stdexcept>
#include <string>
#include <vector>
using namespace arcaderecomp_flex8000;
void check(bool b) { if(!b) throw std::runtime_error("check failed"); }
template<class F> void rejects(F f) {
    bool caught=false; try { f(); } catch(const std::logic_error&) { caught=true; }
    check(caught);
}
ParallelPins selected(std::uint8_t b=0) {
    ParallelPins p{};p.cs=true;p.ncs=false;p.data=b;return p;
}
void send(ConfigIngress& c, ParallelPins& p, std::uint8_t b) {
    p.data=b;c.drive_parallel(p);p.nws=false;c.drive_parallel(p);
    p.nws=true;c.drive_parallel(p);
}
void drain(ConfigIngress& c,std::uint8_t value,unsigned start=0) {
    for(unsigned i=start;i<8;++i) {
        check(c.ready_nbusy()==std::optional<bool>(false));
        check(c.internal_falling_edge()==std::optional<bool>((value>>i)&1u));
    }
    check(c.ready_nbusy()==std::optional<bool>(true));
    check(!c.internal_falling_edge());
}
int main(int argc,char** argv) {
 try {
    if(argc!=2)return 2;
    std::string which=argv[1];
    if(which=="all_bytes") {
        for(auto mode:{LoadingMode::passive_serial,LoadingMode::passive_parallel_sync,
                       LoadingMode::passive_parallel_async}) {
            ConfigIngress c(mode);c.begin_loading();auto p=selected();
            for(unsigned value=0;value<256;++value) {
                if(mode==LoadingMode::passive_parallel_async)send(c,p,value);
                for(unsigned i=0;i<8;++i) {
                    std::optional<bool> bit;
                    if(mode==LoadingMode::passive_parallel_async)bit=c.internal_falling_edge();
                    else {
                        auto rise=c.drive_dclk(true,mode==LoadingMode::passive_serial ? value>>i : value);
                        auto fall=c.drive_dclk(false,0);
                        if(mode==LoadingMode::passive_serial){check(!fall);bit=rise;}
                        else{check(!rise);bit=fall;}
                    }
                    check(bit==std::optional<bool>(((value/(1u<<i))%2u)!=0));
                }
            }
        }
    } else if(which=="edge_and_latch") {
        ConfigIngress ps(LoadingMode::passive_serial);ps.begin_loading();
        check(!ps.drive_dclk(false,1));check(ps.drive_dclk(true,0x81)==std::optional<bool>(true));
        check(!ps.drive_dclk(true,0));check(!ps.drive_dclk(false,1));
        check(ps.drive_dclk(true,0x80)==std::optional<bool>(false));check(!ps.ready_nbusy());
        ConfigIngress pp(LoadingMode::passive_parallel_sync);pp.begin_loading();
        check(!pp.drive_dclk(true,0xa6));
        for(unsigned i=0;i<8;++i){
            if(i)check(!pp.drive_dclk(true,0x59));
            check(!pp.drive_dclk(true,0xff));
            check(pp.drive_dclk(false,0x59)==std::optional<bool>((0xa6u>>i)&1u));
            check(!pp.drive_dclk(false,0xff));
        }
        check(pp.pending_bits()==0);check(!pp.drive_dclk(true,1));
        check(pp.drive_dclk(false,0)==std::optional<bool>(true));check(pp.pending_bits()==7);
    } else if(which=="ppa_capture") {
        ConfigIngress c(LoadingMode::passive_parallel_async);c.begin_loading();auto p=selected(0);
        c.drive_parallel(p);p.nws=false;c.drive_parallel(p);check(c.pending_bits()==0);
        p.data=0xd3;c.drive_parallel(p);check(c.pending_bits()==0);
        p.nws=true;c.drive_parallel(p);check(c.pending_bits()==8);
        p.data=0x2c;c.drive_parallel(p);check(c.pending_bits()==8);drain(c,0xd3);
    } else if(which=="polling") {
        ConfigIngress c(LoadingMode::passive_parallel_async);c.begin_loading();auto p=selected();
        c.drive_parallel(p);check(c.data_bus_drive().mask==0);
        p.nrs=false;c.drive_parallel(p);check(c.data_bus_drive().mask==0x80);
        check(c.data_bus_drive().value==0x80);p.nrs=true;c.drive_parallel(p);
        send(c,p,0xb2);p.nrs=false;c.drive_parallel(p);
        for(unsigned i=0;i<1000;++i){check(c.data_bus_drive().mask==0x80);
            check(c.data_bus_drive().value==0);check(c.pending_bits()==8);}
        p.nrs=true;c.drive_parallel(p);drain(c,0xb2);
    } else if(which=="clock_domains") {
        ConfigIngress c(LoadingMode::passive_parallel_async);c.begin_loading();auto p=selected();send(c,p,0xe1);
        rejects([&]{c.drive_dclk(true,0);});check(c.pending_bits()==8);drain(c,0xe1);
        for(auto mode:{LoadingMode::passive_serial,LoadingMode::passive_parallel_sync}){
            ConfigIngress d(mode);d.begin_loading();rejects([&]{d.internal_falling_edge();});
            rejects([&]{d.drive_parallel(p);});check(!d.ready_nbusy());check(d.data_bus_drive().mask==0);
        }
    } else if(which=="lifecycle") {
        ConfigIngress c(LoadingMode::passive_parallel_async);auto p=selected();
        check(!c.loading());check(!c.ready_nbusy());check(c.data_bus_drive().mask==0);
        rejects([&]{c.drive_parallel(p);});rejects([&]{c.internal_falling_edge();});
        for(unsigned count=0;count<8;++count){c.begin_loading();rejects([&]{c.begin_loading();});
            p=selected();send(c,p,0xff);for(unsigned i=0;i<count;++i)check(c.internal_falling_edge()==true);
            c.abort_loading();check(!c.loading());check(!c.ready_nbusy());check(c.pending_bits()==0);
        }
        c.begin_loading();p=selected();send(c,p,0x42);drain(c,0x42);
    } else if(which=="busy_refusal") {
        ConfigIngress c(LoadingMode::passive_parallel_async);c.begin_loading();auto p=selected();send(c,p,0x93);
        auto bad=p;bad.nws=false;bad.data=0x6c;rejects([&]{c.drive_parallel(bad);});
        check(c.pending_bits()==8);c.drive_parallel(p);check(c.pending_bits()==8);drain(c,0x93);
        send(c,p,0x6c);drain(c,0x6c);
    } else if(which=="selects") {
        for(unsigned sel=0;sel<4;++sel){ConfigIngress c(LoadingMode::passive_parallel_async);c.begin_loading();
            ParallelPins p{};p.cs=sel&1;p.ncs=sel&2;send(c,p,0xad);
            bool accepted=p.cs&&!p.ncs;check(c.pending_bits()==(accepted?8u:0u));
            p.nrs=false;c.drive_parallel(p);check(c.data_bus_drive().mask==(accepted?0x80u:0u));
        }
        ConfigIngress c(LoadingMode::passive_parallel_async);c.begin_loading();auto p=selected();send(c,p,0xba);
        p.cs=false;c.drive_parallel(p);drain(c,0xba); // deselection cannot change captured data
    } else if(which=="turnaround") {
        ConfigIngress c(LoadingMode::passive_parallel_async);c.begin_loading();auto p=selected();c.drive_parallel(p);
        auto bad=p;bad.nws=false;bad.nrs=false;rejects([&]{c.drive_parallel(bad);});
        check(c.pending_bits()==0);p.nrs=false;c.drive_parallel(p);
        bad=p;bad.nws=false;bad.nrs=true;rejects([&]{c.drive_parallel(bad);});
        check(c.data_bus_drive().mask==0x80);p.nrs=true;c.drive_parallel(p);send(c,p,0x51);drain(c,0x51);
        c.abort_loading();c.begin_loading();ParallelPins off{};off.nws=false;c.drive_parallel(off);
        bad=selected();rejects([&]{c.drive_parallel(bad);});check(c.pending_bits()==0);
    } else if(which=="instances") {
        rejects([]{ConfigIngress c(static_cast<LoadingMode>(99));});
        ConfigIngress a(LoadingMode::passive_parallel_async),b(LoadingMode::passive_parallel_async);
        a.begin_loading();b.begin_loading();auto pa=selected(),pb=selected();send(a,pa,0x7d);send(b,pb,0x82);
        drain(a,0x7d);check(b.pending_bits()==8);a.abort_loading();drain(b,0x82);
    } else return 3;
 } catch(const std::exception&) {return 1;}
 return 0;
}
'''

class NativeIngressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.tmp.name)
        cls.compilers = [p for name in ('g++', 'clang++') if (p := shutil.which(name))]
        if not cls.compilers:
            cls.tmp.cleanup()
            raise unittest.SkipTest('C++17 compiler required')
        cls.executables = []
        src = cls.work/'tests.cpp'; src.write_text(HARNESS, encoding='utf-8')
        for i, cxx in enumerate(cls.compilers):
            exe = cls.work/(f'tests{i}'+('.exe' if os.name=='nt' else ''))
            result = subprocess.run([cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I', str(ROOT/'runtime'),
                str(src), '-o', str(exe)], capture_output=True, text=True, timeout=45)
            if result.returncode:
                cls.tmp.cleanup(); raise AssertionError(result.stderr)
            cls.executables.append(exe)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def case(self, name):
        for exe in self.executables:
            with self.subTest(compiler=str(exe), scenario=name):
                result = subprocess.run([str(exe), name], capture_output=True, text=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_exhaustive_byte_values_all_three_modes(self): self.case('all_bytes')
    def test_clock_edges_and_pps_latch_snapshot(self): self.case('edge_and_latch')
    def test_ppa_captures_rising_not_falling_strobe(self): self.case('ppa_capture')
    def test_masked_status_reads_never_advance_clock(self): self.case('polling')
    def test_external_and_internal_clocks_cannot_be_confused(self): self.case('clock_domains')
    def test_loading_contract_abort_and_every_partial_byte(self): self.case('lifecycle')
    def test_busy_rejection_does_not_mutate_pending_byte(self): self.case('busy_refusal')
    def test_chip_select_truth_table_and_latched_deselection(self): self.case('selects')
    def test_overlapping_and_simultaneous_strobes_fail_before_mutation(self): self.case('turnaround')
    def test_invalid_mode_and_independent_device_instances(self): self.case('instances')


class IngressEvidenceTests(unittest.TestCase):
    def report(self, n=1):
        return {'schema_version':1, 'synthetic_pin_stimulus':True, 'board_mode_identified':False,
                'configuration_completed':False, 'stream_bytes':n,
                'modes':[{'mode':m,'accepted_bits':n*8,'matches_input_lsb_first':True}
                         for m in ('PS','PPS','PPA')],
                'ppa_busy_observations':n*8,'ppa_masked_status_reads':n*24}

    def test_complete_mode_set_required_and_no_fidelity_promotion(self):
        validate_report(self.report(),1)
        for field,value in [('configuration_completed',True),('board_mode_identified',True),
                            ('synthetic_pin_stimulus',False),('stream_bytes',True),
                            ('ppa_busy_observations',7)]:
            r=self.report();r[field]=value
            with self.assertRaises(ValueError):validate_report(r,1)
        for mutation in ('missing','duplicate','partial'):
            r=self.report()
            if mutation=='missing':r['modes'].pop()
            elif mutation=='duplicate':r['modes'][2]=copy.deepcopy(r['modes'][1])
            else:r['modes'][2]['accepted_bits']=7
            with self.assertRaises(ValueError):validate_report(r,1)

    def test_private_baseline_hash_guard_runs_before_compiler(self):
        with tempfile.TemporaryDirectory() as tmp:
            image=Path(tmp)/'wrong.bin';image.write_bytes(b'\0'*0x200000)
            with self.assertRaisesRegex(ValueError,'identity'):
                run_probe(image,('nonexistent-compiler',))

    def test_native_probe_all_bytes_and_invalid_sizes(self):
        compiler=shutil.which('g++') or shutil.which('clang++')
        if not compiler:self.skipTest('C++17 compiler required')
        with tempfile.TemporaryDirectory() as tmp:
            tmp=Path(tmp);exe=tmp/('probe.exe' if os.name=='nt' else 'probe')
            built=subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'runtime'),str(ROOT/'tools/experimental/flex8000_ingress_probe.cpp'),
                '-o',str(exe)],capture_output=True,text=True,timeout=45)
            self.assertEqual(built.returncode,0,built.stderr)
            data=tmp/'synthetic.bin';data.write_bytes(bytes(range(256)))
            run=subprocess.run([str(exe),str(data)],capture_output=True,text=True,timeout=15)
            self.assertEqual(run.returncode,0,run.stderr)
            validate_report(json.loads(run.stdout),256)
            for n in (0,65537):
                data.write_bytes(b'\0'*n)
                bad=subprocess.run([str(exe),str(data)],capture_output=True,text=True,timeout=15)
                self.assertEqual(bad.returncode,2);self.assertEqual(bad.stdout,'')

    def test_cli_refuses_output_over_private_input_including_hardlink(self):
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'original.bin';source.write_bytes(b'private synthetic input')
            alias=Path(tmp)/'alias.bin';os.link(source,alias)
            for destination in (source,alias):
                result=subprocess.run([sys.executable,'-m','arcaderecomp.config_ingress_probe',
                    '--image',str(source),'--output',str(destination)],cwd=ROOT,
                    capture_output=True,text=True,timeout=15)
                self.assertEqual(result.returncode,2)
                self.assertIn('overwrite',result.stderr)
                self.assertEqual(source.read_bytes(),b'private synthetic input')

if __name__=='__main__':unittest.main()
