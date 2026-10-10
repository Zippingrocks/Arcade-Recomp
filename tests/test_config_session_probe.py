"""Metadata and native-composition tests use only artificial configuration bytes."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from arcaderecomp.config_session_probe import parse_report,run_probe,main
from arcaderecomp.flex8000_sram import encode_record,serial_to_sof_data

ROOT=Path(__file__).resolve().parents[1]

def report():
    return {'schema_version':1,'synthetic_pin_and_completion_events':True,
      'mode_count':3,'cutoffs_per_mode':221,'reset_trials':663,'device_error_trials':663,
      'reloads_match_expected':1326,'stale_handles_rejected':1326,
      'startup_timeouts_invalidate':3,'explicit_startup_intervals':3,
      'profile_completion_signals_acceptance':False,'configured_circuit_executed':False,
      'silicon_acceptance_claimed':False,'sega_connected':False}

class SessionProbeTests(unittest.TestCase):
    def test_exact_metadata_domain_and_false_hardware_claims_are_checked(self):
        expected=report()
        self.assertEqual(parse_report(json.dumps(expected)),expected)
        for field,value in [('reloads_match_expected',1325),('mode_count',True),
            ('synthetic_pin_and_completion_events',False),('silicon_acceptance_claimed',True),
            ('profile_completion_signals_acceptance',True),('sega_connected',True),('extra',0)]:
            changed=copy.deepcopy(expected);changed[field]=value
            with self.assertRaises(ValueError):parse_report(json.dumps(changed))
        for text in ['{}','[]','x'*16385,json.dumps(expected)[:-1]+',"mode_count":3}']:
            with self.assertRaises(ValueError):parse_report(text)

    def test_original_identity_guard_precedes_native_build(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong.bin';p.write_bytes(bytes(0x200000))
            with self.assertRaisesRegex(ValueError,'identity'):
                run_probe(p,('compiler-that-does-not-exist',))

    def test_cli_never_overwrites_input_or_hard_link(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'image.bin';p.write_bytes(b'not a ROM')
            q=Path(d)/'alias.bin';os.link(p,q)
            for output in (p,q):
                with patch.object(sys,'argv',['probe','--image',str(p),'--output',str(output)]):
                    with self.assertRaises(SystemExit) as e:main()
                    self.assertEqual(e.exception.code,2)
            self.assertEqual(p.read_bytes(),b'not a ROM')

    def test_compiled_session_path_with_artificial_data_and_wrong_expected_guard(self):
        cxx=shutil.which('g++') or shutil.which('clang++')
        if not cxx:self.skipTest('C++17 compiler needed')
        # Invented independent values, never copied from HOTD1 or a reference design.
        stream=bytes(range(31))+b''.join(encode_record((i+1)*0x9182736455) for i in range(212))+b'\xff'
        expected=serial_to_sof_data(stream)
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);payload=d/'synthetic.bin';data=d/'expected.bin';exe=d/'probe'
            payload.write_bytes(stream);data.write_bytes(expected)
            build=subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'runtime'),str(ROOT/'tools/experimental/flex8000_session_probe.cpp'),
                '-o',str(exe)],capture_output=True,text=True,timeout=30)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(exe),str(payload),str(data)],capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(parse_report(run.stdout),report())
            broken=bytearray(expected);broken[2]^=1;data.write_bytes(broken)
            run=subprocess.run([str(exe),str(payload),str(data)],capture_output=True,text=True,timeout=30)
            self.assertNotEqual(run.returncode,0)
            self.assertEqual(run.stdout,'')
            self.assertIn('mismatch',run.stderr)

if __name__=='__main__':unittest.main()
