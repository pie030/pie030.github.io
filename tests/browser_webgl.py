"""Integration test: load and display all three real GLBs using model-viewer + WebGL.

Unlike browser_smoke.py's simulated viewer, this test uses the actual
model-viewer distribution, Chromium software WebGL and the exported GLB files.
The CDN module is fulfilled from a pinned local npm installation so network
availability does not determine the result.

CI installs @google/model-viewer@3.5.0 under /tmp/portfolio-viewer.
"""
import functools
import http.server
import json
import os
import threading
import time
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "test-results" / "webgl"
BUNDLE = Path(os.environ.get(
    "VIEWER_BUNDLE",
    "/tmp/portfolio-viewer/node_modules/@google/model-viewer/dist/model-viewer.min.js",
))
CASES = (
    "projects/creekside-cottage-watchtower.html",
    "projects/coastal-fishing-hut-pier.html",
    "projects/rural-railway-stop-freight-wagon.html",
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RealWebGLTests(unittest.TestCase):
    def test_real_glb_rendering_and_camera_reset(self):
        self.assertTrue(BUNDLE.is_file(), f"Pinned viewer bundle missing: {BUNDLE}")
        OUTPUT.mkdir(parents=True, exist_ok=True)
        bundle = BUNDLE.read_bytes()
        handler = functools.partial(QuietHandler, directory=str(ROOT))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        report = {}
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=True,
                    args=[
                        "--disable-dev-shm-usage",
                        "--enable-webgl",
                        "--use-gl=angle",
                        "--use-angle=swiftshader",
                        "--enable-unsafe-swiftshader",
                    ],
                )
                try:
                    for path in CASES:
                        with self.subTest(path=path):
                            context = browser.new_context(
                                viewport={"width": 1280, "height": 900},
                                device_scale_factor=1,
                                reduced_motion="reduce",
                            )
                            page = context.new_page()
                            errors = []
                            glb_responses = []
                            page.on("pageerror", lambda err: errors.append(str(err)))
                            page.on(
                                "response",
                                lambda response: glb_responses.append(
                                    (response.url, response.status)
                                ) if response.url.endswith(".glb") else None,
                            )
                            page.route(
                                "**/model-viewer.min.js",
                                lambda route: route.fulfill(
                                    status=200,
                                    content_type="text/javascript",
                                    body=bundle,
                                    headers={"access-control-allow-origin": "*"},
                                ),
                            )
                            started = time.monotonic()
                            try:
                                page.goto(
                                    f"http://127.0.0.1:{server.server_port}/{path}",
                                    wait_until="load",
                                    timeout=30000,
                                )
                                webgl = page.evaluate("""() => {
                                    const canvas = document.createElement('canvas');
                                    const gl = canvas.getContext('webgl2');
                                    const supported = !!gl;
                                    gl?.getExtension('WEBGL_lose_context')?.loseContext();
                                    return supported;
                                }""")
                                self.assertTrue(webgl, "Chromium software WebGL2 is unavailable")
                                page.locator("[data-model-launch]").click()
                                page.wait_for_function("""() => {
                                    const stage = document.querySelector('[data-model-preview]');
                                    return stage.classList.contains('is-ready') ||
                                        stage.querySelector('[data-model-launch]')?.disabled === false;
                                }""", timeout=45000)
                                stage = page.locator("[data-model-preview]")
                                feedback = page.locator("[data-model-feedback]").inner_text()
                                self.assertTrue(
                                    stage.evaluate("(el) => el.classList.contains('is-ready')"),
                                    f"GLB viewer failed on {path}: {feedback}; errors={errors}",
                                )
                                viewer = stage.locator("model-viewer")
                                self.assertTrue(viewer.evaluate("(el) => el.loaded === true"))
                                canvas = viewer.evaluate("""(el) => {
                                    const c = el.shadowRoot?.querySelector('canvas');
                                    return c ? {width: c.width, height: c.height} : null;
                                }""")
                                self.assertIsNotNone(canvas, "No WebGL canvas in viewer")
                                self.assertGreater(canvas["width"], 0)
                                self.assertGreater(canvas["height"], 0)
                                self.assertTrue(
                                    any(status == 200 for _, status in glb_responses),
                                    f"GLB did not return HTTP 200: {glb_responses}",
                                )
                                page.wait_for_timeout(400)
                                stage.screenshot(
                                    path=str(OUTPUT / (Path(path).stem + "-webgl.png")),
                                    animations="disabled",
                                )
                                # Visual QA variants: test framing and exposure without
                                # changing the live site. These images are for review.
                                for zoom, exposure in ((85, 0.8), (70, 0.65), (60, 0.55)):
                                    viewer.evaluate("""(el, settings) => {
                                        el.setAttribute('camera-orbit', '35deg 70deg ' + settings.zoom + '%');
                                        el.setAttribute('exposure', String(settings.exposure));
                                        el.jumpCameraToGoal();
                                    }""", {"zoom": zoom, "exposure": exposure})
                                    page.wait_for_timeout(300)
                                    stage.screenshot(
                                        path=str(OUTPUT / (
                                            Path(path).stem + f"-zoom{zoom}-exp{exposure}.png"
                                        )),
                                        animations="disabled",
                                    )
                                page.locator("[data-model-reset]").click()
                                self.assertIn(
                                    "reset", page.locator("[data-model-feedback]").inner_text().lower()
                                )
                                self.assertFalse(errors, f"Uncaught JS errors: {errors}")
                                report[path] = {
                                    "loaded": True,
                                    "webgl2": True,
                                    "canvas": canvas,
                                    "glb_http_status": [s for _, s in glb_responses],
                                    "elapsed_seconds": round(time.monotonic() - started, 2),
                                }
                                print(f"PASS {path}: GLB rendered in {report[path]['elapsed_seconds']}s")
                            finally:
                                context.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            (OUTPUT / "report.json").write_text(
                json.dumps(report, indent=2), encoding="utf-8"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
