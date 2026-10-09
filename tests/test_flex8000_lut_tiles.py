"""Artificial tile-layout tests: no Sega or archived design bytes enter CI."""
from pathlib import Path
import random
import tempfile
import unittest

from arcaderecomp.flex8000_lut_probe import TABLES
from arcaderecomp.flex8000_lut_tiles import (
    CELL_CLASSES,CANDIDATE,classes,tile_offsets,shapes,class_positions,
    scan_tiles,candidate_tables,target_agrees,original_metadata)


def make_sample(candidate=None,width=2048):
    c=candidate or {'first_bit':5,'cell_stride':184,'rows':8,'row_pitch':23,'column_step':1}
    offsets=tile_offsets(c['rows'],c['row_pitch'],c['column_step'])
    data=0
    for cell,group in enumerate(CELL_CLASSES):
        table=TABLES[group]
        for bit,offset in enumerate(offsets):
            data |= ((table >> bit) & 1) << (c['first_bit']+cell*c['cell_stride']+offset)
    return data.to_bytes((width+7)//8,'little'),c


class TiledLutTests(unittest.TestCase):
    def test_default_domain_is_bounded_and_exactly_580_valid_shapes(self):
        self.assertEqual(len(shapes()),580)
        self.assertEqual(len(set(shapes())),580)
        for shape in shapes():self.assertEqual(len(set(tile_offsets(*shape))),16)

    def test_parallel_counter_matches_slow_independent_scalar_oracle(self):
        rng=random.Random(8282)
        for width in (257,1024):
            data=rng.getrandbits(width)
            packed=data.to_bytes((width+7)//8,'little')
            for shape in ((2,19,1),(4,29,3),(8,23,2)):
                offsets=tile_offsets(*shape)
                fast=class_positions(packed,width,offsets)
                slow=[set() for _ in classes()]
                bits=[(packed[i//8]>>(i%8))&1 for i in range(width)]
                for start in range(width-max(offsets)):
                    value=0
                    for i,offset in enumerate(offsets):
                        value+=bits[start+offset]*(2**i)
                    for j,group in enumerate(classes()):
                        if value in group:slow[j].add(start)
                self.assertEqual(fast,tuple(slow))

    def test_discovery_finds_inserted_tile_and_validates_remaining_cells(self):
        sample,c=make_sample()
        result=scan_tiles(sample,2048,((8,23,1),))
        self.assertIn({'first_bit':c['first_bit'],'cell_stride':c['cell_stride']},
                      result['results'][0]['eight_cell_candidates'])
        self.assertGreaterEqual(result['four_cell_candidates'],result['eight_cell_candidate_count'])
        self.assertFalse(result['physical_layout_verified'])

    def test_discovery_supports_negative_cell_order_without_refitting(self):
        sample,c=make_sample({'first_bit':1293,'cell_stride':-184,'rows':8,'row_pitch':23,'column_step':1})
        result=scan_tiles(sample,2048,((8,23,1),))
        self.assertIn({'first_bit':1293,'cell_stride':-184},result['results'][0]['eight_cell_candidates'])

    def test_exact_bit_extraction_preserves_table_order(self):
        sample,c=make_sample()
        self.assertEqual(candidate_tables(sample,c,2048),tuple(TABLES[g] for g in CELL_CLASSES))

    def test_four_cell_discovery_does_not_promote_failed_buffer_validation(self):
        sample,c=make_sample()
        value=int.from_bytes(sample,'little')
        # Flip one buffer truth bit. Its population becomes 7 or 9, not a buffer.
        value ^= 1 << (c['first_bit']+3*c['cell_stride'])
        result=scan_tiles(value.to_bytes(len(sample),'little'),2048,((8,23,1),))
        target={'first_bit':c['first_bit'],'cell_stride':c['cell_stride']}
        self.assertGreater(result['four_cell_candidates'],0)
        self.assertNotIn(target,result['results'][0]['eight_cell_candidates'])

    def test_uniform_negative_control_does_not_create_a_match(self):
        for fill in (0,255):
            result=scan_tiles(bytes([fill])*256,2048,((8,23,1),))
            self.assertEqual(result['eight_cell_candidate_count'],0)

    def test_bad_geometry_padding_and_out_of_range_rejected(self):
        for shape in ((True,23,1),(3,23,1),(8,0,1),(8,709,1),(8,23,213),(8,1,1)):
            with self.assertRaises(ValueError):tile_offsets(*shape)
        with self.assertRaises(ValueError):class_positions(b'\xff'*33,257,tuple(range(16)))
        with self.assertRaises(ValueError):class_positions(b'\0'*32,256,tuple([1]*16))
        with self.assertRaises(ValueError):scan_tiles(b'\0'*256,2048,((8,23,1),(8,23,1)))
        with self.assertRaises(ValueError):scan_tiles(b'\0'*2,16,((8,23,1),))

    def test_candidate_cannot_alias_cells_or_escape_buffer(self):
        sample,c=make_sample()
        for bad in (dict(c,cell_stride=0),dict(c,cell_stride=1),dict(c,first_bit=2040),dict(c,cell_stride=-184),dict(c,extra=True)):
            with self.assertRaises(ValueError):candidate_tables(sample,bad,2048)

    def test_same_basename_or_supported_part_list_cannot_override_target_mismatch(self):
        sof={'device':'EPF8282ALC84-2'}
        self.assertTrue(target_agrees(sof,'Other\n Device: EPF8282ALC84-2\n'))
        self.assertFalse(target_agrees(sof,'AUTO_DEVICE=EPF8282ALC84-2;\nDevice: EPM5130QC'))
        self.assertFalse(target_agrees(sof,'Device: EPF8282ALC84-3'))

    def test_original_profile_rejects_any_unverified_input(self):
        for wrong in (b'',b'\0'*0x200000):
            with self.assertRaises(ValueError):original_metadata(wrong)

    def test_candidate_selects_exactly_128_bits_but_never_claims_netlist(self):
        offsets=tile_offsets(CANDIDATE['rows'],CANDIDATE['row_pitch'],CANDIDATE['column_step'])
        selected={CANDIDATE['first_bit']+i*CANDIDATE['cell_stride']+o for i in range(8) for o in offsets}
        self.assertEqual(len(selected),128)
        self.assertEqual(min(selected),22138)
        self.assertEqual(max(selected),33290)
        self.assertLess(max(selected),37524)


if __name__=='__main__':unittest.main()
