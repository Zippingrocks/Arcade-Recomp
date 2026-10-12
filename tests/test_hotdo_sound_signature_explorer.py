"""ROM-free identity and lane tests for the private sound explorer inputs."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.experimental.hotdo_sound_signature_explorer import (
    SAMPLE_CHIPS, authenticate_samples)


class SoundSignatureExplorerInputTest(unittest.TestCase):
    def test_two_identity_selected_chips_are_word_swapped_in_manifest_order(self):
        first = bytes(range(256)) * 0x4000
        second = bytes(reversed(range(256))) * 0x4000
        identities = {hashlib.sha1(first).hexdigest(): 0,
                      hashlib.sha1(second).hexdigest(): 0x400000}
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "arbitrary-a", Path(folder) / "arbitrary-b"
            a.write_bytes(second); b.write_bytes(first)
            with mock.patch.dict(SAMPLE_CHIPS, identities, clear=True):
                region = authenticate_samples((a, b))
                self.assertEqual(region[:4], bytes((1, 0, 3, 2)))
                self.assertEqual(region[0x400000:0x400004], bytes((254, 255, 252, 253)))
                with self.assertRaisesRegex(ValueError, "size/SHA-1"):
                    authenticate_samples((a, a))

    def test_wrong_size_or_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a", Path(folder) / "b"
            a.write_bytes(b"wrong"); b.write_bytes(bytes(0x400000))
            for paths in ((a, b), (b, b)):
                with self.assertRaisesRegex(ValueError, "size/SHA-1"):
                    authenticate_samples(paths)


if __name__ == "__main__":
    unittest.main()
