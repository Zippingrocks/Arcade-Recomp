"""Metadata-only empirical structure study of the original HOTD1 upload.

This is NOT an Altera decoder, identified endpoint, official CRC model, or
runtime device implementation. Record slicing is an explicit research model.
No original bytes, record bodies, netlists or image fragments are exported.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from .serial_contract import HOTDO_SHA256, UPLOAD_BEGIN, UPLOAD_END

UPLOAD_SHA256 = 'de6e298436c243dd11bc725592b99cf9e87bde6d305583ef0aec511610ec76c1'
MAX_PAYLOAD = 1 << 20


def _int(value: int, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


def polynomial_remainder(value: int, polynomial: int) -> int:
    """GF(2) polynomial division, encoded in integer bit positions."""
    if type(value) is not int or value < 0 or value.bit_length() > 4096:
        raise ValueError('Polynomial value must be nonnegative, at most 4096 bits')
    if type(polynomial) is not int or polynomial < 2 or polynomial.bit_length() > 4096:
        raise ValueError('Divisor must have positive degree, at most 4095')
    width = polynomial.bit_length()
    while value.bit_length() >= width:
        value ^= polynomial << (value.bit_length() - width)
    return value


def polynomial_gcd(left: int, right: int) -> int:
    """Polynomial GCD; gcd(0,0)=0. No statistical or hardware claim."""
    for value in (left, right):
        if type(value) is not int or value < 0 or value.bit_length() > 4096:
            raise ValueError('GCD arguments must be nonnegative, at most 4096 bits')
    while right:
        if right == 1:
            return 1
        left, right = right, polynomial_remainder(left, right)
    return left


def marker_phases(payload: bytes, stride: int = 24, mask: int = 0xfc) -> list[dict]:
    """Count a masked-byte observation at every phase, not only a chosen one."""
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError('Payload must contain 1..1048576 bytes')
    _int(stride, 1, 256, 'stride')
    _int(mask, 1, 255, 'mask')
    return [{'phase': phase, 'sample_count': len(payload[phase::stride]),
             'matching_samples': sum((byte & mask) == mask for byte in payload[phase::stride])}
            for phase in range(stride)]


def analyze_records(payload: bytes, *, offset: int = 31, record_bytes: int = 24,
                    count: int = 212, training_count: int = 64) -> dict:
    """Test explicitly proposed 1-zero/185-variable/6-one bit records.

    The first training_count records determine the maximal GF(2) divisor
    of their differences. Later records are held out from that calculation.
    Correlated data and model selection prevent interpreting this as a
    calibrated statistical confidence or confirmed FPGA checksum.
    """
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_PAYLOAD:
        raise ValueError('Payload must contain 1..1048576 bytes')
    _int(offset, 0, len(payload), 'offset')
    _int(record_bytes, 2, 128, 'record_bytes')
    _int(count, 3, 4096, 'count')
    _int(training_count, 2, count - 1, 'training_count')
    end = offset + count * record_bytes
    if end > len(payload):
        raise ValueError('Record layout exceeds payload')
    middle_bits = record_bytes * 8 - 7
    middle_mask = (1 << middle_bits) - 1
    records = [payload[offset + i * record_bytes:offset + (i + 1) * record_bytes]
               for i in range(count)]
    words = [(int.from_bytes(record, 'little') >> 1) & middle_mask for record in records]
    framing_bad = [i for i, record in enumerate(records)
                   if record[0] & 1 or (record[-1] & 0xfc) != 0xfc]
    divisor = 0
    for word in words[1:training_count]:
        divisor = polynomial_gcd(divisor, word ^ words[0])
    degree = divisor.bit_length() - 1
    usable = 1 < divisor and degree < middle_bits
    residue = polynomial_remainder(words[0], divisor) if usable else None
    bad = ([i for i, word in enumerate(words)
            if polynomial_remainder(word, divisor) != residue] if usable else [])
    train_bad = sum(i < training_count for i in bad)
    hold_bad = sum(i >= training_count for i in bad)
    return {
        'interpretation': 'empirical_record_model_not_manufacturer_format',
        'record_offset': offset, 'record_bytes': record_bytes, 'record_count': count,
        'uninterpreted_prefix_bytes': offset,
        'uninterpreted_suffix_bytes': len(payload) - end,
        'byte_order_for_analysis': 'little', 'low_fixed_bits': 1, 'low_fixed_value': 0,
        'high_fixed_bits': 6, 'high_fixed_value': 63, 'middle_bits': middle_bits,
        'distinct_records': len(set(records)),
        'fixed_bit_failures': framing_bad,
        'training_count': training_count, 'held_out_count': count - training_count,
        'difference_gcd_hex': hex(divisor), 'difference_gcd_degree': degree,
        'nontrivial_relation_found': usable,
        'common_residue_hex': hex(residue) if residue is not None else None,
        'training_relation_failures': train_bad if usable else None,
        'held_out_relation_failures': hold_bad if usable else None,
        'relation_failure_indices': bad if usable else None,
        'fits_proposed_structure': usable and not framing_bad and not bad,
        'checksum_algorithm_identified': False,
        'physical_target_identified': False,
    }


def audit_image(image: bytes) -> dict:
    """Profile ONLY the authenticated original hotdo CPU image; metadata out."""
    if not isinstance(image, bytes) or len(image) != 0x200000:
        raise ValueError('Expected a 2-MiB original hotdo CPU image')
    if hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Original hotdo CPU image hash mismatch')
    payload = image[UPLOAD_BEGIN:UPLOAD_END]
    digest = hashlib.sha256(payload).hexdigest()
    if digest != UPLOAD_SHA256:
        raise ValueError('Original upload payload hash mismatch')
    frequencies = Counter(payload)
    entropy = -sum((n / len(payload)) * math.log2(n / len(payload)) for n in frequencies.values())
    model = analyze_records(payload)
    if (not model['fits_proposed_structure'] or model['difference_gcd_hex'] != '0x111'
            or model['common_residue_hex'] != '0xff'):
        raise ValueError('The specified original upload no longer fits the recorded empirical model')
    return {
        'schema_version': 1, 'evidence_level': 'original_rom_static_empirical_structure',
        'image_sha256': HOTDO_SHA256,
        'payload_begin': hex(UPLOAD_BEGIN), 'payload_end': hex(UPLOAD_END),
        'payload_size_bytes': len(payload), 'payload_size_bits': len(payload) * 8,
        'payload_sha256': digest,
        'zero_bytes': frequencies[0], 'entropy_bits_per_byte': round(entropy, 9),
        'phase_scan': marker_phases(payload), 'record_model': model,
        'device_identity': 'unconfirmed: FPGA-configuration candidate; see evidence note',
        'runtime_changed': False,
        'evidence_boundary': 'No FPGA netlist, serial timing, physical endpoint, or Model 2C completion verified.',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.image.stat().st_size != 0x200000:
            raise ValueError('Expected a 2-MiB original CPU image')
        if args.image.resolve() == args.output.resolve():
            raise ValueError('Output must not replace the input image')
        result = audit_image(args.image.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print('Wrote empirical upload metadata; FPGA identity and hardware behavior remain unconfirmed.')
    except (ValueError, OSError) as error:
        parser.exit(2, f'Upload structure audit failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
