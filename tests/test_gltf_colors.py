"""Validate color conversion without touching exported mesh geometry."""
import importlib.util
import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools' / 'convert_gltf_colors.py'
spec = importlib.util.spec_from_file_location('convert_gltf_colors', SCRIPT)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)
ASSETS = (
    'assets/creekside-yup-v03.glb',
    'assets/coastal-fishing-hut-pier-yup.glb',
    'assets/rural-railway-stop-freight-wagon-yup.glb',
)


def chunks(content):
    offset = 12
    result = []
    while offset < len(content):
        size, kind = struct.unpack_from('<I4s', content, offset)
        offset += 8
        result.append((kind, content[offset:offset + size]))
        offset += size
    return result


class GLTFColorTests(unittest.TestCase):
    def test_srgb_reference_values(self):
        self.assertAlmostEqual(converter.srgb_to_linear(0), 0)
        self.assertAlmostEqual(converter.srgb_to_linear(1), 1)
        self.assertAlmostEqual(converter.srgb_to_linear(0.5), 0.21404114048223255)
        self.assertAlmostEqual(converter.srgb_to_linear(0.04045), 0.0031308049535603713)
        with self.assertRaises(ValueError):
            converter.srgb_to_linear(float('nan'))
        with self.assertRaises(ValueError):
            converter.srgb_to_linear(1.5)

    def test_conversion_preserves_all_geometry_and_alpha(self):
        for relative in ASSETS:
            with self.subTest(relative=relative):
                source = (ROOT / relative).read_bytes()
                result, count = converter.convert_glb(source)
                old, new = chunks(source), chunks(result)
                self.assertEqual(old[1], new[1], 'Binary mesh buffer must remain byte-identical')
                a, b = json.loads(old[0][1]), json.loads(new[0][1])
                self.assertEqual(len(a['materials']), count)
                for ma, mb in zip(a['materials'], b['materials']):
                    ra = ma['pbrMetallicRoughness']['baseColorFactor']
                    rb = mb['pbrMetallicRoughness']['baseColorFactor']
                    self.assertEqual(ra[3], rb[3])
                    for x, y in zip(ra[:3], rb[:3]):
                        self.assertAlmostEqual(y, converter.srgb_to_linear(x))
                b['materials'] = a['materials']
                self.assertEqual(a, b, 'Only material factors may change')
                self.assertEqual(struct.unpack_from('<I', result, 8)[0], len(result))

    def test_invalid_glb_is_rejected(self):
        with self.assertRaises(ValueError):
            converter.convert_glb(b'garbage')


if __name__ == '__main__':
    unittest.main(verbosity=2)
