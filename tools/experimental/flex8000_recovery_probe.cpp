// Original diagnostic: synthetic device-error events during a caller-supplied
// stream, followed by explicitly qualified reset/reload. NOT Sega hardware I/O.
// No payload or LUT contents are output. Error events are NOT inferred from CRC.
#include "flex8000_config_recovery.hpp"
#include "flex8000_config_ingress.hpp"
#include "epf8282_stream_decoder.hpp"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>
using namespace arcaderecomp_flex8000;
namespace {
std::vector<std::uint8_t> read_exact(const char* file,std::size_t size) {
    std::ifstream f(file,std::ios::binary|std::ios::ate);
    if(!f||f.tellg()!=static_cast<std::streamoff>(size))throw std::runtime_error("wrong private input size");
    f.seekg(0);std::vector<std::uint8_t> b((std::istreambuf_iterator<char>(f)),{});
    if(f.bad()||b.size()!=size)throw std::runtime_error("private input read failed");
    return b;
}
void must(bool value,const char* message){if(!value)throw std::runtime_error(message);}
}
int main(int argc,char** argv) {
    if(argc!=3){std::cerr<<"Usage: recovery_probe PRIVATE_STREAM PRIVATE_EXPECTED_DATA\n";return 2;}
    try {
        const auto bytes=read_exact(argv[1],EPF8282StreamDecoder::kStreamBits/8);
        const auto expected=read_exact(argv[2],EPF8282StreamDecoder::kPackedBytes);
        StreamEnvelope e{};std::copy_n(bytes.begin(),e.prefix.size(),e.prefix.begin());e.suffix=bytes.back();
        // Every record tail, plus representative preamble and sub-byte positions.
        std::vector<std::size_t> cutoffs{1,7,8,247,248,249,40959,40960};
        for(std::size_t record=1;record<=212;++record)cutoffs.push_back(248+192*record);
        std::sort(cutoffs.begin(),cutoffs.end());cutoffs.erase(std::unique(cutoffs.begin(),cutoffs.end()),cutoffs.end());
        std::size_t trials=0,invalidated=0,reloaded=0;
        for(unsigned mode=0;mode<3;++mode){for(const auto cutoff:cutoffs){
            const auto inputmode=static_cast<LoadingMode>(mode);
            const auto scheme=mode==0?ConfigScheme::passive_serial:
                              mode==1?ConfigScheme::passive_parallel_sync:ConfigScheme::passive_parallel_async;
            ConfigRecovery recovery;
            auto attempt=recovery.begin_observed_loading({scheme,AutoRestart::disabled},PinLevel::high,PinLevel::high);
            ConfigIngress input(inputmode);input.begin_loading();
            EPF8282StreamDecoder decoder(e);decoder.begin();
            ConfigStartup startup({StartupClock::dclk,StartupClock::dclk,StartupTimeout::enabled});
            auto feed=[&](std::size_t count){
                ParallelPins pins{};pins.cs=true;pins.ncs=false;
                std::size_t sent=0;
                for(const auto byte:bytes){
                    if(mode==2){pins.data=byte;pins.nws=false;input.drive_parallel(pins);pins.nws=true;input.drive_parallel(pins);}
                    for(unsigned bit=0;bit<8;++bit){
                        recovery.require_attempt(attempt);
                        std::optional<bool> sample;
                        if(mode<2){
                            sample=input.drive_dclk(true,mode==0?static_cast<std::uint8_t>(byte>>bit):byte);
                            auto falling=input.drive_dclk(false,byte);
                            if(falling)sample=falling;
                        }else sample=input.internal_falling_edge();
                        must(sample.has_value(),"missing decoder sample");
                        must(decoder.push_bit(*sample),"profile failed before explicit error event");
                        if(++sent==count)return;
                    }
                }
            };
            feed(cutoff);
            const auto old=attempt;
            // Deliberately invented error timing, NOT a chip capture/check result.
            recovery.observe_device_error(ConfigErrorCause::frame_error);
            must(!recovery.attempt_is_current(old),"old attempt survived error");++invalidated;
            input.abort_loading();decoder.reset();
            must(!input.loading()&&!input.pending_bits()&&!decoder.bits_seen(),"stale input survived discard");
            for(unsigned c=0;c<20;++c)recovery.qualified_cycle(StartupClock::internal_oscillator);
            must(recovery.phase()==RecoveryPhase::error_latched,"passive mode restarted itself");
            recovery.assert_nconfig_low();recovery.release_nconfig_after_qualified_reset();
            must(recovery.nstatus_drive()==DrainDrive::unknown,"release invented completed reset preparation");
            // An explicit fresh preparation observation, not timed hardware proof.
            attempt=recovery.begin_observed_loading({scheme,AutoRestart::disabled},PinLevel::high,PinLevel::high);
            input.begin_loading();decoder.begin();feed(EPF8282StreamDecoder::kStreamBits);
            must(!recovery.attempt_is_current(old)&&recovery.attempt_is_current(attempt),"stale generation reused");
            must(decoder.finish(),"fresh profile did not finish");const auto data=decoder.packed_data();
            must(std::equal(data.begin(),data.end(),expected.begin(),expected.end()),"reloaded data mismatch");
            must(startup.phase()==StartupPhase::unestablished,"recovery or parsing armed startup");
            ++trials;++reloaded;
        }}
        std::cout<<"{\"schema_version\":1,\"synthetic_pin_and_error_events\":true,"
          "\"mode_count\":3,\"cutoffs_per_mode\":"<<cutoffs.size()<<",\"trial_count\":"<<trials
          <<",\"old_attempts_invalidated\":"<<invalidated<<",\"reloads_match_expected\":"<<reloaded
          <<",\"startup_armed\":false,\"silicon_acceptance_claimed\":false,\"sega_connected\":false}\n";
    }catch(const std::exception& e){std::cerr<<"Recovery probe failed: "<<e.what()<<'\n';return 2;}
    return 0;
}
