"""Dependency-free integrity checks for the actual shipped GLB geometry.

Validates buffers, indices, finite vertex positions, non-degenerate triangles,
and expected mesh/material counts. Does not reconstruct modeling history.
"""
import json
import math
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "assets/creekside-yup-v03.glb": (28, 15582, 14),
    "assets/coastal-fishing-hut-pier-yup.glb": (49, 13718, 27),
    "assets/rural-railway-stop-freight-wagon-yup.glb": (64, 21722, 37),
}
COMPONENT = {5121: ('B', 1), 5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}


def read_glb(path):
    data = path.read_bytes()
    if data[:4] != b'glTF' or len(data) < 28:
        raise ValueError('Invalid GLB header')
    if struct.unpack_from('<I', data, 8)[0] != len(data):
        raise ValueError('GLB length mismatch')
    offset = 12
    chunks = []
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('Truncated chunk header')
        length, kind = struct.unpack_from('<I4s', data, offset)
        offset += 8
        if offset + length > len(data):
            raise ValueError('Truncated GLB chunk')
        chunks.append((kind, data[offset:offset + length]))
        offset += length
    if len(chunks) != 2 or chunks[0][0] != b'JSON' or chunks[1][0] != b'BIN\x00':
        raise ValueError('Expected JSON and BIN chunks')
    return json.loads(chunks[0][1]), chunks[1][1]


def accessor_values(document, binary, accessor_index):
    accessor = document['accessors'][accessor_index]
    view = document['bufferViews'][accessor['bufferView']]
    component_format, component_size = COMPONENT[accessor['componentType']]
    components = {'SCALAR': 1, 'VEC3': 3}[accessor['type']]
    packed = struct.Struct('<' + component_format * components)
    stride = view.get('byteStride', component_size * components)
    start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    count = accessor['count']
    if stride < packed.size or start < 0 or start + max(0, count - 1) * stride + packed.size > len(binary):
        raise ValueError(f'Accessor {accessor_index} exceeds BIN chunk')
    if count and start + (count - 1) * stride + packed.size > view.get('byteOffset', 0) + view['byteLength']:
        raise ValueError(f'Accessor {accessor_index} exceeds bufferView')
    return [packed.unpack_from(binary, start + i * stride) for i in range(count)]


def squared_double_area(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    cx, cy, cz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    return cx * cx + cy * cy + cz * cz


class ExportGeometryTests(unittest.TestCase):
    def test_01_exported_geometry_is_finite_and_non_degenerate(self):
        for name, expected in EXPECTED.items():
            with self.subTest(asset=name):
                document, binary = read_glb(ROOT / name)
                self.assertEqual(len(document['meshes']), expected[0])
                self.assertEqual(len(document.get('materials', [])), expected[2])
                triangle_count = 0
                positions_count = 0
                min_coords = [float('inf')] * 3
                max_coords = [float('-inf')] * 3
                for mesh in document['meshes']:
                    for primitive in mesh['primitives']:
                        self.assertEqual(primitive.get('mode', 4), 4, 'Non-triangle primitive')
                        positions = accessor_values(document, binary, primitive['attributes']['POSITION'])
                        self.assertTrue(positions)
                        for vertex in positions:
                            self.assertTrue(all(math.isfinite(x) for x in vertex), 'Non-finite vertex')
                            for axis in range(3):
                                min_coords[axis] = min(min_coords[axis], vertex[axis])
                                max_coords[axis] = max(max_coords[axis], vertex[axis])
                        if 'indices' in primitive:
                            indices = [v[0] for v in accessor_values(document, binary, primitive['indices'])]
                        else:
                            indices = list(range(len(positions)))
                        self.assertEqual(len(indices) % 3, 0)
                        self.assertTrue(all(0 <= i < len(positions) for i in indices), 'Index out of range')
                        for i in range(0, len(indices), 3):
                            a, b, c = (positions[indices[i + j]] for j in range(3))
                            self.assertGreater(squared_double_area(a, b, c), 1e-20, 'Degenerate triangle')
                        triangle_count += len(indices) // 3
                        positions_count += len(positions)
                self.assertEqual(triangle_count, expected[1])
                self.assertGreater(positions_count, 0)
                extents = [max_coords[i] - min_coords[i] for i in range(3)]
                self.assertTrue(all(0.1 < extent < 1000 for extent in extents), f'Unexpected bounds: {extents}')
                print(f'{name}: {triangle_count} non-degenerate triangles, {positions_count} vertex positions')


if __name__ == '__main__':
    unittest.main(verbosity=2)
