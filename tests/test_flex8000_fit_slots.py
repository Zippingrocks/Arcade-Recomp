"""Independent, artificial ordered-fitter conformance tests; no archived designs."""
import copy
import itertools
import json
import random
import unittest
from unittest.mock import patch

from arcaderecomp.flex8000_fit_slots import (
    PINNED, build_stamp, parse_fit_slots, ordered_tables,
    common_slot_permutations, audit_pinned_inputs)
from arcaderecomp.flex8000_fit_constraints import transform
from arcaderecomp.flex8000_lut_tiles import CANDIDATE, tile_offsets
from arcaderecomp.flex8000_sram import PACKED_BYTES
from arcaderecomp.flex8000_compare import git_blob_sha1
from test_flex8000_sram import rcs, sof
from test_flex8000_fit_constraints import report as base_report

DEVICE = 'EPF8282ALC84-2'


def report():
    return 'Version 0.1 test\nCompiled: 01/02/03 04:05:06\n'+base_report()


def fit():
    return '''-- Version 0.1 test
-- Compiled: 01/02/03 04:05:06
CHIP "artificial"
BEGIN
DEVICE = "EPF8282ALC84-2";
"a" : INPUT_PIN = 1;
"b" : INPUT_PIN = 2;
"c" : INPUT_PIN = 3;
"d" : INPUT_PIN = 4;
"/RESET" : INPUT_PIN = 5;
END;
INTERNAL_INFO "artificial"
BEGIN
DEVICE = EPF8282ALC84-2;
LC1_B1 : LORAX2 = "OD0P1, OD1P2, OD2P3, OD3P4";
LC2_B1 : LORAX2 = "OD1P2, OD0P1, X, X";
LC3_B1 : LORAX2 = "X, LC2_B1, X, X";
LC4_B1 : LORAX2 = "X, X, OD0P1, X";
LC5_B1 : LORAX2 = "OD0P1, X, X, X";
LC6_B1 : LORAX2 = "X, X, X, OD4P5";
END;
'''


class OrderedFitParserTests(unittest.TestCase):
    def test_explicit_slots_resolve_pins_cells_and_unknowns(self):
        parsed = parse_fit_slots(fit(), DEVICE)
        self.assertEqual(parsed['slots']['LC3_B1'], (None, '_LC2_B1', None, None))
        self.assertEqual(parsed['slots']['LC6_B1'], (None, None, None, '/RESET'))
        self.assertEqual(parsed['selected_slot_row_count'], 6)
        self.assertEqual(parsed['input_pin_count'], 5)

    def test_ordered_tables_match_independent_boolean_evaluation(self):
        tables, meta = ordered_tables(report(), fit(), DEVICE)
        # Evaluate each artificial cell directly in the ordered slot variables.
        expected = [0]*8
        for n in range(16):
            a, b, c, d = [(n >> i) & 1 for i in range(4)]
            values = [a & b & c & d, a | b, b, c, 1 ^ a, d, 1, 0]
            for k, value in enumerate(values): expected[k] |= value << n
        self.assertEqual(tables, tuple(expected))
        self.assertEqual([c['explicit_slot_row'] for c in meta['cells']], [True]*6+[False]*2)
        self.assertEqual([c['data_constant'] for c in meta['cells']], [False]*6+[True]*2)

    def test_compiler_version_timestamp_and_design_mismatch_rejected(self):
        for bad in (fit().replace('0.1 test', '0.2 other'),
                    fit().replace('04:05:06', '04:05:07'),
                    fit().replace('INTERNAL_INFO "artificial"', 'INTERNAL_INFO "other"'),
                    fit()+'-- Compiled: 01/02/03 04:05:06\n'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                ordered_tables(report(), bad, DEVICE)

    def test_target_declarations_are_both_required_and_exact(self):
        for bad in (fit().replace('DEVICE = EPF8282ALC84-2;', 'DEVICE = EPM5130QC;'),
                    fit().replace('DEVICE = "EPF8282ALC84-2";', ''),
                    fit()+'DEVICE = EPF8282ALC84-2;\n'):
            with self.assertRaises(ValueError): parse_fit_slots(bad, DEVICE)

    def test_ambiguous_pins_slots_and_malformed_tokens_rejected(self):
        for old, new in [
            ('"b" : INPUT_PIN = 2;', '"b" : INPUT_PIN = 1;'),
            ('"b" : INPUT_PIN = 2;', '"a" : INPUT_PIN = 2;'),
            ('OD2P3, OD3P4', 'OD2P3, OD9P99'),
            ('OD2P3, OD3P4', 'OD2P3, SOMETHING'),
            ('OD2P3, OD3P4', 'OD2P3'),
            ('OD2P3, OD3P4', 'OD2P3, OD0P1'),
            ('LC1_B1 : LORAX2', 'LC9_B1 : LORAX2'),
            ('LC2_B1 : LORAX2', 'LC1_B1 : LORAX2'),
        ]:
            with self.subTest(old=old,new=new), self.assertRaises(ValueError):
                parse_fit_slots(fit().replace(old,new), DEVICE)

    def test_missing_connected_data_source_is_not_filled_with_zero(self):
        for bad in (fit().replace('OD2P3, OD3P4','OD2P3, X'),
                    fit().replace('LC4_B1 : LORAX2 = "X, X, OD0P1, X";','')):
            with self.assertRaisesRegex(ValueError,'source|nonconstant'):
                ordered_tables(report(), bad, DEVICE)

    def test_missing_constant_row_never_claims_physical_disconnection(self):
        _, meta = ordered_tables(report(), fit(), DEVICE)
        self.assertEqual(meta['cells'][6], {'cell':7,'explicit_slot_row':False,
                                          'report_data_variables':0,'connected_slot_count':0,'data_constant':True})
        self.assertNotIn('physical_input_disconnected', meta['cells'][6])
        for invalid in ('B99', '', 1):
            with self.assertRaises((TypeError,ValueError)):
                parse_fit_slots(fit(), DEVICE, invalid)


class SharedSlotConstraintTests(unittest.TestCase):
    def test_known_common_order_is_unique_for_artificial_cells(self):
        ordered, _ = ordered_tables(report(), fit(), DEVICE)
        permutation = (2,0,3,1)
        raw = tuple(transform(t,permutation,15,0) for t in ordered)
        result = common_slot_permutations(raw, ordered)
        self.assertEqual(result['shared_slot_orders'], [list(permutation)])
        self.assertFalse(result['physical_routing_verified'])

    def test_no_per_cell_reordering_to_rescue_a_conflict(self):
        ordered = (0xAAAA,)*8
        raw = (0x5555, 0x3333)+(0x5555,)*6
        self.assertEqual(common_slot_permutations(raw,ordered)['shared_slot_order_count'],0)

    def test_symmetric_functions_retain_multiple_orders(self):
        result = common_slot_permutations((0xFFFF,)*8,(0xFFFF,)*8)
        self.assertEqual(result['shared_slot_order_count'],24)

    def test_full_permutation_results_match_independent_assignment_oracle(self):
        rng=random.Random(1948)
        for _ in range(6):
            ordered=tuple(rng.randrange(65536) for _ in range(8))
            p=tuple(rng.sample(range(4),4))
            def independent(table,p):
                value=0
                for n in range(16):
                    raw=[1-(n//(2**j))%2 for j in range(4)]
                    index=sum(raw[p[j]]*2**j for j in range(4))
                    value+=((table//(2**index))%2)*2**n
                return value
            raw=tuple(independent(t,p) for t in ordered)
            candidates=[list(q) for q in itertools.permutations(range(4))
                        if all(independent(t,q)==r for t,r in zip(ordered,raw))]
            self.assertEqual(common_slot_permutations(raw,ordered)['shared_slot_orders'],candidates)

    def test_invalid_tables_do_not_produce_candidates(self):
        for bad in ([0]*7, [True]*8, [65536]*8):
            with self.assertRaises(ValueError): common_slot_permutations(bad,(0,)*8)


class PinnedSlotPipelineTests(unittest.TestCase):
    def fixture(self):
        ordered,_=ordered_tables(report(),fit(),DEVICE)
        raw=tuple(transform(t,(2,0,3,1),15,0) for t in ordered)
        data=0
        for cell,t in enumerate(raw):
            for j,off in enumerate(tile_offsets(8,177,1)):
                data|=((t>>j)&1)<<(CANDIDATE['first_bit']+cell*CANDIDATE['cell_stride']+off)
        files=(rcs(sof(data.to_bytes(PACKED_BYTES,'little'))),rcs(report().encode()),rcs(fit().encode()))
        pins={name:git_blob_sha1(data) for name,data in zip(PINNED,files)}
        return files,pins

    def test_end_to_end_keeps_raw_tables_and_reference_net_names_private(self):
        files,pins=self.fixture()
        with patch('arcaderecomp.flex8000_fit_slots.PINNED',pins):
            result=audit_pinned_inputs(*files)
        self.assertEqual(result['ordered_fit_result']['shared_slot_orders'],[[2,0,3,1]])
        self.assertFalse(result['netlist_recovered'])
        text=json.dumps(result)
        for token in ('normalized_table','packed','/RESET','_LC2_B1','artificial'):
            self.assertNotIn(token,text)

    def test_any_of_three_changed_blobs_is_rejected_before_interpretation(self):
        files,pins=self.fixture()
        with patch('arcaderecomp.flex8000_fit_slots.PINNED',pins):
            for i in range(3):
                changed=list(files);changed[i]+=b' '
                with self.assertRaisesRegex(ValueError,'identity'):audit_pinned_inputs(*changed)

if __name__=='__main__':unittest.main()
