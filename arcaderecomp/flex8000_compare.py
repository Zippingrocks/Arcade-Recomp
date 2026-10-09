"""Metadata-only comparison against a pinned, independent EPF8282 compiler build.

This is a format comparison, NOT a recovered FPGA netlist or proof that a
particular Sega PCB receives the stream. Neither reference design bytes nor
Sega upload bytes are written to the output. Network access is explicit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from .serial_contract import HOTDO_SHA256, UPLOAD_BEGIN, UPLOAD_END
from .upload_framing import UPLOAD_SHA256, polynomial_remainder

COMMIT = '6a0d68153d731518f07e98762f82d25e042838a8'
REPOSITORY = 'fayaw/spearlegacyLLRF'
DIRECTORY = 'spear-rf-code-legacy/rfApp/ksc_v152/PLDs/bid/'
SOURCES = {
    'ttf': ('testmux.ttf,v', 'b497a84a8288d94771b3439c36e667cd93cd5b51'),
    'fit': ('testmux.fit,v', '12bd9dc6ce31fb3c70bbedb1a6ce9322a40cb10e'),
}
MAX_FILE = 2 * 1024 * 1024


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


def rcs_head_text(data: bytes) -> tuple[str, str]:
    """Read the full head snapshot, not numbers in RCS headers or older deltas."""
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_FILE:
        raise ValueError('RCS file size outside 1..2 MiB')
    text = data.decode('ascii')
    head = re.match(r'head\s+(\d+(?:\.\d+)+)\s*;', text)
    if not head:
        raise ValueError('Missing RCS head revision')
    revision = head[1]
    # A full head snapshot lives after desc, in a revision/log/text entry.
    pattern = r'(?m)^' + re.escape(revision) + r'[ \t]*\r?\nlog[ \t]*\r?\n'
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError('Missing or ambiguous RCS head text entry')

    def string_at(pos: int) -> tuple[str, int]:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text) or text[pos] != '@':
            raise ValueError('Missing RCS quoted string')
        pos += 1
        out = []
        while pos < len(text):
            if text[pos] != '@':
                out.append(text[pos]); pos += 1
            elif pos + 1 < len(text) and text[pos + 1] == '@':
                out.append('@'); pos += 2
            else:
                return ''.join(out), pos + 1
        raise ValueError('Unterminated RCS quoted string')

    _, pos = string_at(matches[0].end())
    keyword = re.match(r'\s*text\s*', text[pos:])
    if not keyword:
        raise ValueError('RCS text keyword missing after log')
    contents, _ = string_at(pos + keyword.end())
    return revision, contents


def parse_ttf(text: str) -> bytes:
    """Altera tabular text decimal bytes; no revision numbers/hex/delta syntax."""
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_FILE:
        raise ValueError('TTF text size outside 1..2 MiB')
    parts = text.strip().split(',')
    if not parts[-1].strip():
        parts.pop()
    if not parts or len(parts) > (1 << 18):
        raise ValueError('Empty or oversized TTF payload')
    values = []
    for part in parts:
        token = part.strip()
        if not re.fullmatch(r'[0-9]{1,3}', token) or int(token) > 255:
            raise ValueError('TTF requires comma-separated decimal bytes 0..255')
        values.append(int(token))
    return bytes(values)


def framing_profile(payload: bytes) -> dict:
    """Test the PREEXISTING HOTD model on a whole independently sourced file.

    No fitting to reference records: 31+212*24+1, fixed low/high bits and
    GF(2) divisor/residue are locked before reading this reference stream.
    """
    if not isinstance(payload, bytes) or len(payload) != 5120:
        raise ValueError('Expected 5120-byte candidate stream')
    records = [payload[31 + i*24:31 + (i+1)*24] for i in range(212)]
    fixed_bad, relation_bad = [], []
    mask = (1 << 185) - 1
    for i, record in enumerate(records):
        value = int.from_bytes(record, 'little')
        if value & 1 or value >> 186 != 63:
            fixed_bad.append(i)
        if polynomial_remainder((value >> 1) & mask, 0x111) != 0xff:
            relation_bad.append(i)
    return {
        'payload_bytes': 5120, 'payload_sha256': hashlib.sha256(payload).hexdigest(),
        'prefix_bytes': 31, 'prefix_sha256': hashlib.sha256(payload[:31]).hexdigest(),
        'record_bytes': 24, 'record_count': 212, 'distinct_records': len(set(records)),
        'suffix_bytes': 1, 'suffix_sha256': hashlib.sha256(payload[-1:]).hexdigest(),
        'lsb_fixed_bits': 1, 'lsb_value': 0, 'msb_fixed_bits': 6, 'msb_value': 63,
        'middle_bits': 185, 'empirical_polynomial': '0x111', 'empirical_residue': '0xff',
        'fixed_bit_failure_indices': fixed_bad, 'relation_failure_indices': relation_bad,
        'matches_preexisting_model': not fixed_bad and not relation_bad,
    }


def analyze_reference(ttf_rcs: bytes, fit_rcs: bytes, *, require_pinned: bool = True) -> dict:
    if type(require_pinned) is not bool:
        raise ValueError('Invalid identity-check setting')
    if require_pinned:
        for name, data in (('ttf', ttf_rcs), ('fit', fit_rcs)):
            if git_blob_sha1(data) != SOURCES[name][1]:
                raise ValueError('Reference ' + name + ' blob identity mismatch')
    revision, ttf = rcs_head_text(ttf_rcs)
    fit_revision, fit = rcs_head_text(fit_rcs)
    devices = set(re.findall(r'\bDEVICE\s*=\s*"?([A-Za-z0-9-]+)"?\s*;', fit))
    if devices != {'EPF8282ALC84-2'} or not re.search(r'CHIP\s+"testmux"', fit):
        raise ValueError('Reference fit does not unambiguously identify testmux/EPF8282ALC84-2')
    profile = framing_profile(parse_ttf(ttf))
    return {
        'schema_version': 1, 'reference_repository': REPOSITORY, 'reference_commit': COMMIT,
        'source_blobs': {name: {'path': DIRECTORY + SOURCES[name][0],
                               'git_blob_sha1': git_blob_sha1(data),
                               'sha256': hashlib.sha256(data).hexdigest()}
                         for name, data in (('ttf', ttf_rcs), ('fit', fit_rcs))},
        'pinned_blobs_verified': require_pinned,
        'reference_device_from_fit': 'EPF8282ALC84-2',
        'ttf_head_revision': revision, 'fit_head_revision': fit_revision,
        'reference_profile': profile,
        'evidence_boundary': 'Independent compiler-output format evidence, not FPGA logic recovery or physical wiring proof.',
    }


def compare_hotdo(reference: dict, image: bytes) -> dict:
    if not isinstance(image, bytes) or len(image) != 0x200000 or hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Original HOTD1 CPU image identity mismatch')
    if reference.get('pinned_blobs_verified') is not True:
        raise ValueError('Only an identity-verified reference may support a game comparison')
    payload = image[UPLOAD_BEGIN:UPLOAD_END]
    if hashlib.sha256(payload).hexdigest() != UPLOAD_SHA256:
        raise ValueError('Original HOTD1 upload identity mismatch')
    profile = framing_profile(payload)
    other = reference['reference_profile']
    return {**reference, 'hotdo_image_sha256': HOTDO_SHA256,
            'hotdo_profile': profile,
            'comparison': {'both_pass_locked_record_model': profile['matches_preexisting_model'] and other['matches_preexisting_model'],
                           'payloads_identical': profile['payload_sha256'] == other['payload_sha256'],
                           'prefixes_identical': profile['prefix_sha256'] == other['prefix_sha256'],
                           'suffixes_identical': profile['suffix_sha256'] == other['suffix_sha256']},
            'physical_recipient_proven': False, 'fpga_logic_recovered': False,
            'runtime_changed': False, 'model2c_complete': False}


def fetch_reference() -> tuple[bytes, bytes]:
    results = []
    for name in ('ttf', 'fit'):
        path, expected = SOURCES[name]
        url = f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{DIRECTORY}{path}'
        with urllib.request.urlopen(url, timeout=20) as response:
            data = response.read(MAX_FILE + 1)
        if len(data) > MAX_FILE or git_blob_sha1(data) != expected:
            raise ValueError('Downloaded reference identity/size mismatch')
        results.append(data)
    return results[0], results[1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch-pinned', action='store_true', help='Explicitly fetch only two pinned non-Sega reference files')
    p.add_argument('--ttf-rcs', type=Path)
    p.add_argument('--fit-rcs', type=Path)
    p.add_argument('--image', type=Path, help='Optional PRIVATE hash-verified original hotdo CPU image')
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    try:
        if args.fetch_pinned:
            if args.ttf_rcs or args.fit_rcs:
                raise ValueError('Choose fetch OR local reference inputs')
            ttf, fit = fetch_reference()
        else:
            if not args.ttf_rcs or not args.fit_rcs:
                raise ValueError('Provide both reference files or explicit --fetch-pinned')
            if any(path.stat().st_size > MAX_FILE for path in (args.ttf_rcs, args.fit_rcs)):
                raise ValueError('Reference file exceeds 2 MiB')
            ttf, fit = args.ttf_rcs.read_bytes(), args.fit_rcs.read_bytes()
        inputs = [x.resolve() for x in (args.ttf_rcs, args.fit_rcs, args.image) if x]
        if args.output.resolve() in inputs:
            raise ValueError('Output must not overwrite an input')
        report = analyze_reference(ttf, fit)
        if args.image:
            if args.image.stat().st_size != 0x200000:
                raise ValueError('Expected 2-MiB CPU image')
            report = compare_hotdo(report, args.image.read_bytes())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        if not report['reference_profile']['matches_preexisting_model']:
            raise ValueError('Reference failed preexisting model; metadata saved as a negative result')
        print('Pinned reference passes locked framing model; metadata only, no FPGA/device-completion claim.')
    except (ValueError, OSError, UnicodeError) as error:
        p.exit(2, f'Configuration-reference audit failed: {error}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
