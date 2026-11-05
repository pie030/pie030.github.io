"""Capture a reversible WebGL A/B test of sRGB-to-linear material correction.

The original shipped GLBs remain untouched. Browser requests are intercepted
and fulfilled with corrected copies in memory; evidence stays in CI artifacts.
"""
import functools
import http.server
import importlib.util
import json
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'test-results' / 'webgl'
BUNDLE = Path('/tmp/portfolio-viewer/node_modules/@google/model-viewer/dist/model-viewer.min.js')
SCRIPT = ROOT / 'tools' / 'convert_gltf_colors.py'
spec = importlib.util.spec_from_file_location('convert_gltf_colors', SCRIPT)
converter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(converter)
CASES = (
    ('projects/creekside-cottage-watchtower.html', 'assets/creekside-yup-v03.glb'),
    ('projects/coastal-fishing-hut-pier.html', 'assets/coastal-fishing-hut-pier-yup.glb'),
    ('projects/rural-railway-stop-freight-wagon.html', 'assets/rural-railway-stop-freight-wagon-yup.glb'),
)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    bundle = BUNDLE.read_bytes()
    handler = functools.partial(QuietHandler, directory=str(ROOT))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    results = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=[
                '--disable-dev-shm-usage', '--enable-webgl',
                '--use-gl=angle', '--use-angle=swiftshader',
                '--enable-unsafe-swiftshader',
            ])
            try:
                for page_path, glb_path in CASES:
                    content, count = converter.convert_glb((ROOT / glb_path).read_bytes())
                    context = browser.new_context(viewport={'width': 1280, 'height': 900},
                                                  reduced_motion='reduce')
                    try:
                        page = context.new_page()
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.route('**/model-viewer.min.js', lambda route: route.fulfill(
                            status=200, content_type='text/javascript', body=bundle,
                            headers={'access-control-allow-origin': '*'}))
                        page.route('**/*.glb', lambda route: route.fulfill(
                            status=200, content_type='model/gltf-binary', body=content))
                        page.goto(f'http://127.0.0.1:{server.server_port}/{page_path}',
                                  wait_until='load', timeout=30000)
                        page.locator('[data-model-launch]').click()
                        page.wait_for_function('''() => {
                          const stage = document.querySelector('[data-model-preview]');
                          return stage.classList.contains('is-ready') ||
                            stage.querySelector('[data-model-launch]')?.disabled === false;
                        }''', timeout=45000)
                        stage = page.locator('[data-model-preview]')
                        if not stage.evaluate('(el) => el.classList.contains("is-ready")'):
                            raise RuntimeError(f'Corrected GLB did not load: {page_path}')
                        page.wait_for_timeout(400)
                        output = OUTPUT / (Path(page_path).stem + '-color-corrected.png')
                        stage.screenshot(path=str(output), animations='disabled')
                        if errors:
                            raise RuntimeError(f'JS errors in {page_path}: {errors}')
                        results[page_path] = {'materials_converted': count, 'image': output.name}
                        print(f'PREVIEW {page_path}: {count} materials, {output.name}')
                    finally:
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        (OUTPUT / 'color-preview-report.json').write_text(json.dumps(results, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
