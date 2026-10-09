"""Metadata-only HOTD1 host-protocol experiment; never a device implementation.

Runs an isolated AOT routine with explicitly synthetic constant RX values.
No original serial initial-state, timing or endpoint reply is inferred. The
private upload bytes are compared in-process, hashed, and never exported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .i960_cpp import emit_cpp

HOTDO_SHA256 = 'da2315b0b044d279728c8689336da6de0fee5997cf006514a1a633bd0de2fc75'
ENTRY, UPLOAD_BEGIN, UPLOAD_END, UPLOAD_COMMAND = 0xa3750, 0xa3a00, 0xa4e00, 7
COUNTERS = ('steps', 'return_ip', 'tx1_count', 'tx2_count', 'rx1_count',
            'rx2_count', 'status_reads', 'upload_bytes')


def _integer(value: Any, minimum: int, maximum: int, name: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} is not an integer in {minimum}..{maximum}')
    return value


def parse_rows(text: str) -> list[dict]:
    """Bounded JSONL parser; a truncated/partial sweep never becomes evidence."""
    if len(text) > 2_000_000:
        raise ValueError('Native report exceeds size bound')
    lines = text.splitlines()
    if len(lines) != 256:
        raise ValueError('Each RX1 sweep must contain all 256 RX2 cases')
    result = []
    for line in lines:
        def unique(pairs):
            obj = {}
            for key, value in pairs:
                if key in obj:
                    raise ValueError(f'Duplicate JSON key: {key}')
                obj[key] = value
            return obj
        obj = json.loads(line, object_pairs_hook=unique)
        if not isinstance(obj, dict):
            raise ValueError('Expected a JSON object per native case')
        result.append(obj)
    return result


def mask_formula(values: list[int | None]) -> dict:
    """Recognize only exact byte-wise (input & mask) | bits over all 256 values."""
    if len(values) != 256:
        raise ValueError('A full byte domain is required')
    if all(v == values[0] for v in values):
        return {'kind': 'constant', 'value': values[0]}
    if any(v is None for v in values):
        return {'kind': 'not_a_mask_formula'}
    for v in values:
        _integer(v, 0, 255, 'output byte')
    fixed = int(values[0])
    mask = 0
    for bit in range(8):
        delta = int(values[1 << bit]) ^ fixed
        if delta == 1 << bit:
            mask |= delta
        elif delta:
            return {'kind': 'not_a_mask_formula'}
    if any(v != ((i & mask) | fixed) for i, v in enumerate(values)):
        return {'kind': 'not_a_mask_formula'}
    return {'kind': 'rx2_mask', 'and_mask': mask, 'or_bits': fixed}


def summarize_rows(rows: list[dict], rx1_samples: tuple[int, ...] = (0, 255)) -> dict:
    if not rx1_samples or len(set(rx1_samples)) != len(rx1_samples):
        raise ValueError('RX1 sample set must be nonempty and unique')
    if len(rows) != len(rx1_samples) * 256:
        raise ValueError('Incomplete or extra sweep cases')
    cases = {}
    for row in rows:
        if row.get('synthetic_inputs') is not True or row.get('upload_matches_rom') is not True:
            raise ValueError('Missing synthetic-input declaration or failed upload check')
        r1 = _integer(row.get('rx1'), 0, 255, 'RX1')
        r2 = _integer(row.get('rx2'), 0, 255, 'RX2')
        if r1 not in rx1_samples or (r1, r2) in cases:
            raise ValueError('Unexpected or duplicated input case')
        for key in COUNTERS:
            _integer(row.get(key), 0, 0xffffffff, key)
        controls = row.get('controls')
        if not isinstance(controls, list) or len(controls) > 128:
            raise ValueError('Invalid control sequence')
        for control in controls:
            if not isinstance(control, dict):
                raise ValueError('Invalid control record')
            _integer(control.get('command'), 0, 255, 'command')
            if control.get('new_data') is not None:
                _integer(control['new_data'], 0, 255, 'TX2 data')
            if set(control) != {'command', 'new_data'}:
                raise ValueError('Unexpected control fields')
        cases[r1, r2] = row
    if any((a, b) not in cases for a in rx1_samples for b in range(256)):
        raise ValueError('Missing sweep point')
    reference = cases[rx1_samples[0], 0]
    commands = [c['command'] for c in reference['controls']]
    if any([c['command'] for c in row['controls']] != commands for row in rows):
        raise ValueError('Control sequence depends on sampled input; cannot use fixed summary')
    counters = {}
    for key in COUNTERS:
        values = [row[key] for row in rows]
        counters[key] = {'min': min(values), 'max': max(values)}
    controls = []
    invariant = True
    for index, command in enumerate(commands):
        tables = [[cases[r1, r2]['controls'][index]['new_data'] for r2 in range(256)]
                  for r1 in rx1_samples]
        same = all(table == tables[0] for table in tables)
        invariant = invariant and same
        controls.append({'index': index, 'command': command,
                         'same_for_tested_rx1': same,
                         'data_by_rx1': {str(r1): mask_formula(table)
                                         for r1, table in zip(rx1_samples, tables)}})
    return {
        'evidence_level': 'isolated_native_routine_with_synthetic_inputs',
        'not_hardware_validation': True,
        'case_count': len(rows), 'rx1_samples': list(rx1_samples),
        'rx2_domain': [0, 255],
        'input_scope': 'Each run holds RX1 and RX2 constant; not all time-varying reply sequences.',
        'data_same_for_tested_rx1': invariant,
        'counter_ranges': counters,
        'controls': controls,
    }


def run_experiment(image_path: Path, compiler: str = 'c++') -> dict:
    if image_path.stat().st_size != 0x200000:
        raise ValueError('Expected original mapped 2-MiB i960 image')
    image = image_path.read_bytes()
    if hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Image does not match the original hotdo CPU baseline')
    cxx = shutil.which(compiler)
    if not cxx:
        raise ValueError(f'C++ compiler not found: {compiler}')
    root = Path(__file__).resolve().parents[1]
    source, report = emit_cpp(image, ENTRY, 4096)
    if report.unsupported or report.limit_reached:
        raise ValueError('Isolated native codegen is incomplete')
    with tempfile.TemporaryDirectory(prefix='arcaderecomp-private-') as directory:
        work = Path(directory)
        # Private ROM-derived source, automatically removed. Never export it.
        (work / 'hotd1_i960.cpp').write_text(source, encoding='utf-8')
        exe = work / 'contract_probe'
        cmd = [cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
               '-I', str(root / 'runtime'), '-I', str(work),
               str(root / 'tools/experimental/hotd1_serial_contract_probe.cpp'), '-o', str(exe)]
        built = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if built.returncode:
            raise ValueError('Native probe compilation failed: ' + built.stderr[-4000:])
        rows = []
        for rx1 in (0, 255):
            run = subprocess.run([str(exe), str(image_path.resolve()), hex(ENTRY),
                                  hex(UPLOAD_BEGIN), hex(UPLOAD_END), str(UPLOAD_COMMAND), str(rx1)],
                                 capture_output=True, text=True, timeout=45)
            if run.returncode:
                raise ValueError('Native probe failed: ' + run.stderr[-4000:])
            rows += parse_rows(run.stdout)
    result = summarize_rows(rows)
    result.update(schema_version=1, image_sha256=HOTDO_SHA256,
                  entry=hex(ENTRY), upload_begin=hex(UPLOAD_BEGIN), upload_end=hex(UPLOAD_END),
                  upload_command=UPLOAD_COMMAND,
                  upload_sha256=hashlib.sha256(image[UPLOAD_BEGIN:UPLOAD_END]).hexdigest(),
                  upload_identity='Unidentified byte block; firmware/configuration type not established.',
                  native_codegen_sites=report.translated)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--cxx', default='c++')
    args = p.parse_args()
    try:
        result = run_experiment(args.image, args.cxx)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(f'Wrote metadata for {result["case_count"]} SYNTHETIC-input cases; not hardware validation.')
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        p.exit(2, f'Contract audit failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
