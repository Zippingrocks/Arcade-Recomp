"""EPF8282 serial-record/SOF data mapping, not a recovered logic netlist.

The mapping is empirical and restricted to the measured 212 x 177-bit
profile. Reference downloads are explicit and hash-pinned. Only metadata
is exported; configuration bytes never enter CI artifacts or stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import urllib.request

from .flex8000_compare import (COMMIT, DIRECTORY, MAX_FILE, REPOSITORY,
                               git_blob_sha1, parse_ttf)
from .serial_contract import HOTDO_SHA256, UPLOAD_BEGIN, UPLOAD_END
from .upload_framing import UPLOAD_SHA256, polynomial_remainder

RECORDS, DATA_BITS, RECORD_BYTES = 212, 177, 24
TOTAL_BITS = RECORDS * DATA_BITS
PACKED_BYTES = (TOTAL_BITS + 7) // 8
MASK = (1 << DATA_BITS) - 1
# These are two unrelated non-Sega compiler-output pairs. Device identity
# comes from INSIDE each SOF, not from a possibly stale sibling FIT report.
REFERENCES = {
    'testmux': {
        'sof': ('testmux.sof,v', '4bd945df501d848d9fc4fd512945336ec7c24fca'),
        'ttf': ('testmux.ttf,v', 'b497a84a8288d94771b3439c36e667cd93cd5b51'),
    },
    'buff_with_clk': {
        'sof': ('buff_with_clk.sof,v', '224eeb4b8023f9fc0a16166f9e72d224ba32b57b'),
        'ttf': ('buff_with_clk.ttf,v', '8230b4adf18606b955862280a4d6d50b4ef7a06e'),
    },
}


def rcs_binary_head(data: bytes) -> tuple[str, bytes]:
    """Bounded RCS deltatext reader, including binary @-escaped snapshots.

    Only the full head snapshot is returned. Older delta programs are not
    applied. Quoted description/log text cannot impersonate revision entries.
    """
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_FILE:
        raise ValueError('RCS input outside size bounds')
    position, token_count = 0, 0

    def token() -> tuple[str, bytes] | None:
        nonlocal position, token_count
        while position < len(data) and data[position] in b' \t\r\n\f\v':
            position += 1
        if position == len(data):
            return None
        token_count += 1
        if token_count > 50000:
            raise ValueError('RCS token bound exceeded')
        if data[position] == 64:
            position += 1
            parts = []
            while True:
                end = data.find(b'@', position)
                if end < 0:
                    raise ValueError('Unterminated RCS string')
                parts.append(data[position:end])
                position = end + 1
                if position < len(data) and data[position] == 64:
                    parts.append(b'@'); position += 1
                else:
                    return 'string', b''.join(parts)
        if data[position] in b';:':
            result = data[position:position+1]; position += 1
            return 'symbol', result
        begin = position
        while position < len(data) and data[position] not in b' \t\r\n\f\v;:@':
            if not 33 <= data[position] <= 126:
                raise ValueError('Non-ASCII RCS token outside a quoted string')
            position += 1
        if begin == position:
            raise ValueError('Invalid RCS token')
        return 'word', data[begin:position]

    if token() != ('word', b'head'):
        raise ValueError('Missing RCS head')
    head = token()
    if head is None or head[0] != 'word' or not re.fullmatch(rb'\d+(?:\.\d+)+', head[1]):
        raise ValueError('Invalid RCS head revision')
    if token() != ('symbol', b';'):
        raise ValueError('Missing RCS head delimiter')
    while True:
        item = token()
        if item is None:
            raise ValueError('Missing RCS description')
        if item == ('word', b'desc'):
            break
    description = token()
    if description is None or description[0] != 'string':
        raise ValueError('Missing quoted description')
    found, revisions = None, set()
    while (revision := token()) is not None:
        if revision[0] != 'word' or not re.fullmatch(rb'\d+(?:\.\d+)+', revision[1]):
            raise ValueError('Invalid deltatext revision')
        if revision[1] in revisions:
            raise ValueError('Duplicate deltatext revision')
        revisions.add(revision[1])
        if token() != ('word', b'log'):
            raise ValueError('Missing revision log')
        log = token()
        if log is None or log[0] != 'string' or token() != ('word', b'text'):
            raise ValueError('Malformed log/text entry')
        contents = token()
        if contents is None or contents[0] != 'string':
            raise ValueError('Missing revision text')
        if revision[1] == head[1]:
            found = contents[1]
    if found is None:
        raise ValueError('Head snapshot absent')
    return head[1].decode('ascii'), found


def parse_sof(data: bytes) -> dict:
    """Inspect the observed SOF v0 TLV envelope; no checksum semantics claimed."""
    if not isinstance(data, bytes) or not 12 <= len(data) <= MAX_FILE or data[:4] != b'SOF\0':
        raise ValueError('Invalid SOF signature/size')
    version, count = struct.unpack_from('<II', data, 4)
    if version != 0 or not 1 <= count <= 128:
        raise ValueError('Unsupported SOF version or packet count')
    position, packets = 12, {}
    for _ in range(count):
        if position + 6 > len(data):
            raise ValueError('Truncated SOF packet header')
        tag, length = struct.unpack_from('<HI', data, position)
        position += 6
        if tag in packets or position + length > len(data):
            raise ValueError('Duplicate or truncated SOF packet')
        packets[tag] = data[position:position+length]
        position += length
    if position != len(data):
        raise ValueError('Trailing bytes outside declared SOF packets')
    if 2 not in packets or 17 not in packets:
        raise ValueError('SOF device/data packets absent')
    device_bytes = packets[2]
    if not 2 <= len(device_bytes) <= 80 or not device_bytes.endswith(b'\0'):
        raise ValueError('Invalid SOF device field')
    device = device_bytes[:-1].decode('ascii')
    if not re.fullmatch(r'EPF8282A(?:LC84|TC100)-[234]', device):
        raise ValueError('SOF target is outside the observed EPF8282A profile')
    body = packets[17]
    if len(body) != 12 + PACKED_BYTES:
        raise ValueError('Unexpected SOF data-packet length')
    # Field locations observed in pinned compiler output, not a general SOF spec.
    if body[:6] != b'\0' * 6 or struct.unpack_from('<I', body, 6)[0] != TOTAL_BITS \
            or body[10:12] != b'\1\0':
        raise ValueError('Unsupported SOF data-packet header')
    packed = body[12:]
    if int.from_bytes(packed, 'little') >> TOTAL_BITS:
        raise ValueError('Nonzero unused SOF data padding')
    return {'device': device, 'packed': packed, 'packet_count': count,
            'packet_sizes': {str(k): len(v) for k, v in packets.items()},
            'container_checksum_verified': False}


def reverse_bits(value: int, width: int) -> int:
    if type(width) is not int or not 1 <= width <= TOTAL_BITS \
            or type(value) is not int or not 0 <= value < (1 << width):
        raise ValueError('Invalid bounded bit vector')
    return int(format(value, f'0{width}b')[::-1], 2)


# Check bits are uniquely determined by the old locked polynomial relation.
# This is an empirical encoding, not a claim about the manufacturer's LFSR.
_CHECK_INVERSE = {polynomial_remainder(c << DATA_BITS, 0x111): c for c in range(256)}
assert len(_CHECK_INVERSE) == 256


def encode_record(value: int) -> bytes:
    if type(value) is not int or not 0 <= value <= MASK:
        raise ValueError('Record data must fit 177 bits')
    check = _CHECK_INVERSE[0xff ^ polynomial_remainder(value, 0x111)]
    framed = (63 << 186) | (check << 178) | (value << 1)
    return framed.to_bytes(RECORD_BYTES, 'little')


def decode_record(record: bytes) -> int:
    if not isinstance(record, bytes) or len(record) != RECORD_BYTES:
        raise ValueError('Expected one 24-byte record')
    value = int.from_bytes(record, 'little')
    if value & 1 or value >> 186 != 63:
        raise ValueError('Fixed frame bits mismatch')
    if polynomial_remainder((value >> 1) & ((1 << 185) - 1), 0x111) != 0xff:
        raise ValueError('Empirical frame check mismatch')
    return (value >> 1) & MASK


def serial_to_sof_data(stream: bytes) -> bytes:
    """Remove serial overhead and reverse all 37,524 data bits as one vector."""
    if not isinstance(stream, bytes) or len(stream) != 5120:
        raise ValueError('Expected one complete 5120-byte stream')
    serial = 0
    for i in range(RECORDS):
        serial |= decode_record(stream[31+24*i:55+24*i]) << (DATA_BITS*i)
    return reverse_bits(serial, TOTAL_BITS).to_bytes(PACKED_BYTES, 'little')


def sof_data_to_serial(packed: bytes, prefix: bytes, suffix: bytes) -> bytes:
    """Reframe data. The original envelope must be provided, never invented."""
    if not isinstance(packed, bytes) or len(packed) != PACKED_BYTES \
            or int.from_bytes(packed, 'little') >> TOTAL_BITS:
        raise ValueError('Invalid SOF data vector')
    if not isinstance(prefix, bytes) or len(prefix) != 31 or not isinstance(suffix, bytes) or len(suffix) != 1:
        raise ValueError('Explicit 31-byte prefix and 1-byte suffix required')
    serial = reverse_bits(int.from_bytes(packed, 'little'), TOTAL_BITS)
    return prefix + b''.join(encode_record((serial >> (DATA_BITS*i)) & MASK)
                              for i in range(RECORDS)) + suffix


def stream_metadata(stream: bytes) -> dict:
    packed = serial_to_sof_data(stream)
    return {'serial_bytes': len(stream), 'records': RECORDS, 'data_bits_per_record': DATA_BITS,
            'check_bits_per_record': 8, 'fixed_bits_per_record': 7,
            'total_data_bits': TOTAL_BITS, 'packed_data_bytes': len(packed),
            'packed_data_sha256': hashlib.sha256(packed).hexdigest(),
            'serial_sha256': hashlib.sha256(stream).hexdigest(),
            'exact_roundtrip': sof_data_to_serial(packed, stream[:31], stream[-1:]) == stream,
            'envelope_interpreted': False, 'logic_netlist_recovered': False}


def analyze_pair(name: str, sof_rcs: bytes, ttf_rcs: bytes) -> dict:
    if name not in REFERENCES:
        raise ValueError('Unknown pinned reference')
    for kind, data in (('sof', sof_rcs), ('ttf', ttf_rcs)):
        if not isinstance(data, bytes) or len(data) > MAX_FILE or git_blob_sha1(data) != REFERENCES[name][kind][1]:
            raise ValueError('Pinned ' + kind + ' blob mismatch')
    sof_revision, sof = rcs_binary_head(sof_rcs)
    ttf_revision, ttf = rcs_binary_head(ttf_rcs)
    stream = parse_ttf(ttf.decode('ascii'))
    parsed = parse_sof(sof)
    converted = serial_to_sof_data(stream)
    if converted != parsed['packed']:
        raise ValueError('SOF and TTF data do not match the locked bit mapping')
    if sof_data_to_serial(parsed['packed'], stream[:31], stream[-1:]) != stream:
        raise ValueError('SOF to TTF reconstruction differs')
    return {'name': name, 'source_commit': COMMIT,
            'source_blobs': {k: {'path': DIRECTORY + v[0], 'sha1': v[1]}
                             for k, v in REFERENCES[name].items()},
            'sof_revision': sof_revision, 'ttf_revision': ttf_revision,
            'sof_sha256': hashlib.sha256(sof).hexdigest(), 'sof_bytes': len(sof),
            'device_from_sof': parsed['device'], 'packet_sizes': parsed['packet_sizes'],
            'container_checksum_verified': parsed['container_checksum_verified'],
            'exact_sof_ttf_data_match': True, **stream_metadata(stream)}


def fetch_pairs() -> list[dict]:
    results = []
    for name, sources in REFERENCES.items():
        files = {}
        for kind, (path, expected) in sources.items():
            url = f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{DIRECTORY}{path}'
            with urllib.request.urlopen(url, timeout=20) as response:
                data = response.read(MAX_FILE + 1)
            if len(data) > MAX_FILE or git_blob_sha1(data) != expected:
                raise ValueError('Fetched reference does not match pinned blob')
            files[kind] = data
        results.append(analyze_pair(name, files['sof'], files['ttf']))
    return results


def hotdo_metadata(image: bytes) -> dict:
    if not isinstance(image, bytes) or len(image) != 0x200000 or hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Original hotdo CPU image identity mismatch')
    stream = image[UPLOAD_BEGIN:UPLOAD_END]
    if hashlib.sha256(stream).hexdigest() != UPLOAD_SHA256:
        raise ValueError('Original hotdo upload identity mismatch')
    return {'image_sha256': HOTDO_SHA256, **stream_metadata(stream),
            'scope': 'Same measured codec applied to authenticated upload; no original Sega SOF exists in this input.'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-pinned', action='store_true')
    parser.add_argument('--image', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        if not args.fetch_pinned and args.image is None:
            raise ValueError('Select explicit reference fetch and/or private original image')
        if args.image is not None and args.output.resolve() == args.image.resolve():
            raise ValueError('Output must not overwrite input image')
        report = {'schema_version': 1, 'evidence_level': 'empirical_SOF_serial_data_mapping',
                  'physical_receiver_verified': False, 'logic_netlist_recovered': False,
                  'runtime_changed': False, 'model2c_complete': False}
        if args.fetch_pinned:
            report['reference_pairs'] = fetch_pairs()
        if args.image:
            if args.image.stat().st_size != 0x200000:
                raise ValueError('Expected mapped 2-MiB CPU image')
            report['hotdo'] = hotdo_metadata(args.image.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Wrote configuration mapping metadata, not an FPGA logic implementation.')
    except (ValueError, OSError, UnicodeError, struct.error) as error:
        parser.exit(2, f'SOF mapping failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
