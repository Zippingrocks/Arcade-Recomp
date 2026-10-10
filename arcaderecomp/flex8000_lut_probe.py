"""Bounded LUT-layout hypotheses and controlled-build bit correlations.

This module does NOT decode HOTD1 circuitry. A truth-table correlation is
not routing, a flip-flop model, or physical-device validation. HDL files
emitted by --plan are experiments to compile, not precompiled evidence.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import urllib.request
import json
from pathlib import Path

from .flex8000_sram import TOTAL_BITS, parse_sof, rcs_binary_head
from .flex8000_compare import COMMIT, DIRECTORY, REPOSITORY, MAX_FILE, git_blob_sha1


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} must be an integer in {low}..{high}')
    return value


def vector(packed: bytes, width: int) -> int:
    integer(width, 16, TOTAL_BITS, 'vector width')
    if not isinstance(packed, bytes) or len(packed) != (width+7)//8:
        raise ValueError('Wrong configuration vector size')
    result = int.from_bytes(packed, 'little')
    if result >> width:
        raise ValueError('Nonzero padding outside declared configuration bits')
    return result


def truth_table(function):
    return sum(int(bool(function(*[(n >> bit) & 1 for bit in range(4)]))) << n
               for n in range(16))


def npn_orbit(table: int) -> frozenset[int]:
    """Input negations/permutations and output negation; NOT arbitrary LUT wiring."""
    integer(table, 0, 65535, 'four-input truth table')
    values = set()
    for order in itertools.permutations(range(4)):
        for negate in range(16):
            value = 0
            for n in range(16):
                address = sum((((n >> order[j]) & 1) ^ ((negate >> j) & 1)) << j
                              for j in range(4))
                value |= ((table >> address) & 1) << n
            values.update((value, value ^ 65535))
    return frozenset(values)


# Abstract truth classes calculated from the eight-cell fitted testmux report.
# Association with that SOF is archival, not a controlled rebuild guarantee.
TABLES = (
    truth_table(lambda a,b,c,d: not a and d and (not b or not c)),
    truth_table(lambda a,b,c,d: a and b and c and d),
    truth_table(lambda a,b,c,d: a or b),
    truth_table(lambda a,b,c,d: a),
    65535,
)
DEFAULT_STRIDES = (1,2,4,8,16,26,104,106,177,208,212)


def scan_regular_layout(packed: bytes, width=TOTAL_BITS,
                        bit_strides=DEFAULT_STRIDES, max_cell_stride=512) -> dict:
    data = vector(packed, width)
    integer(max_cell_stride, 1, 512, 'maximum cell stride')
    if not 1 <= len(bit_strides) <= 16 or len(set(bit_strides)) != len(bit_strides):
        raise ValueError('Expected 1..16 distinct bit strides')
    for stride in bit_strides:
        integer(stride, 1, 212, 'LUT bit stride')
    classes = tuple(npn_orbit(table) for table in TABLES)
    bits = [(data >> bit) & 1 for bit in range(width)]
    results = []
    for stride in bit_strides:
        positions = [set() for _ in classes]
        for start in range(max(0, width - 15*stride)):
            value = sum(bits[start+j*stride] << j for j in range(16))
            for k, group in enumerate(classes):
                if value in group:
                    positions[k].add(start)
        four, eight, examples = 0, 0, []
        for start in sorted(positions[0]):
            for step in range(-max_cell_stride, max_cell_stride+1):
                if not step or start+step not in positions[1] or start+2*step not in positions[2] \
                        or start+6*step not in positions[2]:
                    continue
                four += 1
                if any(start+n*step not in positions[3] for n in (3,4,7)) \
                        or start+5*step not in positions[4]:
                    continue
                eight += 1
                if len(examples) < 32:
                    examples.append({'first_lut_bit': start, 'cell_stride': step})
        results.append({'lut_bit_stride': stride, 'class_window_counts': [len(p) for p in positions],
                        'nontrivial_four_cell_candidates': four,
                        'full_eight_cell_candidates': eight, 'examples': examples})
    return {'vector_bits': width, 'npn_class_sizes': [len(g) for g in classes],
            'cell_strides_inclusive': [-max_cell_stride, max_cell_stride], 'results': results,
            'scope': 'Only regular bit spacing and a uniform signed cell stride; not all possible encodings.',
            'logic_decoded': False, 'physical_device_verified': False}


HOLDOUTS = (0x6996, 0xE880, 0xB249, 0x5A69, 0x17E8, 0xC53A)


def probe_plan() -> dict:
    """16 single-minterm training designs, an exact repeat, and six holdouts."""
    cases = [{'name': f'minterm_{i:02d}', 'role': 'train', 'truth': 1 << i} for i in range(16)]
    cases += [{'name': 'repeat_00', 'role': 'repeat', 'truth': 1}]
    cases += [{'name': f'holdout_{i:02d}', 'role': 'holdout', 'truth': t}
              for i,t in enumerate(HOLDOUTS)]
    return {'schema_version': 1, 'target': 'EPF8282ALC84-2', 'truth_address': 'a[0] is least-significant',
            'cases': cases, 'compiled': False, 'placement_or_routing_guaranteed': False,
            'requirements': ['Same compiler and settings; fixed pins, physical LC and input ordering.',
                             'Check fitted reports and routing, not just source filenames.',
                             'An exact repeated build and withheld truth functions must pass.',
                             'Compiler may optimize/reorder logic; generated source does not prevent that.']}


def ahdl(table: int) -> str:
    integer(table, 0, 65535, 'truth table')
    terms = []
    for n in range(16):
        if table & (1 << n):
            terms.append('(' + ' & '.join(('' if n & (1 << j) else '!') + f'a[{j}]'
                                          for j in range(4)) + ')')
    expression = ' #\n        '.join(terms) if terms else 'GND'
    return ('% Original test source; NOT compiled or proven fit-preserving. %\n'
            'SUBDESIGN lut_probe\n(\n    a[3..0] : INPUT;\n    q : OUTPUT;\n)\n'
            'BEGIN\n    q = '+expression+';\nEND;\n')


def correlate(training: list[bytes], repeat: bytes,
              heldouts: list[tuple[int, bytes]], width=TOTAL_BITS) -> dict:
    """Require all 16 minterms and heldouts; keep duplicate-bit ambiguities.

    Same configuration across repeat builds is necessary, NOT sufficient
    proof of stable routing/input ordering. No hardware truth is assigned.
    """
    if len(training) != 16 or not 4 <= len(heldouts) <= 32:
        raise ValueError('Need sixteen minterms and 4..32 held-out truth functions')
    values = [vector(p, width) for p in training]
    if vector(repeat, width) != values[0]:
        raise ValueError('Repeated baseline build differs; placement/settings/data are not controlled')
    seen, held = set(), []
    for truth, packed in heldouts:
        integer(truth, 0, 65535, 'held-out truth table')
        if truth in seen or truth in [1 << i for i in range(16)]:
            raise ValueError('Duplicated or training-reused holdout truth table')
        seen.add(truth)
        held.append((truth, vector(packed, width)))
    before = [[] for _ in range(16)]
    after = [[] for _ in range(16)]
    for position in range(width):
        signature = sum(((v >> position) & 1) << n for n,v in enumerate(values))
        for polarity in (0, 1):
            normalized = signature ^ (65535 if polarity else 0)
            if normalized == 0 or normalized & (normalized-1):
                continue
            truth_bit = normalized.bit_length()-1
            candidate = {'configuration_bit': position, 'inverted': bool(polarity)}
            before[truth_bit].append(candidate)
            if all(((v >> position) & 1) == (((t >> truth_bit) & 1) ^ polarity) for t,v in held):
                after[truth_bit].append(candidate)
    rows = []
    for bit,(b,a) in enumerate(zip(before,after)):
        rows.append({'truth_bit': bit, 'training_candidates': len(b), 'heldout_candidates': len(a),
                     'status': 'unique_in_corpus' if len(a)==1 else 'ambiguous' if a else 'not_identified',
                     'candidates': a[:32], 'candidates_truncated': len(a)>32})
    return {'schema_version': 1, 'evidence_level': 'configuration_bit_correlations_in_supplied_corpus',
            'training_designs': 16, 'repeat_matches': True, 'heldout_designs': len(held),
            'vector_bits': width, 'unique_truth_bits': sum(len(a)==1 for a in after), 'bits': rows,
            'physical_routing_verified': False, 'logic_netlist_recovered': False,
            'warning': 'Even unique correlations require controlled fitted-resource evidence; not a hardware implementation.'}


def read_corpus(manifest_path: Path) -> dict:
    """Read private identity-checked samples, shared by correlation analyzers."""
    if manifest_path.stat().st_size > 65536:
        raise ValueError('Manifest too large')
    def no_duplicates(pairs):
        obj = {}
        for k,v in pairs:
            if k in obj:
                raise ValueError('Duplicate manifest key')
            obj[k] = v
        return obj
    doc = json.loads(manifest_path.read_text('utf-8'), object_pairs_hook=no_duplicates)
    if not isinstance(doc,dict) or set(doc)!={'schema_version','cases'} or type(doc['schema_version']) is not int or doc['schema_version']!=1:
        raise ValueError('Expected schema version 1 and cases')
    if not isinstance(doc['cases'],list) or not 21 <= len(doc['cases']) <= 49:
        raise ValueError('Invalid case count')
    root = manifest_path.resolve().parent
    samples, identities, target = {}, [], None
    for item in doc['cases']:
        if not isinstance(item,dict) or set(item)!={'role','truth','sof','sha256'}:
            raise ValueError('Each case requires role, truth, sof and sha256')
        role,truth = item['role'], integer(item['truth'],0,65535,'truth')
        if role not in ('train','repeat','holdout') or (role,truth) in samples:
            raise ValueError('Invalid or duplicate case role/truth')
        if not isinstance(item['sof'],str):
            raise ValueError('SOF path must be relative text')
        path = (root/item['sof']).resolve()
        if Path(item['sof']).is_absolute() or not path.is_relative_to(root) or path.stat().st_size > 2_000_000:
            raise ValueError('SOF path outside corpus or oversized')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != item['sha256']:
            raise ValueError('SOF identity mismatch')
        parsed = parse_sof(raw)
        if target is not None and parsed['device'] != target:
            raise ValueError('Corpus mixes devices/packages')
        target = parsed['device']
        samples[role,truth] = parsed['packed']
        identities.append({'role':role,'truth':truth,'sof_sha256':digest})
    if set(t for r,t in samples if r=='train') != {1<<i for i in range(16)} \
            or [t for r,t in samples if r=='repeat'] != [1]:
        raise ValueError('Missing minterms or wrong repeated baseline')
    return {'training': [samples['train',1<<i] for i in range(16)],
            'repeat': samples['repeat',1],
            'heldouts': [(t,v) for (r,t),v in samples.items() if r=='holdout'],
            'device': target, 'identities': identities}


def load_corpus(manifest_path: Path) -> dict:
    corpus = read_corpus(manifest_path)
    result = correlate(corpus['training'], corpus['repeat'], corpus['heldouts'])
    result.update(device=corpus['device'], source_hashes=corpus['identities'],
                  compiler_executed_by_this_tool=False)
    return result


REFERENCE_FILES = {
    'testmux.sof,v': '4bd945df501d848d9fc4fd512945336ec7c24fca',
    'testmux.rpt,v': '88deb079d565b038b1bc4a71e015fd324dddd3ab',
}


def reference_layout() -> dict:
    """Explicit download of two pinned NON-SEGA files; export counts, not bytes."""
    files = {}
    for name, expected in REFERENCE_FILES.items():
        url = f'https://raw.githubusercontent.com/{REPOSITORY}/{COMMIT}/{DIRECTORY}{name}'
        with urllib.request.urlopen(url, timeout=20) as response:
            raw = response.read(MAX_FILE+1)
        if len(raw) > MAX_FILE or git_blob_sha1(raw) != expected:
            raise ValueError('Reference file identity mismatch')
        files[name] = rcs_binary_head(raw)[1]
    parsed = parse_sof(files['testmux.sof,v'])
    report = files['testmux.rpt,v'].decode('ascii')
    if 'Device: '+parsed['device'] not in report or 'Total logic cells required:                      8' not in report:
        raise ValueError('Fitted-report target/cell count mismatch')
    result = scan_regular_layout(parsed['packed'])
    result.update(source_commit=COMMIT, source_blobs=REFERENCE_FILES,
                  device=parsed['device'], sega_data_used=False,
                  report_association='Same archived basename and target, not a controlled recompile guarantee.')
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--fetch-reference',action='store_true',help='Explicit pinned non-Sega layout audit')
    g.add_argument('--plan',type=Path,help='Create ORIGINAL uncompiled AHDL probe sources')
    g.add_argument('--corpus',type=Path,help='Analyze existing private hash-pinned SOF corpus')
    p.add_argument('--output',type=Path)
    args = p.parse_args()
    try:
        if args.plan:
            if args.output is not None or args.plan.exists():
                raise ValueError('Plan path must be new; --output is only for --corpus')
            args.plan.mkdir(parents=True)
            plan = probe_plan()
            for case in plan['cases']:
                folder=args.plan/case['name']; folder.mkdir()
                (folder/'lut_probe.tdf').write_text(ahdl(case['truth']),encoding='ascii')
            (args.plan/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
            print('Created 23 uncompiled probes; no compiler, license, fit or bit mapping is claimed.')
        else:
            if args.output is None:
                raise ValueError('--output is required')
            if args.corpus and args.output.resolve().is_relative_to(args.corpus.resolve().parent):
                raise ValueError('Output must be outside the input corpus directory')
            result = reference_layout() if args.fetch_reference else load_corpus(args.corpus)
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2)+'\n')
            print('Wrote correlation metadata, not a recovered FPGA netlist.')
    except (OSError,ValueError,UnicodeError,KeyError,TypeError) as e:
        p.exit(2,f'LUT probe failed: {e}\n')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
