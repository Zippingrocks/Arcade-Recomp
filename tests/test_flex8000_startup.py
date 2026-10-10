"""Synthetic native startup/line-resolution tests, not Sega hardware captures.

Oracle: Altera AN33 (June 2000), printed pp. 58-63. Every native case runs
under each installed GCC/Clang with UBSan. Integration deliberately DOES NOT
interpret the end of an input byte stream as accepted FPGA configuration.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PREFIX='''
#include "flex8000_startup.hpp"
#include "flex8000_config_ingress.hpp"
#include <iostream>
using namespace arcaderecomp_flex8000;
using C=StartupClock; using P=StartupPhase; using D=DrainDrive;
using L=PinLevel; using T=StartupTimeout;
[[maybe_unused]] static constexpr StartupOptions options{C::dclk,C::internal_oscillator,T::enabled};
template<class F> bool rejected(F f) {
    try {f();} catch(const std::logic_error&) {return true;} return false;
}
'''


def native(body):
    compilers=[x for x in (shutil.which('g++'),shutil.which('clang++')) if x]
    if not compilers:
        raise unittest.SkipTest('C++17 compiler required')
    results=[]
    for compiler in compilers:
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); source=d/'test.cpp'; exe=d/('test.exe' if os.name=='nt' else 'test')
            source.write_text(PREFIX+body,encoding='utf-8')
            cmd=[compiler,'-std=c++17','-O1','-Wall','-Wextra','-Werror',
                 '-fsanitize=undefined','-fno-sanitize-recover=all',
                 '-I',str(ROOT/'runtime'),str(source),'-o',str(exe)]
            build=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
            if build.returncode: raise AssertionError(compiler+'\n'+build.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            if run.returncode: raise AssertionError(f'{compiler}: exit {run.returncode}\n{run.stdout}{run.stderr}')
            results.append(run.stdout)
    if len(set(results))!=1: raise AssertionError('Compiler results differ')
    return results[0]


class StartupTests(unittest.TestCase):
    def test_missing_and_invalid_configuration_options_are_rejected(self):
        native(r'''
int main(){
 if(!rejected([]{ConfigStartup x(StartupOptions{});}))return 1;
 for(auto invalid:{C::unknown,static_cast<C>(99)}){
  if(!rejected([&]{ConfigStartup x({invalid,C::dclk,T::enabled});}))return 2;
  if(!rejected([&]{ConfigStartup x({C::dclk,invalid,T::enabled});}))return 3;
 }
 for(auto invalid:{T::unknown,static_cast<T>(99)})
  if(!rejected([&]{ConfigStartup x({C::dclk,C::dclk,invalid});}))return 4;
 return 0;
}''')

    def test_all_open_drain_combinations_against_independent_resolution_oracle(self):
        text=native(r'''
int main(){for(unsigned a=0;a<3;++a){for(unsigned b=0;b<3;++b){for(unsigned p=0;p<3;++p){
 std::cout<<a<<' '<<b<<' '<<p<<' '<<static_cast<unsigned>(resolve_open_drain(
  static_cast<D>(a),static_cast<D>(b),static_cast<PullUp>(p)))<<'\n';
 }}}
 return 0;}
''')
        rows=[tuple(map(int,line.split())) for line in text.splitlines()]
        self.assertEqual(len(rows),27)
        for a,b,p,result in rows:
            # 0 unknown, 1 released, 2 sinking; result 0 unknown,1 low,2 high.
            expected=1 if 2 in (a,b) else (2 if (a,b,p)==(1,1,2) else 0)
            self.assertEqual(result,expected,(a,b,p))

    def test_invalid_open_drain_values_are_not_treated_as_high(self):
        native(r'''
int main(){
 if(!rejected([]{resolve_open_drain(static_cast<D>(9),D::released,PullUp::present);}))return 1;
 if(!rejected([]{resolve_open_drain(D::released,static_cast<D>(9),PullUp::present);}))return 2;
 if(!rejected([]{resolve_open_drain(D::released,D::released,static_cast<PullUp>(9));}))return 3;
 return 0;
}''')

    def test_initial_unknown_state_and_release_do_not_claim_a_high_pin(self):
        native(r'''
int main(){ConfigStartup x(options);
 if(x.phase()!=P::unestablished || x.conf_done_drive()!=D::unknown || x.nstatus_drive()!=D::unknown)return 1;
 if(!rejected([&]{x.qualified_cycle(C::dclk);}))return 2;
 x.begin_after_conf_done_release();
 if(x.conf_done_drive()!=D::released || x.nstatus_drive()!=D::released)return 3;
 if(resolve_open_drain(x.conf_done_drive(),D::sink_low,PullUp::present)!=L::low)return 4;
 if(resolve_open_drain(x.conf_done_drive(),D::released,PullUp::absent)!=L::unknown)return 5;
 if(!rejected([&]{x.qualified_cycle(C::dclk);}) || x.observed_wait_cycles_capped()!=0)return 6;
 return 0;
}''')

    def test_timeout_at_ten_not_nine_and_error_latches(self):
        native(r'''
int main(){ConfigStartup x(options);x.begin_after_conf_done_release();x.observe_conf_done(L::low);
 for(unsigned n=0;n<9;++n)x.qualified_cycle(C::dclk);
 if(x.phase()!=P::waiting_conf_done || x.nstatus_drive()!=D::released)return 1;
 x.qualified_cycle(C::dclk);
 if(x.phase()!=P::timeout_error || x.nstatus_drive()!=D::sink_low || x.conf_done_drive()!=D::unknown)return 2;
 for(unsigned n=0;n<100;++n)x.qualified_cycle(C::dclk);
 if(x.observed_wait_cycles_capped()!=10 || x.initialization_interval_elapsed())return 3;
 if(!rejected([&]{x.begin_after_conf_done_release();}))return 4;
 if(!rejected([&]{x.observe_conf_done(L::high);}))return 5;
 return 0;
}''')

    def test_disabled_timeout_preserves_wait_until_external_high(self):
        native(r'''
int main(){ConfigStartup x({C::dclk,C::clkusr,T::disabled});x.begin_after_conf_done_release();
 x.observe_conf_done(L::low);for(unsigned n=0;n<10000;++n)x.qualified_cycle(C::dclk);
 if(x.phase()!=P::waiting_conf_done || x.observed_wait_cycles_capped()!=10)return 1;
 x.observe_conf_done(L::high);
 for(unsigned n=0;n<9;++n)x.qualified_cycle(C::clkusr);
 if(x.initialization_interval_elapsed())return 2;
 x.qualified_cycle(C::clkusr);if(!x.initialization_interval_elapsed())return 3;
 return 0;
}''')

    def test_repeated_pin_reads_do_not_advance_either_clock_window(self):
        native(r'''
int main(){ConfigStartup x(options);x.begin_after_conf_done_release();x.observe_conf_done(L::low);
 for(unsigned n=0;n<10000;++n){(void)x.conf_done_drive();(void)x.nstatus_drive();(void)x.phase();}
 if(x.observed_wait_cycles_capped()!=0)return 1;
 x.observe_conf_done(L::high);
 for(unsigned n=0;n<10000;++n){x.observe_conf_done(L::high);(void)x.initialization_interval_elapsed();}
 if(x.initialization_cycles()!=0 || x.initialization_interval_elapsed())return 2;
 return 0;
}''')

    def test_separate_clock_domains_and_early_clock_events_cannot_accumulate(self):
        native(r'''
int main(){ConfigStartup x(options);x.begin_after_conf_done_release();x.observe_conf_done(L::low);
 for(unsigned n=0;n<20;++n){x.qualified_cycle(C::internal_oscillator);x.qualified_cycle(C::clkusr);}
 if(x.observed_wait_cycles_capped()!=0)return 1;
 x.observe_conf_done(L::high);
 for(unsigned n=0;n<20;++n){x.qualified_cycle(C::dclk);x.qualified_cycle(C::clkusr);}
 if(x.initialization_cycles()!=0)return 2;
 for(unsigned n=0;n<10;++n)x.qualified_cycle(C::internal_oscillator);
 if(!x.initialization_interval_elapsed())return 3;
 return 0;
}''')

    def test_resolved_high_starts_but_does_not_complete_initialization(self):
        native(r'''
int main(){ConfigStartup x(options);x.begin_after_conf_done_release();
 x.observe_conf_done(resolve_open_drain(x.conf_done_drive(),D::released,PullUp::present));
 if(x.phase()!=P::initializing || x.initialization_cycles()!=0)return 1;
 for(unsigned n=0;n<10;++n){
  if(x.initialization_interval_elapsed())return 2;
  x.qualified_cycle(C::internal_oscillator);
 }
 if(!x.initialization_interval_elapsed() || x.initialization_cycles()!=10)return 3;
 for(unsigned n=0;n<100;++n)x.qualified_cycle(C::internal_oscillator);
 if(x.initialization_cycles()!=10 || !rejected([&]{x.begin_after_conf_done_release();}))return 4;
 return 0;
}''')

    def test_unmodeled_pin_changes_are_rejected_without_state_mutation(self):
        native(r'''
int main(){ConfigStartup x(options);x.begin_after_conf_done_release();
 if(!rejected([&]{x.observe_conf_done(L::unknown);}))return 1;
 if(!rejected([&]{x.observe_conf_done(static_cast<L>(99));}))return 2;
 if(x.phase()!=P::waiting_conf_done)return 3;
 x.observe_conf_done(L::high);x.qualified_cycle(C::internal_oscillator);
 if(!rejected([&]{x.observe_conf_done(L::low);}))return 4;
 if(!rejected([&]{x.qualified_cycle(C::unknown);}))return 5;
 if(x.phase()!=P::initializing || x.initialization_cycles()!=1)return 6;
 return 0;
}''')

    def test_reset_invalidates_every_stage_and_does_not_accept_a_configuration(self):
        native(r'''
int main(){for(unsigned stage=0;stage<5;++stage){ConfigStartup x(options);
 if(stage){x.begin_after_conf_done_release();x.observe_conf_done(L::low);}
 if(stage==2 || stage==3)x.observe_conf_done(L::high);
 if(stage==3)for(unsigned n=0;n<10;++n)x.qualified_cycle(C::internal_oscillator);
 if(stage==4)for(unsigned n=0;n<10;++n)x.qualified_cycle(C::dclk);
 x.assert_nconfig_low();
 if(x.phase()!=P::reset_asserted || x.conf_done_drive()!=D::sink_low || x.nstatus_drive()!=D::sink_low)return 1;
 if(x.initialization_interval_elapsed() || x.observed_wait_cycles_capped()!=0 || x.initialization_cycles()!=0)return 2;
 if(!rejected([&]{x.begin_after_conf_done_release();}) || !rejected([&]{x.qualified_cycle(C::dclk);}))return 3;
 x.release_nconfig_high();
 if(x.phase()!=P::unestablished || x.conf_done_drive()!=D::unknown)return 4;
 if(!rejected([&]{x.release_nconfig_high();}) || !rejected([&]{x.qualified_cycle(C::dclk);}))return 5;
 x.begin_after_conf_done_release();x.observe_conf_done(L::high);
 for(unsigned n=0;n<10;++n)x.qualified_cycle(C::internal_oscillator);
 if(!x.initialization_interval_elapsed())return 6;
}return 0;
}''')

    def test_timeout_and_initialization_matrix_against_independent_count_oracle(self):
        text=native(r'''
int main(){for(unsigned a=1;a<=3;++a){for(unsigned b=1;b<=3;++b){
 for(unsigned off=0;off<2;++off){for(unsigned wait=0;wait<13;++wait){for(unsigned init=0;init<12;++init){
  ConfigStartup x({static_cast<C>(a),static_cast<C>(b),off?T::disabled:T::enabled});
  x.begin_after_conf_done_release();x.observe_conf_done(L::low);
  for(unsigned n=0;n<wait;++n)x.qualified_cycle(static_cast<C>(a));
  if(x.phase()!=P::timeout_error){x.observe_conf_done(L::high);
   for(unsigned n=0;n<init;++n)x.qualified_cycle(static_cast<C>(b));}
  std::cout<<a<<' '<<b<<' '<<off<<' '<<wait<<' '<<init<<' '
   <<static_cast<unsigned>(x.phase())<<' '<<x.observed_wait_cycles_capped()<<' '
   <<x.initialization_cycles()<<'\n';
 }}}}}
 return 0;}
''')
        rows=[tuple(map(int,line.split())) for line in text.splitlines()]
        self.assertEqual(len(rows),2808)
        for a,b,off,wait,init,phase,waited,count in rows:
            failed=not off and wait>=10
            expected=4 if failed else (3 if init>=10 else 2)
            self.assertEqual((phase,waited,count),(expected,min(wait,10),0 if failed else min(init,10)),
                             (a,b,off,wait,init))

    def test_serialization_of_bytes_never_arms_startup(self):
        native(r'''
int main(){ConfigStartup startup(options);
 for(auto mode:{LoadingMode::passive_serial,LoadingMode::passive_parallel_sync,LoadingMode::passive_parallel_async}){
  ConfigIngress input(mode);input.begin_loading();unsigned emitted=0;
  for(unsigned byte=0;byte<256;++byte){
   if(mode==LoadingMode::passive_parallel_async){
    ParallelPins p{static_cast<std::uint8_t>(byte),true,false,false,true};
    input.drive_parallel(p);p.nws=true;input.drive_parallel(p);
    for(unsigned bit=0;bit<8;++bit)if(input.internal_falling_edge().has_value())++emitted;
   } else for(unsigned bit=0;bit<8;++bit){
    auto data=static_cast<std::uint8_t>(mode==LoadingMode::passive_serial?(byte>>bit):byte);
    if(input.drive_dclk(true,data).has_value())++emitted;
    if(input.drive_dclk(false,data).has_value())++emitted;
   }
  }
  if(emitted!=2048 || input.pending_bits()!=0)return 1;
  if(startup.phase()!=P::unestablished || startup.initialization_interval_elapsed())return 2;
  if(!rejected([&]{startup.qualified_cycle(C::dclk);}))return 3;
 }return 0;
}''')

    def test_one_devices_release_does_not_override_other_devices_low(self):
        native(r'''
int main(){ConfigStartup a({C::dclk,C::dclk,T::disabled}),b({C::dclk,C::dclk,T::disabled});
 a.begin_after_conf_done_release();b.assert_nconfig_low();
 auto net=resolve_open_drain(a.conf_done_drive(),b.conf_done_drive(),PullUp::present);
 if(net!=L::low)return 1;
 a.observe_conf_done(net);
 for(unsigned n=0;n<25;++n)a.qualified_cycle(C::dclk);
 if(a.phase()!=P::waiting_conf_done)return 2;
 b.release_nconfig_high();b.begin_after_conf_done_release();
 net=resolve_open_drain(a.conf_done_drive(),b.conf_done_drive(),PullUp::present);
 a.observe_conf_done(net);b.observe_conf_done(net);
 for(unsigned n=0;n<10;++n){a.qualified_cycle(C::dclk);b.qualified_cycle(C::dclk);}
 if(!a.initialization_interval_elapsed()||!b.initialization_interval_elapsed())return 3;
 return 0;
}''')

if __name__=='__main__':unittest.main()
