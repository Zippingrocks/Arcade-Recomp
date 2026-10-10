"""Verify a private HOTD1 upload through manufacturer-specified input stages.

The ORIGINAL bytes are exercised using SYNTHETIC loading-mode and pin/clock
choices. Passing is not a board-mode identification or complete FPGA load.
No private bytes or generated game code enter the metadata report.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from .serial_contract import HOTDO_SHA256, UPLOAD_BEGIN, UPLOAD_END
from .upload_framing import UPLOAD_SHA256


def validate_report(report: dict, length: int) -> None:
    if type(report) is not dict or type(length) is not int or not 1 <= length <= 65536:
        raise ValueError('Invalid input-stage report')
    if set(report) != {'schema_version', 'synthetic_pin_stimulus', 'board_mode_identified',
                       'configuration_completed', 'stream_bytes', 'modes',
                       'ppa_busy_observations', 'ppa_masked_status_reads'}:
        raise ValueError('Unexpected or missing report fields')
    for key, expected in [('schema_version', 1), ('stream_bytes', length),
                          ('ppa_busy_observations', length*8),
                          ('ppa_masked_status_reads', length*24)]:
        if type(report[key]) is not int or report[key] != expected:
            raise ValueError('Incorrect measured counter: ' + key)
    if report['synthetic_pin_stimulus'] is not True or report['board_mode_identified'] is not False \
            or report['configuration_completed'] is not False:
        raise ValueError('Missing experimental evidence boundaries')
    modes = report['modes']
    if type(modes) is not list or len(modes) != 3:
        raise ValueError('All three input modes must be tested')
    for row, name in zip(modes, ('PS', 'PPS', 'PPA')):
        if type(row) is not dict or set(row) != {'mode', 'accepted_bits', 'matches_input_lsb_first'} \
                or row['mode'] != name or row['matches_input_lsb_first'] is not True \
                or type(row['accepted_bits']) is not int or row['accepted_bits'] != length*8:
            raise ValueError('Failed, duplicated, or incomplete loading-mode result')


def run_probe(image_path: Path, compilers: tuple[str, ...] = ('g++', 'clang++')) -> dict:
    if image_path.stat().st_size != 0x200000:
        raise ValueError('Expected mapped 2-MiB original CPU image')
    image = image_path.read_bytes()
    if hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Original hotdo image identity mismatch')
    stream = image[UPLOAD_BEGIN:UPLOAD_END]
    if hashlib.sha256(stream).hexdigest() != UPLOAD_SHA256:
        raise ValueError('Original upload identity mismatch')
    if not compilers or len(set(compilers)) != len(compilers):
        raise ValueError('Compiler selection must be nonempty and unique')
    root = Path(__file__).resolve().parents[1]
    reports = []
    with tempfile.TemporaryDirectory(prefix='arcaderecomp-private-ingress-') as tmp:
        work = Path(tmp); private = work/'upload.bin'
        private.write_bytes(stream)
        for index, compiler in enumerate(compilers):
            cxx = shutil.which(compiler)
            if not cxx:
                raise ValueError('Compiler not found: ' + compiler)
            exe = work/('probe'+str(index)+('.exe' if os.name == 'nt' else ''))
            built = subprocess.run([cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I', str(root/'runtime'),
                str(root/'tools/experimental/flex8000_ingress_probe.cpp'), '-o', str(exe)],
                capture_output=True, text=True, timeout=45)
            if built.returncode:
                raise ValueError('Native build failed: ' + built.stderr[-3000:])
            run = subprocess.run([str(exe), str(private)], capture_output=True, text=True, timeout=15)
            if run.returncode or len(run.stdout) > 16384:
                raise ValueError('Native input-stage probe failed: ' + run.stderr[-3000:])
            def unique(pairs):
                out = {}
                for key, value in pairs:
                    if key in out:
                        raise ValueError('Duplicate report key')
                    out[key] = value
                return out
            report = json.loads(run.stdout, object_pairs_hook=unique)
            validate_report(report, len(stream))
            reports.append(report)
    if any(report != reports[0] for report in reports):
        raise ValueError('Compiler results disagree')
    return {'schema_version': 1, 'image_sha256': HOTDO_SHA256, 'upload_sha256': UPLOAD_SHA256,
            'compilers': list(compilers), 'compiler_reports_identical': True,
            'evidence_level': 'original_upload_with_synthetic_pin_and_clock_stimulus',
            'input_stage': reports[0], 'sega_serial_backend_connected': False,
            'model2c_complete': False}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cxx', action='append')
    args = p.parse_args()
    try:
        if args.image.resolve() == args.output.resolve() or \
                (args.output.exists() and os.path.samefile(args.image, args.output)):
            raise ValueError('Output must not overwrite input image')
        result = run_probe(args.image, tuple(args.cxx) if args.cxx else ('g++', 'clang++'))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        print('Three input-stage paths checked; Sega wiring and full configuration remain unverified.')
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        p.exit(2, f'Configuration ingress check failed: {error}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
