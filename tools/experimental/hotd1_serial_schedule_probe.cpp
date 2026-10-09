// Original-ROM host-contract research with EXPLICITLY SYNTHETIC input.
// Not a gun-board implementation; never installed in the normal runtime.
// Varies RX bytes per transaction and independent receive-ready delays.
#include <array>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
#include "model2c_bus.hpp"
#include "hotd1_i960.cpp"

namespace {
constexpr std::uint32_t kBegin=0xa3a00, kEnd=0xa4e00, kEntry=0xa3750;
constexpr unsigned kTransactions=5132;
struct Control { unsigned command; int data; };
std::uint8_t sample(unsigned seed, unsigned transaction, unsigned channel) {
    // Reproducible arithmetic fixture, NOT an emulated hardware response.
    std::uint32_t x = 0x9e3779b9u * (transaction + 1u);
    x ^= (seed + 1u) * 0x85ebca6bu; x ^= channel * 0xc2b2ae35u;
    x ^= x >> 16u; x *= 0x7feb352du; x ^= x >> 15u;
    return static_cast<std::uint8_t>(x ^ (x >> 8u));
}
struct Probe {
    const std::vector<std::uint8_t>& image;
    unsigned seed, delay1, delay2, noise;
    unsigned transactions=0, data_writes=0, uploaded=0;
    unsigned polls=0, polls_this=0, reads1=0, reads2=0;
    bool consumed1=true, consumed2=true, upload_matches=true;
    int pending=-1;
    std::vector<Control> controls;
    void tx(std::uint8_t byte, unsigned channel) {
        if (channel==2) {
            if (pending!=-1) throw std::runtime_error("unpaired data write");
            pending=byte; ++data_writes; return;
        }
        if (channel!=1 || !consumed1 || !consumed2)
            throw std::runtime_error("command before receiving both prior bytes");
        if (byte==7) {
            if (pending<0 || uploaded>=kEnd-kBegin)
                throw std::runtime_error("invalid upload shape");
            upload_matches &= static_cast<unsigned>(pending)==image[kBegin+uploaded];
            ++uploaded;
        } else {
            if (controls.size()==32) throw std::runtime_error("too many controls");
            controls.push_back({byte,pending});
        }
        pending=-1; ++transactions; polls_this=0;
        consumed1=false;consumed2=false;
    }
    std::uint8_t status() {
        if (!transactions) throw std::runtime_error("status before first command");
        ++polls; ++polls_this;
        // Low TX-status and high error bits are test noise, not real observations.
        unsigned result = (sample(seed, polls, 3) & 0xf3u) * noise;
        if (polls_this>delay1) result|=4;
        if (polls_this>delay2) result|=8;
        return static_cast<std::uint8_t>(result);
    }
    std::uint8_t rx(unsigned channel) {
        if (!transactions || polls_this<=delay1 || polls_this<=delay2)
            throw std::runtime_error("receive occurred before both modeled ready bits");
        if (channel==1) {
            if (consumed1) throw std::runtime_error("duplicate RX1");
            consumed1=true; ++reads1;
        } else if (channel==2) {
            if (!consumed1 || consumed2) throw std::runtime_error("RX order changed");
            consumed2=true; ++reads2;
        } else throw std::runtime_error("unknown channel");
        return sample(seed,transactions-1,channel);
    }
    bool complete() const {
        constexpr unsigned commands[12]={1,8,0x81,0x88,0x81,1,0x81,1,0x82,0x82,8,0x88};
        if (transactions!=kTransactions || reads1!=kTransactions || reads2!=kTransactions ||
            data_writes!=5125 || uploaded!=5120 || !upload_matches ||
            pending!=-1 || !consumed1 || !consumed2 || controls.size()!=12) return false;
        for(unsigned n=0;n<12;++n) if(controls[n].command!=commands[n]) return false;
        const int expected[12]={255,125,-1,-1,-1, sample(seed,4,2)&0xfe,
            -1, sample(seed,6,2)|1,-1,-1,126,-1};
        for(unsigned n=0;n<12;++n) if(controls[n].data!=expected[n]) return false;
        return polls==kTransactions*(1+ (delay1>delay2?delay1:delay2));
    }
};
}
int main(int argc,char** argv) {
    if(argc!=2) {std::cerr<<"Usage: serial_schedule_probe PRIVATE/maincpu.bin\n";return 2;}
    std::cerr<<"EXPLICITLY SYNTHETIC variable RX and ready delays; NOT physical hardware validation\n";
    try {
        std::ifstream f(argv[1],std::ios::binary|std::ios::ate);
        if(!f || f.tellg()!=std::streampos(0x200000)) throw std::runtime_error("expected 2 MiB ROM");
        f.seekg(0);const std::vector<std::uint8_t> image((std::istreambuf_iterator<char>(f)),{});
        constexpr unsigned delays[6][2]={{0,0},{1,0},{0,2},{4,7},{7,4},{9,9}};
        for(unsigned seed=0;seed<16;++seed) for(const auto& delay:delays) for(unsigned noise=0;noise<2;++noise) {
            arcaderecomp_model2c::StrictBus board(image);board.enable_partial_serial_io();
            Probe p{image,seed,delay[0],delay[1],noise,0,0,0,0,0,0,0,true,true,true,-1,{}};
            auto& serial=board.serial_device();
            serial.set_serial_tx_observer([&](std::uint8_t b,unsigned c){p.tx(b,c);});
            serial.set_serial_rx([&](std::uint8_t,unsigned c){return p.rx(c);});
            serial.set_serial_status_source([&](){return p.status();});
            arcaderecomp_generated::CPU cpu{};
            if(!arcaderecomp_generated::frame_init(cpu,0x00510400,kEntry)) throw std::runtime_error("frame failed");
            auto bus=board.callbacks();unsigned steps=0;
            constexpr unsigned limit=600000;
            while(steps<limit && arcaderecomp_generated::step(cpu,bus)) ++steps;
            if(steps==limit || cpu.ip!=0xa38b8 ||
                cpu.stop_code!=arcaderecomp_generated::StopCode::return_without_caller || !p.complete())
                throw std::runtime_error("variable-input host contract failed");
            std::cout<<"{\"kind\":\"upload\",\"seed\":"<<seed<<",\"delay1\":"<<delay[0]<<",\"delay2\":"<<delay[1]
                <<",\"noise\":"<<noise<<",\"steps\":"<<steps<<",\"polls\":"<<p.polls
                <<",\"transactions\":"<<p.transactions<<",\"upload_bytes\":"<<p.uploaded
                <<",\"upload_matches\":true,\"synthetic_inputs\":true,\"feedback_matches\":true}\n";
        }
        // Exhaust the byte domain at the original wait subroutine, not an
        // independent recreation. Missing-ready cases are bounded observations.
        for(unsigned status=0;status<256;++status) {
            arcaderecomp_model2c::StrictBus board(image);board.enable_partial_serial_io();
            unsigned reads=0;
            board.serial_device().set_serial_status_source([&](){++reads;return static_cast<std::uint8_t>(status);});
            arcaderecomp_generated::CPU cpu{};
            if(!arcaderecomp_generated::frame_init(cpu,0x00510400,0xa3720)) throw std::runtime_error("wait frame failed");
            auto bus=board.callbacks();unsigned steps=0;
            constexpr unsigned limit=128;
            while(steps<limit && arcaderecomp_generated::step(cpu,bus)) ++steps;
            bool returned=cpu.stop_code==arcaderecomp_generated::StopCode::return_without_caller;
            bool expected=(status&12u)==12u;
            if(returned!=expected || (returned && cpu.ip!=0xa3740) || (!returned && steps!=limit) || !reads)
                throw std::runtime_error("status-domain wait contract failed");
            std::cout<<"{\"kind\":\"wait\",\"status\":"<<status
                <<",\"steps\":"<<steps<<",\"polls\":"<<reads
                <<",\"returned\":"<<(returned?"true":"false")
                <<",\"step_bound\":"<<limit<<",\"synthetic_inputs\":true}\n";
        }
    } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 2;}
    return 0;
}
