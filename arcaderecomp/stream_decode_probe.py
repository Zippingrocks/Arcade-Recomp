"""Private-ROM incremental EPF8282 data decoder audit; not chip acceptance.

Connects the three separately selected configuration input stages to the native
streaming profile decoder and compares with the existing independent Python
mapping. All pin/clock stimulus is synthetic; no Sega responses are generated.
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
from .flex8000_sram import serial_to_sof_data, TOTAL_BITS


def parse_report(text: str) -> dict:
    if not isinstance(text, str) or len(text)>16384:
        raise ValueError('Native report exceeds bound')
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result:
                raise ValueError('Duplicate native report key')
            result[key]=value
        return result
    result=json.loads(text,object_pairs_hook=unique)
    keys={'schema_version','synthetic_pin_stimulus','opaque_envelope_supplied_from_input',
          'silicon_configuration_accepted','startup_armed','sega_serial_connected','data_bits','modes'}
    if type(result) is not dict or set(result)!=keys:
        raise ValueError('Invalid native report fields')
    for key,value in [('schema_version',1),('data_bits',37524)]:
        if type(result[key]) is not int or result[key]!=value:
            raise ValueError('Wrong native count: '+key)
    for key in ('synthetic_pin_stimulus','opaque_envelope_supplied_from_input'):
        if result[key] is not True:
            raise ValueError('Missing synthetic/opaque declaration')
    for key in ('silicon_configuration_accepted','startup_armed','sega_serial_connected'):
        if result[key] is not False:
            raise ValueError('Unsupported hardware-success claim')
    if type(result['modes']) is not list or len(result['modes'])!=3:
        raise ValueError('Missing loading mode')
    for row,name in zip(result['modes'],('PS','PPS','PPA')):
        if type(row) is not dict or set(row)!={'mode','input_bits','records_validated','matches_python_data'}:
            raise ValueError('Unexpected mode fields')
        if row['mode']!=name or row['matches_python_data'] is not True:
            raise ValueError('Wrong mode or data mismatch')
        for key,count in [('input_bits',40960),('records_validated',212)]:
            if type(row[key]) is not int or row[key]!=count:
                raise ValueError('Incomplete native mode')
    return result


def run_probe(image_path: Path, compilers: tuple[str,...]=('g++','clang++')) -> dict:
    if image_path.stat().st_size!=0x200000:
        raise ValueError('Expected 2-MiB mapped original CPU image')
    image=image_path.read_bytes()
    if hashlib.sha256(image).hexdigest()!=HOTDO_SHA256:
        raise ValueError('Original image identity mismatch')
    stream=image[UPLOAD_BEGIN:UPLOAD_END]
    if hashlib.sha256(stream).hexdigest()!=UPLOAD_SHA256:
        raise ValueError('Original upload identity mismatch')
    if not compilers or len(set(compilers))!=len(compilers):
        raise ValueError('Compiler selection must be nonempty and unique')
    expected=serial_to_sof_data(stream)
    root=Path(__file__).resolve().parents[1]
    reports=[]
    with tempfile.TemporaryDirectory(prefix='arcade-private-stream-') as folder:
        work=Path(folder)
        private,packed=work/'upload.bin',work/'expected.bin'
        private.write_bytes(stream);packed.write_bytes(expected)
        for i,compiler in enumerate(compilers):
            cxx=shutil.which(compiler)
            if not cxx:
                raise ValueError('Compiler not found: '+compiler)
            exe=work/('probe'+str(i)+('.exe' if os.name=='nt' else ''))
            build=subprocess.run([cxx,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(root/'runtime'),
                str(root/'tools/experimental/epf8282_stream_decode_probe.cpp'),'-o',str(exe)],
                capture_output=True,text=True,timeout=45)
            if build.returncode:
                raise ValueError('Native build failed: '+build.stderr[-3000:])
            run=subprocess.run([str(exe),str(private),str(packed)],
                               capture_output=True,text=True,timeout=15)
            if run.returncode:
                raise ValueError('Native check failed: '+run.stderr[-3000:])
            reports.append(parse_report(run.stdout))
    if any(report!=reports[0] for report in reports):
        raise ValueError('Compiler reports disagree')
    return {'schema_version':1,'image_sha256':HOTDO_SHA256,'upload_sha256':UPLOAD_SHA256,
            'data_sha256':hashlib.sha256(expected).hexdigest(),'data_bits':TOTAL_BITS,
            'compilers':list(compilers),'compiler_reports_identical':True,
            'evidence_level':'original_upload_with_synthetic_pin_stimulus_and_empirical_record_profile',
            'decode':reports[0],'model2c_complete':False}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cxx',action='append')
    args=parser.parse_args()
    try:
        if args.image.resolve()==args.output.resolve() or \
                (args.output.exists() and os.path.samefile(args.image,args.output)):
            raise ValueError('Output must not overwrite original input')
        result=run_probe(args.image,tuple(args.cxx) if args.cxx else ('g++','clang++'))
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print('Three profile-decoding paths checked; hardware acceptance is NOT established.')
    except (OSError,ValueError,subprocess.TimeoutExpired) as error:
        parser.exit(2,f'Stream decode audit failed: {error}\n')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
