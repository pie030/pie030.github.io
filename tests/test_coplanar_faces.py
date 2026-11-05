"""Detect exact coincident, same-facing GLB triangles (a common z-fighting source).

Touching solids can legitimately share a boundary with opposite normals.
This test distinguishes those seams from duplicate visible faces; it does not
claim to detect every possible partial or near-coplanar overlap.
"""
import math
import unittest
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from test_glb_geometry import accessor_values, read_glb

ROOT = Path(__file__).resolve().parents[1]
ASSETS = (
    "assets/creekside-yup-v03.glb",
    "assets/coastal-fishing-hut-pier-yup.glb",
    "assets/rural-railway-stop-freight-wagon-yup.glb",
)


def multiply(a, b):
    return [[sum(a[r][k] * b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def local_matrix(node):
    if "matrix" in node:
        m = node["matrix"]  # glTF stores 4x4 matrices column-major.
        return [[m[4 * c + r] for c in range(4)] for r in range(4)]
    x, y, z, w = node.get("rotation", [0, 0, 0, 1])
    sx, sy, sz = node.get("scale", [1, 1, 1])
    tx, ty, tz = node.get("translation", [0, 0, 0])
    return [
        [(1 - 2 * (y*y + z*z))*sx, 2*(x*y - z*w)*sy, 2*(x*z + y*w)*sz, tx],
        [2*(x*y + z*w)*sx, (1 - 2*(x*x + z*z))*sy, 2*(y*z - x*w)*sz, ty],
        [2*(x*z - y*w)*sx, 2*(y*z + x*w)*sy, (1 - 2*(x*x + y*y))*sz, tz],
        [0, 0, 0, 1],
    ]


def transform(m, vertex):
    return tuple(sum(m[row][col] * vertex[col] for col in range(3)) + m[row][3]
                 for row in range(3))


def world_matrices(nodes):
    parents = {}
    for parent, node in enumerate(nodes):
        for child in node.get("children", []):
            if child in parents:
                raise ValueError("Node has multiple parents")
            parents[child] = parent

    @lru_cache(maxsize=None)
    def world(index):
        local = local_matrix(nodes[index])
        return multiply(world(parents[index]), local) if index in parents else local

    return [world(index) for index in range(len(nodes))]


def unit_normal(triangle):
    a, b, c = triangle
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    normal = (u[1]*v[2] - u[2]*v[1], u[2]*v[0] - u[0]*v[2], u[0]*v[1] - u[1]*v[0])
    magnitude = math.sqrt(sum(n*n for n in normal))
    return tuple(n / magnitude for n in normal) if magnitude else None


def face_key(triangle):
    return tuple(sorted(tuple(round(component, 5) for component in vertex) for vertex in triangle))


def classify_faces(faces):
    seen = defaultdict(list)
    same_facing = []
    shared_boundaries = 0
    for label, triangle in faces:
        normal = unit_normal(triangle)
        if normal is None:
            continue  # Degenerate faces are rejected by test_glb_geometry.
        key = face_key(triangle)
        matches = seen[key]
        for other_label, other_normal in matches:
            dot = sum(a*b for a, b in zip(normal, other_normal))
            if dot > 0.9999:
                same_facing.append((other_label, label))
            elif dot < -0.9999:
                shared_boundaries += 1
            else:
                same_facing.append((other_label, label))
        matches.append((label, normal))
    return same_facing, shared_boundaries


def scene_faces(document, binary):
    matrices = world_matrices(document["nodes"])
    for node_index, node in enumerate(document["nodes"]):
        if "mesh" not in node:
            continue
        for primitive_index, primitive in enumerate(document["meshes"][node["mesh"]]["primitives"]):
            positions = accessor_values(document, binary, primitive["attributes"]["POSITION"])
            positions = [transform(matrices[node_index], vertex) for vertex in positions]
            if "indices" in primitive:
                indices = [value[0] for value in accessor_values(document, binary, primitive["indices"])]
            else:
                indices = list(range(len(positions)))
            label = f"{node.get('name', node_index)}/primitive-{primitive_index}"
            for i in range(0, len(indices), 3):
                yield label, tuple(positions[indices[i + j]] for j in range(3))


class CoincidentFaceTests(unittest.TestCase):
    def test_01_detects_same_facing_but_allows_touching_solid_boundaries(self):
        triangle = ((0., 0., 0.), (1., 0., 0.), (0., 1., 0.))
        same, shared = classify_faces((("a", triangle), ("b", triangle)))
        self.assertEqual(same, [("a", "b")])
        self.assertEqual(shared, 0)
        same, shared = classify_faces((("a", triangle), ("b", triangle[::-1])))
        self.assertEqual(same, [])
        self.assertEqual(shared, 1)

    def test_02_world_transform_supports_translation_and_rotation(self):
        nodes = [
            {"translation": [3, 0, 0], "children": [1]},
            {"translation": [0, 2, 0], "rotation": [0, 0, 1, 0]},
        ]
        matrices = world_matrices(nodes)
        result = transform(matrices[1], (1, 0, 0))
        self.assertEqual(tuple(round(x, 6) for x in result), (2., 2., 0.))

    def test_03_no_same_facing_exact_overlaps_in_exported_scenes(self):
        for relative in ASSETS:
            with self.subTest(asset=relative):
                document, binary = read_glb(ROOT / relative)
                same, shared = classify_faces(scene_faces(document, binary))
                self.assertFalse(same, f"Potential z-fighting in {relative}: {same[:12]}")
                print(f"{relative}: no same-facing duplicate triangles; {shared} opposite-facing shared seams")


if __name__ == "__main__":
    unittest.main(verbosity=2)
