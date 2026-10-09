"""Invented data only; byte/bit mapping and provenance guards, not Sega logic."""
import hashlib
import json
from pathlib import Path
import random
import struct
import tempfile
import unittest
from unittest.mock import patch

from arcaderecomp import flex8000_sram as codec


def rcs(body, *, log=b'synthetic', desc=b'synthetic'):
    quote = lambda value: b'@' + value.replace(b'@', b'@@') + b'@'
    return (b'head 1.1;\nbranch 1.1.1;\ncomment @# @;\n'
            b'1.1\ndate 2020.01.01.00.00.00; author test; state Exp;\n'
            b'desc\n' + quote(desc) + b'\n1.1\nlog\n' + quote(log) +
            b'\ntext\n' + quote(body) + b'\n1.1.1.1\nlog\n@import@\ntext\n@@\n')


def sof(packed, *, device=b'EPF8282ALC84-2\0', total=37524):
    body = b'\0' * 6 + struct.pack('<IH', total, 1) + packed
    values = [(1, b'INVENTED TEST COMPILER\0'), (2, device), (3, b'\0'),
              (5, b'\0\0'), (18, b'\xff\xff'), (17, body), (8, b'\0\0')]
    return b'SOF\0' + struct.pack('<II', 0, len(values)) + b''.join(
        struct.pack('<HI', tag, len(value)) + value for tag, value in values)


def independent_check(data):
    # Independent long division over a list of coefficients, not integer shifts
    # through the production remainder function. Every possible check is tried.
    found = []
    for check in range(256):
        coefficients = [int(bit) for bit in f'{check:08b}{data:0177b}']
        for i in range(len(coefficients) - 8):
            if coefficients[i]:
                for delta in (0, 4, 8):
                    coefficients[i + delta] ^= 1
        if coefficients[-8:] == [1] * 8:
            found.append(check)
    if len(found) != 1:
        raise AssertionError('Oracle does not give a unique check byte')
    return found[0]


def fixture():
    rng = random.Random(8282)
    data = [rng.getrandbits(177) for _ in range(212)]
    # Not a real header. The generic codec intentionally requires but does not
    # interpret caller-supplied prefix/suffix bytes.
    stream = b'X' * 31 + b''.join(codec.encode_record(x) for x in data) + b'Y'
    # Separate bit-by-bit packing oracle. Serial data bit order is reversed
    # globally, not just bytes, just records, or each 177-bit value.
    bits = [((value >> bit) & 1) for value in data for bit in range(177)][::-1]
    raw = bytearray(4691)
    for index, bit in enumerate(bits):
        raw[index // 8] |= bit << (index % 8)
    return data, stream, bytes(raw)


class BinaryRcsTests(unittest.TestCase):
    def test_binary_escape_and_decoy_revision_inside_log_are_not_executable(self):
        value = b'\xff\0@\x80@@\r\nSOF\0'
        deceptive = b'\n1.1\nlog\n@ignored@\ntext\n@not the body@'
        self.assertEqual(codec.rcs_binary_head(rcs(value, log=deceptive, desc=deceptive)), ('1.1', value))

    def test_missing_duplicate_unterminated_and_oversized_snapshots_fail(self):
        good = rcs(b'test')
        bad = [b'', good.replace(b'head 1.1;', b'head 1.2;'), good[:-3],
               good + b'1.1\nlog\n@@\ntext\n@duplicate@',
               b'head 1.1; desc @unclosed', good + b'\xff', b'x' * (codec.MAX_FILE + 1)]
        for value in bad:
            with self.subTest(size=len(value)), self.assertRaises(ValueError):
                codec.rcs_binary_head(value)


class SofEnvelopeTests(unittest.TestCase):
    def test_embedded_device_declared_bit_count_and_exact_packet_bounds(self):
        _, _, packed = fixture()
        result = codec.parse_sof(sof(packed))
        self.assertEqual(result['device'], 'EPF8282ALC84-2')
        self.assertEqual(result['packet_sizes']['17'], 4703)
        self.assertEqual(result['packed'], packed)
        self.assertFalse(result['container_checksum_verified'])

    def test_stale_wrong_target_bad_size_count_header_and_padding_fail(self):
        _, _, packed = fixture()
        good = sof(packed)
        padding = packed[:-1] + bytes([packed[-1] | 0x80])
        bad = [good[:-1], good + b'extra', b'bad!' + good[4:],
               good[:4] + struct.pack('<II', 1, 7) + good[12:],
               good[:4] + struct.pack('<II', 0, 129) + good[12:],
               good[:4] + struct.pack('<II', 0, 8) + good[12:],
               sof(packed, total=37525), sof(padding), sof(packed + b'\0'),
               sof(packed, device=b'EPM5130QC\0'), sof(packed, device=b'EPF8282ALC84-2'),
               sof(packed, device=b'EPF8282ALC84-2\0wrong\0')]
        for data in bad:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                codec.parse_sof(data)

    def test_duplicate_packet_and_missing_data_are_rejected(self):
        device = b'EPF8282ALC84-2\0'
        packet = struct.pack('<HI', 2, len(device)) + device
        for count, tail in ((1, packet), (2, packet * 2)):
            with self.assertRaises(ValueError):
                codec.parse_sof(b'SOF\0' + struct.pack('<II', 0, count) + tail)


class ConfigurationDataTests(unittest.TestCase):
    def test_check_byte_agrees_with_separate_coefficient_oracle(self):
        rng = random.Random(177)
        for data in [0, codec.MASK, 1, 1 << 176] + [rng.getrandbits(177) for _ in range(12)]:
            encoded = codec.encode_record(data)
            check = (int.from_bytes(encoded, 'little') >> 178) & 255
            self.assertEqual(check, independent_check(data))
            self.assertEqual(codec.decode_record(encoded), data)

    def test_global_reversal_matches_independent_bit_by_bit_packing(self):
        _, stream, packed = fixture()
        self.assertEqual(codec.serial_to_sof_data(stream), packed)
        self.assertEqual(codec.sof_data_to_serial(packed, stream[:31], stream[-1:]), stream)
        result = codec.stream_metadata(stream)
        self.assertTrue(result['exact_roundtrip'])
        self.assertEqual(result['total_data_bits'], 37524)
        self.assertEqual(result['packed_data_sha256'], hashlib.sha256(packed).hexdigest())
        self.assertFalse(result['logic_netlist_recovered'])
        self.assertNotIn('packed', result)

    def test_every_single_bit_error_in_a_record_is_detected(self):
        record = codec.encode_record(random.Random(8).getrandbits(177))
        value = int.from_bytes(record, 'little')
        for bit in range(192):
            with self.subTest(bit=bit), self.assertRaises(ValueError):
                codec.decode_record((value ^ (1 << bit)).to_bytes(24, 'little'))

    def test_relation_is_not_cryptographic_and_does_not_detect_all_multibit_errors(self):
        # x^12 + 1 is divisible by x^8 + x^4 + 1. The original hash guard,
        # not this weak empirical relation, authenticates the full upload.
        record = codec.encode_record(0)
        changed = int.from_bytes(record, 'little') ^ (1 << 1) ^ (1 << 13)
        self.assertEqual(codec.decode_record(changed.to_bytes(24, 'little')), (1 << 12) | 1)

    def test_wrong_record_vector_envelope_and_numeric_bounds_fail(self):
        _, stream, packed = fixture()
        for value in [-1, True, 1 << 177]:
            with self.assertRaises(ValueError): codec.encode_record(value)
        for value in [b'', b'\0' * 23, bytearray(24)]:
            with self.assertRaises(ValueError): codec.decode_record(value)
        for value in [stream[:-1], stream + b'\0', bytearray(stream)]:
            with self.assertRaises(ValueError): codec.serial_to_sof_data(value)
        for raw, pre, post in [(packed[:-1], b'X'*31, b'Y'), (packed, b'X'*30, b'Y'),
                                (packed, b'X'*31, b'YY')]:
            with self.assertRaises(ValueError): codec.sof_data_to_serial(raw, pre, post)
        for value, width in [(0, 0), (2, 1), (-1, 10), (True, 3), (0, 37525)]:
            with self.assertRaises(ValueError): codec.reverse_bits(value, width)

    def test_envelope_preserved_but_not_falsely_authenticated(self):
        _, stream, packed = fixture()
        changed = b'Z' + stream[1:]
        self.assertEqual(codec.serial_to_sof_data(changed), packed)
        self.assertFalse(codec.stream_metadata(changed)['envelope_interpreted'])
        self.assertNotEqual(codec.stream_metadata(changed)['serial_sha256'], codec.stream_metadata(stream)['serial_sha256'])


class ProvenanceTests(unittest.TestCase):
    def test_exact_pairs_checked_and_mismatched_bits_never_report_success(self):
        _, stream, packed = fixture()
        s = rcs(sof(packed))
        t = rcs(','.join(str(b) for b in stream).encode())
        pins = {'synthetic': {'sof': ('synthetic.sof', codec.git_blob_sha1(s)),
                              'ttf': ('synthetic.ttf', codec.git_blob_sha1(t))}}
        with patch.object(codec, 'REFERENCES', pins):
            result = codec.analyze_pair('synthetic', s, t)
            self.assertTrue(result['exact_sof_ttf_data_match'])
            self.assertTrue(result['exact_roundtrip'])
            # New hashes alone must not let a different but valid stream match.
            altered = bytearray(packed); altered[0] ^= 1
            wrong = rcs(sof(bytes(altered)))
            pins['synthetic']['sof'] = ('synthetic.sof', codec.git_blob_sha1(wrong))
            with self.assertRaisesRegex(ValueError, 'locked bit mapping'):
                codec.analyze_pair('synthetic', wrong, t)
        with self.assertRaisesRegex(ValueError, 'blob mismatch'):
            codec.analyze_pair('testmux', s, t)

    def test_private_original_guard_and_cli_never_replace_input(self):
        with self.assertRaises(ValueError): codec.hotdo_metadata(b'\0' * 0x200000)
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'input.bin'
            image.write_bytes(b'\0' * 0x200000)
            original = image.read_bytes()
            for output in (image, Path(directory) / 'report.json'):
                with patch('sys.argv', ['audit', '--image', str(image), '--output', str(output)]):
                    with self.assertRaises(SystemExit) as raised: codec.main()
                self.assertEqual(raised.exception.code, 2)
            self.assertEqual(image.read_bytes(), original)
            self.assertFalse((Path(directory) / 'report.json').exists())


if __name__ == '__main__':
    unittest.main()
