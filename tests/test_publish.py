"""Deployment boundary checks: never publish development files as website assets."""
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "build_public_site.py"
spec = importlib.util.spec_from_file_location("build_public_site", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PublicSiteTests(unittest.TestCase):
    def test_only_allowlisted_files_are_published(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "site"
            report = builder.build(output)
            expected = set(builder.public_files())
            actual = {path.relative_to(output) for path in output.rglob("*") if path.is_file()}
            self.assertEqual(actual, expected)
            self.assertGreater(report["files"], 30)
            self.assertEqual(report['color_corrected_glbs'], 3)
            for relative in builder.COLOR_CORRECTED_GLB:
                source = (ROOT / relative).read_bytes()
                published = (output / relative).read_bytes()
                self.assertNotEqual(source, published, relative)
                # The GLB BIN chunk containing all vertex/index data must be identical.
                def bin_chunk(data):
                    json_length = struct.unpack_from('<I', data, 12)[0]
                    offset = 20 + json_length
                    bin_length, kind = struct.unpack_from('<I4s', data, offset)
                    self.assertEqual(kind, bytes([66, 73, 78, 0]))
                    return data[offset + 8:offset + 8 + bin_length]
                self.assertEqual(bin_chunk(source), bin_chunk(published), relative)
            self.assertEqual((output / 'index.html').read_bytes(),
                             (ROOT / 'index.html').read_bytes())
            for forbidden in ("README.md", "tests", "tools", "docs", ".github", "test-results", ".gitignore"):
                self.assertFalse((output / forbidden).exists(), forbidden)
            for important in ("index.html", "404.html", "assets/creekside-yup-v03.glb", "assets/wildgrade-gameplay-film.mp4"):
                self.assertTrue((output / important).is_file(), important)

    def test_rejects_output_inside_repository(self):
        with self.assertRaises(ValueError):
            builder.build(ROOT / "public")


if __name__ == "__main__":
    unittest.main()
