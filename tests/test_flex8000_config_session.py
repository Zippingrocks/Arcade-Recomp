"""Composed lifetime/phase tests on invented bytes; no Sega data in CI."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_epf8282_stream_decoder import synthetic

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include "flex8000_config_session.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>
using namespace arcaderecomp_flex8000;
using D=EPF8282StreamDecoder;
using Bytes=std::vector<std::uint8_t>;
void ck(bool b){if(!b)throw std::runtime_error("session assertion");}
template<class F> bool refuses(F f){try{f();return false;}catch(const std::logic_error&){return true;}}
Bytes read(const char* name){std::ifstream f(name,std::ios::binary);if(!f)throw std::runtime_error("file");return Bytes((std::istreambuf_iterator<char>(f)),{});}
StreamEnvelope envelope(const Bytes& b){StreamEnvelope e{};std::copy_n(b.begin(),31,e.prefix.begin());e.suffix=b.back();return e;}
auto begin(ConfigSession& s){return s.begin_observed_loading(AutoRestart::disabled,PinLevel::high,PinLevel::high);}
bool unavailable(ConfigSession& s,ConfigSession::Attempt t){return refuses([&]{(void)s.decoded_data(t);});}
bool feed(ConfigSession& s,ConfigSession::Attempt t,LoadingMode mode,const Bytes& b,std::size_t count){
 if(!count)return true;
 std::size_t n=0;ParallelPins pins{};pins.cs=true;pins.ncs=false;
 for(const auto byte:b){
  if(mode==LoadingMode::passive_parallel_async){pins.data=byte;pins.nws=false;s.drive_parallel(t,pins);pins.nws=true;s.drive_parallel(t,pins);}
  for(unsigned bit=0;bit<8;++bit){
   if(mode==LoadingMode::passive_parallel_async){if(!s.internal_falling_edge(t))return false;}
   else {if(!s.drive_dclk(t,true,mode==LoadingMode::passive_serial?std::uint8_t(byte>>bit):byte))return false;
         if(!s.drive_dclk(t,false,byte))return false;}
   if(++n==count)return true;
  }
 }throw std::runtime_error("bad cutoff");
}
void complete(ConfigSession& s,ConfigSession::Attempt t,LoadingMode m,const Bytes& b){ck(feed(s,t,m,b,D::kStreamBits));ck(s.finish_profile(t));}
StartupOptions options(){return {StartupClock::dclk,StartupClock::clkusr,StartupTimeout::enabled};}
void reset(ConfigSession& s){s.assert_nconfig_low();s.release_nconfig_after_qualified_reset();}
int main(int argc,char** argv){try{
 ck(argc==4);const auto b=read(argv[1]),expected=read(argv[2]);const std::string action=argv[3];const auto e=envelope(b);
 for(unsigned mode=0;mode<3;++mode){const auto m=static_cast<LoadingMode>(mode);ConfigSession s(m,e);
  if(action=="policy"){
   for(auto a:{AutoRestart::unknown,AutoRestart::enabled})ck(refuses([&]{s.begin_observed_loading(a,PinLevel::high,PinLevel::high);}));
   for(auto pin:{PinLevel::low,PinLevel::unknown}){
    ck(refuses([&]{s.begin_observed_loading(AutoRestart::disabled,pin,PinLevel::high);}));
    ck(refuses([&]{s.begin_observed_loading(AutoRestart::disabled,PinLevel::high,pin);}));}
   ck(s.phase()==SessionPhase::idle&&s.nstatus_drive()==DrainDrive::unknown);
   ck(refuses([&]{s.release_nconfig_after_qualified_reset();}));auto t=begin(s);
   ck(s.attempt_is_current(t)&&refuses([&]{begin(s);}));
  }else if(action=="complete"){
   auto t=begin(s);ck(unavailable(s,t));ck(feed(s,t,m,b,D::kStreamBits));
   ck(unavailable(s,t)&&!s.initialization_interval_elapsed()&&s.conf_done_drive()==DrainDrive::unknown);
   ck(refuses([&]{s.observe_conf_done_release(t,options(),PinLevel::high);}));
   ck(s.finish_profile(t));const auto data=s.decoded_data(t);ck(std::equal(data.begin(),data.end(),expected.begin(),expected.end()));
   ck(refuses([&]{s.qualified_startup_cycle(t,StartupClock::dclk);})&&s.phase()==SessionPhase::profile_ready);
   ck(refuses([&]{s.finish_profile(t);}));
  }else if(action=="owners"){
   ConfigSession other(m,e);auto t=begin(s),foreign=begin(other);
   ck(!s.attempt_is_current(foreign)&&!other.attempt_is_current(t));
   ck(refuses([&]{s.drive_dclk(foreign,true,0);})&&refuses([&]{s.finish_profile(foreign);}));
   ck(refuses([&]{s.observe_device_error(foreign,ConfigErrorCause::frame_error);}));
   complete(s,t,m,b);ck(refuses([&]{s.observe_conf_done_release(foreign,options(),PinLevel::high);}));
   reset(s);auto fresh=begin(s);complete(s,fresh,m,b);
   ck(!s.attempt_is_current(t)&&unavailable(s,t)&&s.attempt_is_current(fresh));
   ck(refuses([&]{s.observe_conf_done_release(t,options(),PinLevel::high);}));
  }else if(action=="reset"){
   auto t=begin(s);
   for(std::size_t cut:{0u,1u,7u,8u,247u,248u,249u,433u,439u,440u,40959u,40960u}){
    ck(feed(s,t,m,b,cut));s.assert_nconfig_low();s.assert_nconfig_low();
    ck(!s.attempt_is_current(t)&&unavailable(s,t)&&!s.bits_seen()&&!s.pending_bits());
    ck(s.nstatus_drive()==DrainDrive::sink_low&&s.conf_done_drive()==DrainDrive::sink_low);
    ck(refuses([&]{begin(s);}));s.release_nconfig_after_qualified_reset();
    ck(s.nstatus_drive()==DrainDrive::unknown&&s.conf_done_drive()==DrainDrive::unknown);
    t=begin(s);
   }complete(s,t,m,b);
  }else if(action=="errors"){
   for(auto cause:{ConfigErrorCause::frame_error,ConfigErrorCause::external_nstatus_low}){
    auto t=begin(s);ck(feed(s,t,m,b,251));s.observe_device_error(t,cause);
    ck(s.phase()==SessionPhase::device_error&&!s.attempt_is_current(t)&&unavailable(s,t));
    ck(!s.bits_seen()&&!s.pending_bits()&&s.nstatus_drive()==DrainDrive::sink_low);
    ck(!s.profile_failure()&&refuses([&]{s.qualified_startup_cycle(t,StartupClock::internal_oscillator);}));
    reset(s);
   }auto t=begin(s);complete(s,t,m,b);s.observe_device_error(t,ConfigErrorCause::frame_error);
   ck(unavailable(s,t)&&!s.pending_bits());reset(s);t=begin(s);complete(s,t,m,b);
  }else if(action=="diagnostic"){
   auto t=begin(s);Bytes wrong=b;wrong[0]^=1;ck(!feed(s,t,m,wrong,D::kStreamBits));
   auto f=s.profile_failure();ck(f&&f->error==StreamError::prefix_mismatch&&f->bit_position==0);
   ck(s.phase()==SessionPhase::profile_error&&s.nstatus_drive()==DrainDrive::unknown);
   ck(!s.pending_bits()&&!s.bits_seen()&&!s.attempt_is_current(t)&&unavailable(s,t));
   ck(refuses([&]{begin(s);})&&refuses([&]{s.observe_device_error(t,ConfigErrorCause::frame_error);}));
   reset(s);t=begin(s);complete(s,t,m,b);ck(!s.profile_failure());
  }else if(action=="truncation"){
   for(std::size_t cut:{0u,1u,7u,248u,251u,433u,439u,40959u}){
    auto t=begin(s);ck(feed(s,t,m,b,cut));ck(!s.finish_profile(t));auto f=s.profile_failure();
    ck(f&&f->error==StreamError::truncated&&f->bit_position==cut&&f->bits_seen==cut);
    ck(!s.pending_bits()&&!s.bits_seen()&&unavailable(s,t)&&s.nstatus_drive()==DrainDrive::unknown);reset(s);
   }
  }else if(action=="extra"){
   auto t=begin(s);ck(feed(s,t,m,b,D::kStreamBits));
   if(m==LoadingMode::passive_parallel_async){ParallelPins p{};p.cs=true;p.ncs=false;p.nws=false;s.drive_parallel(t,p);p.nws=true;s.drive_parallel(t,p);}
   else ck(m==LoadingMode::passive_serial?!s.drive_dclk(t,true,0):s.drive_dclk(t,true,0));
   if(m!=LoadingMode::passive_serial){ck(s.pending_bits()==8);ck(!s.finish_profile(t));}
   ck(s.profile_failure()->error==StreamError::extra_bits&&s.profile_failure()->bit_position==40960);
   ck(!s.pending_bits()&&!s.bits_seen()&&unavailable(s,t));
  }else if(action=="options"){
   auto t=begin(s);complete(s,t,m,b);
   ck(refuses([&]{s.observe_conf_done_release(t,{},PinLevel::high);}));
   ck(refuses([&]{s.observe_conf_done_release(t,options(),PinLevel::unknown);}));
   ck(s.phase()==SessionPhase::profile_ready&&s.attempt_is_current(t)&&!unavailable(s,t));
   s.observe_conf_done_release(t,options(),PinLevel::low);
   ck(refuses([&]{s.observe_conf_done_release(t,options(),PinLevel::high);}));
   ck(refuses([&]{s.observe_conf_done(t,PinLevel::unknown);})&&s.phase()==SessionPhase::waiting_conf_done);
  }else if(action=="startup"){
   auto t=begin(s);complete(s,t,m,b);s.observe_conf_done_release(t,options(),PinLevel::low);
   for(unsigned i=0;i<50;++i)s.qualified_startup_cycle(t,StartupClock::internal_oscillator);
   for(unsigned i=0;i<9;++i)s.qualified_startup_cycle(t,StartupClock::dclk);
   ck(s.phase()==SessionPhase::waiting_conf_done);s.observe_conf_done(t,PinLevel::high);
   for(unsigned i=0;i<50;++i)s.qualified_startup_cycle(t,StartupClock::dclk);
   ck(s.initialization_cycles()==0);
   for(unsigned i=0;i<9;++i)s.qualified_startup_cycle(t,StartupClock::clkusr);
   ck(!s.initialization_interval_elapsed());s.qualified_startup_cycle(t,StartupClock::clkusr);
   ck(s.initialization_interval_elapsed()&&s.initialization_cycles()==10&&!unavailable(s,t));
   ck(refuses([&]{s.drive_dclk(t,true,0);})&&refuses([&]{s.observe_device_error(t,ConfigErrorCause::frame_error);}));
   reset(s);ck(unavailable(s,t)&&!s.initialization_interval_elapsed());
  }else if(action=="timeout"){
   auto t=begin(s);complete(s,t,m,b);s.observe_conf_done_release(t,options(),PinLevel::low);
   for(unsigned i=0;i<10;++i)s.qualified_startup_cycle(t,StartupClock::dclk);
   ck(s.phase()==SessionPhase::startup_error&&s.nstatus_drive()==DrainDrive::sink_low);
   ck(!s.bits_seen()&&!s.pending_bits()&&!s.attempt_is_current(t)&&unavailable(s,t));
   ck(refuses([&]{s.observe_conf_done(t,PinLevel::high);})&&refuses([&]{begin(s);}));
   reset(s);auto fresh=begin(s);complete(s,fresh,m,b);ck(!s.attempt_is_current(t));
   auto opt=options();opt.timeout=StartupTimeout::disabled;s.observe_conf_done_release(fresh,opt,PinLevel::low);
   for(unsigned i=0;i<100;++i)s.qualified_startup_cycle(fresh,StartupClock::dclk);
   ck(s.phase()==SessionPhase::waiting_conf_done&&!unavailable(s,fresh));
  }else if(action=="phase_reset"){
   for(unsigned phase=0;phase<4;++phase){
    auto t=begin(s);complete(s,t,m,b);
    if(phase>0)s.observe_conf_done_release(t,options(),PinLevel::low);
    if(phase>1)s.observe_conf_done(t,PinLevel::high);
    if(phase>2)for(unsigned i=0;i<10;++i)s.qualified_startup_cycle(t,StartupClock::clkusr);
    reset(s);ck(!s.attempt_is_current(t)&&unavailable(s,t)&&!s.initialization_cycles());
    ck(refuses([&]{s.observe_conf_done_release(t,options(),PinLevel::high);}));
   }
  }else if(action=="reads"){
   auto t=begin(s);ck(feed(s,t,m,b,3));const auto bits=s.bits_seen();const auto left=s.pending_bits();
   for(unsigned i=0;i<1000;++i){(void)s.phase();(void)s.ready_nbusy(t);(void)s.data_bus_drive(t);
    (void)s.nstatus_drive();(void)s.conf_done_drive();(void)s.profile_failure();}
   ck(s.bits_seen()==bits&&s.pending_bits()==left&&!s.initialization_interval_elapsed());
   if(m==LoadingMode::passive_parallel_async)ck(!s.ready_nbusy(t).value());
   else ck(!s.ready_nbusy(t).has_value());
  }else if(action=="collision"){
   Bytes changed=b;for(std::size_t bit:{249u,261u})changed[bit/8]^=std::uint8_t(1u<<(bit%8));
   auto t=begin(s);complete(s,t,m,changed);const auto data=s.decoded_data(t);
   ck(!std::equal(data.begin(),data.end(),expected.begin(),expected.end()));
   ck(s.conf_done_drive()==DrainDrive::unknown&&!s.initialization_interval_elapsed());
   // Already obtained copies are plain data, not magically revocable objects.
   reset(s);ck(unavailable(s,t));auto fresh=begin(s);complete(s,fresh,m,b);ck(s.decoded_data(fresh)!=data);
  }else throw std::runtime_error("unknown action");
 }
 std::cout<<"passed\n";return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
'''

class ConfigSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='session-synthetic-')
        cls.root=Path(cls.temp.name);cls.executables=[]
        stream,expected=synthetic()
        (cls.root/'stream').write_bytes(stream);(cls.root/'expected').write_bytes(expected)
        (cls.root/'case.cpp').write_text(HARNESS,encoding='utf-8')
        try:
            for name in ('g++','clang++'):
                compiler=shutil.which(name)
                if not compiler:continue
                exe=cls.root/('case-'+name)
                run=subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                    '-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'runtime'),
                    str(cls.root/'case.cpp'),'-o',str(exe)],capture_output=True,text=True,timeout=40)
                if run.returncode:raise AssertionError(run.stderr)
                cls.executables.append(exe)
            if not cls.executables:raise unittest.SkipTest('C++17 compiler required')
        except BaseException:
            cls.temp.cleanup();raise
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def check(self,action):
        for exe in self.executables:
            with self.subTest(compiler=exe.name):
                p=subprocess.run([str(exe),str(self.root/'stream'),str(self.root/'expected'),action],
                                 capture_output=True,text=True,timeout=15)
                self.assertEqual(p.returncode,0,p.stderr)
                self.assertEqual(p.stdout,'passed\n')
    def test_explicit_policy_preparation_and_legal_begin(self):self.check('policy')
    def test_profile_data_is_not_automatic_acceptance(self):self.check('complete')
    def test_cross_instance_and_stale_handles_cannot_access_or_arm(self):self.check('owners')
    def test_reset_discards_data_and_partial_serializer_together(self):self.check('reset')
    def test_explicit_hardware_error_invalidates_current_and_completed_data(self):self.check('errors')
    def test_profile_failure_does_not_assert_hardware_error_signal(self):self.check('diagnostic')
    def test_truncation_discards_staging_and_preserves_diagnostic_position(self):self.check('truncation')
    def test_extra_bit_or_unserialized_parallel_byte_is_rejected(self):self.check('extra')
    def test_unknown_options_and_pin_levels_do_not_partially_arm(self):self.check('options')
    def test_external_release_and_separate_clock_intervals(self):self.check('startup')
    def test_timeout_invalidates_data_and_requires_reset(self):self.check('timeout')
    def test_reset_during_each_startup_phase_revokes_old_attempt(self):self.check('phase_reset')
    def test_reads_neither_advance_input_nor_startup(self):self.check('reads')
    def test_empirical_check_collision_is_not_physical_acceptance(self):self.check('collision')

if __name__=='__main__':unittest.main()
