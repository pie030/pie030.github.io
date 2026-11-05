"""Chromium smoke tests for real rendering, navigation, galleries and 3D fallback.

Run locally:
  python -m pip install playwright==1.57.0
  python -m playwright install chromium
  python tests/browser_smoke.py

The local server is created automatically. Evidence is saved in
test-results/browser/ and uploaded on CI failures.
"""
import functools
import http.server
import os
import threading
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "test-results" / "browser"
CASES = (
    "projects/creekside-cottage-watchtower.html",
    "projects/coastal-fishing-hut-pier.html",
    "projects/rural-railway-stop-freight-wagon.html",
)
GAMES = ("projects/wildgrade.html", "projects/dungeon-descent.html")


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class BrowserSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        handler = functools.partial(QuietHandler, directory=str(ROOT))
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def setUp(self):
        self.contexts = []
        self.errors = []

    def tearDown(self):
        for context in self.contexts:
            context.close()

    def open_page(self, path="", width=1440, height=900, mobile=False, no_webgl=False):
        context = self.browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=1,
            is_mobile=mobile,
            has_touch=mobile,
            reduced_motion="reduce",
        )
        self.contexts.append(context)
        page = context.new_page()
        page.on("pageerror", lambda error: self.errors.append(f"{path}: {error}"))
        if no_webgl:
            page.add_init_script("""(() => {
              const original = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                if (type === 'webgl2') return null;
                return original.call(this, type, ...args);
              };
            })();""")
        page.goto(f"{self.base}/{path}", wait_until="load", timeout=30000)
        return page

    def assert_no_overflow(self, page):
        dimensions = page.evaluate("""() => ({
          width: document.documentElement.clientWidth,
          scroll: document.documentElement.scrollWidth,
          body: document.body.scrollWidth
        })""")
        self.assertLessEqual(
            max(dimensions["scroll"], dimensions["body"]),
            dimensions["width"] + 2,
            f"Horizontal overflow: {page.url} {dimensions}",
        )

    def screenshot(self, page, name):
        # A full-page screenshot does not itself trigger off-screen lazy images.
        # Load and decode them first, then reset scroll for reproducible evidence.
        missing = page.evaluate("""async () => {
          const images = [...document.images].filter(img => img.getAttribute('src'));
          for (const image of images) image.loading = 'eager';
          await Promise.all(images.map(image => image.decode().catch(() => {})));
          document.documentElement.style.scrollBehavior = 'auto';
          window.scrollTo(0, 0);
          await new Promise(resolve => requestAnimationFrame(resolve));
          return images.filter(img => !img.complete || img.naturalWidth === 0)
            .map(img => img.currentSrc || img.src);
        }""")
        self.assertFalse(missing, f"Images failed to load on {page.url}: {missing}")
        page.screenshot(path=str(EVIDENCE / name), full_page=True, animations="disabled")

    def assert_no_errors(self):
        self.assertFalse(self.errors, "Uncaught browser errors:\n" + "\n".join(self.errors))

    def test_01_home_desktop(self):
        page = self.open_page()
        self.assertEqual(page.locator("h1").count(), 1)
        self.assertEqual(page.locator("article.case").count(), 5)
        self.assertTrue(page.locator(".hero-media img").first.evaluate("(img) => img.complete && img.naturalWidth > 0"))
        self.assert_no_overflow(page)
        self.screenshot(page, "home-desktop.png")
        self.assert_no_errors()

    def test_02_home_mobile_menu_and_gallery(self):
        page = self.open_page(width=390, height=844, mobile=True)
        menu = page.locator("#menuBtn")
        self.assertTrue(menu.is_visible())
        menu.click()
        self.assertEqual(menu.get_attribute("aria-expanded"), "true")
        page.locator("#navlinks a[href='#work']").click()
        self.assertEqual(menu.get_attribute("aria-expanded"), "false")
        thumbnail = page.locator("[data-lightbox]").first
        thumbnail.scroll_into_view_if_needed()
        thumbnail.click()
        self.assertTrue(page.locator("#lightbox").evaluate("(el) => el.classList.contains('open')"))
        page.keyboard.press("Escape")
        self.assertFalse(page.locator("#lightbox").evaluate("(el) => el.classList.contains('open')"))
        self.assertTrue(thumbnail.evaluate("(el) => document.activeElement === el"))
        self.assert_no_overflow(page)
        self.screenshot(page, "home-mobile.png")
        self.assert_no_errors()

    def test_03_case_study_galleries(self):
        for path in CASES:
            with self.subTest(path=path):
                page = self.open_page(path)
                trigger = page.locator("[data-zoom]").first
                self.assertTrue(trigger.is_visible())
                trigger.click()
                dialog = page.locator("[data-gallery-dialog]")
                self.assertTrue(dialog.is_visible())
                self.assertEqual(page.locator("[data-gallery-counter]").inner_text(), "01 / " + str(page.locator("[data-zoom]").count()).zfill(2))
                page.keyboard.press("ArrowRight")
                self.assertTrue(page.locator("[data-gallery-counter]").inner_text().startswith("02 / "))
                page.keyboard.press("Escape")
                self.assertFalse(dialog.is_visible())
                self.assertTrue(trigger.evaluate("(el) => document.activeElement === el"))
                self.assert_no_overflow(page)
                self.screenshot(page, Path(path).stem + "-desktop.png")
        self.assert_no_errors()

    def test_04_mobile_case_studies_and_games(self):
        for path in (*CASES, *GAMES):
            with self.subTest(path=path):
                page = self.open_page(path, width=390, height=844, mobile=True)
                self.assertEqual(page.locator("h1").count(), 1)
                self.assertTrue(page.locator("h1").is_visible())
                self.assert_no_overflow(page)
                self.screenshot(page, Path(path).stem + "-mobile.png")
        self.assert_no_errors()

    def test_05_model_is_opt_in_and_has_graceful_fallback(self):
        for path in CASES:
            with self.subTest(path=path):
                page = self.open_page(path, no_webgl=True)
                requests = []
                page.on("request", lambda request: requests.append(request.url))
                launch = page.locator("[data-model-launch]")
                self.assertTrue(launch.is_visible())
                self.assertEqual(page.locator("[data-model-preview] model-viewer").count(), 0)
                self.assertFalse(any(url.endswith(".glb") for url in requests))
                launch.click()
                self.assertIn("could not start", page.locator("[data-model-feedback]").inner_text())
                self.assertTrue(launch.is_visible())
                self.assertTrue(page.locator("[data-model-preview] .model-placeholder img").is_visible())
                self.assertEqual(page.locator("[data-model-preview] model-viewer").count(), 0)
                self.assert_no_overflow(page)
        self.assert_no_errors()

    def test_06_not_found_navigation(self):
        page = self.open_page("404.html", width=390, height=844, mobile=True)
        self.assertIn("Not found", page.locator("h1").inner_text())
        page.locator("main a").click()
        self.assertTrue(page.url.endswith("/"))
        self.assertEqual(page.locator("article.case").count(), 5)
        self.assert_no_errors()


if __name__ == "__main__":
    unittest.main(verbosity=2)
