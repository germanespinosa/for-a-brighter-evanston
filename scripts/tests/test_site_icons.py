"""Verify favicon formats reproduce the approved artwork, not another logo."""
import base64
import io
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
from typing import cast
from PIL import Image
from PIL.IcoImagePlugin import IcoImageFile
ROOT = Path(__file__).resolve().parents[2]


class SiteIconTests(unittest.TestCase):
    def test_png_icons_are_faithful_square_derivatives(self):
        with Image.open(ROOT / 'assets/img/brand-icon.png') as source:
            master = source.convert('RGBA')
        for relative, size in [('assets/img/icon-48.png', 48),
                               ('assets/img/icon-192.png', 192),
                               ('assets/img/icon-512.png', 512),
                               ('assets/img/apple-touch-icon.png', 180),
                               ('assets/img/logo-512.png', 512)]:
            with self.subTest(path=relative), Image.open(ROOT / relative) as opened:
                actual = opened.convert('RGBA')
                expected = master.resize((size, size), Image.Resampling.LANCZOS)
                self.assertEqual(actual.size, (size, size))
                self.assertTrue(actual.tobytes() == expected.tobytes(), relative)

    def test_ico_and_svg_use_the_same_approved_icon(self):
        with Image.open(ROOT / 'assets/img/brand-icon.png') as opened:
            master = opened.convert('RGBA')
        with Image.open(ROOT / 'favicon.ico') as opened:
            ico = cast(IcoImageFile, opened)
            self.assertEqual(ico.ico.sizes(), {(16, 16), (32, 32), (48, 48)})
            for size in ico.ico.sizes():
                actual = ico.ico.getimage(size).convert('RGBA')
                expected = master.resize(size, Image.Resampling.LANCZOS)
                self.assertTrue(actual.tobytes() == expected.tobytes(), f'ICO frame {size}')
        root = ET.fromstring((ROOT / 'favicon.svg').read_text())
        image = root.find('{http://www.w3.org/2000/svg}image')
        self.assertIsNotNone(image)
        assert image is not None
        uri = image.attrib['href']
        self.assertTrue(uri.startswith('data:image/png;base64,'))
        embedded = Image.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[1]))).convert('RGBA')
        self.assertEqual(embedded.size, (192, 192))
        self.assertTrue(embedded.tobytes() == master.resize((192, 192), Image.Resampling.LANCZOS).tobytes())


if __name__ == '__main__':
    unittest.main()
