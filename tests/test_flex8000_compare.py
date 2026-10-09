"""ROM-free compiler-reference reader tests; entirely artificial config data.

Public compiler-output bytes and the private Sega upload are NOT fixtures.
The independent primary-file comparison runs in an opt-in reference job.
"""
import copy
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from arcaderecomp.flex8000_compare import (analyze_reference, compare_hotdo,
    framing_profile, git_blob_sha1, parse_ttf, rcs_head_text)


def synthetic(seed=7):
    # Separate bit-serial polynomial oracle, not imported implementation.
    rng = random.Random(seed)
    payload = bytearray(b'\xff' * 31)
    for _ in range(212):
        value = rng.getrandbits(177) << 8
        remainder = 0
        for bit in range(value.bit_length() - 1, -1, -1):
            remainder = (remainder << 1) | ((value >> bit) & 1)
            if remainder & 256:
                remainder ^= 0x111
        value ^= remainder ^ 255
        payload.extend(((value << 1) | (63 << 186)).to_bytes(24, 'little'))
    return bytes(payload + b'\xff')


def rcs(text, log='a log with escaped @@ at signs'):
    return ('head\t1.1;\naccess;\n1.1\ndate 2000.01.01.00.00.00; next;\n'
            'desc\n@@\n1.1\nlog\n@' + log + '@\ntext\n@' + text.replace('@', '@@') +
            '@\n1.1.1.1\nlog\n@older@\ntext\n@a1 2\nnot full text\n@\n').encode('ascii')


def fit(device='EPF8282ALC84-2'):
    return rcs(f'CHIP "testmux"\nBEGIN\n DEVICE = "{device}";\nEND;\n')


class ConfigurationReferenceTests(unittest.TestCase):
    def test_blob_hash_matches_git_object_encoding(self):
        self.assertEqual(git_blob_sha1(b'hello\n'), 'ce013625030ba8dba906f756967f9e9ca394464a')

    def test_rcs_reads_only_head_and_decodes_at_escape(self):
        revision, text = rcs_head_text(rcs('body @ marker\n255,0,1'))
        self.assertEqual((revision, text), ('1.1', 'body @ marker\n255,0,1'))
        self.assertNotIn('not full text', text)

    def test_rcs_rejects_missing_duplicate_and_unterminated_entries(self):
        base = rcs('0,1')
        for bad in (b'', b'head;\n', base.replace(b'1.1\nlog', b'1.2\nlog', 1),
                    base + b'1.1\nlog\n@@\ntext\n@@',
                    b'head 1.1;\n1.1\nlog\n@@\ntext\n@no end'):
            with self.subTest(bad=bad[:30]), self.assertRaises(ValueError):
                rcs_head_text(bad)

    def test_ttf_accepts_decimal_bytes_not_rcs_or_hex(self):
        self.assertEqual(parse_ttf('255, 0, 001,\n 32, '), b'\xff\x00\x01\x20')
        for text in ('', ',', '256', '-1', '0x10', '1,,2', '1,2,,', '1 2', 'head 1.1;', 'a1 2', '1000'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_ttf(text)

    def test_locked_model_validates_all_synthetic_frames(self):
        report = framing_profile(synthetic())
        self.assertTrue(report['matches_preexisting_model'])
        self.assertEqual(report['record_count'], 212)
        self.assertEqual(report['empirical_residue'], '0xff')
        self.assertNotIn('payload', report)
        self.assertNotIn('records', report)

    def test_fixed_model_cannot_refit_mutated_reference(self):
        payload = synthetic()
        for frame in (0, 63, 64, 148, 211):
            for bit in (0, 1, 8, 91, 185, 186, 191):
                damaged = bytearray(payload)
                damaged[31 + 24*frame + bit//8] ^= 1 << (bit % 8)
                report = framing_profile(bytes(damaged))
                self.assertFalse(report['matches_preexisting_model'], (frame, bit))
                self.assertIn(frame, report['fixed_bit_failure_indices'] + report['relation_failure_indices'])

    def test_prefix_changes_do_not_masquerade_as_payload_identity(self):
        a = synthetic(); b = bytearray(a); b[0] ^= 8
        pa, pb = framing_profile(a), framing_profile(bytes(b))
        self.assertTrue(pa['matches_preexisting_model'] and pb['matches_preexisting_model'])
        self.assertNotEqual(pa['payload_sha256'], pb['payload_sha256'])
        self.assertNotEqual(pa['prefix_sha256'], pb['prefix_sha256'])

    def test_reference_device_and_pin_blob_guard(self):
        ttf = rcs(','.join(map(str, synthetic())))
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            analyze_reference(ttf, fit())
        report = analyze_reference(ttf, fit(), require_pinned=False)
        self.assertFalse(report['pinned_blobs_verified'])
        self.assertTrue(report['reference_profile']['matches_preexisting_model'])
        for bad in (fit('EPF8452'), rcs('CHIP "other"\nDEVICE=EPF8282ALC84-2;'),
                    rcs('CHIP "testmux"\nDEVICE=EPF8282ALC84-2;\nDEVICE=EPF8452;')):
            with self.assertRaisesRegex(ValueError, 'unambiguously'):
                analyze_reference(ttf, bad, require_pinned=False)

    def test_wrong_stream_shape_rejected_not_truncated(self):
        for n in (0, 31, 5119, 5121):
            with self.assertRaises(ValueError):
                framing_profile(b'\0' * n)
        self.assertFalse(framing_profile(b'\0' * 5120)['matches_preexisting_model'])

    def test_wrong_original_image_cannot_get_a_comparison_report(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            compare_hotdo({'pinned_blobs_verified': True}, b'\0' * 0x200000)

    def test_cli_identity_failure_produces_no_false_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d/'ttf').write_bytes(rcs('1,2,3'))
            (d/'fit').write_bytes(fit())
            result = subprocess.run([sys.executable, '-m', 'arcaderecomp.flex8000_compare',
                '--ttf-rcs', str(d/'ttf'), '--fit-rcs', str(d/'fit'), '--output', str(d/'report')],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn('identity mismatch', result.stderr)
            self.assertFalse((d/'report').exists())


if __name__ == '__main__':
    unittest.main()
