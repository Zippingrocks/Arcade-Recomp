"""Synthetic pointer-table tests; no game bytes or real chip layout in CI."""
import struct
import unittest
from arcaderecomp.memory_test_layout import audit_hotdo, cstring, descriptor_groups

class MemoryTestLayoutTests(unittest.TestCase):
    def image(self):
        image=bytearray(1024)
        struct.pack_into('<2I',image,0,0x100,0)
        struct.pack_into('<6I',image,0x100,0x200,1,2,0xffff,0x00500000,0x100)
        struct.pack_into('<I',image,0x208,0x300)
        image[0x300:0x315]=b'IC12 CHECK IC34 CHECK\0'
        return image

    def test_table_metadata_and_chip_designators(self):
        result=descriptor_groups(bytes(self.image()),0)
        self.assertEqual(len(result),1)
        item=result[0]['descriptors'][0]
        self.assertEqual(item['chip_designators'],[12,34])
        self.assertEqual(item['address_field'],'0x500000')
        self.assertNotIn('display_text',item)

    def test_invalid_duplicate_and_unmapped_pointers_rejected(self):
        for pointer in [0x101,0x400,0xffffffff]:
            image=self.image();struct.pack_into('<I',image,0,pointer)
            with self.assertRaises(ValueError):descriptor_groups(bytes(image),0)
        image=self.image();struct.pack_into('<I',image,4,0x100)
        with self.assertRaises(ValueError):descriptor_groups(bytes(image),0)

    def test_invalid_text_and_span_rejected(self):
        image=self.image();image[0x300:0x3a0]=b'X'*160
        with self.assertRaises(ValueError):descriptor_groups(bytes(image),0)
        image=self.image();struct.pack_into('<I',image,0x114,0)
        with self.assertRaises(ValueError):descriptor_groups(bytes(image),0)
        with self.assertRaises(ValueError):cstring(b'\xff\0',0)

    def test_blank_display_labels_are_explicit_not_inherited(self):
        image=self.image();image[0x300:0x302]=b' \0'
        item=descriptor_groups(bytes(image),0)[0]['descriptors'][0]
        self.assertTrue(item['display_label_blank'])
        self.assertEqual(item['chip_designators'],[])

    def test_hotdo_profile_refuses_unverified_image(self):
        with self.assertRaisesRegex(ValueError,'verified'):
            audit_hotdo(bytes(self.image()))

if __name__=='__main__':unittest.main()
