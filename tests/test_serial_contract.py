"""Synthetic contract/provenance tests; no Sega bytes are present in CI."""
import copy
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from arcaderecomp.i960_cpp import emit_cpp
from arcaderecomp.serial_contract import (mask_formula, parse_rows, summarize_rows,
                                          run_experiment)

ROOT = Path(__file__).resolve().parents[1]


def rows():
    return [{'synthetic_inputs': True, 'rx1': a, 'rx2': b, 'steps': 42,
             'return_ip': 100, 'tx1_count': 2, 'tx2_count': 1,
             'rx1_count': 1, 'rx2_count': 1, 'status_reads': 1,
             'upload_bytes': 2, 'upload_matches_rom': True,
             'controls': [{'command': 1, 'new_data': b & 254},
                          {'command': 129, 'new_data': b | 1}]}
            for a in (0, 255) for b in range(256)]


class SerialContractSummaryTests(unittest.TestCase):
    def test_exact_byte_domain_derives_bit_clear_set(self):
        result = summarize_rows(rows())
        self.assertEqual(result['case_count'], 512)
        self.assertTrue(result['not_hardware_validation'])
        self.assertTrue(result['data_same_for_tested_rx1'])
        self.assertEqual(result['controls'][0]['data_by_rx1']['0'],
                         {'kind': 'rx2_mask', 'and_mask': 254, 'or_bits': 0})
        self.assertEqual(result['controls'][1]['data_by_rx1']['255'],
                         {'kind': 'rx2_mask', 'and_mask': 254, 'or_bits': 1})

    def test_incomplete_duplicate_and_non_synthetic_cases_rejected(self):
        base = rows()
        variants = [base[:-1], base + [base[0]], [base[0]] + base[:-1]]
        for field, value in [('synthetic_inputs', False), ('rx2', True),
                             ('upload_matches_rom', False), ('steps', -1)]:
            data = copy.deepcopy(base)
            data[0][field] = value
            variants.append(data)
        for data in variants:
            with self.assertRaises(ValueError):
                summarize_rows(data)

    def test_no_generalization_over_rx1_dependence(self):
        data = rows()
        for row in data:
            row['controls'][0]['new_data'] = row['rx1']
        result = summarize_rows(data)
        self.assertFalse(result['data_same_for_tested_rx1'])
        self.assertEqual(result['controls'][0]['data_by_rx1']['255'],
                         {'kind': 'constant', 'value': 255})

    def test_mask_inference_checks_all_256_outputs(self):
        values = [n & 254 for n in range(256)]
        values[123] = 99
        self.assertEqual(mask_formula(values), {'kind': 'not_a_mask_formula'})
        self.assertEqual(mask_formula([None] * 256), {'kind': 'constant', 'value': None})
        with self.assertRaises(ValueError):
            mask_formula([0])

    def test_jsonl_rejects_truncation_duplicates_and_excessive_size(self):
        text = '\n'.join(json.dumps(row) for row in rows()[:256])
        self.assertEqual(len(parse_rows(text)), 256)
        for invalid in [text[:text.rfind('\n')], 'x' * 2_000_001,
                        '\n'.join(['{"a":1,"a":2}'] * 256), '\n'.join(['[]'] * 256)]:
            with self.assertRaises(ValueError):
                parse_rows(invalid)

    def test_baseline_hash_is_required_before_any_native_execution(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'wrong.bin'
            p.write_bytes(b'\0' * 0x200000)
            with self.assertRaisesRegex(ValueError, 'baseline'):
                run_experiment(p)


class SerialContractNativeTests(unittest.TestCase):
    def test_compiled_fixture_checks_upload_and_mask_without_distributing_bytes(self):
        cxx = shutil.which('g++') or shutil.which('clang++')
        if not cxx:
            self.skipTest('Need C++17 compiler')
        image = bytearray(0x200000)
        image[0x1000:0x1002] = b'\x12\x34'  # entirely invented input data
        words = []
        def reg(op, a, b, d, literal=False):
            return (op >> 4) << 24 | (op & 15) << 7 | a | b << 14 | d << 19 | int(literal) << 11
        def mem(op, r, base=10, offset=0):
            return op << 24 | r << 19 | base << 14 | 0x2000 | offset
        def lda(value, dst):
            words.extend([0x8c000000 | dst << 19 | 0x3000, value])
        lda(0x01c00000, 10)
        lda(0x1000, 3)
        words.append(reg(0x5cc, 2, 0, 5, True))
        loop = 0x100 + 4 * len(words)
        words.extend([mem(0x80, 4, 3), mem(0x82, 4, offset=0x14),
                      reg(0x5cc, 7, 0, 4, True), mem(0x82, 4, offset=0x12),
                      reg(0x590, 1, 3, 3, True), reg(0x5a7, 1, 5, 5, True)])
        branch = 0x100 + 4 * len(words)
        words.append(0x15000000 | ((loop - branch) & 0xfffffc))
        words.extend([mem(0x80, 4, offset=0x18), reg(0x58c, 0, 4, 4, True),
                      mem(0x82, 4, offset=0x14), reg(0x5cc, 1, 0, 3, True),
                      mem(0x82, 3, offset=0x12), 0x0a000000])
        struct.pack_into('<' + 'I' * len(words), image, 0x100, *words)
        generated, report = emit_cpp(bytes(image), 0x100, 128)
        self.assertFalse(report.unsupported)
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            (work / 'hotd1_i960.cpp').write_text(generated, encoding='utf-8')
            (work / 'synthetic.bin').write_bytes(image)
            exe = work / 'probe'
            built = subprocess.run([cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                                    '-I', str(ROOT/'runtime'), '-I', str(work),
                                    str(ROOT/'tools/experimental/hotd1_serial_contract_probe.cpp'),
                                    '-o', str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(built.returncode, 0, built.stderr)
            cmd = [str(exe), str(work/'synthetic.bin'), '0x100', '0x1000', '0x1002', '7', '255']
            run = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = parse_rows(run.stdout)
            self.assertEqual(len(result), 256)
            for row in result:
                self.assertEqual(row['upload_bytes'], 2)
                self.assertEqual(row['controls'], [{'command': 1, 'new_data': row['rx2'] & 254}])
            self.assertIn('SYNTHETIC', run.stderr)
            cmd[4] = '0x1003'  # mismatch: do NOT claim the entire requested block was sent
            bad = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(bad.stdout, '')

if __name__ == '__main__':
    unittest.main()
