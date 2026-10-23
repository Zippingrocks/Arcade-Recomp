// SCSP completed MIDI-input byte events, not a serial clock or board transport.
// Sega ST-077-R2-052594 sections 4.2.4 and 4.2.12.
#pragma once
#include <array>
#include <cstdint>

namespace arcaderecomp::scsp {

class MidiInput final {
    std::array<std::uint8_t,4> bytes_{};
    unsigned head_=0, count_=0;
    bool occupancy_known_=false;
public:
    // Explicit caller-supplied premise; construction is NOT a physical reset.
    void establish_empty_research(){head_=0;count_=0;occupancy_known_=true;}
    bool occupancy(unsigned& count)const{
        if(!occupancy_known_)return false;
        count=count_;return true;
    }
    // False means the event was NOT applied. Stop before an unknown/full FIFO;
    // overflow retention/clear semantics are outside this bounded model.
    bool receive(std::uint8_t value){
        if(!occupancy_known_||count_==4u)return false;
        bytes_[(head_+count_)&3u]=value;++count_;return true;
    }
    bool read(std::uint8_t& value){
        if(!occupancy_known_||!count_)return false;
        value=bytes_[head_];head_=(head_+1u)&3u;--count_;return true;
    }
};

} // namespace arcaderecomp::scsp
