"""Original HOTD1 host-write audit with explicit synthetic peer/wire inputs.

No ROM/network fetches. Private outputs live only in a temporary directory;
only metadata is returned. A Model 2B report is not proof of 2C wiring or baud.
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
from .serial_wire import capture_report, unwrap_07_pairs

COUNTERS = ('steps', 'commands', 'data_latch_writes', 'commands_without_fresh_data',
            'commands_with_unknown_data', 'upload_bytes', 'predicted_upload_wire_bytes')


def parse_native(text: str) -> dict:
    if len(text) > 4096:
        raise ValueError('Native metadata exceeds bound')
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                raise ValueError('Duplicate metadata key')
            result[k] = v
        return result
    row = json.loads(text, object_pairs_hook=unique)
    if type(row) is not dict or set(row) != set(COUNTERS) | {'synthetic_inputs', 'hardware_capture'}:
        raise ValueError('Unexpected metadata fields')
    if row['synthetic_inputs'] is not True or row['hardware_capture'] is not False:
        raise ValueError('Missing synthetic-input declaration')
    if any(type(row[k]) is not int or not 0 <= row[k] <= 250000 for k in COUNTERS):
        raise ValueError('Invalid metadata counters')
    size = UPLOAD_END - UPLOAD_BEGIN
    if row['upload_bytes'] != size or row['predicted_upload_wire_bytes'] != 2*size:
        raise ValueError('Upload count mismatch')
    if row['commands'] < size or row['commands_without_fresh_data'] > row['commands']:
        raise ValueError('Inconsistent command counts')
    return row


def synthetic_samples(wire: bytes) -> bytes:
    """Invented 12-MHz, D4, 2-Mbaud 8N1 stimulus. No ACK delays are modeled."""
    samples = bytearray(b'\x10'*18)
    for value in wire:
        for bit in (0, *((value >> n) & 1 for n in range(8)), 1):
            samples.extend(bytes((bit << 4,))*6)
    samples.extend(b'\x10'*18)
    return bytes(samples)


def run_experiment(image_path: Path, compiler: str = 'c++') -> dict:
    if image_path.stat().st_size != 0x200000:
        raise ValueError('Expected original mapped 2-MiB image')
    image = image_path.read_bytes()
    if hashlib.sha256(image).hexdigest() != HOTDO_SHA256:
        raise ValueError('Original hotdo hash mismatch')
    cxx = shutil.which(compiler)
    if not cxx:
        raise ValueError('C++17 compiler not found')
    root = Path(__file__).resolve().parents[1]
    code, report = emit_cpp(image, ENTRY, 4096)
    if report.unsupported or report.limit_reached:
        raise ValueError('Isolated native translation incomplete')
    payload = image[UPLOAD_BEGIN:UPLOAD_END]
    runs = []
    with tempfile.TemporaryDirectory(prefix='arcade-private-tx-') as d:
        work = Path(d)
        (work/'hotd1_i960.cpp').write_text(code, encoding='utf-8')
        exe = work/'probe'
        build = subprocess.run([cxx, '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
            '-fsanitize=undefined', '-fno-sanitize-recover=all', '-I', str(root/'runtime'),
            '-I', str(work), str(root/'tools/experimental/hotd1_tx_capture_probe.cpp'),
            '-o', str(exe)], capture_output=True, text=True, timeout=45)
        if build.returncode:
            raise ValueError('Native build failed: '+build.stderr[-4000:])
        for rx1, rx2 in ((0, 0), (255, 255)):
            wire_path = work/f'{rx1}-{rx2}.wire'
            p = subprocess.run([str(exe), str(image_path.resolve()), str(wire_path),
                hex(ENTRY), hex(UPLOAD_BEGIN), hex(UPLOAD_END), str(rx1), str(rx2)],
                capture_output=True, text=True, timeout=20)
            if p.returncode:
                raise ValueError('Native probe failed: '+p.stderr[-4000:])
            row = parse_native(p.stdout)
            if wire_path.stat().st_size != 2*len(payload):
                raise ValueError('Private wire size mismatch')
            wire = wire_path.read_bytes()
            if unwrap_07_pairs(wire) != payload:
                raise ValueError('Observed upload data does not match ROM')
            audit = capture_report(synthetic_samples(wire), payload,
                sample_rate=12_000_000, baud=2_000_000, channel=4, first_frame=0,
                inverted=False, provenance='synthetic')
            if not audit['all_bytes_match']:
                raise ValueError('Synthetic sampled-waveform comparison failed')
            row.update(rx1=rx1, rx2=rx2, wire_sha256=hashlib.sha256(wire).hexdigest(),
                naive_drop_all_07_bytes_lost=len(payload)-len(wire.replace(b'\x07', b'')),
                sampled_waveform_audit=audit)
            runs.append(row)
    return {'schema_version': 1, 'image_sha256': HOTDO_SHA256,
            'compiler': compiler, 'original_rom_used': True, 'synthetic_peer_inputs': True,
            'synthetic_wire_samples': True, 'physical_model2c_transport_verified': False,
            'isolated_original_codegen_sites': report.translated, 'runs': runs,
            'existing_runtime_changed': False, 'model2c_complete': False}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cxx', default='c++')
    a = p.parse_args()
    try:
        if a.image.resolve() == a.output.resolve() or (a.output.exists() and a.output.samefile(a.image)):
            raise ValueError('Output aliases the input image')
        report = run_experiment(a.image, a.cxx)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print('Wrote original-host TX metadata with SYNTHETIC peer and wire stimulus.')
    except (ValueError, OSError, subprocess.TimeoutExpired) as e:
        p.exit(2, f'TX audit failed: {e}\n')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
