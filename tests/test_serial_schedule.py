"""Synthetic verifier tests and native harness smoke test; no Sega ROM data."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from arcaderecomp.i960_cpp import emit_cpp
from arcaderecomp.serial_schedule import DELAYS, checked_image, summarize

ROOT=Path(__file__).resolve().parents[1]

def fixtures():
    rows=[]
    for seed in range(16):
        for d1,d2 in DELAYS:
            for noise in (0,1):
                rows.append(dict(kind='upload',seed=seed,delay1=d1,delay2=d2,noise=noise,
                    steps=89199+6*5132*max(d1,d2),polls=5132*(1+max(d1,d2)),
                    transactions=5132,upload_bytes=5120,upload_matches=True,
                    synthetic_inputs=True,feedback_matches=True))
    for status in range(256):
        ret=status&12==12
        rows.append(dict(kind='wait',status=status,steps=6 if ret else 128,
                         polls=1 if ret else 21,returned=ret,step_bound=128,synthetic_inputs=True))
    return rows

def encoded(rows):
    return '\n'.join(json.dumps(row) for row in rows)

class SerialScheduleTests(unittest.TestCase):
    def test_complete_domains_and_no_hardware_fidelity_claim(self):
        r=summarize(encoded(fixtures()))
        self.assertEqual((r['upload_cases'],r['wait_cases']),(192,256))
        self.assertEqual((r['wait_returned_cases'],r['wait_bounded_nonreturn_cases']),(64,192))
        self.assertFalse(r['physical_hardware_verified'])
        self.assertEqual(r['steps_range'],[89199,366327])

    def test_missing_duplicate_or_added_cases_fail(self):
        rows=fixtures()
        for altered in (rows[:-1],rows+[rows[0]],rows[:-1]+[rows[0]]):
            with self.assertRaises(ValueError):summarize(encoded(altered))

    def test_changes_in_native_counts_feedback_and_upload_fail(self):
        for key,value in [('steps',89198),('polls',5131),('transactions',5131),
                          ('upload_bytes',5119),('upload_matches',False),('feedback_matches',False)]:
            rows=fixtures(); rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):summarize(encoded(rows))

    def test_wrong_wait_outcome_or_bound_rejected(self):
        for key,value in [('returned',True),('steps',127),('polls',22),('step_bound',129)]:
            rows=fixtures(); rows[192][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):summarize(encoded(rows))

    def test_unknown_fields_bool_numbers_and_missing_declaration_rejected(self):
        for key,value in [('seed',True),('noise',False),('synthetic_inputs',1),('unexpected','extra')]:
            rows=fixtures(); rows[0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):summarize(encoded(rows))

    def test_json_repeated_keys_size_and_malformed_records(self):
        text=encoded(fixtures())
        for candidate in (text.replace('"seed": 0','"seed": 0, "seed": 0',1),
                          ' ' * 1_000_001, '['+'\n'.join(text.splitlines()[1:])):
            with self.assertRaises(ValueError):summarize(candidate)
        rows=fixtures();rows[0]=[]
        with self.assertRaises(ValueError):summarize(encoded(rows))

    def test_original_image_guard_precedes_native_execution(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fake.bin';p.write_bytes(b'\xff'*16)
            with self.assertRaisesRegex(ValueError,'2-MiB'):checked_image(p)
            p.write_bytes(b'\xff'*0x200000)
            with self.assertRaisesRegex(ValueError,'hash mismatch'):checked_image(p)

    def test_case_order_does_not_create_false_missing_results(self):
        rows=fixtures();r=summarize(encoded(rows))
        self.assertEqual(r,summarize(encoded(list(reversed(rows)))))

    def test_native_harness_compiles_and_rejects_incomplete_synthetic_program(self):
        cxx=shutil.which('g++') or shutil.which('clang++')
        if not cxx:self.skipTest('Need C++17 compiler')
        image=b'\xff'*0x200000
        source,report=emit_cpp(image,0xa3750,32)
        self.assertEqual(report.translated,0)
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);(d/'hotd1_i960.cpp').write_text(source,encoding='utf-8')
            (d/'synthetic.bin').write_bytes(image)
            exe=d/'probe'
            run=subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-I',str(d),'-I',str(ROOT/'runtime'),
                str(ROOT/'tools/experimental/hotd1_serial_schedule_probe.cpp'),'-o',str(exe)],
                capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr)
            result=subprocess.run([str(exe),str(d/'synthetic.bin')],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertEqual(result.stdout,'')
            self.assertIn('NOT physical hardware validation',result.stderr)
            self.assertIn('contract failed',result.stderr)

if __name__=='__main__':unittest.main()
