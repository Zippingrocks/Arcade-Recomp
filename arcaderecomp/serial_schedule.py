"""Bounded, metadata-only native HOTD1 serial scheduling experiment.

The status/RX values are deliberately synthetic. Passing this experiment
establishes host-program behavior only, never physical receiver fidelity.
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
from .serial_contract import HOTDO_SHA256, ENTRY, UPLOAD_BEGIN, UPLOAD_END

DELAYS = ((0, 0), (1, 0), (0, 2), (4, 7), (7, 4), (9, 9))
UPLOAD_SHA256 = 'de6e298436c243dd11bc725592b99cf9e87bde6d305583ef0aec511610ec76c1'
TRANSACTIONS = 5132


def checked_image(path: Path) -> bytes:
    if path.stat().st_size != 0x200000:
        raise ValueError('Expected the original mapped 2-MiB i960 image')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != HOTDO_SHA256:
        raise ValueError('Original hotdo image hash mismatch')
    if hashlib.sha256(data[UPLOAD_BEGIN:UPLOAD_END]).hexdigest() != UPLOAD_SHA256:
        raise ValueError('Original upload hash mismatch')
    return data


def summarize(text: str) -> dict:
    if len(text) > 1_000_000:
        raise ValueError('Native report too large')
    lines = text.splitlines()
    if len(lines) != 448:
        raise ValueError('Expected 192 upload and 256 wait cases')
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate JSON key')
            obj[key] = value
        return obj
    uploads, waits = {}, {}
    def integer(obj, key, minimum, maximum):
        value = obj.get(key)
        if type(value) is not int or not minimum <= value <= maximum:
            raise ValueError(f'Invalid {key}')
        return value
    for line in lines:
        row = json.loads(line, object_pairs_hook=unique)
        if not isinstance(row, dict) or row.get('synthetic_inputs') is not True:
            raise ValueError('Missing explicit synthetic-input declaration')
        if row.get('kind') == 'upload':
            if set(row) != {'kind','seed','delay1','delay2','noise','steps','polls',
                            'transactions','upload_bytes','upload_matches',
                            'synthetic_inputs','feedback_matches'}:
                raise ValueError('Unexpected upload fields')
            seed = integer(row,'seed',0,15)
            d1, d2 = integer(row,'delay1',0,9), integer(row,'delay2',0,9)
            noise = integer(row,'noise',0,1)
            key = seed, d1, d2, noise
            if (d1,d2) not in DELAYS or key in uploads:
                raise ValueError('Unexpected or duplicate upload case')
            if row.get('upload_matches') is not True or row.get('feedback_matches') is not True:
                raise ValueError('Upload/feedback contract did not pass')
            if integer(row,'transactions',0,10000) != TRANSACTIONS or integer(row,'upload_bytes',0,10000) != 5120:
                raise ValueError('Incomplete upload/transaction count')
            if integer(row,'polls',0,100000) != TRANSACTIONS * (1+max(d1,d2)):
                raise ValueError('Missing/extra readiness polling')
            # The instruction count is a reference observation, not hardware cycles.
            if integer(row,'steps',0,600000) != 89199 + 6*TRANSACTIONS*max(d1,d2):
                raise ValueError('Native control-flow count changed')
            uploads[key] = row
        elif row.get('kind') == 'wait':
            if set(row) != {'kind','status','steps','polls','returned','step_bound','synthetic_inputs'}:
                raise ValueError('Unexpected waiter fields')
            status = integer(row,'status',0,255)
            if status in waits or type(row.get('returned')) is not bool:
                raise ValueError('Duplicate/invalid waiter case')
            if integer(row,'step_bound',0,1000) != 128:
                raise ValueError('Unexpected waiter step bound')
            expected = (status & 12) == 12
            if row['returned'] != expected:
                raise ValueError('Original wait mask changed')
            if integer(row,'steps',0,128) != (6 if expected else 128):
                raise ValueError('Unexpected waiter stop')
            if integer(row,'polls',0,128) != (1 if expected else 21):
                raise ValueError('Unexpected waiter polling count')
            waits[status] = row
        else:
            raise ValueError('Unknown record kind')
    expected_keys = {(s,a,b,n) for s in range(16) for a,b in DELAYS for n in (0,1)}
    if set(uploads) != expected_keys or set(waits) != set(range(256)):
        raise ValueError('Incomplete experiment domains')
    return {
        'schema_version': 1,
        'evidence_level': 'isolated_original_native_host_with_synthetic_inputs',
        'physical_hardware_verified': False,
        'upload_cases': 192,
        'wait_cases': 256,
        'variable_reply_seeds': 16,
        'delay_pairs_in_status_polls': [list(p) for p in DELAYS],
        'non_ready_status_bits_varied': True,
        'uploaded_bytes_per_case': 5120,
        'all_upload_bytes_match_original': True,
        'feedback': [
            {'output_control_index':5,'rx2_transaction_index':4,'and_mask':254,'or_bits':0},
            {'output_control_index':7,'rx2_transaction_index':6,'and_mask':255,'or_bits':1},
        ],
        'steps_range': [min(r['steps'] for r in uploads.values()),max(r['steps'] for r in uploads.values())],
        'wait_return_condition': '(status & 0x0c) == 0x0c',
        'wait_returned_cases': sum(r['returned'] for r in waits.values()),
        'wait_bounded_nonreturn_cases': sum(not r['returned'] for r in waits.values()),
        'wait_step_bound': 128,
        'boundary': 'Host ignores other status bits in this routine; this does not identify the chip, wire format, replies, or real timing.',
    }


def run_experiment(path: Path, compiler: str = 'c++', sanitize: bool = False) -> dict:
    image = checked_image(path)
    cxx = shutil.which(compiler)
    if cxx is None:
        raise ValueError(f'C++ compiler unavailable: {compiler}')
    root = Path(__file__).resolve().parents[1]
    source, report = emit_cpp(image, ENTRY, 4096)
    if report.unsupported or report.limit_reached:
        raise ValueError('Isolated host codegen incomplete')
    with tempfile.TemporaryDirectory(prefix='arcade-private-schedule-') as tmp:
        folder = Path(tmp)
        (folder/'hotd1_i960.cpp').write_text(source,encoding='utf-8')
        exe = folder/'schedule_probe'
        flags = ['-std=c++17','-O2','-Wall','-Wextra','-Werror']
        if sanitize:
            flags += ['-fsanitize=undefined','-fno-sanitize-recover=all']
        cmd = [cxx,*flags,'-I',str(root/'runtime'),'-I',str(folder),
               str(root/'tools/experimental/hotd1_serial_schedule_probe.cpp'),'-o',str(exe)]
        built = subprocess.run(cmd,capture_output=True,text=True,timeout=40)
        if built.returncode:
            raise ValueError(f'Native compile failed: {built.stderr[-4000:]}')
        run = subprocess.run([str(exe),str(path.resolve())],capture_output=True,text=True,timeout=40)
        if run.returncode:
            raise ValueError(f'Native experiment failed: {run.stderr[-4000:]}')
        result = summarize(run.stdout)
    result.update(image_sha256=HOTDO_SHA256,upload_sha256=UPLOAD_SHA256,
                  compiler=Path(cxx).name,sanitizer_enabled=sanitize)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--cxx',default='c++')
    p.add_argument('--sanitize',action='store_true')
    p.add_argument('--output',type=Path)
    args = p.parse_args()
    try:
        report = run_experiment(args.image,args.cxx,args.sanitize)
        text = json.dumps(report,indent=2)+'\n'
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(text,encoding='utf-8')
        else:
            print(text,end='')
    except (ValueError,OSError,subprocess.TimeoutExpired) as e:
        p.exit(2,f'Serial schedule experiment failed: {e}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
