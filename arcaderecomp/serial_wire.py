"""Offline, bounded 8-N-1 capture comparison. Never produces device replies.

Input: raw samples, one byte per sample, selected bit = TTL UART line.
Only a caller-selected 07/data upload window is compared. No heuristic removal
of every 0x07: that byte may itself be payload. No auto-baud or auto-polarity.
The Model 2B 2-Mbaud measurement is a hypothesis for 2C, not a default here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from dataclasses import dataclass

MAX_SAMPLES = 64 * 1024 * 1024
MAX_BYTES = 1_000_000


def integer(value: int, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in {low}..{high}')
    return value


@dataclass(frozen=True)
class UARTFrame:
    start_sample: int
    value: int


def decode_8n1(samples: bytes, sample_rate: int, baud: int, channel: int,
               *, inverted: bool = False) -> list[UARTFrame]:
    """Sample start/data/stop centers with integer-rational timing.

    Capture must begin idle and include complete frames. Reject false starts,
    bad stops and trailing partial frames; never silently resynchronize past an
    error. This is a digital sample decoder, not electrical-timing validation.
    At least 4 samples/bit are required. Clock drift/jitter is not corrected.
    """
    if type(samples) is not bytes or not 1 <= len(samples) <= MAX_SAMPLES:
        raise ValueError('Expected 1..64 MiB of raw samples')
    integer(sample_rate, 1, 1_000_000_000, 'sample rate')
    integer(baud, 1, 100_000_000, 'baud')
    integer(channel, 0, 7, 'channel')
    if type(inverted) is not bool or sample_rate < 4 * baud:
        raise ValueError('Invalid polarity or fewer than four samples per bit')
    def level(i: int) -> int:
        return ((samples[i] >> channel) & 1) ^ int(inverted)
    if level(0) != 1:
        raise ValueError('Capture does not begin at an observed idle-high level')
    frames = []
    i = 1
    while i < len(samples):
        if level(i - 1) != 1 or level(i) != 0:
            i += 1
            continue
        start = i
        # floor((k+0.5)*rate/baud), k=0 start, 1..8 data, 9 stop.
        points = [start + ((2*k+1)*sample_rate)//(2*baud) for k in range(10)]
        end = start + (10*sample_rate + baud - 1)//baud
        if end > len(samples) or points[-1] >= len(samples):
            raise ValueError(f'Truncated UART frame at sample {start}')
        if level(points[0]) != 0:
            raise ValueError(f'False start at sample {start}')
        if level(points[-1]) != 1:
            raise ValueError(f'Invalid UART stop bit at sample {start}')
        value = sum(level(points[k+1]) << k for k in range(8))
        if len(frames) >= MAX_BYTES:
            raise ValueError('Decoded byte limit exceeded')
        frames.append(UARTFrame(start, value))
        # Resume inside the observed stop bit, not after a rounded frame end:
        # this preserves back-to-back starts at fractional samples/bit.
        i = points[-1] + 1
    return frames


def unwrap_07_pairs(wire: bytes) -> bytes:
    """Decode only an explicitly delimited run of complete command/data pairs."""
    if type(wire) is not bytes or not wire or len(wire) > MAX_BYTES or len(wire) % 2:
        raise ValueError('Expected a nonempty bounded sequence of whole 07/data pairs')
    for i in range(0, len(wire), 2):
        if wire[i] != 7:
            raise ValueError(f'Expected command 07 at byte {i}; no resynchronization attempted')
    return wire[1::2]


def capture_report(samples: bytes, expected: bytes, *, sample_rate: int,
                   baud: int, channel: int, first_frame: int, inverted: bool,
                   provenance: str) -> dict:
    """Caller declares a window; do not search for a payload then claim alignment."""
    if provenance not in ('synthetic', 'external_capture_unverified'):
        raise ValueError('Provenance must explicitly identify synthetic or unverified capture')
    if type(expected) is not bytes or not 1 <= len(expected) <= MAX_BYTES // 2:
        raise ValueError('Invalid expected payload size')
    integer(first_frame, 0, MAX_BYTES, 'first frame')
    frames = decode_8n1(samples, sample_rate, baud, channel, inverted=inverted)
    end = first_frame + 2*len(expected)
    if end > len(frames):
        raise ValueError('Selected upload window extends beyond decoded capture')
    payload = unwrap_07_pairs(bytes(f.value for f in frames[first_frame:end]))
    matches = payload == expected
    return {
        'schema_version': 1, 'provenance': provenance,
        'hardware_verified': False,
        'capture_sha256': hashlib.sha256(samples).hexdigest(),
        'expected_sha256': hashlib.sha256(expected).hexdigest(),
        'decoded_payload_sha256': hashlib.sha256(payload).hexdigest(),
        'sample_rate': sample_rate, 'baud': baud, 'channel': channel,
        'inverted': inverted, 'decoded_frames': len(frames),
        'first_frame': first_frame, 'window_frames': 2*len(expected),
        'first_start_sample': frames[first_frame].start_sample,
        'last_start_sample': frames[end-1].start_sample,
        'payload_bytes': len(payload), 'payload_07_bytes': payload.count(7),
        'all_bytes_match': matches,
        'mismatched_bytes': sum(a != b for a, b in zip(payload, expected)),
        'interpretation': 'Caller-selected TX window only; no RX, ACK, FPGA wiring or acceptance inference.'
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--samples', type=Path, required=True)
    p.add_argument('--expected-upload', type=Path, required=True)
    p.add_argument('--sample-rate', type=int, required=True)
    p.add_argument('--baud', type=int, required=True)
    p.add_argument('--channel', type=int, required=True)
    p.add_argument('--first-frame', type=int, required=True)
    p.add_argument('--inverted', action='store_true')
    p.add_argument('--provenance', choices=('synthetic', 'external_capture_unverified'), required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    try:
        for input_path, maximum in ((a.samples, MAX_SAMPLES), (a.expected_upload, MAX_BYTES//2)):
            if input_path.stat().st_size > maximum:
                raise ValueError('Input exceeds size bound')
            if a.output.resolve() == input_path.resolve() or (a.output.exists() and a.output.samefile(input_path)):
                raise ValueError('Output would overwrite an input')
        report = capture_report(a.samples.read_bytes(), a.expected_upload.read_bytes(),
            sample_rate=a.sample_rate, baud=a.baud, channel=a.channel,
            first_frame=a.first_frame, inverted=a.inverted, provenance=a.provenance)
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        print('TX window matches' if report['all_bytes_match'] else 'TX window MISMATCH')
        return 0 if report['all_bytes_match'] else 3
    except (ValueError, OSError) as e:
        p.exit(2, f'Capture comparison failed: {e}\n')


if __name__ == '__main__':
    raise SystemExit(main())
