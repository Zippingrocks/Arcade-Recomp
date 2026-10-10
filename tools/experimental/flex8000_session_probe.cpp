// Original diagnostic: single owned configuration session, original/private
// bytes with EXPLICITLY SYNTHETIC loading/reset/error/completion observations.
// No Sega transport or silicon configuration acceptance is inferred here.
#include "flex8000_config_session.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
using namespace arcaderecomp_flex8000;
namespace {
using Decoder=EPF8282StreamDecoder;
using Bytes=std::vector<std::uint8_t>;
void must(bool b,const char* message){if(!b)throw std::runtime_error(message);}
Bytes read_exact(const char* name,std::size_t size){
    std::ifstream file(name,std::ios::binary|std::ios::ate);
    if(!file || file.tellg()!=static_cast<std::streamoff>(size))throw std::runtime_error("wrong private input size");
    file.seekg(0);Bytes bytes((std::istreambuf_iterator<char>(file)),{});
    if(file.bad() || bytes.size()!=size)throw std::runtime_error("private read failed");
    return bytes;
}
void feed(ConfigSession& s,ConfigSession::Attempt ticket,LoadingMode mode,const Bytes& bytes,std::size_t count){
    std::size_t sent=0;
    if(count==0)return;
    ParallelPins pins{};pins.cs=true;pins.ncs=false;
    for(const auto byte:bytes){
        if(mode==LoadingMode::passive_parallel_async){
            pins.data=byte;pins.nws=false;s.drive_parallel(ticket,pins);
            pins.nws=true;s.drive_parallel(ticket,pins);
        }
        for(unsigned bit=0;bit<8;++bit){
            if(mode==LoadingMode::passive_parallel_async)must(s.internal_falling_edge(ticket),"stream check failed");
            else {
                must(s.drive_dclk(ticket,true,mode==LoadingMode::passive_serial?std::uint8_t(byte>>bit):byte),"stream check failed");
                must(s.drive_dclk(ticket,false,byte),"stream check failed");
            }
            if(++sent==count)return;
        }
    }
    throw std::runtime_error("feed cutoff outside stream");
}
bool unavailable(ConfigSession& s,ConfigSession::Attempt t){
    try{(void)s.decoded_data(t);return false;}catch(const std::logic_error&){return true;}
}
void ready(ConfigSession& s,ConfigSession::Attempt t,LoadingMode mode,const Bytes& bytes,const Bytes& expected){
    feed(s,t,mode,bytes,Decoder::kStreamBits);
    must(unavailable(s,t),"last bit exposed unfinished profile");
    must(s.finish_profile(t),"profile finish failed");
    const auto data=s.decoded_data(t);
    must(std::equal(data.begin(),data.end(),expected.begin(),expected.end()),"decoded data mismatch");
    must(s.phase()==SessionPhase::profile_ready && s.conf_done_drive()==DrainDrive::unknown,
         "profile parsing manufactured CONF_DONE");
    must(!s.initialization_interval_elapsed(),"profile parsing manufactured initialization");
}
StartupOptions options(LoadingMode mode){
    const auto c=mode==LoadingMode::passive_parallel_async?StartupClock::internal_oscillator:StartupClock::dclk;
    return {c,c,StartupTimeout::enabled};
}
}
int main(int argc,char** argv){
    if(argc!=3){std::cerr<<"Usage: session_probe PRIVATE_STREAM PRIVATE_EXPECTED_DATA\n";return 2;}
    std::cerr<<"SYNTHETIC completion, pin, reset and error observations; NOT silicon acceptance or Sega execution\n";
    try{
        const auto bytes=read_exact(argv[1],Decoder::kStreamBits/8);
        const auto expected=read_exact(argv[2],Decoder::kPackedBytes);
        StreamEnvelope e{};std::copy_n(bytes.begin(),31,e.prefix.begin());e.suffix=bytes.back();
        std::vector<std::size_t> cuts{0,1,7,8,247,248,249,40959,40960};
        for(std::size_t r=1;r<=212;++r)cuts.push_back(248+r*192);
        std::sort(cuts.begin(),cuts.end());cuts.erase(std::unique(cuts.begin(),cuts.end()),cuts.end());
        std::size_t resets=0,errors=0,reloads=0,observed_starts=0,timeouts=0,stale=0;
        for(unsigned m=0;m<3;++m){
            const auto mode=static_cast<LoadingMode>(m);
            for(const auto cut:cuts)for(unsigned fault=0;fault<2;++fault){
                ConfigSession s(mode,e);
                auto t=s.begin_observed_loading(AutoRestart::disabled,PinLevel::high,PinLevel::high);
                feed(s,t,mode,bytes,cut);const auto old=t;
                if(fault){s.observe_device_error(t,ConfigErrorCause::frame_error);++errors;
                    must(s.nstatus_drive()==DrainDrive::sink_low,"explicit hardware error not latched");
                }else{ s.assert_nconfig_low();++resets; }
                must(!s.attempt_is_current(old)&&unavailable(s,old)&&!s.pending_bits()&&!s.bits_seen(),"discard leaked across stages");
                s.assert_nconfig_low();s.release_nconfig_after_qualified_reset();
                must(s.nstatus_drive()==DrainDrive::unknown,"reset release invented preparation");
                t=s.begin_observed_loading(AutoRestart::disabled,PinLevel::high,PinLevel::high);
                must(!s.attempt_is_current(old),"stale handle survived new load");++stale;
                ready(s,t,mode,bytes,expected);++reloads;
            }
            // Separate explicit fixture observations exercise the next boundary.
            ConfigSession s(mode,e);auto t=s.begin_observed_loading(AutoRestart::disabled,PinLevel::high,PinLevel::high);
            ready(s,t,mode,bytes,expected);const auto opts=options(mode);
            s.observe_conf_done_release(t,opts,PinLevel::low);
            for(unsigned i=0;i<9;++i)s.qualified_startup_cycle(t,opts.timeout_clock);
            must(s.attempt_is_current(t),"timeout fired early");
            s.qualified_startup_cycle(t,opts.timeout_clock);
            must(s.phase()==SessionPhase::startup_error&&!s.attempt_is_current(t)&&unavailable(s,t),"timeout exposed old image");++timeouts;
            s.assert_nconfig_low();s.release_nconfig_after_qualified_reset();
            t=s.begin_observed_loading(AutoRestart::disabled,PinLevel::high,PinLevel::high);ready(s,t,mode,bytes,expected);
            s.observe_conf_done_release(t,opts,PinLevel::low);
            for(unsigned i=0;i<9;++i)s.qualified_startup_cycle(t,opts.timeout_clock);
            s.observe_conf_done(t,PinLevel::high);
            for(unsigned i=0;i<9;++i)s.qualified_startup_cycle(t,opts.initialization_clock);
            must(!s.initialization_interval_elapsed(),"initialization finished early");
            s.qualified_startup_cycle(t,opts.initialization_clock);
            must(s.initialization_interval_elapsed(),"qualified interval did not finish");++observed_starts;
            // The fixture has not recovered or run the configured user circuit.
        }
        std::cout<<"{\"schema_version\":1,\"synthetic_pin_and_completion_events\":true,\"mode_count\":3,"
            <<"\"cutoffs_per_mode\":"<<cuts.size()<<",\"reset_trials\":"<<resets<<",\"device_error_trials\":"<<errors
            <<",\"reloads_match_expected\":"<<reloads<<",\"stale_handles_rejected\":"<<stale
            <<",\"startup_timeouts_invalidate\":"<<timeouts<<",\"explicit_startup_intervals\":"<<observed_starts
            <<",\"profile_completion_signals_acceptance\":false,\"silicon_acceptance_claimed\":false,"
            <<"\"configured_circuit_executed\":false,\"sega_connected\":false}\n";
    }catch(const std::exception& e){std::cerr<<"Session probe failed: "<<e.what()<<'\n';return 2;}
    return 0;
}
