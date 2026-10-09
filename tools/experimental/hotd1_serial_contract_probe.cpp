// Original ArcadeRecomp diagnostic. Runs an AOT-compiled isolated routine
// with EXPLICITLY SYNTHETIC constant RX bytes and ready status. NOT hardware
// emulation, a full game boot, or evidence for real UART timing/replies.
// Only metadata leaves this process: never output the private upload bytes.
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>
#include "model2c_bus.hpp"
#include "hotd1_i960.cpp"

namespace {
std::uint32_t number(const char* s) {
    std::size_t used=0;
    std::string text(s);
    if(text.empty() || text[0]=='-') throw std::invalid_argument("negative/empty argument");
    unsigned long long value=std::stoull(text,&used,0);
    if(used!=text.size() || value>0xffffffffULL) throw std::invalid_argument("invalid uint32 argument");
    return static_cast<std::uint32_t>(value);
}
struct Control { unsigned command; int new_data; };
struct Observation {
    const std::vector<std::uint8_t>& image;
    std::uint32_t begin,end;
    unsigned upload_command;
    unsigned rx1,rx2;
    std::size_t tx1=0,tx2=0,reads1=0,reads2=0,status_reads=0,uploaded=0;
    bool upload_matches=true;
    int pending_data=-1;
    std::vector<Control> controls;

    void transmit(std::uint8_t byte,unsigned channel) {
        if(channel==2u) {
            ++tx2;
            if(pending_data!=-1) throw std::runtime_error("unpaired data-lane write");
            pending_data=byte;
            return;
        }
        if(channel!=1u) throw std::runtime_error("invalid channel");
        ++tx1;
        // Group adjacent TX2 writes with following TX1 commands as an
        // OBSERVATION of host ordering. This is not a chip protocol claim.
        if(byte==upload_command) {
            if(pending_data<0) throw std::runtime_error("upload command without new data byte");
            if(uploaded>=end-begin) throw std::runtime_error("upload exceeds declared range");
            if(static_cast<unsigned>(pending_data)!=image[begin+uploaded]) upload_matches=false;
            ++uploaded;
        } else {
            if(controls.size()>=128) throw std::runtime_error("too many non-upload commands");
            controls.push_back({byte,pending_data});
        }
        pending_data=-1;
    }
};
}

int main(int argc,char** argv) {
    if(argc!=7) {
        std::cerr<<"Usage: serial_contract_probe PRIVATE_IMAGE ENTRY UPLOAD_BEGIN UPLOAD_END UPLOAD_COMMAND RX1\n";
        return 2;
    }
    std::cerr<<"SYNTHETIC RX/READY SWEEP: isolated original routine, NOT ARCADE HARDWARE VALIDATION\n";
    try {
        std::ifstream f(argv[1],std::ios::binary|std::ios::ate);
        if(!f || f.tellg()!=std::streampos(0x200000)) throw std::runtime_error("expected 2-MiB mapped i960 image");
        f.seekg(0);
        std::vector<std::uint8_t> image((std::istreambuf_iterator<char>(f)),{});
        if(!f.eof() && f.fail()) throw std::runtime_error("image read failed");
        const auto entry=number(argv[2]), begin=number(argv[3]), end=number(argv[4]);
        const auto command=number(argv[5]),rx1=number(argv[6]);
        if(entry%4 || entry>=image.size() || begin>=end || end>image.size() || command>255 || rx1>255)
            throw std::invalid_argument("invalid entry/range/command/input");
        for(unsigned rx2=0;rx2<256;++rx2) {
            arcaderecomp_model2c::StrictBus board(image);
            board.enable_partial_serial_io();
            Observation obs{image,begin,end,command,rx1,rx2,0,0,0,0,0,0,true,-1,{}};
            board.serial_device().set_serial_tx_observer([&](std::uint8_t b,unsigned ch){obs.transmit(b,ch);});
            board.serial_device().set_serial_status_source([&]()->std::uint8_t{++obs.status_reads;return 0x0c;});
            board.serial_device().set_serial_rx([&](std::uint8_t,unsigned ch)->std::uint8_t{
                if(ch==1){++obs.reads1;return static_cast<std::uint8_t>(rx1);}
                if(ch==2){++obs.reads2;return static_cast<std::uint8_t>(rx2);}
                throw std::runtime_error("invalid RX channel");
            });
            arcaderecomp_generated::CPU cpu{};
            if(!arcaderecomp_generated::frame_init(cpu,0x00510400u,entry)) throw std::runtime_error("invalid frame");
            const auto bus=board.callbacks();
            unsigned steps=0;
            constexpr unsigned max_steps=250000;
            while(steps<max_steps && arcaderecomp_generated::step(cpu,bus)) ++steps;
            // A root RET has no caller in this isolated harness. The stop is
            // expected only if the entire sampled procedure reached that RET.
            bool returned=steps<max_steps && cpu.stop_code==arcaderecomp_generated::StopCode::return_without_caller;
            if(!returned || !obs.upload_matches || obs.uploaded!=end-begin || obs.pending_data!=-1)
                throw std::runtime_error("routine/transfer contract failed; no success report");
            std::cout<<"{\"synthetic_inputs\":true,\"rx1\":"<<rx1<<",\"rx2\":"<<rx2
                     <<",\"steps\":"<<steps<<",\"return_ip\":"<<cpu.ip
                     <<",\"tx1_count\":"<<obs.tx1<<",\"tx2_count\":"<<obs.tx2
                     <<",\"rx1_count\":"<<obs.reads1<<",\"rx2_count\":"<<obs.reads2
                     <<",\"status_reads\":"<<obs.status_reads<<",\"upload_bytes\":"<<obs.uploaded
                     <<",\"upload_matches_rom\":true,\"controls\":[";
            for(std::size_t n=0;n<obs.controls.size();++n){
                if(n)std::cout<<',';
                std::cout<<"{\"command\":"<<obs.controls[n].command<<",\"new_data\":";
                if(obs.controls[n].new_data<0)std::cout<<"null";else std::cout<<obs.controls[n].new_data;
                std::cout<<'}';
            }
            std::cout<<"]}\n";
        }
    } catch(const std::exception& e) {
        std::cerr<<"Contract probe failed: "<<e.what()<<'\n';return 2;
    }
    return 0;
}
