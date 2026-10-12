"""Entirely synthetic references; no archived circuit or Sega bytes."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from arcaderecomp import flex8000_legacy_audit as audit
from arcaderecomp.flex8000_compare import git_blob_sha1
from arcaderecomp.flex8000_lut_tiles import CANDIDATE
from arcaderecomp.flex8000_sram import PACKED_BYTES, parse_sof, sof_data_to_serial
from test_flex8000_sram import rcs, sof


def fit(name='DIV_10'):
    return f'''-- Version 0.1 synthetic
-- Compiled: 01/02/03 04:05:06
CHIP "{name.lower()}"
BEGIN
DEVICE = "EPF8282LC84";
"input" : INPUT_PIN = 12;
"invented:1" : LOCATION = LC1_B1;
"invented:2" : LOCATION = LC2_B1;
"invented:3" : LOCATION = LC3_A2;
END;
INTERNAL_INFO "{name.lower()}"
BEGIN
DEVICE = EPF8282LC84;
LC1_B1 : LORAX = "UNINTERPRETED";
END;
'''


def packed_tables(tables):
    packed = bytearray(PACKED_BYTES)
    # Independent literal-coordinate oracle; do not call tile extraction.
    for cell, table in enumerate(tables):
        for row in range(8):
            for column in range(2):
                location = 22138 + 1416 * cell + 177 * row + column
                packed[location // 8] |= ((table >> (2 * row + column)) & 1) << (location % 8)
    return bytes(packed)


def files(name='DIV_10', tables=(3, 0xff00, 0, 0xffff, 0x6996, 0, 0, 0)):
    packed = packed_tables(tables)
    stream = sof_data_to_serial(packed, b'X' * 31, b'Y')
    data = {'SOF': rcs(sof(packed, device=b'EPF8282LC84\0')),
            'TTF': rcs(','.join(str(n) for n in stream).encode('ascii')),
            'FIT': rcs(fit(name).encode('ascii'))}
    return data, {kind: git_blob_sha1(raw) for kind, raw in data.items()}


class LegacySofTests(unittest.TestCase):
    def test_legacy_profile_requires_explicit_opt_in_and_keeps_exact_target(self):
        data = sof(bytes(PACKED_BYTES), device=b'EPF8282LC84\0')
        with self.assertRaises(ValueError): parse_sof(data)
        self.assertEqual(parse_sof(data, allow_legacy_epf8282=True)['device'], 'EPF8282LC84')
        for device in (b'EPF8282TC100\0', b'EPF8282LC84-2\0', b'EPF8282LC84X\0', b'EPM5130QC\0'):
            with self.subTest(device=device), self.assertRaises(ValueError):
                parse_sof(sof(bytes(PACKED_BYTES), device=device), allow_legacy_epf8282=True)
        for setting in (1, None, 'yes'):
            with self.assertRaises(ValueError): parse_sof(data, allow_legacy_epf8282=setting)

    def test_legacy_opt_in_does_not_weaken_size_padding_or_header_checks(self):
        bad = bytes(PACKED_BYTES - 1) + b'\x80'
        for data in (sof(bad, device=b'EPF8282LC84\0'),
                     sof(bytes(PACKED_BYTES), device=b'EPF8282LC84\0', total=37525),
                     sof(bytes(PACKED_BYTES), device=b'EPF8282LC84\0') + b'extra'):
            with self.assertRaises(ValueError): parse_sof(data, allow_legacy_epf8282=True)


class PlacementTests(unittest.TestCase):
    def test_only_unique_explicit_b1_placements_are_reported(self):
        result = audit.fit_placement_metadata(fit(), 'DIV_10')
        self.assertEqual(result['placed_cell_count'], 3)
        self.assertEqual(result['b1_placed_cells'], [1, 2])
        self.assertEqual(result['ordered_input_slot_rows'], 0)
        self.assertFalse(result['fitted_equations_available'])
        self.assertFalse(result['sof_fit_same_build_proven'])

    def test_wrong_identity_ambiguous_malformed_or_missing_placements_fail(self):
        for old, new in (
            ('CHIP "div_10"', 'CHIP "other"'),
            ('DEVICE = EPF8282LC84;', 'DEVICE = EPF8282ALC84-2;'),
            ('LC2_B1', 'LC1_B1'), ('"invented:2"', '"invented:1"'),
            ('LC2_B1', 'LC9_B1'), ('LC3_A2', 'LC3_A14'),
            ('"invented:2" : LOCATION = LC2_B1;', 'junk LOCATION = LC2_B1;'),
            ('LC1_B1 : LORAX', '"extra" : LOCATION = LC4_B1;\nLC1_B1 : LORAX'),
        ):
            with self.subTest(old=old, new=new), self.assertRaises(ValueError):
                audit.fit_placement_metadata(fit().replace(old, new), 'DIV_10')
        only_comments = '\n'.join('-- ' + line if 'LOCATION' in line else line for line in fit().splitlines())
        with self.assertRaises(ValueError): audit.fit_placement_metadata(only_comments, 'DIV_10')

    def test_comments_do_not_create_device_or_placement_evidence(self):
        text = fit() + '-- DEVICE = EPM5130QC;\n-- "false" : LOCATION = LC8_B1;\n'
        self.assertEqual(audit.fit_placement_metadata(text, 'DIV_10')['b1_placed_cells'], [1, 2])


class FixedCandidateTests(unittest.TestCase):
    def test_class_properties_match_independent_literal_truth_tables(self):
        tables = (3, 0xff00, 0, 0xffff, 0x6996, 0xaaaa, 0xfffc, 0)
        result = audit.candidate_observations(packed_tables(tables), [1, 2])
        self.assertEqual(result['candidate'], CANDIDATE)
        self.assertFalse(result['candidate_refitted'])
        self.assertEqual([c['essential_input_count'] for c in result['cells']], [3, 1, 0, 0, 4, 1, 3, 0])
        self.assertEqual([c['class'] for c in result['cells']], [
            'three_input_and_npn', 'buffer_or_inverter', 'constant', 'constant',
            'unclassified', 'buffer_or_inverter', 'three_input_and_npn', 'constant'])
        self.assertEqual([c['fit_places_cell'] for c in result['cells']], [True, True] + [False] * 6)
        self.assertEqual(result['held_out_logic_validation'], 'NOT_ESTABLISHED')
        self.assertNotIn('tables', result)

    def test_mutated_class_is_reported_not_refitted(self):
        original = audit.candidate_observations(packed_tables((3,) * 8), [1])
        changed = audit.candidate_observations(packed_tables((7,) * 8), [1])
        self.assertEqual(original['cells'][0]['class'], 'three_input_and_npn')
        self.assertEqual(changed['cells'][0]['class'], 'unclassified')
        self.assertEqual(original['candidate'], changed['candidate'])
        for placed in ([1, 1], [True], [0], [9], (1,)):
            with self.assertRaises(ValueError): audit.candidate_observations(bytes(PACKED_BYTES), placed)


class AuditTests(unittest.TestCase):
    def test_exact_mapping_and_metadata_boundaries_on_synthetic_reference(self):
        data, pins = files()
        with patch.object(audit, 'PINNED', {'DIV_10': pins}):
            result = audit.analyze_reference('DIV_10', data)
        self.assertTrue(result['exact_sof_ttf_data_match'])
        self.assertEqual(result['matched_data_bits'], 37524)
        self.assertTrue(result['stream_metadata']['exact_roundtrip'])
        self.assertTrue(result['framing_profile']['matches_preexisting_model'])
        self.assertFalse(result['container_checksum_verified'])
        self.assertFalse(result['device_matches_original_candidate_reference'])
        for forbidden in ('packed', 'tables', 'payload', 'equations'):
            self.assertNotIn('"' + forbidden + '":', json.dumps(result))

    def test_wrong_hash_size_missing_kind_and_unknown_name_fail(self):
        data, pins = files()
        with patch.object(audit, 'PINNED', {'DIV_10': pins}):
            for kind in data:
                changed = dict(data); changed[kind] += b'changed'
                with self.assertRaises(ValueError): audit.analyze_reference('DIV_10', changed)
            for changed in ({}, {**data, 'EXTRA': b'x'}, {**data, 'SOF': b'x' * (audit.MAX_FILE + 1)}):
                with self.assertRaises(ValueError): audit.analyze_reference('DIV_10', changed)
            with self.assertRaises(ValueError): audit.analyze_reference('OTHER', data)

    def test_valid_but_mismatched_payload_or_device_is_not_success(self):
        data, pins = files()
        other, _ = files(tables=(0,) * 8)
        wrong_target = rcs(sof(bytes(PACKED_BYTES)))
        for replacement in (other['SOF'], wrong_target):
            changed = {**data, 'SOF': replacement}
            repinned = {**pins, 'SOF': git_blob_sha1(replacement)}
            with patch.object(audit, 'PINNED', {'DIV_10': repinned}), self.assertRaises(ValueError):
                audit.analyze_reference('DIV_10', changed)

    def test_fetch_uses_only_pinned_six_sources_and_returns_metadata(self):
        references = {name: files(name) for name in ('DIV_10', 'RCV_TRIG')}
        pins = {name: item[1] for name, item in references.items()}
        seen = []
        def fetch(url, timeout):
            seen.append(url)
            self.assertEqual(timeout, 20)
            prefix = f'https://raw.githubusercontent.com/{audit.REPOSITORY}/{audit.COMMIT}/{audit.DIRECTORY}'
            self.assertTrue(url.startswith(prefix))
            filename = url[len(prefix):]
            name, extension = filename.split('.')
            return io.BytesIO(references[name][0][extension.removesuffix(',v')])
        with patch.object(audit, 'PINNED', pins), patch.object(audit.urllib.request, 'urlopen', fetch):
            result = audit.fetch_audit()
        self.assertEqual(len(set(seen)), 6)
        self.assertEqual(len(result['references']), 2)
        self.assertFalse(result['physical_device_verified'])
        self.assertFalse(result['netlist_recovered'])
        self.assertFalse(result['runtime_changed'])

    def test_cli_failure_preserves_old_output_and_success_writes_only_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metadata.json'
            path.write_text('old', encoding='utf-8')
            args = ['audit', '--fetch-reference', '--output', str(path)]
            with patch('sys.argv', args), patch.object(audit, 'fetch_audit', side_effect=ValueError('mismatch')):
                with self.assertRaises(SystemExit) as error: audit.main()
                self.assertEqual(error.exception.code, 2)
            self.assertEqual(path.read_text(encoding='utf-8'), 'old')
            with patch('sys.argv', args), patch.object(audit, 'fetch_audit', return_value={'metadata': True}):
                self.assertEqual(audit.main(), 0)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'metadata': True})
            self.assertNotIn(b'\r', path.read_bytes())


if __name__ == '__main__':
    unittest.main()
