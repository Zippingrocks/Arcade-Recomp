"""Independent synthetic programs exercise the research harness, not ROM data."""
import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from arcaderecomp.i960_cpp import emit_cpp
from arcaderecomp.input_contract import EXPECTED_COUNTS, main, run_experiment, summarize

ROOT = Path(__file__).resolve().parents[1]


def valid_report():
    return {**EXPECTED_COUNTS, 'synthetic_inputs': True,
            'all_contracts_passed': True, 'step_min': 276, 'step_max': 1032}


def reg(op, a, b=0, d=0, lit=False):
    return (op>>4)<<24 | (op&15)<<7 | a | b<<14 | d<<19 | int(lit)<<11


class Assembly:
    def __init__(self):
        self.image = bytearray(b'\xff' * 0xb0000)
        self.pc = 0
    def at(self, address): self.pc = address
    def word(self, value):
        struct.pack_into('<I', self.image, self.pc, value); self.pc += 4
    def branch(self, opcode, destination):
        self.word(opcode<<24 | ((destination-self.pc) & 0xfffffc))
    def literal(self, value, dest):
        self.word(0x8c000000 | dest<<19 | 0x3000); self.word(value)
    def mov(self, value, dest): self.word(reg(0x5cc, value, d=dest, lit=True))
    def mem(self, opcode, register, offset=0):
        self.word(opcode<<24 | register<<19 | 10<<14 | 0x2000 | offset)
    def transaction(self, selector=None, destination=4):
        if selector is not None: self.mem(0x82, selector, 0x14)
        self.literal(0 if selector is not None else 0x87, 3)
        self.mem(0x82, 3, 0x12); self.branch(9, 0x200)
        self.mem(0x80, 4, 0x16); self.mem(0x80, destination, 0x18)


def toy_image(mask=3, flag_xor=3, reversed_selectors=False):
    """Original test code at separate addresses, not copied guest instructions."""
    a = Assembly()
    a.at(0xa3980); a.branch(8, 0x1000)
    a.at(0xa39f0); a.word(0x0a000000)
    a.at(0xa38c0); a.branch(8, 0x4000)
    a.at(0xa3974); a.word(0x0a000000)
    # Synthetic status waiter, with its own registers and code placement.
    a.at(0x200); a.literal(0x01c00000, 10)
    loop=a.pc; a.mem(0x80, 4, 0x1a)
    a.word(reg(0x581,12,4,4,True)); a.word(reg(0x5a0,12,4,0,True))
    a.branch(0x15,loop); a.word(0x0a000000)
    # Synthetic two-selector helper with explicitly different instruction layout.
    a.at(0x1000); a.literal(0x01c00000,10)
    a.word(reg(0x5cc,17,d=11))
    a.transaction(16); a.transaction(destination=6)
    a.transaction(11); a.transaction(destination=7)
    a.word(reg(0x581,mask,7,7,True)); a.word(reg(0x59c,8,7,7,True))
    a.word(reg(0x587,6,7,16)); a.branch(8,0xa39f0)
    # Separate full-snapshot test program calls that helper and writes metadata
    # destinations. Physical axes/buttons are intentionally not labeled.
    a.at(0x4000); a.literal(0x01c00000,10)
    for index, destination in enumerate((0x51eef2,0x51eef0,0x51ef0e,0x51ef0c)):
        a.mov(2*index+(1 if reversed_selectors else 0),16); a.mov(2*index+1,17)
        a.branch(9,0xa3980)
        a.word(0x8a000000 | 16<<19 | 0x3000); a.word(destination)
    a.mov(8,6); a.transaction(6); a.transaction(destination=6)
    a.word(reg(0x586,flag_xor,6,6,True))
    a.word(reg(0x581,1,6,7,True))
    a.word(0x82000000 | 7<<19 | 0x3000); a.word(0x51ef08)
    a.word(reg(0x598,1,6,6,True)); a.word(reg(0x581,1,6,7,True))
    a.word(0x82000000 | 7<<19 | 0x3000); a.word(0x51ef24)
    a.branch(8,0xa3974)
    return bytes(a.image)


class InputReportTests(unittest.TestCase):
    def test_complete_summary_keeps_evidence_boundary(self):
        report=summarize(json.dumps(valid_report()))
        self.assertFalse(report['physical_receiver_verified'])
        self.assertFalse(report['calibration_verified'])
        self.assertEqual(report['selector_order'], list(range(9)))
        self.assertEqual(report['raw_value_rule'], 'low_byte | ((high_byte & 3) << 8)')
    def test_missing_extra_and_wrong_domain_fields_rejected(self):
        valid=valid_report()
        for key in valid:
            row=copy.deepcopy(valid); del row[key]
            with self.assertRaises(ValueError): summarize(json.dumps(row))
        for key,value in [('pair_cases',65536),('pair_cases',True),('synthetic_inputs',False),
                          ('all_contracts_passed',False),('step_min',0),('step_max',4096)]:
            row=copy.deepcopy(valid);row[key]=value
            with self.assertRaises(ValueError): summarize(json.dumps(row))
        with self.assertRaises(ValueError): summarize(json.dumps({**valid,'payload':'do not export'}))
    def test_duplicate_json_and_invalid_step_bounds_rejected(self):
        text=json.dumps(valid_report())
        with self.assertRaises(ValueError): summarize(text[:-1]+',"pair_cases":131072}')
        with self.assertRaises(ValueError): summarize(' '*4097)
        row=valid_report();row['step_min']=2000
        with self.assertRaises(ValueError): summarize(json.dumps(row))
        with self.assertRaises(ValueError): summarize('[]')
    def test_wrong_baseline_fails_before_compiler(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'wrong.bin';p.write_bytes(b'\0'*0x200000)
            with self.assertRaisesRegex(ValueError,'hash mismatch'): run_experiment(p)
    def test_output_must_not_replace_private_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.bin';p.write_bytes(b'unchanged')
            with patch('sys.argv',['input_contract','--image',str(p),'--output',str(p)]):
                with self.assertRaises(SystemExit): main()
            self.assertEqual(p.read_bytes(),b'unchanged')


class InputProbeNativeTests(unittest.TestCase):
    def execute(self, image):
        cxx=shutil.which('g++') or shutil.which('clang++')
        if cxx is None: self.skipTest('C++17 compiler unavailable')
        source,report=emit_cpp(image,0xa3980,4096,additional_entries=(0xa38c0,))
        self.assertFalse(report.unsupported)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);(path/'hotd1_i960.cpp').write_text(source,encoding='utf-8')
            exe=path/'probe'
            built=subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-I',str(ROOT/'runtime'),'-I',str(path),
                str(ROOT/'tools/experimental/hotd1_input_contract_probe.cpp'),'-o',str(exe)],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(built.returncode,0,built.stderr)
            return subprocess.run([str(exe)],capture_output=True,text=True,timeout=15)
    def test_synthetic_host_contract_runs_full_sweep(self):
        run=self.execute(toy_image())
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(summarize(run.stdout)['native_result']['pair_cases'],131072)
        self.assertIn('SYNTHETIC',run.stderr)
    def test_missing_high_byte_mask_is_detected(self):
        run=self.execute(toy_image(mask=31))
        self.assertNotEqual(run.returncode,0)
        self.assertEqual(run.stdout,'')
        self.assertIn('10-bit pair',run.stderr)
    def test_wrong_flag_polarity_is_detected(self):
        run=self.execute(toy_image(flag_xor=0))
        self.assertNotEqual(run.returncode,0)
        self.assertEqual(run.stdout,'')
        self.assertIn('flag0',run.stderr)
    def test_reordered_selectors_are_detected(self):
        run=self.execute(toy_image(reversed_selectors=True))
        self.assertNotEqual(run.returncode,0)
        self.assertEqual(run.stdout,'')
        self.assertIn('selector order',run.stderr)


if __name__=='__main__': unittest.main()
