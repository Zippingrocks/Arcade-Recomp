"""Pinned non-A EPF8282 format holdouts; metadata only, not circuit recovery.

Reuses the existing codec and unchanged tiled-LUT candidate. No fitted
equations are available for these designs, so class observations cannot
be promoted to a successful held-out logic validation.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from .flex8000_compare import (
    COMMIT, MAX_FILE, REPOSITORY, framing_profile, git_blob_sha1, parse_ttf)
from .flex8000_fit_slots import build_stamp, parse_fit_slots
from .flex8000_lut_probe import npn_orbit, truth_table
from .flex8000_lut_tiles import CANDIDATE, candidate_tables
from .flex8000_sram import (
    TOTAL_BITS, parse_sof, rcs_binary_head, serial_to_sof_data,
    sof_data_to_serial, stream_metadata)

DIRECTORY = 'spear-rf-code-legacy/rfApp/ksc_v152/PLDs/sla/'
DEVICE = 'EPF8282LC84'
PINNED = {
    'DIV_10': {
        'SOF': 'a4b2eac2c87580a9a4e40f748aa9b7f5fb42ddfa',
        'TTF': '9558faece11a93b8d67788df0fa63c340d6a2b12',
        'FIT': '8966e1214219d26ba1807157d184889fc715cb63',
    },
    'RCV_TRIG': {
        'SOF': '6be86ddc1161fd104618f1cb5587b9a363ea2c5e',
        'TTF': 'c128f6d2badf7b3d00894226d2a752ce19b83eaf',
        'FIT': '7583e3b60dcaad1acd1889fb3992974d004d77fa',
    },
}


def fit_placement_metadata(text: str, design: str) -> dict:
    """Exact target/design/unique placement checks, not a netlist parser."""
    # Reuse strict CHIP/INTERNAL_INFO, target and input declaration guards.
    slots = parse_fit_slots(text, DEVICE)
    clean = re.sub(r'--[^\r\n]*', '', text)
    chips = re.findall(r'\b(?:CHIP|INTERNAL_INFO)\s+"([^"\r\n]+)"', clean)
    if chips != [design.lower(), design.lower()]:
        raise ValueError('Unexpected fitted design identity')
    # Restrict LOCATION assignments to the CHIP section, before INTERNAL_INFO.
    chip = clean.split('INTERNAL_INFO', 1)[0]
    cells, nodes = set(), set()
    for line in chip.splitlines():
        if 'LOCATION' not in line:
            continue
        match = re.fullmatch(
            r'\s*"([^"\r\n]+)"\s*:\s*LOCATION\s*=\s*'
            r'(LC[1-8]_[AB](?:[1-9]|1[0-3]))\s*;\s*', line)
        if not match:
            raise ValueError('Malformed fitted location')
        node, cell = match.groups()
        if node in nodes or cell in cells:
            raise ValueError('Duplicate fitted node or cell')
        nodes.add(node)
        cells.add(cell)
    if not cells:
        raise ValueError('No fitted cells declared')
    if 'LOCATION' in clean.split('INTERNAL_INFO', 1)[1]:
        raise ValueError('Location assignment outside CHIP section')
    version, compiled = build_stamp(text)
    return {'compiler_version_from_fit': version, 'compiled_from_fit': compiled,
            'placed_cell_count': len(cells),
            'b1_placed_cells': sorted(int(c[2]) for c in cells if c.endswith('_B1')),
            'ordered_input_slot_rows': len(slots['slots']),
            'fitted_equations_available': False,
            'sof_fit_same_build_proven': False}


@lru_cache(maxsize=1)
def observed_classes() -> dict[str, frozenset[int]]:
    # Mathematically defined classes, not fitted circuit predictions.
    return {
        'constant': npn_orbit(0),
        'buffer_or_inverter': npn_orbit(truth_table(lambda a, b, c, d: a)),
        'three_input_and_npn': npn_orbit(truth_table(lambda a, b, c, d: a & b & c)),
    }


def candidate_observations(packed: bytes, placed: list[int]) -> dict:
    """Inspect fixed B1 coordinates without searching, fitting, or exporting bits."""
    if not isinstance(placed, list) or any(type(c) is not int or not 1 <= c <= 8 for c in placed) \
            or len(set(placed)) != len(placed):
        raise ValueError('Invalid B1 placed-cell list')
    tables = candidate_tables(packed, CANDIDATE)
    cells = []
    for number, table in enumerate(tables, 1):
        labels = [name for name, orbit in observed_classes().items() if table in orbit]
        cells.append({'cell': number, 'fit_places_cell': number in placed,
                      'class': labels[0] if labels else 'unclassified',
                      'essential_input_count': sum(
                          any(((table >> n) & 1) != ((table >> (n ^ (1 << bit))) & 1)
                              for n in range(16)) for bit in range(4))})
    return {'candidate': dict(CANDIDATE), 'candidate_refitted': False,
            'cells': cells, 'held_out_logic_validation': 'NOT_ESTABLISHED',
            'reason': 'No matched fitted equations; non-A to A circuit-layout transfer unproven.'}


def analyze_reference(name: str, files: dict[str, bytes]) -> dict:
    if name not in PINNED or set(files) != set(PINNED[name]):
        raise ValueError('Unknown or incomplete pinned reference')
    bodies, sources, revisions = {}, {}, {}
    for kind, expected in PINNED[name].items():
        raw = files[kind]
        if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_FILE \
                or git_blob_sha1(raw) != expected:
            raise ValueError('Pinned reference identity/size mismatch')
        revisions[kind], bodies[kind] = rcs_binary_head(raw)
        path = f'{DIRECTORY}{name}.{kind},v'
        sources[kind] = {'path': path, 'git_blob_sha1': expected,
                         'sha256': hashlib.sha256(raw).hexdigest(),
                         'url': f'https://github.com/{REPOSITORY}/blob/{COMMIT}/{path}'}
    parsed = parse_sof(bodies['SOF'], allow_legacy_epf8282=True)
    if parsed['device'] != DEVICE:
        raise ValueError('Reference is not the exact legacy device')
    fit = fit_placement_metadata(bodies['FIT'].decode('ascii'), name)
    stream = parse_ttf(bodies['TTF'].decode('ascii'))
    profile = framing_profile(stream)
    converted = serial_to_sof_data(stream)
    if converted != parsed['packed']:
        raise ValueError('SOF/TTF differ under the locked bit mapping')
    if sof_data_to_serial(parsed['packed'], stream[:31], stream[-1:]) != stream:
        raise ValueError('SOF/TTF roundtrip differs')
    return {'name': name, 'source_blobs': sources, 'head_revisions': revisions,
            'device_from_sof_and_fit': DEVICE,
            'device_matches_original_candidate_reference': False,
            'packet_sizes': parsed['packet_sizes'],
            'container_checksum_verified': parsed['container_checksum_verified'],
            'exact_sof_ttf_data_match': True, 'matched_data_bits': TOTAL_BITS,
            'framing_profile': profile, 'stream_metadata': stream_metadata(stream),
            'fit_metadata': fit,
            'fixed_candidate_observations': candidate_observations(converted, fit['b1_placed_cells'])}


def fetch_audit() -> dict:
    references = []
    for name in PINNED:
        files = {}
        for kind, expected in PINNED[name].items():
            url = f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{DIRECTORY}{name}.{kind},v'
            with urllib.request.urlopen(url, timeout=20) as response:
                raw = response.read(MAX_FILE + 1)
            if len(raw) > MAX_FILE or git_blob_sha1(raw) != expected:
                raise ValueError('Fetched reference identity/size mismatch')
            files[kind] = raw
        references.append(analyze_reference(name, files))
    return {'schema_version': 1, 'reference_repository': REPOSITORY,
            'reference_commit': COMMIT, 'references': references,
            'proof_level': 'non-Sega compiler-output format comparison',
            'held_out_logic_validation': 'NOT_ESTABLISHED',
            'physical_device_verified': False, 'netlist_recovered': False,
            'runtime_changed': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-reference', action='store_true', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = fetch_audit()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(2, f'Legacy EPF8282 audit failed: {error}\n')
    print('Format holdouts checked; fixed-coordinate observations are not circuit validation.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
