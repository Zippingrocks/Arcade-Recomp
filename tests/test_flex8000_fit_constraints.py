"""Independent synthetic equation/encoding tests; no third-party design data."""
import itertools
import json
import random
import unittest
from unittest.mock import patch

from arcaderecomp.flex8000_fit_constraints import (
    parse_expression,table_from_ast,evaluate,parse_fitted_report,
    transform,common_conventions,audit_pinned_inputs)
from arcaderecomp.flex8000_lut_tiles import CANDIDATE,tile_offsets
from arcaderecomp.flex8000_compare import git_blob_sha1
from arcaderecomp.flex8000_sram import PACKED_BYTES
from test_flex8000_sram import rcs,sof


def report():
    # Artificial names/functions. Cell 2's physical output alias complements
    # its logical name; cell 3 consumes that logical name. Cell 7 is a DFF.
    return '''Device: EPF8282ALC84-2
_EQ101 = a & b & c & d;
_EQ102 = a # b;
!_LC2_B1 = _LC2_B1~NOT;
_LC1_B1 = LCELL(_EQ101);
_LC2_B1~NOT = LCELL(_EQ102);
_LC3_B1 = LCELL(!_LC2_B1);
_LC4_B1 = LCELL(a);
_LC5_B1 = LCELL(!a);
_LC6_B1 = LCELL(/RESET);
_LC7_B1 = DFF(VCC, clock, clear, VCC);
_LC8_B1 = LCELL(GND);
'''


class FittedParserTests(unittest.TestCase):
    def test_precedence_parentheses_and_active_low_names(self):
        ast=parse_expression('!a & (b # /RESET)')
        for a,b,r in itertools.product((0,1),repeat=3):
            self.assertEqual(evaluate(ast,{'a':a,'b':b,'/RESET':r},set()),int(not a and (b or r)))
        table,n=table_from_ast(parse_expression('/RESET'))
        self.assertEqual((table,n),(0xaaaa,1)) # Slash is part of name, NOT inversion.

    def test_normalizes_only_explicit_report_aliases(self):
        cells=parse_fitted_report(report(),'EPF8282ALC84-2')['cells']
        self.assertEqual(cells[2]['logical_table'],0x5555)
        self.assertEqual(cells[2]['normalized_table'],0xaaaa)
        self.assertEqual(cells[6]['normalized_table'],0xffff)
        self.assertEqual(cells[6]['kind'],'DFF')
        self.assertEqual(cells[7]['normalized_table'],0)
        self.assertEqual(sum(c['inverted_output_alias'] for c in cells),1)

    def test_bad_device_alias_definition_and_equation_are_rejected(self):
        for text in (report().replace('Device: EPF8282ALC84-2','Device: EPM5130QC'),
                     report()+'Device: EPF8282ALC84-2\n',
                     report()+'_EQ101 = a;\n',
                     report()+'_LC1_B1 = LCELL(a);\n',
                     report().replace('_LC2_B1~NOT;', '_LC3_B1~NOT;'),
                     report().replace('_EQ101);','_EQ999);'),
                     report().replace('a & b & c & d','a & b & c & d & e'),
                     report().replace('!_LC2_B1);','!_LC1_A1);')):
            with self.subTest(text=text),self.assertRaises(ValueError):
                parse_fitted_report(text,'EPF8282ALC84-2')

    def test_does_not_evaluate_clock_or_unsupported_function_syntax(self):
        parsed=parse_fitted_report(report(),'EPF8282ALC84-2')
        self.assertFalse(parsed['clock_or_routing_decoded'])
        for bad in ('a + b','__import__(x)','a b','a &','((a)','!','a ^ b','('*40+'a'+')'*40):
            with self.subTest(bad=bad),self.assertRaises(ValueError):parse_expression(bad)
        with self.assertRaises(ValueError):
            parse_fitted_report(report().replace('DFF(VCC, clock, clear, VCC)','DFF(VCC, clock)'),'EPF8282ALC84-2')


class ConventionTests(unittest.TestCase):
    def test_transform_matches_independent_tuple_oracle(self):
        rng=random.Random(391)
        for _ in range(100):
            table=rng.randrange(65536);p=tuple(rng.sample(range(4),4));mask=rng.randrange(16);inv=rng.randrange(2)
            wanted=[]
            for x in range(16):
                inputs=[(x//2**i)%2 for i in range(4)]
                for i in range(4):inputs[i]^=(mask//2**i)%2
                address=sum(inputs[p[j]]*2**j for j in range(4))
                wanted.append(((table//2**address)%2)^inv)
            self.assertEqual(transform(table,p,mask,inv),sum(v*2**i for i,v in enumerate(wanted)))

    def test_one_common_encoding_recovers_planted_convention(self):
        rng=random.Random(51)
        expected=tuple(rng.randrange(65536) for _ in range(8))
        raw=tuple(transform(t,tuple(rng.sample(range(4),4)),10,1) for t in expected)
        r=common_conventions(raw,expected)
        self.assertTrue(any(x['address_xor']==10 and x['output_xor']==1 for x in r['conventions']))
        self.assertFalse(r['physical_input_assignment_verified'])

    def test_symmetry_does_not_turn_into_unique_pin_assignment(self):
        r=common_conventions((0xffff,)*8,(0xffff,)*8)
        self.assertEqual(r['common_convention_count'],16)
        self.assertTrue(all(x['per_cell_permutation_counts']==[24]*8 for x in r['conventions']))

    def test_per_cell_output_fudging_is_rejected(self):
        r=common_conventions((0,0xffff,0,0,0,0,0,0),(0,)*8)
        self.assertEqual(r['common_convention_count'],0)

    def test_invalid_domains_rejected(self):
        for raw,expected in (([0]*7,[0]*8),([True]*8,[0]*8),([-1]*8,[0]*8)):
            with self.assertRaises(ValueError):common_conventions(raw,expected)
        for p,m,i in (((0,0,2,3),0,0),((0,1,2,3),16,0),((0,1,2,3),0,2)):
            with self.assertRaises(ValueError):transform(0,p,m,i)


class FullSyntheticAuditTests(unittest.TestCase):
    def fixture(self):
        text=report()
        cells=parse_fitted_report(text,'EPF8282ALC84-2')['cells']
        raw=[transform(c['normalized_table'],(3,1,0,2),6,1) for c in cells]
        value=0;offsets=tile_offsets(8,177,1)
        for i,t in enumerate(raw):
            for j,delta in enumerate(offsets):
                value|=((t>>j)&1)<<(CANDIDATE['first_bit']+i*CANDIDATE['cell_stride']+delta)
        a,b=rcs(sof(value.to_bytes(PACKED_BYTES,'little'))),rcs(text.encode('ascii'))
        return a,b,{'testmux.sof,v':git_blob_sha1(a),'testmux.rpt,v':git_blob_sha1(b)}

    def test_pinned_pipeline_keeps_raw_configuration_and_tables_out_of_report(self):
        a,b,pins=self.fixture()
        with patch('arcaderecomp.flex8000_fit_constraints.PINNED',pins):r=audit_pinned_inputs(a,b)
        self.assertTrue(any(c['address_xor']==6 and c['output_xor']==1
                            for c in r['models']['normalized_fitted_output_aliases']['conventions']))
        self.assertEqual(r['registered_data_cells'],1)
        self.assertEqual(r['cell_count'],8)
        self.assertFalse(r['netlist_recovered']);self.assertFalse(r['runtime_changed'])
        text=json.dumps(r)
        for key in ('logical_table','normalized_table','packed','VCC','_LC1_B1'):
            self.assertNotIn(key,text)

    def test_changed_reference_refused_before_interpretation(self):
        a,b,pins=self.fixture()
        with patch('arcaderecomp.flex8000_fit_constraints.PINNED',pins):
            with self.assertRaisesRegex(ValueError,'identity'):audit_pinned_inputs(a+b' ',b)

    def test_expected_report_input_count_and_bank_guards(self):
        cells=parse_fitted_report(report(),'EPF8282ALC84-2')['cells']
        self.assertEqual([c['input_count'] for c in cells],[4,2,1,1,1,1,0,0])
        with self.assertRaises(ValueError):parse_fitted_report(report(),'EPF8282ALC84-2','B99')

if __name__=='__main__':unittest.main()
