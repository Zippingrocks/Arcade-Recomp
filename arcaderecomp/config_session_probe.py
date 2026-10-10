"""Original-upload session diagnostic with explicitly synthetic completion/pin events.

Tests the composed software lifecycle, not the unknown Sega board transport,
physical acceptance or configured circuit. Only metadata leaves private input.
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
from .flex8000_sram import serial_to_sof_data


def parse_report(text: str) -> dict:
    if not isinstance(text,str) or len(text)>16384:raise ValueError('Report size invalid')
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:raise ValueError('Duplicate report key')
            obj[key]=value
        return obj
    obj=json.loads(text,object_pairs_hook=unique)
    counts={'schema_version':1,'mode_count':3,'cutoffs_per_mode':221,
            'reset_trials':663,'device_error_trials':663,'reloads_match_expected':1326,
            'stale_handles_rejected':1326,'startup_timeouts_invalidate':3,
            'explicit_startup_intervals':3}
    flags={'synthetic_pin_and_completion_events':True,'profile_completion_signals_acceptance':False,
           'configured_circuit_executed':False,
           'silicon_acceptance_claimed':False,'sega_connected':False}
    if type(obj) is not dict or set(obj)!=counts.keys()|flags.keys():raise ValueError('Report schema invalid')
    for name,value in counts.items():
        if type(obj[name]) is not int or obj[name]!=value:raise ValueError('Incomplete report count: '+name)
    for name,value in flags.items():
        if obj[name] is not value:raise ValueError('Missing evidence boundary: '+name)
    return obj


def run_probe(path: Path, compilers: tuple[str,...]=('g++','clang++')) -> dict:
    if path.stat().st_size!=0x200000:raise ValueError('Expected 2-MiB original CPU image')
    image=path.read_bytes()
    if hashlib.sha256(image).hexdigest()!=HOTDO_SHA256:raise ValueError('Original CPU image identity mismatch')
    stream=image[UPLOAD_BEGIN:UPLOAD_END]
    if hashlib.sha256(stream).hexdigest()!=UPLOAD_SHA256:raise ValueError('Original upload identity mismatch')
    if not compilers or len(set(compilers))!=len(compilers):raise ValueError('Select distinct compilers')
    expected=serial_to_sof_data(stream);root=Path(__file__).resolve().parents[1]
    reports=[]
    with tempfile.TemporaryDirectory(prefix='arcade-private-session-') as folder:
        work=Path(folder);payload=work/'upload.bin';data=work/'expected.bin'
        payload.write_bytes(stream);data.write_bytes(expected)
        for index,name in enumerate(compilers):
            compiler=shutil.which(name)
            if not compiler:raise ValueError('Missing compiler: '+name)
            exe=work/('probe'+str(index)+('.exe' if os.name=='nt' else ''))
            build=subprocess.run([compiler,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                 '-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(root/'runtime'),
                 str(root/'tools/experimental/flex8000_session_probe.cpp'),'-o',str(exe)],
                 capture_output=True,text=True,timeout=45)
            if build.returncode:raise ValueError('Native build failed: '+build.stderr[-3000:])
            run=subprocess.run([str(exe),str(payload),str(data)],capture_output=True,text=True,timeout=30)
            if run.returncode:raise ValueError('Native probe failed: '+run.stderr[-3000:])
            reports.append(parse_report(run.stdout))
    if any(obj!=reports[0] for obj in reports):raise ValueError('Compiler results differ')
    return {'schema_version':1,'image_sha256':HOTDO_SHA256,'upload_sha256':UPLOAD_SHA256,
            'data_sha256':hashlib.sha256(expected).hexdigest(),'compilers':list(compilers),
            'reports_identical':True,'evidence':'original_data_with_synthetic_pin_error_and_completion_events',
            'result':reports[0],'model2c_complete':False}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--cxx',action='append')
    args=parser.parse_args()
    try:
        if args.image.resolve()==args.output.resolve() or (args.output.exists() and os.path.samefile(args.image,args.output)):
            raise ValueError('Output must not overwrite input image')
        report=run_probe(args.image,tuple(args.cxx) if args.cxx else ('g++','clang++'))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print('Session integration checked with synthetic events; silicon acceptance is not established.')
    except (OSError,ValueError,subprocess.TimeoutExpired) as error:parser.exit(2,f'Session audit failed: {error}\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
