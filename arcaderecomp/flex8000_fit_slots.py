"""Test fixed LUT coordinates against ordered, archived fitter input slots.

The ordered LORAX2 tokens are compiler metadata, not decoded switch bits or
physical pin measurements. No source equations/configuration are exported.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import urllib.request

from .flex8000_compare import COMMIT, DIRECTORY, MAX_FILE, REPOSITORY, git_blob_sha1
from .flex8000_fit_constraints import (
    NAME, NODE, names, parse_expression, parse_fitted_report, transform)
from .flex8000_lut_tiles import CANDIDATE, candidate_tables
from .flex8000_sram import parse_sof, rcs_binary_head

PINNED = {
    'testmux.sof,v': '4bd945df501d848d9fc4fd512945336ec7c24fca',
    'testmux.rpt,v': '88deb079d565b038b1bc4a71e015fd324dddd3ab',
    'testmux.fit,v': '12bd9dc6ce31fb3c70bbedb1a6ce9322a40cb10e',
}
# Freeze the earlier convention. This pass may NOT change it to force a match.
ADDRESS_XOR, OUTPUT_XOR = 15, 0
PERMUTATIONS = tuple(itertools.permutations(range(4)))


def build_stamp(text: str) -> tuple[str, str]:
    if not isinstance(text, str) or not 0 < len(text) <= MAX_FILE:
        raise ValueError('Invalid compiler text size')
    def one(pattern, label):
        found = re.findall(pattern, text, re.M)
        if len(found) != 1:
            raise ValueError(f'Missing or ambiguous {label}')
        return found[0].strip()
    version = one(r'^\s*(?:--\s*)?Version\s+([^\r\n]+)', 'compiler version')
    compiled = one(r'^\s*(?:--\s*)?Compiled:\s*([^\r\n]+)', 'build timestamp')
    return version, compiled


def parse_fit_slots(text: str, device: str, bank: str = 'B1') -> dict:
    """Read only explicit assignments. X stays unassigned, never a constant."""
    build_stamp(text)
    if not re.fullmatch(r'[AB](?:[1-9]|1[0-3])', bank):
        raise ValueError('Invalid logic-array bank')
    clean = re.sub(r'--[^\r\n]*', '', text)
    devices = re.findall(r'\bDEVICE\s*=\s*"?([A-Za-z0-9-]+)"?\s*;', clean)
    if devices != [device, device]:
        raise ValueError('Fit CHIP/INTERNAL_INFO targets differ or are absent')
    blocks = re.findall(r'\b(CHIP|INTERNAL_INFO)\s+"([^"\r\n]+)"\s*BEGIN(.*?)END\s*;', clean, re.S)
    if len(blocks) != 2 or [b[0] for b in blocks] != ['CHIP', 'INTERNAL_INFO'] or blocks[0][1] != blocks[1][1]:
        raise ValueError('Expected one matching CHIP/INTERNAL_INFO pair')
    pins = {}
    for name, pin in re.findall(r'"(' + NAME + r')"\s*:\s*INPUT_PIN\s*=\s*(\d+)\s*;', blocks[0][2]):
        number = int(pin)
        if not 1 <= number <= 100 or number in pins or name in pins.values():
            raise ValueError('Ambiguous input-pin declaration')
        pins[number] = name
    slots = {}
    for line in blocks[1][2].splitlines():
        if 'LORAX2' not in line:
            continue
        match = re.fullmatch(r'\s*(LC[1-8]_[AB](?:[1-9]|1[0-3]))\s*:\s*LORAX2\s*=\s*"([^"\r\n]*)"\s*;\s*', line)
        if not match:
            raise ValueError('Malformed ordered fitter-input row')
        cell, payload = match.groups()
        if cell in slots:
            raise ValueError('Duplicate fitter-input row')
        tokens = [part.strip() for part in payload.split(',')]
        if len(tokens) != 4:
            raise ValueError('Expected exactly four ordered input slots')
        resolved = []
        for token in tokens:
            if token == 'X':
                resolved.append(None)
            elif re.fullmatch(r'LC[1-8]_[AB](?:[1-9]|1[0-3])', token):
                resolved.append('_' + token)
            else:
                external = re.fullmatch(r'OD\d+P(\d+)', token)
                if not external or int(external[1]) not in pins:
                    raise ValueError('Unknown fitter input token or undeclared pin')
                resolved.append(pins[int(external[1])])
        connected = [n for n in resolved if n is not None]
        if len(set(connected)) != len(connected):
            raise ValueError('Tied slots need a restricted-domain model, not this full-table test')
        slots[cell] = tuple(resolved)
    return {'slots': slots, 'input_pin_count': len(pins),
            'selected_slot_row_count': sum(c.endswith('_'+bank) for c in slots)}


def ordered_tables(report: str, fit: str, device: str, bank: str = 'B1') -> tuple[tuple[int, ...], dict]:
    """Express already normalized report functions in explicit fitter-slot order."""
    if build_stamp(report) != build_stamp(fit):
        raise ValueError('Report and fit have different compiler/build timestamps')
    parsed = parse_fitted_report(report, device, bank)
    layout = parse_fit_slots(fit, device, bank)
    # The existing strict parser validates duplicate definitions/aliases first.
    aliases = dict(re.findall(r'^\s*!('+NODE+r')\s*=\s*('+NODE+r'~NOT)\s*;', report, re.M))
    equations = dict(re.findall(r'^\s*(_EQ\d+)\s*=\s*([^;]+);', report, re.M))
    definitions = {node: (kind, args) for node, kind, args in re.findall(
        r'^\s*('+NODE+r'(?:~NOT)?)\s*=\s*(LCELL|DFF)\s*\(([^;]*)\)\s*;', report, re.M)}
    tables, metadata = [], []
    for cell in parsed['cells']:
        logical = f'_LC{cell["cell"]}_{bank}'
        kind, expression = definitions[aliases.get(logical, logical)]
        if kind == 'DFF':
            expression = expression.split(',')[0]  # Data only. No clock interpretation.
        expression = equations.get(expression.strip(), expression)
        inputs = sorted(names(parse_expression(expression)))
        if len(inputs) != cell['input_count']:
            raise ValueError('Report parser source-order disagreement')
        explicit = logical[1:] in layout['slots']
        slots = layout['slots'].get(logical[1:], (None,)*4)
        if not explicit and inputs:
            raise ValueError('A nonconstant cell has no ordered fitter-input row')
        if any(name not in slots for name in inputs):
            raise ValueError('Report source is absent from explicit fitter slots')
        positions = [slots.index(name) for name in inputs]
        table = 0
        for address in range(16):
            source_address = sum(((address >> slot) & 1) << j for j, slot in enumerate(positions))
            table |= ((cell['normalized_table'] >> source_address) & 1) << address
        tables.append(table)
        metadata.append({'cell': cell['cell'], 'explicit_slot_row': explicit,
                         'report_data_variables': len(inputs),
                         'connected_slot_count': sum(s is not None for s in slots),
                         'data_constant': not inputs})
    return tuple(tables), {'cells': metadata, 'build_stamp_matches': True,
                           'input_pin_count': layout['input_pin_count']}


def common_slot_permutations(raw, ordered) -> dict:
    if len(raw) != 8 or len(ordered) != 8:
        raise ValueError('Expected exactly eight cells')
    for table in (*raw, *ordered):
        if type(table) is not int or not 0 <= table <= 65535:
            raise ValueError('Invalid truth table')
    matches = []
    for permutation in PERMUTATIONS:
        if all(transform(table, permutation, ADDRESS_XOR, OUTPUT_XOR) == actual
               for table, actual in zip(ordered, raw)):
            matches.append(list(permutation))
    return {'address_xor': ADDRESS_XOR, 'output_xor': OUTPUT_XOR,
            'tested_shared_slot_orders': 24, 'shared_slot_order_count': len(matches),
            'shared_slot_orders': matches,
            'slot_order_meaning': 'Entry j is the candidate-address bit feeding compiler slot j before common XOR.',
            'physical_routing_verified': False}


def audit_pinned_inputs(sof_rcs: bytes, report_rcs: bytes, fit_rcs: bytes) -> dict:
    payloads = (sof_rcs, report_rcs, fit_rcs)
    for name, payload in zip(PINNED, payloads):
        if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_FILE or git_blob_sha1(payload) != PINNED[name]:
            raise ValueError('Pinned reference identity mismatch')
    sof = parse_sof(rcs_binary_head(sof_rcs)[1])
    report, fit = (rcs_binary_head(p)[1].decode('ascii') for p in payloads[1:])
    ordered, details = ordered_tables(report, fit, sof['device'])
    raw = candidate_tables(sof['packed'], CANDIDATE)
    return {'schema_version': 1, 'reference_commit': COMMIT, 'source_blobs': dict(PINNED),
            'candidate': CANDIDATE, 'reference_device': sof['device'],
            'configuration_sha256': hashlib.sha256(sof['packed']).hexdigest(),
            'ordered_fit_result': common_slot_permutations(raw, ordered),
            'fit_metadata': details, 'new_independent_design': False,
            'netlist_recovered': False, 'runtime_changed': False,
            'scope': 'Fixed coordinates/polarities plus one shared input order; same archival design, additional fitter file.'}


def fetch_audit() -> dict:
    files = []
    for name in PINNED:
        url = f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{DIRECTORY}{name}'
        with urllib.request.urlopen(url, timeout=20) as response:
            data = response.read(MAX_FILE+1)
        if len(data) > MAX_FILE:
            raise ValueError('Reference exceeds size bound')
        files.append(data)
    return audit_pinned_inputs(*files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-reference', action='store_true', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = fetch_audit()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(2, f'Ordered fitter audit failed: {error}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
