"""Dependency-free static quality checks for the public portfolio.

Run: python3 -m unittest discover -s tests -p "test_*.py" -v
These tests validate repository artifacts; they are not browser-rendering tests.
"""
import json
import posixpath
import struct
import unittest
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
PAGES = sorted(ROOT.rglob("*.html"))
PROJECTS = (
    "projects/creekside-cottage-watchtower.html",
    "projects/coastal-fishing-hut-pier.html",
    "projects/rural-railway-stop-freight-wagon.html",
)
ASSETS = (
    "assets/creekside-yup-v03.glb",
    "assets/coastal-fishing-hut-pier-yup.glb",
    "assets/rural-railway-stop-freight-wagon-yup.glb",
)


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    handle_startendtag = handle_starttag


def read_page(path):
    return (ROOT / path).read_text(encoding="utf-8")


def parsed_pages():
    pages = {}
    for path in PAGES:
        relative = path.relative_to(ROOT).as_posix()
        parser = Tags()
        parser.feed(read_page(relative))
        pages[relative] = parser.elements
    return pages


def local_target(source, url):
    if not url or url.startswith(("data:", "mailto:", "tel:", "//")):
        return None
    parsed = urlsplit(url)
    if parsed.scheme:
        return None
    route = unquote(parsed.path)
    if not route:
        return source, parsed.fragment
    if route == '/':
        return 'index.html', parsed.fragment
    if route.startswith("/"):
        result = posixpath.normpath(route.lstrip("/"))
    else:
        result = posixpath.normpath(posixpath.join(posixpath.dirname(source), route))
    if result in ("", "."):
        result = "index.html"
    if route.endswith("/"):
        result = posixpath.join(result, "index.html")
    return result, parsed.fragment


class PortfolioQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = parsed_pages()

    def test_01_expected_pages_exist(self):
        for path in ("index.html", "404.html", *PROJECTS, "projects/wildgrade.html", "projects/dungeon-descent.html"):
            with self.subTest(path=path):
                self.assertIn(path, self.pages)

    def test_02_language_and_single_heading(self):
        for path, tags in self.pages.items():
            with self.subTest(path=path):
                html = [attrs for tag, attrs in tags if tag == "html"]
                self.assertEqual(len(html), 1)
                self.assertEqual(html[0].get("lang"), "en")
                self.assertEqual(sum(tag == "h1" for tag, _ in tags), 1)

    def test_03_titles_and_search_metadata(self):
        for path, tags in self.pages.items():
            with self.subTest(path=path):
                self.assertEqual(sum(tag == "title" for tag, _ in tags), 1)
                if path == "404.html":
                    continue
                self.assertTrue(any(tag == "meta" and attrs.get("name") == "description" and attrs.get("content") for tag, attrs in tags))
                self.assertTrue(any(tag == "link" and attrs.get("rel") == "canonical" and attrs.get("href") for tag, attrs in tags))

    def test_04_unique_ids(self):
        for path, tags in self.pages.items():
            ids = [attrs["id"] for _, attrs in tags if attrs.get("id")]
            with self.subTest(path=path):
                self.assertEqual(len(ids), len(set(ids)), str(Counter(ids)))

    def test_05_images_have_alt_text(self):
        for path, tags in self.pages.items():
            for tag, attrs in tags:
                if tag == "img":
                    with self.subTest(path=path, src=(attrs.get("src") or "")[:80]):
                        self.assertIn("alt", attrs)

    def test_06_local_resources_resolve(self):
        for path, tags in self.pages.items():
            for tag, attrs in tags:
                for attr in ("href", "src"):
                    if attr not in attrs:
                        continue
                    url = attrs[attr]
                    target = local_target(path, url)
                    if target is None:
                        continue
                    file_path, _ = target
                    with self.subTest(path=path, tag=tag, url=url[:100]):
                        self.assertTrue((ROOT / file_path).is_file(), f"Missing: {file_path}")

    def test_07_internal_fragments_resolve(self):
        ids = {path: {attrs["id"] for _, attrs in tags if attrs.get("id")} for path, tags in self.pages.items()}
        for path, tags in self.pages.items():
            for tag, attrs in tags:
                if tag != "a" or not attrs.get("href"):
                    continue
                target = local_target(path, attrs["href"])
                if target is None:
                    continue
                file_path, fragment = target
                if fragment and file_path in ids:
                    with self.subTest(path=path, target=attrs["href"][:100]):
                        self.assertIn(unquote(fragment), ids[file_path])

    def test_08_external_new_tabs_are_safe(self):
        for path, tags in self.pages.items():
            for tag, attrs in tags:
                if tag == "a" and attrs.get("target") == "_blank":
                    with self.subTest(path=path, href=(attrs.get("href") or "")[:100]):
                        self.assertIn("noopener", (attrs.get("rel") or "").split())
                        self.assertIn("noreferrer", (attrs.get("rel") or "").split())

    def test_09_glb_files_are_valid_containers(self):
        for relative in ASSETS:
            with self.subTest(asset=relative):
                content = (ROOT / relative).read_bytes()
                self.assertGreaterEqual(len(content), 20)
                magic, version, declared = struct.unpack_from("<4sII", content)
                self.assertEqual(magic, b"glTF")
                self.assertEqual(version, 2)
                self.assertEqual(declared, len(content))
                chunk_size, chunk_type = struct.unpack_from("<I4s", content, 12)
                self.assertEqual(chunk_type, b"JSON")
                document = json.loads(content[20:20 + chunk_size].decode("utf-8"))
                self.assertEqual(document.get("asset", {}).get("version"), "2.0")
                self.assertTrue(document.get("meshes"), "No meshes in GLB")

    def test_10_interactive_preview_is_connected(self):
        self.assertTrue((ROOT / "js/model-preview.js").is_file())
        for path, asset in zip(PROJECTS, ASSETS):
            tags = self.pages[path]
            stages = [attrs for _, attrs in tags if "data-model-preview" in attrs]
            with self.subTest(page=path):
                self.assertEqual(len(stages), 1)
                target = local_target(path, stages[0].get("data-model-src", ""))
                self.assertIsNotNone(target)
                self.assertEqual(target[0], asset)
                self.assertTrue((ROOT / local_target(path, stages[0].get("data-model-poster", ""))[0]).is_file())
                self.assertTrue(any("data-model-launch" in attrs for _, attrs in tags))
                self.assertTrue(any("data-model-reset" in attrs for _, attrs in tags))
                self.assertTrue(any("data-model-close" in attrs for _, attrs in tags))
                self.assertTrue(any(tag == "script" and attrs.get("src") == "../js/model-preview.js" for tag, attrs in tags))

    def test_11_raster_assets_have_expected_headers(self):
        for asset in sorted((ROOT / "assets").iterdir()):
            if asset.suffix.lower() not in (".webp", ".jpg", ".jpeg"):
                continue
            header = asset.read_bytes()[:12]
            with self.subTest(asset=asset.name):
                if asset.suffix.lower() == ".webp":
                    self.assertEqual(header[:4], b"RIFF")
                    self.assertEqual(header[8:12], b"WEBP")
                else:
                    self.assertEqual(header[:2], b"\xff\xd8")

        for page in self.pages:
            with self.subTest(page=page, check='no embedded raster images'):
                self.assertNotIn('data:image/', read_page(page))

    def test_12_sitemap_covers_project_pages(self):
        document = ET.parse(ROOT / "sitemap.xml")
        locations = [node.text for node in document.findall(".//{*}loc")]
        self.assertEqual(len(locations), len(set(locations)))
        expected = {"https://pie030.github.io/"}
        expected.update("https://pie030.github.io/" + p for p in self.pages if p.startswith("projects/"))
        self.assertTrue(expected.issubset(set(locations)), expected - set(locations))
        for location in locations:
            parsed = urlsplit(location)
            self.assertEqual(parsed.netloc, "pie030.github.io")
            file_path = parsed.path.lstrip("/") or "index.html"
            self.assertTrue((ROOT / file_path).is_file(), location)


if __name__ == "__main__":
    unittest.main()
