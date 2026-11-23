"""Integration test: load and display all three real GLBs using model-viewer + WebGL.

Unlike browser_smoke.py's simulated viewer, this test uses the actual
model-viewer distribution, Chromium software WebGL and the exported GLB files.
The CDN module is fulfilled from a pinned local npm installation so network
availability does not determine the result.

CI installs @google/model-viewer@3.5.0 under /tmp/portfolio-viewer.
"""
import functools
import io
import http.server
import json
import os
import threading
import time
import unittest
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get('PORTFOLIO_ROOT', str(REPO_ROOT))).resolve()
OUTPUT = REPO_ROOT / "test-results" / "webgl"
PUBLISHED_BUILD = "PORTFOLIO_ROOT" in os.environ
BUNDLE = Path(os.environ.get(
    "VIEWER_BUNDLE",
    "/tmp/portfolio-viewer/node_modules/@google/model-viewer/dist/model-viewer.min.js",
))
CASES = (
    "projects/creekside-cottage-watchtower.html",
    "projects/coastal-fishing-hut-pier.html",
    "projects/rural-railway-stop-freight-wagon.html",
    "projects/riftward.html",
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class RealWebGLTests(unittest.TestCase):
    def assert_visible_geometry(self, png, label):
        # Detect a blank WebGL canvas, not just a successful load event.
        with Image.open(io.BytesIO(png)) as image:
            image = image.convert("RGB")
            width, height = image.size
            center = image.crop((
                int(width * 0.15), int(height * 0.20),
                int(width * 0.85), int(height * 0.80),
            )).resize((80, 50))
            pixels = list(center.getdata())
        unique_colors = len(set(pixels))
        luminances = [sum(pixel) / 3 for pixel in pixels]
        self.assertGreater(unique_colors, 100, f"Blank/flat WebGL render: {label}")
        self.assertGreater(
            max(luminances) - min(luminances), 60,
            f"Insufficient visible contrast in render: {label}",
        )
        return unique_colors


    def test_sondante_revised_glb_animates_with_native_controls(self):
        handler = functools.partial(QuietHandler, directory=str(ROOT))
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch(
                        headless=True, args=["--use-gl=angle", "--use-angle=swiftshader",
                                             "--enable-unsafe-swiftshader", "--disable-dev-shm-usage"])
                    try:
                        for width, mobile in ((1280, False), (390, True)):
                            with self.subTest(width=width):
                                context = browser.new_context(viewport={"width": width, "height": 900},
                                                              device_scale_factor=1, is_mobile=mobile,
                                                              has_touch=mobile, reduced_motion="reduce")
                                try:
                                    page = context.new_page()
                                    errors = []
                                    page.on("pageerror", lambda error: errors.append(str(error)))
                                    page.goto(f"http://127.0.0.1:{server.server_port}/projects/sondante-04.html")
                                    viewer = page.locator("#viewer")
                                    self.assertEqual(viewer.get_attribute("data-ready"), "false")
                                    with page.expect_response(lambda r: r.url.endswith("/assets/sondante-04.glb")) as response:
                                        page.get_by_role("button", name="Open live model").click()
                                    self.assertEqual(response.value.status, 200)
                                    viewer.locator("#controls").wait_for(state="visible")
                                    self.assertEqual(viewer.get_attribute("data-ready"), "true")
                                    canvas = viewer.locator("#model")
                                    self.assert_visible_geometry(canvas.screenshot(), "Sondante, styled")
                                    if page.evaluate("document.fullscreenEnabled"):
                                        fullscreen=page.locator("[data-viewer-fullscreen]")
                                        fullscreen.click()
                                        page.wait_for_function("document.fullscreenElement !== null")
                                        self.assert_visible_geometry(canvas.screenshot(), "Sondante, fullscreen")
                                        fullscreen.click()
                                        page.wait_for_function("document.fullscreenElement === null")

                                    start = canvas.screenshot()
                                    page.get_by_role("button", name="Sampling", exact=True).click()
                                    self.assertIn("6.70 / 12.00 s", viewer.locator("#cycle-clock").inner_text())
                                    self.assertNotEqual(start, canvas.screenshot())
                                    wireframe = page.get_by_role("button", name="Wireframe")
                                    wireframe.click()
                                    self.assertEqual(wireframe.get_attribute("aria-pressed"), "true")
                                    OUTPUT.mkdir(parents=True, exist_ok=True)
                                    canvas.screenshot(path=str(OUTPUT / f"sondante-{width}-wireframe.png"))
                                    page.get_by_role("button", name="Play cycle").click()
                                    page.wait_for_function("document.querySelector('#cycle-clock').textContent !== '6.70 / 12.00 s'")
                                    page.get_by_role("button", name="Pause cycle").click()
                                    self.assertFalse(errors)
                                finally:
                                    context.close()
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                thread.join()

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
                            # Published tests use the actual first-party viewer, not
                            # a test-supplied module or a third-party CDN.
                            external_requests = []
                            if PUBLISHED_BUILD:
                                page.route("https://**/*", lambda route: route.abort())
                                page.on("request", lambda request: external_requests.append(
                                    request.url
                                ) if request.url.startswith("https://") else None)
                            else:
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
                                screenshot = stage.screenshot(
                                    path=str(OUTPUT / (Path(path).stem + "-webgl.png")),
                                    animations="disabled",
                                )
                                colors = self.assert_visible_geometry(screenshot, path)
                                initial_orbit = viewer.evaluate("""(el) => {
                                    const orbit = el.getCameraOrbit();
                                    return [orbit.theta, orbit.phi, orbit.radius];
                                }""")
                                viewer.evaluate("""(el) => {
                                    el.cameraOrbit = '90deg 60deg 85%';
                                    el.jumpCameraToGoal();
                                }""")
                                changed = viewer.evaluate("(el) => el.getCameraOrbit().theta")
                                self.assertGreater(abs(changed - initial_orbit[0]), 0.1)
                                page.locator("[data-model-reset]").click()
                                self.assertIn(
                                    "reset", page.locator("[data-model-feedback]").inner_text().lower()
                                )
                                restored = viewer.evaluate("""(el) => {
                                    const orbit = el.getCameraOrbit();
                                    return [orbit.theta, orbit.phi, orbit.radius];
                                }""")
                                for before, after in zip(initial_orbit, restored):
                                    self.assertAlmostEqual(
                                        before, after, delta=max(0.05, abs(before) * 0.02),
                                        msg=f"Camera did not reset on {path}",
                                    )
                                # Validate real pointer rotation, zoom and panning.
                                box = viewer.bounding_box()
                                cx, cy = box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5
                                theta = viewer.evaluate("(el) => el.getCameraOrbit().theta")
                                page.mouse.move(cx, cy)
                                page.mouse.down()
                                page.mouse.move(cx + 65, cy - 18, steps=8)
                                page.mouse.up()
                                page.wait_for_function("(before) => Math.abs(document.querySelector('model-viewer').getCameraOrbit().theta-before)>0.02", arg=theta)
                                radius = viewer.evaluate("(el) => el.getCameraOrbit().radius")
                                page.mouse.wheel(0, -180)
                                page.wait_for_function("(before) => document.querySelector('model-viewer').getCameraOrbit().radius < before*0.99", arg=radius)
                                target = viewer.evaluate("(el) => {const t=el.getCameraTarget(); return [t.x,t.y,t.z];}")
                                page.mouse.move(cx, cy)
                                page.keyboard.down("Shift")
                                page.mouse.down()
                                page.mouse.move(cx + 36, cy + 20, steps=6)
                                page.mouse.up()
                                page.keyboard.up("Shift")
                                page.wait_for_function("(before) => {const t=document.querySelector('model-viewer').getCameraTarget();return Math.hypot(t.x-before[0],t.y-before[1],t.z-before[2])>0.00001;}", arg=target)
                                page.locator("[data-model-reset]").click()
                                fullscreen = page.locator("[data-viewer-fullscreen]")
                                if page.evaluate("document.fullscreenEnabled"):
                                    fullscreen.click()
                                    page.wait_for_function("document.fullscreenElement !== null")
                                    fullscreen.click()
                                    page.wait_for_function("document.fullscreenElement === null")
                                if path == "projects/riftward.html":
                                    controls = page.locator("[data-model-animation-controls]")
                                    controls.wait_for(state="visible")
                                    self.assertEqual(page.locator("[data-model-clip] option").count(), 2)
                                    page.locator("[data-model-clip]").select_option("Impacto")
                                    start_image = viewer.screenshot()
                                    viewer.evaluate("(el) => { el.currentTime = el.duration * 0.55; }")
                                    page.wait_for_timeout(250)
                                    self.assertNotEqual(start_image, viewer.screenshot())
                                    page.locator("[data-model-play]").click()
                                    page.wait_for_function("document.querySelector('model-viewer').currentTime > 0")
                                    page.locator("[data-model-play]").click()
                                    self.assertTrue(viewer.evaluate("(el) => el.paused"))
                                self.assertFalse(errors, f"Uncaught JS errors: {errors}")
                                if PUBLISHED_BUILD:
                                    self.assertFalse(
                                        external_requests,
                                        f"Published 3D preview attempted external CDN requests: {external_requests}",
                                    )
                                page.locator("[data-model-close]").click()
                                self.assertEqual(stage.locator("model-viewer").count(), 0)
                                self.assertTrue(stage.locator(".model-placeholder img").is_visible())
                                self.assertTrue(page.locator("[data-model-launch]").is_visible())
                                self.assertIn(
                                    "restored", page.locator("[data-model-feedback]").inner_text().lower()
                                )
                                report[path] = {
                                    "loaded": True,
                                    "visible_color_samples": colors,
                                    "webgl2": True,
                                    "canvas": canvas,
                                    "glb_http_status": [s for _, s in glb_responses],
                                    "elapsed_seconds": round(time.monotonic() - started, 2),
                                }
                                print(f"PASS {path}: GLB rendered in {report[path]['elapsed_seconds']}s")
                            finally:
                                context.close()

                            # Real mobile emulation (not merely a responsive screenshot).
                            mobile = browser.new_context(
                                viewport={"width": 390, "height": 844},
                                is_mobile=True,
                                has_touch=True,
                                device_scale_factor=1,
                                reduced_motion="reduce",
                            )
                            try:
                                mobile_page = mobile.new_page()
                                if PUBLISHED_BUILD:
                                    mobile_page.route("https://**/*", lambda route: route.abort())
                                else:
                                    mobile_page.route(
                                        "**/model-viewer.min.js",
                                        lambda route: route.fulfill(
                                            status=200,
                                            content_type="text/javascript",
                                            body=bundle,
                                            headers={"access-control-allow-origin": "*"},
                                        ),
                                    )
                                mobile_page.goto(
                                    f"http://127.0.0.1:{server.server_port}/{path}",
                                    wait_until="load",
                                    timeout=30000,
                                )
                                mobile_page.locator("[data-model-launch]").click()
                                mobile_page.wait_for_function("""() => {
                                    const stage = document.querySelector('[data-model-preview]');
                                    return stage.classList.contains('is-ready') ||
                                        stage.querySelector('[data-model-launch]')?.disabled === false;
                                }""", timeout=45000)
                                mobile_stage = mobile_page.locator("[data-model-preview]")
                                self.assertTrue(
                                    mobile_stage.evaluate(
                                        "(el) => el.classList.contains('is-ready')"
                                    ),
                                    f"Mobile GLB failed: {path}",
                                )
                                mobile_screenshot = mobile_stage.screenshot(
                                    path=str(OUTPUT / (Path(path).stem + "-mobile-webgl.png")),
                                    animations="disabled",
                                )
                                report[path]["mobile_visible_color_samples"] = (
                                    self.assert_visible_geometry(mobile_screenshot, path + " mobile")
                                )
                                dimensions = mobile_page.evaluate("""() => ({
                                    client: document.documentElement.clientWidth,
                                    scroll: document.documentElement.scrollWidth,
                                })""")
                                self.assertLessEqual(dimensions["scroll"], dimensions["client"] + 2)
                                # Touch gestures must alter the actual camera.
                                mobile_viewer = mobile_stage.locator("model-viewer")
                                mobile_viewer.scroll_into_view_if_needed()
                                box = mobile_viewer.bounding_box()
                                cx, cy = box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5
                                initial_theta = mobile_viewer.evaluate("(el) => el.getCameraOrbit().theta")
                                session = mobile.new_cdp_session(mobile_page)
                                session.send("Input.dispatchTouchEvent", {"type":"touchStart","touchPoints":[{"x":cx,"y":cy,"id":1}]})
                                for step in range(1,7):
                                    session.send("Input.dispatchTouchEvent", {"type":"touchMove","touchPoints":[{"x":cx+step*7,"y":cy-2,"id":1}]})
                                session.send("Input.dispatchTouchEvent", {"type":"touchEnd","touchPoints":[]})
                                mobile_page.wait_for_function("(before) => Math.abs(document.querySelector('model-viewer').getCameraOrbit().theta-before)>0.02", arg=initial_theta)
                                radius = mobile_viewer.evaluate("(el) => el.getCameraOrbit().radius")
                                session.send("Input.dispatchTouchEvent", {"type":"touchStart","touchPoints":[{"x":cx-25,"y":cy,"id":1},{"x":cx+25,"y":cy,"id":2}]})
                                for step in range(1,7):
                                    distance = 25 + step*5
                                    session.send("Input.dispatchTouchEvent", {"type":"touchMove","touchPoints":[{"x":cx-distance,"y":cy,"id":1},{"x":cx+distance,"y":cy,"id":2}]})
                                session.send("Input.dispatchTouchEvent", {"type":"touchEnd","touchPoints":[]})
                                mobile_page.wait_for_function("(before) => Math.abs(document.querySelector('model-viewer').getCameraOrbit().radius-before)>before*0.01", arg=radius)
                                session.detach()
                                report[path]["mobile_loaded"] = True
                            finally:
                                mobile.close()
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
