"""Synthetic vectors for empirical upload framing; no original game bytes.

Artificial CRC-like records below test the mathematics and refusal paths,
not the physical FPGA device or its configuration semantics.
"""
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from arcaderecomp.upload_framing import (analyze_records, audit_image, marker_phases,
                                        polynomial_gcd, polynomial_remainder)


def reference_remainder(value, divisor):
    # Separate bit-serial oracle, rather than calling the implementation.
    degree = divisor.bit_length() - 1
    remainder = 0
    for bit in range(value.bit_length() - 1, -1, -1):
        remainder = (remainder << 1) | ((value >> bit) & 1)
        if remainder & (1 << degree):
            remainder ^= divisor
    return remainder


def synthetic(count=212, seed=123):
    rng = random.Random(seed)
    output = bytearray(b'\0' * 31)
    for _ in range(count):
        body = rng.getrandbits(177) << 8
        body ^= reference_remainder(body, 0x111) ^ 0xff
        framed = (body << 1) | (0x3f << 186)
        output.extend(framed.to_bytes(24, 'little'))
    output.extend(b'\0')
    return bytes(output)


class EmpiricalUploadFramingTests(unittest.TestCase):
    def test_gf_polynomial_division_against_bitserial_oracle(self):
        rng = random.Random(312)
        for degree in range(1, 17):
            for _ in range(50):
                divisor = (1 << degree) | rng.getrandbits(degree)
                value = rng.getrandbits(256)
                self.assertEqual(polynomial_remainder(value, divisor),
                                 reference_remainder(value, divisor))
        self.assertEqual(polynomial_gcd(0, 0), 0)
        self.assertEqual(polynomial_gcd(1, 0x111), 1)
        self.assertEqual(polynomial_gcd(0x1110, 0x333), 0x111)

    def test_training_and_heldout_relation_match_synthetic_records(self):
        result = analyze_records(synthetic())
        self.assertEqual(result['difference_gcd_hex'], '0x111')
        self.assertEqual(result['common_residue_hex'], '0xff')
        self.assertEqual(result['held_out_count'], 148)
        self.assertEqual(result['held_out_relation_failures'], 0)
        self.assertTrue(result['fits_proposed_structure'])
        self.assertFalse(result['physical_target_identified'])
        self.assertFalse(result['checksum_algorithm_identified'])
        self.assertNotIn('records', result)
        self.assertNotIn('payload', result)

    def test_single_bit_damage_in_each_heldout_bit_is_detected(self):
        # Alter every position in one unseen 192-bit record. The training
        # relation cannot adapt to fit these later mutations.
        original = synthetic()
        record = 100
        for bit in range(192):
            changed = bytearray(original)
            changed[31 + 24 * record + bit // 8] ^= 1 << (bit % 8)
            result = analyze_records(bytes(changed))
            self.assertFalse(result['fits_proposed_structure'], bit)
            if 1 <= bit <= 185:
                self.assertIn(record, result['relation_failure_indices'])
            else:
                self.assertIn(record, result['fixed_bit_failures'])

    def test_heldout_record_changes_do_not_change_derived_divisor(self):
        changed = bytearray(synthetic())
        changed[31 + 24 * 70 + 5] ^= 0x10
        changed[31 + 24 * 150 + 9] ^= 0x40
        result = analyze_records(bytes(changed))
        self.assertEqual(result['difference_gcd_hex'], '0x111')
        self.assertEqual(result['relation_failure_indices'], [70, 150])
        self.assertEqual(result['training_relation_failures'], 0)

    def test_uniform_and_unstructured_data_do_not_prove_a_format(self):
        for payload in (b'\0' * 5120, b'\xff' * 5120,
                        random.Random(13).randbytes(5120)):
            self.assertFalse(analyze_records(payload)['fits_proposed_structure'])

    def test_marker_scan_reports_all_phases_without_device_label(self):
        records = synthetic()
        phases = marker_phases(records[31:-1])
        self.assertEqual(len(phases), 24)
        self.assertEqual(phases[23], {'phase': 23, 'sample_count': 212,
                                     'matching_samples': 212})
        self.assertTrue(all(x['matching_samples'] < 212 for x in phases[:23]))
        self.assertEqual(marker_phases(b'\xfc', 24)[1]['sample_count'], 0)

    def test_input_and_arithmetic_bounds_reject_malformed_parameters(self):
        for opts in ({'offset': -1}, {'count': 0}, {'record_bytes': 1},
                     {'training_count': 212}, {'training_count': True},
                     {'offset': 4000}, {'record_bytes': 129}):
            with self.assertRaises(ValueError):
                analyze_records(synthetic(), **opts)
        for value, divisor in ((-1, 3), (1, 1), (True, 3), (1 << 4096, 3)):
            with self.assertRaises(ValueError):
                polynomial_remainder(value, divisor)
        with self.assertRaises(ValueError):
            polynomial_gcd(-1, 3)
        with self.assertRaises(ValueError):
            marker_phases(b'\0', stride=0)

    def test_original_profile_rejects_wrong_rom_and_sizes(self):
        for image in (b'', b'\0' * 5120, b'\0' * 0x200000):
            with self.assertRaises(ValueError):
                audit_image(image)

    def test_cli_failure_never_outputs_false_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            image, output = directory / 'wrong.bin', directory / 'report.json'
            image.write_bytes(b'\0' * 0x200000)
            run = subprocess.run([sys.executable, '-m', 'arcaderecomp.upload_framing',
                                  '--image', str(image), '--output', str(output)],
                                 capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 2)
            self.assertIn('hash mismatch', run.stderr)
            self.assertFalse(output.exists())

    def test_empirical_model_does_not_authenticate_unmodeled_prefix(self):
        original = synthetic()
        changed = bytearray(original)
        changed[0] ^= 0x80
        # Shape alone does not authenticate a stream; the actual hotdo CLI
        # additionally verifies full image and payload SHA-256.
        self.assertEqual(analyze_records(original), analyze_records(bytes(changed)))


if __name__ == '__main__':
    unittest.main()
