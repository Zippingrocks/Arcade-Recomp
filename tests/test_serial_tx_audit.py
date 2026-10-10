"""Synthetic wrapper and native integration regressions."""
import json
import struct
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arcaderecomp.serial_tx_audit import parse_native, run_experiment, synthetic_samples, main
from arcaderecomp.serial_wire import decode_8n1


class SerialTxAuditTests(unittest.TestCase):
    def test_metadata_requires_synthetic_declaration_and_full_counts(self):
        row={'synthetic_inputs':True,'hardware_capture':False,'steps':100000,'commands':5132,
             'data_latch_writes':5125,'commands_without_fresh_data':7,'commands_with_unknown_data':0,
             'upload_bytes':5120,'predicted_upload_wire_bytes':10240}
        self.assertEqual(parse_native(json.dumps(row)),row)
        for key,value in (('synthetic_inputs',False),('hardware_capture',True),('steps',True),
                          ('upload_bytes',5119),('commands_without_fresh_data',10000)):
            bad={**row,key:value}
            with self.assertRaises(ValueError):parse_native(json.dumps(bad))
        with self.assertRaises(ValueError):parse_native('{"a":1,"a":2}')
        with self.assertRaises(ValueError):parse_native(' '*4097)

    def test_profile_guard_precedes_compilation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong';p.write_bytes(b'\0'*0x200000)
            with patch('subprocess.run',side_effect=AssertionError('must not compile')):
                with self.assertRaisesRegex(ValueError,'hash'):run_experiment(p)

    def test_wrapper_refuses_input_output_alias_before_experiment(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'input';p.write_bytes(b'protected')
            alias=Path(d)/'alias';alias.hardlink_to(p)
            with patch('sys.argv',['audit','--image',str(p),'--output',str(alias)]):
                with self.assertRaises(SystemExit) as e:main()
                self.assertEqual(e.exception.code,2)
            self.assertEqual(p.read_bytes(),b'protected')

    def test_explicit_synthetic_waveform_roundtrip_all_values(self):
        wire=bytes(range(256))*2
        self.assertEqual(bytes(f.value for f in decode_8n1(synthetic_samples(wire),12_000_000,2_000_000,4)),wire)

    def test_native_probe_on_invented_program_and_no_overwrite(self):
        from arcaderecomp.i960_cpp import emit_cpp
        root=Path(__file__).resolve().parents[1]
        compilers=[x for x in (shutil.which('g++'),shutil.which('clang++')) if x]
        if not compilers:self.skipTest('C++17 compiler required')
        image=bytearray(0x200000);image[0x1000:0x1002]=bytes((7,255));words=[]
        def reg(op,a,b,d,literal=False):
            return (op>>4)<<24|(op&15)<<7|a|b<<14|d<<19|int(literal)<<11
        def mem(op,r,base=16,offset=0):return op<<24|r<<19|base<<14|0x2000|offset
        def lda(value,dst):words.extend([0x8c000000|dst<<19|0x3000,value])
        lda(0x01c00000,16);lda(0x1000,3);words.append(reg(0x5cc,2,0,5,True))
        loop=0x100+len(words)*4
        words.extend([mem(0x80,4,3),mem(0x82,4,offset=0x14),reg(0x5cc,7,0,4,True),
                      mem(0x82,4,offset=0x12),reg(0x590,1,3,3,True),reg(0x5a7,1,5,5,True)])
        branch=0x100+len(words)*4;words.append(0x15000000|((loop-branch)&0xfffffc))
        words.extend([reg(0x5cc,1,0,4,True),mem(0x82,4,offset=0x12),0x0a000000])
        struct.pack_into('<'+'I'*len(words),image,0x100,*words)
        code,report=emit_cpp(bytes(image),0x100,256);self.assertFalse(report.unsupported)
        for cxx in compilers:
            with tempfile.TemporaryDirectory() as d:
                w=Path(d);(w/'hotd1_i960.cpp').write_text(code);img=w/'invented.bin';img.write_bytes(image)
                exe=w/'probe';out=w/'wire'
                built=subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                    '-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(root/'runtime'),
                    '-I',str(w),str(root/'tools/experimental/hotd1_tx_capture_probe.cpp'),'-o',str(exe)],
                    capture_output=True,text=True,timeout=30)
                self.assertEqual(built.returncode,0,built.stderr)
                cmd=[str(exe),str(img),str(out),'0x100','0x1000','0x1002','0','0']
                run=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
                self.assertEqual(run.returncode,0,run.stderr);r=json.loads(run.stdout)
                self.assertEqual((r['commands'],r['data_latch_writes'],r['commands_without_fresh_data']),(3,2,1))
                self.assertEqual(out.read_bytes(),bytes((7,7,7,255)))
                self.assertIn('SYNTHETIC',run.stderr)
                run=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
                self.assertNotEqual(run.returncode,0);self.assertEqual(run.stdout,'')
                out.unlink();cmd[5]='0x1003'
                run=subprocess.run(cmd,capture_output=True,text=True,timeout=10)
                self.assertNotEqual(run.returncode,0);self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
