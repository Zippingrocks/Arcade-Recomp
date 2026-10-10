"""Native streaming conformance using artificial payloads, never Sega bytes."""
from pathlib import Path
import copy
import json
import os
import random
import shutil
import subprocess
import tempfile
import unittest

from arcaderecomp.flex8000_sram import encode_record, serial_to_sof_data, TOTAL_BITS
from arcaderecomp.stream_decode_probe import parse_report, run_probe

ROOT=Path(__file__).resolve().parents[1]
HARNESS=r'''
#include "epf8282_stream_decoder.hpp"
#include "flex8000_startup.hpp"
#include <algorithm>
#include <array>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
using namespace arcaderecomp_flex8000;
using Decoder=EPF8282StreamDecoder;
using Bytes=std::vector<std::uint8_t>;
void check(bool condition){if(!condition)throw std::runtime_error("test assertion");}
Bytes read(const char* p){std::ifstream f(p,std::ios::binary);if(!f)throw std::runtime_error("input");return Bytes((std::istreambuf_iterator<char>(f)),{});}
bool bit(const Bytes& b,std::size_t n){return ((b[n/8]>>(n%8))&1u)!=0;}
StreamEnvelope envelope(const Bytes& bytes){StreamEnvelope e{};std::copy_n(bytes.begin(),31,e.prefix.begin());e.suffix=bytes.back();return e;}
bool unavailable(Decoder& d){try{(void)d.packed_data();return false;}catch(const std::logic_error&){return true;}}
template<class F> bool refuses(F f){try{f();return false;}catch(const std::logic_error&){return true;}}
void feed(Decoder& d,const Bytes& b,std::size_t n){for(std::size_t i=0;i<n;++i)check(d.push_bit(bit(b,i)));}
void success(Decoder& d,const Bytes& b,const Bytes& expected){
 d.begin();feed(d,b,Decoder::kStreamBits);check(d.finish());const auto got=d.packed_data();
 check(std::equal(got.begin(),got.end(),expected.begin(),expected.end()));
}
int main(int argc,char** argv){try{
 check(argc==4);const Bytes clean=read(argv[1]),expected=read(argv[2]);const std::string action=argv[3];
 check(clean.size()==5120 && expected.size()==Decoder::kPackedBytes);
 const auto env=envelope(clean);
 if(action=="valid"){
  Decoder d(env);check(unavailable(d));d.begin();
  check(refuses([&]{d.begin();}));
  for(std::size_t i=0;i<Decoder::kStreamBits;++i){
   check(d.push_bit(bit(clean,i)));const auto n=i+1;
   const auto records=n<Decoder::kPrefixBits?0:std::min(Decoder::kRecords,(n-Decoder::kPrefixBits)/Decoder::kRecordBits);
   check(d.records_validated()==records && d.bits_seen()==n);
  }
  check(unavailable(d) && d.state()==StreamState::receiving);check(d.finish());
  const auto got=d.packed_data();check(std::equal(got.begin(),got.end(),expected.begin()));
  check((got.back()&0xf0u)==0 && d.records_validated()==212);
  check(refuses([&]{d.push_bit(false);}) && refuses([&]{d.finish();}));
 }else if(action=="pauses"){
  for(std::size_t chunk: {1u,7u,8u,23u,177u,185u,192u,193u,257u,40959u}){
   Decoder d(env);d.begin();
   for(std::size_t pos=0;pos<Decoder::kStreamBits;){
    const auto end=std::min(pos+chunk,Decoder::kStreamBits);
    while(pos<end){check(d.push_bit(bit(clean,pos)));++pos;}
    const auto n=d.bits_seen();check(unavailable(d));
    for(unsigned j=0;j<3;++j)check(d.bits_seen()==n && d.state()==StreamState::receiving);
   }
   check(d.finish());const auto got=d.packed_data();check(std::equal(got.begin(),got.end(),expected.begin()));
  }
 }else if(action=="singlebits"){
  Bytes changed=clean;
  for(std::size_t record: {0u,106u,211u})for(std::size_t offset=0;offset<192;++offset){
   const auto index=248+record*192+offset;changed[index/8]^=std::uint8_t(1u<<(index%8));
   Decoder d(env);d.begin();bool failed=false;
   for(std::size_t i=0;i<Decoder::kStreamBits;++i)if(!d.push_bit(bit(changed,i))){failed=true;break;}
   check(failed && d.state()==StreamState::failed && unavailable(d));
   const bool middle=offset>=1 && offset<=185;
   check(d.error()==(middle?StreamError::record_check_mismatch:StreamError::fixed_bit_mismatch));
   check(d.failure_bit()==248+record*192+(middle?185:offset));
   check(d.records_validated()==record);
   const auto error=d.error();check(refuses([&]{d.push_bit(false);}) && d.error()==error);
   changed[index/8]^=std::uint8_t(1u<<(index%8));
  }
 }else if(action=="envelope"){
  for(std::size_t k=0;k<256;++k){
   const auto index=k<248?k:Decoder::kStreamBits-8+(k-248);
   Bytes changed=clean;changed[index/8]^=std::uint8_t(1u<<(index%8));
   Decoder d(env);d.begin();bool failed=false;
   for(std::size_t i=0;i<Decoder::kStreamBits;++i)if(!d.push_bit(bit(changed,i))){failed=true;break;}
   check(failed && unavailable(d) && d.failure_bit()==index);
   check(d.error()==(k<248?StreamError::prefix_mismatch:StreamError::suffix_mismatch));
  }
 }else if(action=="truncate"){
  std::vector<std::size_t> cuts={0,1,7,8,247,248,249,432,433,434,439,440,40951,40952,40959};
  for(std::size_t i=0;i<212;++i)cuts.push_back(248+i*192+191);
  for(auto cut:cuts){Decoder d(env);d.begin();feed(d,clean,cut);
   check(!d.finish() && d.error()==StreamError::truncated && d.failure_bit()==cut && unavailable(d));
   check(refuses([&]{d.push_bit(true);}) && refuses([&]{d.finish();}));}
 }else if(action=="extra"){
  Decoder d(env);d.begin();feed(d,clean,Decoder::kStreamBits);
  check(!d.push_bit(false) && d.error()==StreamError::extra_bits && d.failure_bit()==40960);
  check(unavailable(d) && d.bits_seen()==40960 && refuses([&]{d.finish();}));
 }else if(action=="reset"){
  for(std::size_t offset=0;offset<192;++offset){
   Decoder d(env);d.begin();feed(d,clean,248+192+offset);d.reset();
   check(d.state()==StreamState::idle && d.bits_seen()==0 && d.records_validated()==0 && unavailable(d));
   check(refuses([&]{d.push_bit(false);}));success(d,clean,expected);
  }
  Decoder d(env);d.begin();check(!d.push_bit(!bit(clean,0)));d.reset();success(d,clean,expected);
 }else if(action=="collision"){
  Bytes changed=clean; // x^12+1 is divisible by the empirical x^8+x^4+1.
  for(std::size_t index:{249u,261u})changed[index/8]^=std::uint8_t(1u<<(index%8));
  Decoder d(env);d.begin();feed(d,changed,Decoder::kStreamBits);check(d.finish());
  const auto got=d.packed_data();check(!std::equal(got.begin(),got.end(),expected.begin()));
  ConfigStartup startup({StartupClock::internal_oscillator,StartupClock::internal_oscillator,StartupTimeout::enabled});
  check(startup.phase()==StartupPhase::unestablished && startup.nstatus_drive()==DrainDrive::unknown);
 }else if(action=="copies"){
  Decoder d(env);success(d,clean,expected);const auto copy=d.packed_data();d.reset();
  Bytes changed=clean;for(std::size_t index:{249u,261u})changed[index/8]^=std::uint8_t(1u<<(index%8));
  d.begin();feed(d,changed,Decoder::kStreamBits);check(d.finish());
  check(d.packed_data()!=copy && std::equal(copy.begin(),copy.end(),expected.begin()));
 }else throw std::runtime_error("unknown test action");
 std::cout<<"passed\n";return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}}
'''


def synthetic():
    rng=random.Random(0x8282)
    data=[rng.getrandbits(177) for _ in range(212)]
    prefix=bytes(rng.randrange(256) for _ in range(31))
    stream=prefix+b''.join(encode_record(x) for x in data)+bytes([0xa6])
    # Separate bit-by-bit packing oracle, not a call to the Python reversal helper.
    packed=bytearray((TOTAL_BITS+7)//8)
    for r,value in enumerate(data):
        for i in range(177):
            target=TOTAL_BITS-1-(r*177+i)
            packed[target//8]|=((value>>i)&1)<<(target%8)
    assert bytes(packed)==serial_to_sof_data(stream)
    return stream,bytes(packed)


class NativeStreamingDecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='epf8282-synthetic-')
        cls.work=Path(cls.tmp.name)
        cls.stream,cls.packed=synthetic()
        (cls.work/'input.bin').write_bytes(cls.stream)
        (cls.work/'expected.bin').write_bytes(cls.packed)
        (cls.work/'checks.cpp').write_text(HARNESS,encoding='utf-8')
        cls.executables=[]
        for n,compiler in enumerate((shutil.which('g++'),shutil.which('clang++'))):
            if not compiler:continue
            built=[]
            for name,source in [('checks',cls.work/'checks.cpp'),
                ('pipeline',ROOT/'tools/experimental/epf8282_stream_decode_probe.cpp')]:
                exe=cls.work/(name+str(n)+('.exe' if os.name=='nt' else ''))
                run=subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                    '-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'runtime'),
                    str(source),'-o',str(exe)],capture_output=True,text=True,timeout=45)
                if run.returncode:raise AssertionError(run.stderr)
                built.append(exe)
            cls.executables.append((compiler,*built))
        if not cls.executables:raise unittest.SkipTest('GCC or Clang required')

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def run_action(self,action):
        for compiler,exe,_ in self.executables:
            with self.subTest(compiler=compiler):
                run=subprocess.run([str(exe),str(self.work/'input.bin'),str(self.work/'expected.bin'),action],
                                   capture_output=True,text=True,timeout=30)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_progress_exact_global_bit_order_and_explicit_finish(self):self.run_action('valid')
    def test_arbitrary_pauses_never_change_decoder_state(self):self.run_action('pauses')
    def test_all_192_bit_mutations_in_first_middle_last_records(self):self.run_action('singlebits')
    def test_all_256_envelope_bit_mutations(self):self.run_action('envelope')
    def test_every_record_tail_and_selected_partial_inputs_truncate(self):self.run_action('truncate')
    def test_extra_bit_invalidates_unsealed_image(self):self.run_action('extra')
    def test_reset_every_record_offset_and_after_failure(self):self.run_action('reset')
    def test_explicit_two_bit_collision_is_not_file_authentication(self):self.run_action('collision')
    def test_snapshot_is_a_value_not_a_reference_to_next_load(self):self.run_action('copies')

    def test_all_three_input_paths_decode_exact_data_without_arming_startup(self):
        reports=[]
        for compiler,_,exe in self.executables:
            with self.subTest(compiler=compiler):
                run=subprocess.run([str(exe),str(self.work/'input.bin'),str(self.work/'expected.bin')],
                                   capture_output=True,text=True,timeout=20)
                self.assertEqual(run.returncode,0,run.stderr)
                reports.append(parse_report(run.stdout))
        self.assertTrue(all(x==reports[0] for x in reports))

    def test_wrong_expected_data_cannot_produce_success_report(self):
        bad=bytearray(self.packed);bad[0]^=1;(self.work/'wrong.bin').write_bytes(bad)
        for _,_,exe in self.executables:
            run=subprocess.run([str(exe),str(self.work/'input.bin'),str(self.work/'wrong.bin')],
                               capture_output=True,text=True,timeout=20)
            self.assertNotEqual(run.returncode,0);self.assertEqual(run.stdout,'')


class StreamReportTests(unittest.TestCase):
    def valid(self):
        return {'schema_version':1,'synthetic_pin_stimulus':True,'opaque_envelope_supplied_from_input':True,
            'silicon_configuration_accepted':False,'startup_armed':False,'sega_serial_connected':False,
            'data_bits':37524,'modes':[{'mode':name,'input_bits':40960,'records_validated':212,
                                      'matches_python_data':True} for name in ('PS','PPS','PPA')]}

    def test_schema_and_nonhardware_boundaries(self):
        original=self.valid();self.assertEqual(parse_report(json.dumps(original)),original)
        for key,value in [('startup_armed',True),('silicon_configuration_accepted',True),
            ('sega_serial_connected',True),('synthetic_pin_stimulus',False),('data_bits',True)]:
            data=copy.deepcopy(original);data[key]=value
            with self.assertRaises(ValueError):parse_report(json.dumps(data))

    def test_duplicate_truncated_extra_and_misordered_reports_rejected(self):
        for text in ['{"a":1,"a":2}', '{}','[]','x'*16385]:
            with self.assertRaises(ValueError):parse_report(text)
        base=self.valid()
        for mode_change in [base['modes'][:-1],base['modes'][::-1]]:
            data=copy.deepcopy(base);data['modes']=mode_change
            with self.assertRaises(ValueError):parse_report(json.dumps(data))
        data=copy.deepcopy(base);data['modes'][0]['records_validated']=211
        with self.assertRaises(ValueError):parse_report(json.dumps(data))

    def test_wrong_original_identity_rejected_before_native_tools(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'wrong.bin';path.write_bytes(bytes(0x200000))
            with self.assertRaisesRegex(ValueError,'identity'):run_probe(path)

    def test_cli_refuses_input_overwrite_including_hardlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'original.bin';path.write_bytes(b'preserve')
            for output in [path,Path(folder)/'hardlink.bin']:
                if output!=path:os.link(path,output)
                run=subprocess.run([os.sys.executable,'-m','arcaderecomp.stream_decode_probe',
                    '--image',str(path),'--output',str(output)],cwd=ROOT,capture_output=True,text=True,timeout=15)
                self.assertNotEqual(run.returncode,0);self.assertEqual(path.read_bytes(),b'preserve')
                self.assertIn('overwrite',run.stderr)

if __name__=='__main__':unittest.main()
