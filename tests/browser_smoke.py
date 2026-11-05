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

    def open_page(self, path="", width=1440, height=900, mobile=False, no_webgl=False, fake_viewer=False, slow_viewer=False, request_log=None):
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
        if request_log is not None:
            page.on("request", lambda request: request_log.append(request.url))
        if no_webgl:
            page.add_init_script("""(() => {
              const original = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                if (type === 'webgl2') return null;
                return original.call(this, type, ...args);
              };
            })();""")
        if fake_viewer or slow_viewer:
            # Exercise the successful UI transition without external CDN or GPU.
            # This is NOT a test of real GLB rendering.
            page.add_init_script("""(() => {
              const original = HTMLCanvasElement.prototype.getContext;
              HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                if (type === 'webgl2') return {};
                return original.call(this, type, ...args);
              };
              customElements.define('model-viewer', class extends HTMLElement {
                connectedCallback() {
                  if (window.__slowViewer) {
                    setTimeout(() => this.dispatchEvent(new Event('load')), 700);
                  } else {
                    queueMicrotask(() => this.dispatchEvent(new Event('load')));
                  }
                }
              });
            })();""")
            if slow_viewer:
                page.add_init_script("window.__slowViewer = true;")
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
                requests = []
                page = self.open_page(path, no_webgl=True, request_log=requests)
                launch = page.locator("[data-model-launch]")
                self.assertTrue(launch.is_visible())
                self.assertEqual(page.locator("[data-model-preview] model-viewer").count(), 0)
                self.assertFalse(any(url.endswith(".glb") for url in requests))
                self.assertTrue(all(url.startswith(self.base) for url in requests),
                                f"Unexpected network request before 3D opt-in: {requests}")
                launch.click()
                self.assertIn("could not start", page.locator("[data-model-feedback]").inner_text())
                self.assertTrue(launch.is_visible())
                self.assertTrue(page.locator("[data-model-preview] .model-placeholder img").is_visible())
                self.assertEqual(page.locator("[data-model-preview] model-viewer").count(), 0)
                self.assert_no_overflow(page)
        self.assert_no_errors()

    def test_06_model_preview_success_ui_with_simulated_viewer(self):
        for path in CASES:
            with self.subTest(path=path):
                page = self.open_page(path, fake_viewer=True)
                launch = page.locator("[data-model-launch]")
                launch.click()
                self.assertTrue(page.locator("[data-model-preview]").evaluate(
                    "(el) => el.classList.contains('is-ready')"
                ))
                self.assertEqual(page.locator("[data-model-preview] model-viewer").count(), 1)
                self.assertFalse(launch.is_visible())
                reset = page.locator("[data-model-reset]")
                self.assertTrue(reset.is_visible())
                reset.click()
                self.assertIn("reset", page.locator("[data-model-feedback]").inner_text().lower())
                close = page.locator("[data-model-close]")
                self.assertTrue(close.is_visible())
                close.click()
                self.assertEqual(page.locator("[data-model-preview] model-viewer").count(), 0)
                self.assertTrue(page.locator("[data-model-preview] .model-placeholder img").is_visible())
                self.assertTrue(launch.is_visible())
                self.assertTrue(launch.evaluate("(el) => document.activeElement === el"))
                self.assertIn("restored", page.locator("[data-model-feedback]").inner_text().lower())
                launch.click()
                self.assertTrue(page.locator("[data-model-preview]").evaluate(
                    "(el) => el.classList.contains('is-ready')"
                ))
                page.locator("[data-model-preview] model-viewer").evaluate(
                    "(el) => el.dispatchEvent(new Event('error'))"
                )
                self.assertEqual(page.locator("[data-model-preview] model-viewer").count(), 0)
                self.assertTrue(launch.is_visible())
                self.assertIn("restored", page.locator("[data-model-feedback]").inner_text().lower())
        self.assert_no_errors()

    def test_07_cancel_slow_3d_loading_without_late_reopen(self):
        page = self.open_page(CASES[0], slow_viewer=True)
        launch = page.locator("[data-model-launch]")
        launch.click()
        close = page.locator("[data-model-close]")
        self.assertTrue(close.is_visible())
        self.assertIn("cancel", close.inner_text().lower())
        close.click()
        stage = page.locator("[data-model-preview]")
        self.assertEqual(stage.locator("model-viewer").count(), 0)
        self.assertTrue(launch.is_visible())
        self.assertIn("cancelled", page.locator("[data-model-feedback]").inner_text().lower())
        page.wait_for_timeout(850)
        self.assertFalse(stage.evaluate("(el) => el.classList.contains('is-ready')"))
        self.assertEqual(stage.locator("model-viewer").count(), 0)
        launch.click()
        page.wait_for_function(
            "() => document.querySelector('[data-model-preview]').classList.contains('is-ready')",
            timeout=5000,
        )
        self.assertEqual(stage.locator("model-viewer").count(), 1)
        self.assertIn("close", close.inner_text().lower())
        close.click()
        self.assertTrue(launch.is_visible())
        self.assert_no_errors()

    def test_07_not_found_navigation(self):
        page = self.open_page("404.html", width=390, height=844, mobile=True)
        self.assertIn("Not found", page.locator("h1").inner_text())
        page.locator("main a").click()
        self.assertTrue(page.url.endswith("/"))
        self.assertEqual(page.locator("article.case").count(), 5)
        self.assert_no_errors()


    def assert_headings_fit_viewport(self, page):
        # Scroll width alone misses headings clipped by overflow:hidden.
        clipped = page.evaluate("""() => {
          const width = document.documentElement.clientWidth;
          const issues = [];
          for (const heading of document.querySelectorAll('h1, h2, h3')) {
            if (!heading.getClientRects().length) continue;
            const range = document.createRange();
            range.selectNodeContents(heading);
            for (const rect of range.getClientRects()) {
              if (rect.width < 2 || rect.height < 2) continue;
              if (rect.left < -3 || rect.right > width + 3) {
                issues.push({
                  heading: heading.textContent.trim().slice(0, 65),
                  left: Math.round(rect.left),
                  right: Math.round(rect.right),
                  width,
                });
              }
            }
          }
          return issues.slice(0, 12);
        }""")
        self.assertFalse(clipped, f"Heading text clipped on {page.url}: {clipped}")

    def test_08_narrow_viewports_and_large_text_zoom(self):
        # Cover 320px phones and tablet widths not exercised by the 390px tests.
        for path in ("", *CASES, *GAMES):
            for width in (320, 360, 768):
                with self.subTest(path=path or "home", width=width):
                    page = self.open_page(path, width=width, height=800)
                    self.assert_no_overflow(page)
                    self.assert_headings_fit_viewport(page)
                    if width == 320 and path in ("", CASES[0]):
                        name = "home-320.png" if not path else "creekside-320.png"
                        self.screenshot(page, name)
        # Browser zoom reflows CSS pixels: a 1280px display at 200% has
        # approximately a 640px CSS layout viewport. Setting CSS zoom on
        # the root is NOT equivalent and produces a false scrollWidth.
        for path in ("", CASES[0]):
            with self.subTest(path=path or "home", zoom="200%-equivalent"):
                page = self.open_page(path, width=640, height=450)
                self.assert_no_overflow(page)
                self.assert_headings_fit_viewport(page)
        self.assert_no_errors()

    def test_09_keyboard_only_navigation_and_dialog_focus(self):
        home = self.open_page(width=390, height=844, mobile=True)
        menu = home.locator("#menuBtn")
        menu.focus()
        home.keyboard.press("Enter")
        self.assertEqual(menu.get_attribute("aria-expanded"), "true")
        home.keyboard.press("Escape")
        self.assertEqual(menu.get_attribute("aria-expanded"), "false")
        self.assertTrue(menu.evaluate("(el) => document.activeElement === el"))
        thumb = home.locator("[data-lightbox]").first
        thumb.focus()
        home.keyboard.press("Enter")
        self.assertTrue(home.locator("#lightbox").evaluate("(el) => el.classList.contains('open')"))
        home.keyboard.press("Tab")
        self.assertTrue(home.locator("#lightboxClose").evaluate("(el) => document.activeElement === el"))
        home.keyboard.press("Escape")
        self.assertTrue(thumb.evaluate("(el) => document.activeElement === el"))

        project = self.open_page(CASES[0])
        trigger = project.locator("[data-zoom]").first
        trigger.focus()
        project.keyboard.press("Enter")
        dialog = project.locator("[data-gallery-dialog]")
        self.assertTrue(dialog.is_visible())
        project.keyboard.press("Tab")
        self.assertTrue(project.locator("[data-gallery-prev]").evaluate(
            "(el) => document.activeElement === el"))
        project.keyboard.press("Shift+Tab")
        self.assertTrue(project.locator("[data-gallery-close]").evaluate(
            "(el) => document.activeElement === el"))
        project.keyboard.press("ArrowLeft")
        total = project.locator("[data-zoom]").count()
        self.assertTrue(project.locator("[data-gallery-counter]").inner_text().startswith(
            str(total).zfill(2) + " / "))
        project.keyboard.press("Escape")
        self.assertTrue(trigger.evaluate("(el) => document.activeElement === el"))
        self.assert_no_errors()

if __name__ == "__main__":
    unittest.main(verbosity=2)
