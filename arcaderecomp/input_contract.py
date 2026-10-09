"""Verify isolated original HOTD1 input-read behavior with synthetic replies.

This is not an endpoint emulator, calibration, timing or full-game proof.
Only metadata is exported; native ROM-derived source is private/temporary.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from .i960_cpp import emit_cpp
from .serial_contract import HOTDO_SHA256

PAIR_ENTRY, SNAPSHOT_ENTRY = 0xa3980, 0xa38c0
OUTPUT_ADDRESSES = (0x51eef2, 0x51eef0, 0x51ef0e, 0x51ef0c, 0x51ef08, 0x51ef24)
EXPECTED_COUNTS = {
    'pair_cases': 131072, 'snapshot_cases': 4096, 'pair_byte_domain': 65536,
    'pair_distractor_patterns': 2, 'raw_values_per_slot': 1024,
    'flag_reply_values': 256, 'snapshot_transactions': 18,
    'snapshot_selections': 9, 'snapshot_outputs': 6,
}


def summarize(text: str) -> dict:
    """Strictly accept one complete native result, never a truncated success."""
    if not isinstance(text, str) or len(text) > 4096:
        raise ValueError('Invalid or oversized native report')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate result key')
            result[key] = value
        return result
    obj = json.loads(text, object_pairs_hook=unique)
    keys = set(EXPECTED_COUNTS) | {'synthetic_inputs', 'all_contracts_passed', 'step_min', 'step_max'}
    if not isinstance(obj, dict) or set(obj) != keys:
        raise ValueError('Unexpected report fields')
    if obj['synthetic_inputs'] is not True or obj['all_contracts_passed'] is not True:
        raise ValueError('Failed contract or missing synthetic-input declaration')
    for key, expected in EXPECTED_COUNTS.items():
        if type(obj[key]) is not int or obj[key] != expected:
            raise ValueError(f'Incomplete/invalid {key}')
    for key in ('step_min', 'step_max'):
        if type(obj[key]) is not int or not 0 < obj[key] < 4096:
            raise ValueError(f'Invalid {key}')
    if obj['step_min'] > obj['step_max']:
        raise ValueError('Inverted step bounds')
    return {
        'schema_version': 1,
        'evidence_level': 'isolated_original_host_code_with_synthetic_inputs',
        'physical_receiver_verified': False, 'calibration_verified': False,
        'native_result': obj,
        'raw_value_rule': 'low_byte | ((high_byte & 3) << 8)',
        'raw_flag_rules': ['(reply ^ 3) & 1', '((reply ^ 3) >> 1) & 1'],
        'word_destinations': [hex(x) for x in OUTPUT_ADDRESSES[:4]],
        'byte_destinations': [hex(x) for x in OUTPUT_ADDRESSES[4:]],
        'selector_order': list(range(9)), 'commands_per_selector': [0, 0x87],
        'labels': 'Four raw 10-bit values and two inverted flags; physical axes/buttons not assigned.',
        'boundary': 'No serial device replies, FPGA behavior, hardware clock, interrupt or boot bypass implemented.',
    }


def run_experiment(path: Path, compiler: str = 'c++', sanitize: bool = False) -> dict:
    if path.stat().st_size != 0x200000:
        raise ValueError('Expected original mapped 2-MiB image')
    image = path.read_bytes()
    if hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Original hotdo image hash mismatch')
    cxx = shutil.which(compiler)
    if cxx is None:
        raise ValueError('Requested C++ compiler is unavailable')
    source, coverage = emit_cpp(image, PAIR_ENTRY, 4096, additional_entries=(SNAPSHOT_ENTRY,))
    if coverage.unsupported or coverage.limit_reached:
        raise ValueError('Isolated code generation incomplete')
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='arcade-private-input-') as tmp:
        folder = Path(tmp)
        (folder / 'hotd1_i960.cpp').write_text(source, encoding='utf-8')
        exe = folder / 'input_probe'
        flags = ['-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror']
        if sanitize:
            flags += ['-fsanitize=undefined', '-fno-sanitize-recover=all']
        built = subprocess.run([cxx, *flags, '-I', str(root/'runtime'), '-I', str(folder),
                                str(root/'tools/experimental/hotd1_input_contract_probe.cpp'),
                                '-o', str(exe)], capture_output=True, text=True, timeout=40)
        if built.returncode:
            raise ValueError('Probe compilation failed: ' + built.stderr[-2000:])
        executed = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        if executed.returncode:
            raise ValueError('Probe failed: ' + executed.stderr[-2000:])
        result = summarize(executed.stdout)
    result.update(image_sha256=HOTDO_SHA256, native_codegen_sites=coverage.translated,
                  pair_entry=hex(PAIR_ENTRY), snapshot_entry=hex(SNAPSHOT_ENTRY),
                  compiler=Path(cxx).name, sanitizer_enabled=sanitize)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cxx', default='c++')
    p.add_argument('--sanitize', action='store_true')
    args = p.parse_args()
    try:
        if args.image.resolve() == args.output.resolve():
            raise ValueError('Output must not overwrite input image')
        result = run_experiment(args.image, args.cxx, args.sanitize)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print('Wrote isolated input-decoding metadata; physical receiver remains unverified.')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        p.exit(2, f'Input contract failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
