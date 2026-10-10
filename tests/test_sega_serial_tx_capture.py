"""Compiled observation checks; no claim of cabinet hardware validation."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def native(body):
    compilers=[c for c in (shutil.which('g++'),shutil.which('clang++')) if c]
    if not compilers:raise unittest.SkipTest('C++17 compiler needed')
    for compiler in compilers:
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'test.cpp';exe=Path(d)/'test'
            source.write_text('#include "sega3155649_tx_capture.hpp"\nusing namespace arcaderecomp_model2c;\n'+body)
            p=subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(ROOT/'runtime'),
                str(source),'-o',str(exe)],capture_output=True,text=True,timeout=30)
            if p.returncode:raise AssertionError(p.stderr)
            p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
            if p.returncode:raise AssertionError(f'{compiler} exit {p.returncode}: {p.stderr}')


class SerialTxCaptureTests(unittest.TestCase):
    def test_all_commands_and_data_without_latch_write_transmission(self):
        native(r'''int main(){
            SerialTxCapture o;std::uint64_t seq=0;
            for(unsigned cmd=0;cmd<256;++cmd){for(unsigned data=0;data<256;++data){
                if(o.observe(++seq,o.TXD2,data))return 1;
                const auto e=o.observe(++seq,o.TXD1,cmd);
                if(!e||e->command!=cmd||e->data!=data||!e->fresh_data||e->data_sequence!=seq-1)return 2;
                if(cmd==7){const auto wire=o.model2b_reported_07_pair(*e);if(wire[0]!=7||wire[1]!=data)return 3;}
                else {try{o.model2b_reported_07_pair(*e);return 4;}catch(const std::invalid_argument&) {}}
            }}
            return 0;}''')

    def test_snapshot_reuse_and_reset_do_not_invent_initial_value(self):
        native(r'''int main(){SerialTxCapture o;
            auto unknown=o.observe(0,o.TXD1,7);
            if(!unknown||unknown->data||unknown->fresh_data)return 1;
            try{o.model2b_reported_07_pair(*unknown);return 2;}catch(const std::invalid_argument&){}
            o.observe(1,o.TXD2,0xa5);const auto first=*o.observe(2,o.TXD1,7);
            const auto repeated=*o.observe(3,o.TXD1,7);
            if(!first.fresh_data||repeated.fresh_data||repeated.data!=0xa5||repeated.data_sequence!=1)return 3;
            o.observe(4,o.TXD2,0x5a);if(first.data!=0xa5)return 4;
            o.reset_observation();if(o.observe(0,o.TXD1,1)->data)return 5;
            return 0;}''')

    def test_bad_order_or_address_does_not_change_latch(self):
        native(r'''int main(){SerialTxCapture o;o.observe(10,o.TXD2,0x42);
            try{o.observe(10,o.TXD2,0x99);return 1;}catch(const std::invalid_argument&){}
            try{o.observe(9,o.TXD1,7);return 2;}catch(const std::invalid_argument&){}
            try{o.observe(11,0x01c00013,0x99);return 3;}catch(const std::invalid_argument&){}
            const auto e=o.observe(11,o.TXD1,7);if(e->data!=0x42||!e->fresh_data)return 4;
            SerialTxCapture other;if(other.observe(1,other.TXD1,7)->data)return 5;
            return 0;}''')

    def test_data_overwrite_is_recorded_without_fabricating_a_transfer(self):
        native(r'''int main(){SerialTxCapture o;
            o.observe(1,o.TXD2,10);o.observe(2,o.TXD2,20);
            auto e=o.observe(3,o.TXD1,7);
            if(e->data!=20||e->data_sequence!=2)return 1;
            return 0;}''')

if __name__=='__main__':unittest.main()
