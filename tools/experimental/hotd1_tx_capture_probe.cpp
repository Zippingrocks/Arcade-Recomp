// Original ArcadeRecomp isolated host trace. Explicit SYNTHETIC RX/status.
// Outputs metadata to stdout and predicted 07/data pairs to a PRIVATE file.
// These bytes are not measured on Sega hardware. No other commands are encoded.
#include "model2c_bus.hpp"
#include "sega3155649_tx_capture.hpp"
#include "hotd1_i960.cpp"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>

static std::uint32_t number(const char* p){
    const std::string s(p);std::size_t n=0;
    if(s.empty()||s[0]=='-')throw std::invalid_argument("bad uint32");
    const auto v=std::stoull(s,&n,0);
    if(n!=s.size()||v>0xffffffffULL)throw std::invalid_argument("bad uint32");
    return static_cast<std::uint32_t>(v);
}
int main(int argc,char** argv){
    if(argc!=8){std::cerr<<"PRIVATE_IMAGE NEW_PRIVATE_WIRE ENTRY BEGIN END RX1 RX2\n";return 2;}
    std::cerr<<"SYNTHETIC RX/status; conditional Model 2B TX framing, NOT hardware capture\n";
    try{
        if(std::filesystem::exists(argv[2])||std::filesystem::is_symlink(argv[2]))
            throw std::invalid_argument("refusing to overwrite a wire-output path");
        std::ifstream in(argv[1],std::ios::binary|std::ios::ate);
        if(!in||in.tellg()!=std::streampos(0x200000))throw std::invalid_argument("expected 2 MiB");
        in.seekg(0);std::vector<std::uint8_t> image((std::istreambuf_iterator<char>(in)),{});
        const auto entry=number(argv[3]),begin=number(argv[4]),end=number(argv[5]);
        const auto rx1=number(argv[6]),rx2=number(argv[7]);
        if(entry%4||entry>=image.size()||begin>=end||end>image.size()||rx1>255||rx2>255)
            throw std::invalid_argument("invalid experiment profile");
        using namespace arcaderecomp_model2c;
        using namespace arcaderecomp_generated;
        StrictBus board(image);board.enable_partial_serial_io();SerialTxCapture capture;
        CPU cpu{};if(!frame_init(cpu,0x00510400u,entry))throw std::runtime_error("bad frame");
        std::uint64_t writes=0,commands=0,latches=0,reused=0,unknown=0,upload=0;
        std::vector<std::uint8_t> wire;wire.reserve(2*(end-begin));
        board.serial_device().set_serial_tx_observer([&](std::uint8_t value,unsigned channel){
            if(channel!=1&&channel!=2)throw std::runtime_error("bad channel");
            if(channel==2)++latches;
            auto e=capture.observe(++writes,channel==1?capture.TXD1:capture.TXD2,value);
            if(!e)return;
            ++commands;if(!e->fresh_data)++reused;if(!e->data)++unknown;
            if(e->command!=7)return; // No wire claim about other commands.
            if(!e->fresh_data||!e->data||upload>=end-begin||*e->data!=image[begin+upload])
                throw std::runtime_error("upload does not match observed data-latch writes");
            const auto pair=capture.model2b_reported_07_pair(*e);
            wire.insert(wire.end(),pair.begin(),pair.end());++upload;
        });
        board.serial_device().set_serial_status_source([]()->std::uint8_t{return 12;});
        board.serial_device().set_serial_rx([&](std::uint8_t,unsigned ch)->std::uint8_t{
            return static_cast<std::uint8_t>(ch==1?rx1:rx2);
        });
        const auto bus=board.callbacks();unsigned steps=0;
        while(steps<250000&&step(cpu,bus))++steps;
        if(steps==250000||cpu.stop_code!=StopCode::return_without_caller||upload!=end-begin)
            throw std::runtime_error("isolated routine did not complete expected upload");
        std::ofstream out(argv[2],std::ios::binary);out.write(reinterpret_cast<const char*>(wire.data()),wire.size());
        out.close();if(!out)throw std::runtime_error("private output write failed");
        std::cout<<"{\"synthetic_inputs\":true,\"hardware_capture\":false,\"steps\":"<<steps
            <<",\"commands\":"<<commands<<",\"data_latch_writes\":"<<latches
            <<",\"commands_without_fresh_data\":"<<reused<<",\"commands_with_unknown_data\":"<<unknown
            <<",\"upload_bytes\":"<<upload<<",\"predicted_upload_wire_bytes\":"<<wire.size()<<"}\n";
    }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 2;}
    return 0;
}
