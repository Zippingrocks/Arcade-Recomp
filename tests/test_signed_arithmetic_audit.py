"""Metadata/private-input tests using invented instructions, never Sega bytes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from arcaderecomp.signed_arithmetic_audit import parse_result, render_harness, run_audit, vectors
from test_i960_integer_arithmetic import native, regop


class SignedArithmeticAuditTests(unittest.TestCase):
    def test_native_harness_rejects_wrong_expected_arithmetic(self):
        row = (0, 16, 17, 17, 0, 1, 0x7fffffff, 0x80000000, 1)
        native([regop(0x591, d=17), 0xffffffff], render_harness([row]))
        bad = row[:-2] + (0, 1)
        with self.assertRaises(AssertionError):
            native([regop(0x591, d=17), 0xffffffff], render_harness([bad]))

    def test_vector_counts_and_masked_unmasked_domains(self):
        rows = vectors()
        self.assertEqual(len(rows), 1672)
        self.assertEqual({row[0] for row in rows}, {0x1034, 0x103c, 0x1060})
        self.assertEqual(sum(row[0] == 0x1060 for row in rows), 520)
        self.assertTrue(any(row[-1] for row in rows))
        self.assertTrue(any(not row[-1] for row in rows))

    def test_report_refuses_duplicates_missing_counts_and_false_provenance(self):
        good = {'checks': 32, 'synthetic_cpu_state': True, 'hardware_verified': False}
        self.assertEqual(parse_result(json.dumps(good), 32), good)
        variants = []
        for field, value in (('checks', 31), ('checks', True), ('hardware_verified', True),
                             ('synthetic_cpu_state', False)):
            variants.append(json.dumps({**good, field: value}))
        variants += ['[]', '{}', 'x'*1025,
                     '{"checks":32,"checks":32,"synthetic_cpu_state":true,"hardware_verified":false}']
        for text in variants:
            with self.assertRaises(ValueError):
                parse_result(text, 32)

    def test_unverified_image_is_rejected_before_compilation(self):
        with tempfile.TemporaryDirectory() as d:
            image = Path(d)/'synthetic.bin'
            image.write_bytes(bytes(0x200000))
            with self.assertRaisesRegex(ValueError, 'hash'):
                run_audit(image, ('compiler-must-not-be-run',))

    def test_cli_prevents_input_output_aliases_including_hardlinks(self):
        with tempfile.TemporaryDirectory() as d:
            image, alias = Path(d)/'input.bin', Path(d)/'alias.bin'
            image.write_bytes(b'preserve input')
            os.link(image, alias)
            for output in (image, alias):
                p = subprocess.run([sys.executable, '-m', 'arcaderecomp.signed_arithmetic_audit',
                    '--image', str(image), '--output', str(output)], capture_output=True,
                    text=True, timeout=10)
                self.assertEqual(p.returncode, 2)
                self.assertIn('overwrite input', p.stderr)
                self.assertEqual(image.read_bytes(), b'preserve input')

if __name__ == '__main__':
    unittest.main()
