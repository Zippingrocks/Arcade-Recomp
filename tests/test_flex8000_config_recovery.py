"""Manufacturer-scoped recovery tests; inputs are synthetic, not cabinet captures.

Altera AN33 pp. 39/58/60/62/69. Error notifications are explicit device-event
fixtures; empirical stream parsing never creates an inferred hardware error.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PREFIX=r'''
#include "flex8000_config_recovery.hpp"
#include "flex8000_config_ingress.hpp"
#include "epf8282_stream_decoder.hpp"
#include <iostream>
using namespace arcaderecomp_flex8000;
using S=ConfigScheme; using A=AutoRestart; using P=RecoveryPhase;
using C=StartupClock; using L=PinLevel; using D=DrainDrive;
template<class F> bool refused(F f) {
 try{f();}catch(const std::logic_error&){return true;}return false;
}
[[maybe_unused]] constexpr RecoveryPolicy passive{S::passive_serial,A::disabled};
[[maybe_unused]] constexpr RecoveryPolicy active{S::active_serial,A::enabled};
'''

def native(body):
    compilers=[p for p in (shutil.which('g++'),shutil.which('clang++')) if p]
    if not compilers: raise unittest.SkipTest('C++17 compiler required')
    outputs=[]
    for compiler in compilers:
        with tempfile.TemporaryDirectory() as d:
            d=Path(d); source=d/'test.cpp'; exe=d/('test.exe' if os.name=='nt' else 'test')
            source.write_text(PREFIX+body,encoding='utf-8')
            run=subprocess.run([compiler,'-std=c++17','-O1','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'runtime'),
                str(source),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            if run.returncode:raise AssertionError(compiler+'\n'+run.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            if run.returncode:raise AssertionError(f'{compiler}: exit {run.returncode}\n{run.stdout}{run.stderr}')
            outputs.append(run.stdout)
    if len(set(outputs))!=1:raise AssertionError('Compiler metadata differs')
    return outputs[0]


class ConfigurationRecoveryTests(unittest.TestCase):
    def test_exact_mode_straps_and_reserved_or_unknown_inputs(self):
        output=native(r'''
int main(){
 for(unsigned mask=0;mask<8;++mask){
  try{std::cout<<mask<<' '<<static_cast<unsigned>(decode_config_straps(
   mask&4?L::high:L::low,mask&2?L::high:L::low,mask&1?L::high:L::low))<<'\n';}
  catch(const std::invalid_argument&){std::cout<<"reserved\n";}
 }
 for(unsigned pos=0;pos<3;++pos){
  L pins[3]={L::low,L::low,L::low};pins[pos]=L::unknown;
  if(!refused([&]{decode_config_straps(pins[0],pins[1],pins[2]);}))return 1;
  pins[pos]=static_cast<L>(88);
  if(!refused([&]{decode_config_straps(pins[0],pins[1],pins[2]);}))return 2;
 }
 return 0;
}''')
        self.assertEqual(output.splitlines(),['0 0','1 reserved','2 3','3 reserved',
                                               '4 1','5 4','6 2','7 5'])

    def test_passive_autorestart_is_rejected_not_silently_disabled(self):
        native(r'''
int main(){
 for(S s:{S::passive_serial,S::passive_parallel_sync,S::passive_parallel_async}){
  ConfigRecovery r;
  if(!refused([&]{r.begin_observed_loading({s,A::enabled},L::high,L::high);}))return 1;
  if(r.phase()!=P::unestablished||r.generation()!=0||r.nstatus_drive()!=D::unknown)return 2;
  auto t=r.begin_observed_loading({s,A::disabled},L::high,L::high);
  r.observe_device_error(ConfigErrorCause::frame_error);
  for(unsigned i=0;i<100;++i)r.qualified_cycle(C::internal_oscillator);
  if(r.attempt_is_current(t)||r.phase()!=P::error_latched||r.nstatus_drive()!=D::sink_low)return 3;
 }
 return 0;
}''')

    def test_unknown_policies_pins_and_initial_error_are_nonmutating(self):
        native(r'''
int main(){ConfigRecovery r;
 for(auto bad:{A::unknown,static_cast<A>(88)})
  if(!refused([&]{r.begin_observed_loading({S::active_serial,bad},L::high,L::high);}))return 1;
 if(!refused([&]{r.begin_observed_loading({static_cast<S>(88),A::disabled},L::high,L::high);}))return 2;
 for(L level:{L::unknown,L::low,static_cast<L>(88)}){
  if(!refused([&]{r.begin_observed_loading(active,level,L::high);}))return 3;
  if(!refused([&]{r.begin_observed_loading(active,L::high,level);}))return 4;
 }
 if(!refused([&]{r.observe_device_error(ConfigErrorCause::frame_error);}))return 5;
 if(!refused([&]{r.release_nconfig_after_qualified_reset();}))return 6;
 if(r.phase()!=P::unestablished||r.generation()!=0||r.nstatus_drive()!=D::unknown)return 7;
 return 0;
}''')

    def test_restart_cycles_against_independent_python_count_oracle(self):
        output=native(r'''
int main(){
 for(unsigned scheme=0;scheme<6;++scheme){for(unsigned enable=0;enable<2;++enable){
 if(scheme>=3&&enable)continue;
 for(unsigned cause=0;cause<2;++cause){for(unsigned source=1;source<=3;++source){
 for(unsigned ticks=0;ticks<23;++ticks){
  ConfigRecovery r;auto t=r.begin_observed_loading({static_cast<S>(scheme),
      enable?A::enabled:A::disabled},L::high,L::high);
  r.observe_device_error(static_cast<ConfigErrorCause>(cause));
  for(unsigned i=0;i<ticks;++i)r.qualified_cycle(static_cast<C>(source));
  std::cout<<scheme<<' '<<enable<<' '<<cause<<' '<<source<<' '<<ticks<<' '
   <<static_cast<unsigned>(r.phase())<<' '<<r.restart_cycles()<<' '
   <<static_cast<unsigned>(r.nstatus_drive())<<' '<<r.attempt_is_current(t)<<'\n';
 }}}}}
 return 0;
}''')
        rows=[list(map(int,s.split())) for s in output.splitlines()]
        self.assertEqual(len(rows),1242)
        for scheme,enable,cause,source,ticks,phase,count,drive,current in rows:
            expected_count=min(ticks,10) if enable and source==2 else 0
            expected_phase=2 if not enable else (4 if expected_count==10 else 3)
            expected_drive=1 if expected_phase==4 else 2
            self.assertEqual((phase,count,drive,current),
                (expected_phase,expected_count,expected_drive,0),
                (scheme,enable,cause,source,ticks))

    def test_tenth_cycle_release_is_not_resolved_high_or_a_new_load(self):
        native(r'''
int main(){ConfigRecovery r;auto old=r.begin_observed_loading(active,L::high,L::high);
 r.observe_device_error(ConfigErrorCause::frame_error);
 for(unsigned n=0;n<9;++n)r.qualified_cycle(C::internal_oscillator);
 if(r.nstatus_drive()!=D::sink_low||r.restart_cycles()!=9)return 1;
 r.qualified_cycle(C::internal_oscillator);
 if(r.nstatus_drive()!=D::released||r.attempt_is_current(old))return 2;
 auto held=resolve_open_drain(r.nstatus_drive(),D::sink_low,PullUp::present);
 if(held!=L::low||!refused([&]{r.begin_observed_loading(active,L::high,held);}))return 3;
 if(r.phase()!=P::restart_released)return 4;
 auto floating=resolve_open_drain(r.nstatus_drive(),D::released,PullUp::absent);
 if(floating!=L::unknown||!refused([&]{r.begin_observed_loading(active,L::high,floating);}))return 5;
 auto high=resolve_open_drain(r.nstatus_drive(),D::released,PullUp::present);
 auto current=r.begin_observed_loading(active,L::high,high);
 if(!r.attempt_is_current(current)||r.attempt_is_current(old)||current.generation==old.generation)return 6;
 return 0;
}''')

    def test_reads_invalid_clocks_and_repeated_errors_do_not_advance(self):
        native(r'''
int main(){ConfigRecovery r;r.begin_observed_loading(active,L::high,L::high);
 if(!refused([&]{r.observe_device_error(static_cast<ConfigErrorCause>(88));}))return 1;
 if(r.phase()!=P::loading)return 2;
 r.observe_device_error(ConfigErrorCause::frame_error);auto g=r.generation();
 for(unsigned i=0;i<100;++i){
  (void)r.nstatus_drive();(void)r.phase();(void)r.restart_cycles();(void)r.generation();
  r.qualified_cycle(C::dclk);r.qualified_cycle(C::clkusr);
 }
 if(r.restart_cycles()!=0||r.generation()!=g)return 3;
 for(auto bad:{C::unknown,static_cast<C>(88)})
  if(!refused([&]{r.qualified_cycle(bad);}))return 4;
 if(!refused([&]{r.observe_device_error(ConfigErrorCause::frame_error);}))return 5;
 if(r.restart_cycles()!=0||r.generation()!=g||r.phase()!=P::restart_pulse)return 6;
 return 0;
}''')

    def test_reset_interrupts_each_partial_restart_and_does_not_resume_by_itself(self):
        native(r'''
int main(){for(unsigned partial=0;partial<=10;++partial){
 ConfigRecovery r;auto first=r.begin_observed_loading(active,L::high,L::high);
 r.observe_device_error(ConfigErrorCause::frame_error);
 for(unsigned n=0;n<partial;++n)r.qualified_cycle(C::internal_oscillator);
 r.assert_nconfig_low();auto g=r.generation();r.assert_nconfig_low();
 if(r.generation()!=g||r.nstatus_drive()!=D::sink_low||r.attempt_is_current(first))return 1;
 for(unsigned n=0;n<20;++n)r.qualified_cycle(C::internal_oscillator);
 if(r.phase()!=P::reset_asserted||r.restart_cycles()!=0)return 2;
 r.release_nconfig_after_qualified_reset();
 if(r.nstatus_drive()!=D::unknown||r.phase()!=P::reset_released)return 3;
 if(!refused([&]{r.require_attempt(first);}))return 4;
 auto fresh=r.begin_observed_loading(passive,L::high,L::high);r.require_attempt(fresh);
 r.observe_device_error(ConfigErrorCause::frame_error);
 for(unsigned n=0;n<20;++n)r.qualified_cycle(C::internal_oscillator);
 if(r.phase()!=P::error_latched)return 5;
 }
 return 0;
}''')

    def test_manual_recovery_requires_low_high_and_new_qualified_window(self):
        native(r'''
int main(){ConfigRecovery r;auto first=r.begin_observed_loading(passive,L::high,L::high);
 if(!refused([&]{r.begin_observed_loading(passive,L::high,L::high);}))return 1;
 r.observe_device_error(ConfigErrorCause::external_nstatus_low);
 if(!refused([&]{r.begin_observed_loading(passive,L::high,L::high);}))return 2;
 if(!refused([&]{r.release_nconfig_after_qualified_reset();}))return 3;
 r.assert_nconfig_low();
 if(!refused([&]{r.begin_observed_loading(passive,L::high,L::high);}))return 4;
 r.release_nconfig_after_qualified_reset();
 for(unsigned i=0;i<20;++i)r.qualified_cycle(C::internal_oscillator);
 if(r.phase()!=P::reset_released||r.nstatus_drive()!=D::unknown)return 5;
 auto t=r.begin_observed_loading(passive,L::high,L::high);
 if(!r.attempt_is_current(t)||r.attempt_is_current(first))return 6;
 return 0;
}''')

    def test_empirical_decoder_failure_never_invents_a_device_error(self):
        native(r'''
int main(){
 ConfigRecovery r;auto t=r.begin_observed_loading(passive,L::high,L::high);
 EPF8282StreamDecoder decoder(StreamEnvelope{});decoder.begin();
 if(decoder.push_bit(true)||decoder.state()!=StreamState::failed)return 1;
 if(!r.attempt_is_current(t)||r.nstatus_drive()!=D::released)return 2;
 ConfigStartup startup({C::dclk,C::dclk,StartupTimeout::enabled});
 if(startup.phase()!=StartupPhase::unestablished||startup.conf_done_drive()!=D::unknown)return 3;
 // An explicit *separate* synthetic hardware-event fixture is necessary.
 r.observe_device_error(ConfigErrorCause::frame_error);
 if(r.attempt_is_current(t)||r.nstatus_drive()!=D::sink_low)return 4;
 return 0;
}''')

    def test_parent_discards_stale_data_and_every_partial_byte_after_error(self):
        native(r'''
int main(){
 for(auto mode:{LoadingMode::passive_parallel_sync,LoadingMode::passive_parallel_async}){
 for(unsigned partial=0;partial<8;++partial){
  ConfigRecovery r;auto attempt=r.begin_observed_loading(passive,L::high,L::high);
  ConfigIngress ingress(mode);ingress.begin_loading();
  EPF8282StreamDecoder decoder(StreamEnvelope{});decoder.begin();
  if(mode==LoadingMode::passive_parallel_sync)(void)ingress.drive_dclk(true,0);
  else{ingress.drive_parallel({0,true,false,false,true});ingress.drive_parallel({0,true,false,true,true});}
  for(unsigned n=0;n<partial;++n){
   auto b=mode==LoadingMode::passive_parallel_sync?ingress.drive_dclk(false,0):ingress.internal_falling_edge();
   if(!b||!decoder.push_bit(*b))return 1;
   if(mode==LoadingMode::passive_parallel_sync)(void)ingress.drive_dclk(true,255);
  }
  r.observe_device_error(ConfigErrorCause::frame_error);
  if(!refused([&]{r.require_attempt(attempt);}))return 2;
  // Explicit parent integration: no discarded bits survive the failed attempt.
  ingress.abort_loading();decoder.reset();
  if(ingress.loading()||ingress.pending_bits()!=0||decoder.bits_seen()!=0)return 3;
  r.assert_nconfig_low();r.release_nconfig_after_qualified_reset();
  auto fresh=r.begin_observed_loading(passive,L::high,L::high);r.require_attempt(fresh);
  ingress.begin_loading();decoder.begin();
  if(decoder.bits_seen()!=0||ingress.pending_bits()!=0||r.attempt_is_current(attempt))return 4;
 }}return 0;
}''')

    def test_independent_instances_and_reset_invalidation_of_loading(self):
        native(r'''
int main(){ConfigRecovery a,b;
 auto x=a.begin_observed_loading(active,L::high,L::high);
 auto y=b.begin_observed_loading(passive,L::high,L::high);
 if(a.attempt_is_current(y)||b.attempt_is_current(x))return 4;
 if(!refused([&]{b.require_attempt(x);}))return 5;
 a.observe_device_error(ConfigErrorCause::frame_error);
 if(!b.attempt_is_current(y)||b.nstatus_drive()!=D::released)return 1;
 b.assert_nconfig_low();
 if(b.attempt_is_current(y)||a.attempt_is_current(x))return 2;
 for(unsigned i=0;i<10;++i)a.qualified_cycle(C::internal_oscillator);
 if(a.phase()!=P::restart_released||b.phase()!=P::reset_asserted)return 3;
 return 0;
}''')


if __name__=='__main__':unittest.main()
