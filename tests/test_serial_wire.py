"""Invented sampled waveforms; no hardware capture or Sega data in CI."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arcaderecomp.serial_wire import (UARTFrame, decode_8n1, unwrap_07_pairs,
                                     capture_report, main)


def waveform(wire, rate=12_000_000, baud=2_000_000, channel=4, invert=False):
    # Independent synthesizer: sample a pre-built continuous bit-cell sequence.
    cells = [1]*3
    for b in wire:
        cells += [0] + [(b >> n) & 1 for n in range(8)] + [1]
    cells += [1]*3
    count = len(cells)*rate//baud
    return bytes((((cells[(i*baud)//rate] ^ invert) << channel) | (1 << ((channel+1)%8)))
                 for i in range(count))


class SerialWireTests(unittest.TestCase):
    def test_all_bytes_back_to_back_and_fractional_sample_period(self):
        data = bytes(range(256))*2
        for rate in (8_000_000, 12_000_000, 13_000_000, 15_000_000):
            for inverted in (False, True):
                frames = decode_8n1(waveform(data, rate=rate, invert=inverted), rate,
                                    2_000_000, 4, inverted=inverted)
                self.assertEqual(bytes(f.value for f in frames), data)
                self.assertTrue(all(a.start_sample < b.start_sample for a,b in zip(frames,frames[1:])))

    def test_preserves_payload_seven_instead_of_deleting_it(self):
        payload = bytes(range(256)) + b'\x07'*25
        wire = b''.join(bytes((7,b)) for b in payload)
        self.assertEqual(unwrap_07_pairs(wire), payload)
        self.assertNotEqual(wire.replace(b'\x07', b''), payload)

    def test_no_silent_resync_on_false_start_bad_stop_or_truncation(self):
        good = bytearray(waveform(b'\xa5'))
        # Leading idle = 18 samples, start center = 21, stop center = 75.
        variants = []
        bad = good.copy();bad[21] |= 16;variants.append(bytes(bad))
        bad = good.copy();bad[75] &= ~16;variants.append(bytes(bad))
        variants += [bytes(good[:72]), bytes(good[:78-1]), b'\x00'+bytes(good)]
        for sample in variants:
            with self.assertRaises(ValueError):decode_8n1(sample,12_000_000,2_000_000,4)

    def test_invalid_rates_polarity_channel_and_types(self):
        for rate,baud,ch,inv in ((1,1,4,False),(True,1,4,False),(12_000_000,0,4,False),
                                (12_000_000,2_000_000,8,False),(12_000_000,2_000_000,4,1)):
            with self.assertRaises(ValueError):
                decode_8n1(b'\xff'*128,rate,baud,ch,inverted=inv)
        with self.assertRaises(ValueError):decode_8n1(b'',12_000_000,2_000_000,4)

    def test_pair_parser_rejects_missing_strobe_and_partial_pair(self):
        for wire in (b'',b'\x07',b'\x07\x42\x06\x10',b'\x00\x07'):
            with self.assertRaises(ValueError):unwrap_07_pairs(wire)

    def test_explicit_window_and_provenance_never_claim_hardware_verification(self):
        expected = b'\x00\x07\xff'
        wire = b'\x42\x06'+b''.join(bytes((7,b)) for b in expected)+b'\x55'
        report = capture_report(waveform(wire),expected,sample_rate=12_000_000,
            baud=2_000_000,channel=4,first_frame=2,inverted=False,provenance='external_capture_unverified')
        self.assertTrue(report['all_bytes_match']);self.assertFalse(report['hardware_verified'])
        self.assertEqual(report['payload_07_bytes'],1)
        self.assertEqual(report['decoded_frames'],9)
        for first,prov in ((0,'synthetic'),(4,'synthetic'),(2,'hardware_verified')):
            with self.assertRaises(ValueError):
                capture_report(waveform(wire),expected,sample_rate=12_000_000,
                    baud=2_000_000,channel=4,first_frame=first,inverted=False,provenance=prov)

    def test_mismatch_is_reported_not_hidden(self):
        report=capture_report(waveform(b'\x07\x40'),b'\x41',sample_rate=12_000_000,
            baud=2_000_000,channel=4,first_frame=0,inverted=False,provenance='synthetic')
        self.assertFalse(report['all_bytes_match']);self.assertEqual(report['mismatched_bytes'],1)
        self.assertNotIn('payload',report)

    def test_readonly_cli_prevents_same_path_symlink_hardlink_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);samples=root/'samples.bin';expected=root/'expected.bin'
            samples.write_bytes(waveform(b'\x07\x42'));expected.write_bytes(b'\x42')
            symlink=root/'symlink';symlink.symlink_to(expected)
            hardlink=root/'hardlink';hardlink.hardlink_to(expected)
            original=samples.read_bytes()
            base=['serial_wire','--samples',str(samples),'--expected-upload',str(expected),
                  '--sample-rate','12000000','--baud','2000000','--channel','4',
                  '--first-frame','0','--provenance','synthetic','--output']
            for output in (samples,expected,symlink,hardlink):
                with patch('sys.argv',base+[str(output)]), self.assertRaises(SystemExit) as e: main()
                self.assertEqual(e.exception.code,2)
            self.assertEqual(samples.read_bytes(),original);self.assertEqual(expected.read_bytes(),b'\x42')
            with patch('sys.argv',base+[str(root/'report.json')]):self.assertEqual(main(),0)

if __name__=='__main__': unittest.main()
