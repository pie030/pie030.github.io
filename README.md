# Pietro Braz — Portfolio

A small, static portfolio for selected game-development work.

**Live site:** https://pie030.github.io/

## Featured projects

- **Wildgrade** — a browser-based driving prototype exploring procedural environments, vehicle handling, and interactive landscapes.
- **Dungeon Descent** — an experimental Windows dungeon crawler built with C and the Win32 API.
- **Creekside Cottage & Watchtower** — a low-poly 3D environment refined in Blender, with attention to geometry, materials and visual composition. Downloadable GLB and real model renders.
- **Coastal Fishing Hut & Pier** — a low-poly coastal scene refined in Blender, with attention to geometry, materials and visual composition; includes a hut, supported pier and rowboat.
- **Rural Railway Stop & Freight Wagon (v1.1)** — a low-poly railway environment refined in Blender, with attention to geometry, materials and visual composition; includes a station, wagon and woodland.

Wildgrade and Dungeon Descent are game prototypes; Creekside, Coastal and Rural Railway are low-poly 3D environment studies with Blender refinements to Python-generated base geometry. All five use genuine project captures or model renders, with their current limitations stated explicitly.

## Structure

- `index.html` — home page
- `projects/` — detailed project pages
- `css/` and `js/` — presentation and interactions
- `assets/` — optimized images and the Wildgrade gameplay video

The pages are static and require no frontend bundler or backend. GitHub Actions uses a small packaging step to publish only the public files and normalize legacy GLB material colors. To preview locally, download the repository and open `index.html`, keeping the directory structure intact.

## Deployment

Only an explicit allowlist of public files is uploaded to GitHub Pages: the HTML pages, CSS, JavaScript, images, video, GLB exports, icons, sitemap and robots file. The site builder in `tools/build_public_site.py` excludes source utilities, tests, screenshot evidence, workflow configuration and repository documentation. The GitHub Actions screenshots remain available as separate workflow artifacts instead of becoming public website files. The builder verifies all copies before applying a documented color-space correction to the three public GLBs. The original repository assets and their binary mesh buffers remain unchanged.

Pushes to `main` trigger the GitHub Pages workflow in `.github/workflows/pages.yml`. GitHub Pages must be enabled with **GitHub Actions** as its source in the repository settings.

## Project links

- https://github.com/pie030/Wildgrade
- https://github.com/pie030/Dungeon-Descent
- https://pie030.github.io/projects/creekside-cottage-watchtower.html
- https://pie030.github.io/projects/coastal-fishing-hut-pier.html
- https://pie030.github.io/projects/rural-railway-stop-freight-wagon.html

The public project repositories are showcases; they do not expose the full game source code.

## Interactive 3D previews

The Creekside, Coastal and Rural Railway case studies offer opt-in, interactive inspection of their actual downloadable GLB assets. Static posters and direct downloads remain available if WebGL is unsupported or a third-party viewer library cannot load. The preview uses the open-source Google model-viewer component loaded on demand from a CDN; no build step is needed. Camera framing and exposure are calibrated from captured WebGL renders; users can still rotate and zoom freely. The site packaging step corrects the legacy flat-color RGB material factors from sRGB to glTF linear space for the public GLBs, leaving the source GLBs unchanged. The packaged GLBs are rendered again in CI on desktop and mobile to verify the actual published files.

## Quality checks and Blender recovery

The deployment workflow runs 18 dependency-free static tests before publishing. They check page structure, internal links, image metadata, sitemap coverage, downloadable GLB containers, GLB vertex/index integrity, triangle geometry, and the optional viewer integration. The workflow also runs Chromium browser smoke tests on desktop and mobile layouts, including gallery navigation, keyboard focus, horizontal overflow and 3D fallback. Screenshots are retained for 7 days as GitHub Actions artifacts. A separate integration test loads each real GLB in Chromium with software WebGL and the pinned model-viewer library, then captures the rendered canvas and checks camera reset. The integration also checks screenshot color variation to catch blank canvases and verifies real camera restoration, with actual model loading in mobile emulation. This validates the browser rendering path on CI, but not every physical GPU, browser or device.

To recreate editable Blender scenes from the existing GLBs, install Blender 4.x and run:

```bash
blender --background --factory-startup --python tools/recover_blender_projects.py -- --output-dir blender
```

This creates three `.blend` files and an import report in `blender/`. A separate **Recover editable Blender scenes** GitHub Actions workflow also generates and validates the three `.blend` files as a downloadable artifact (14-day retention), including a portable import report and opening instructions. The workflow also renders nine neutral QA views (three per scene) using Blender Cycles on CPU, then validates PNG dimensions and SHA-256 hashes. The import restores mesh objects and materials from the GLBs, not the original editing history, modifiers, or modeling source files. Generated Blender files are intentionally not committed to the website repository.

## Media performance

Wildgrade and Dungeon Descent use the existing, byte-identical screenshot and icon files instead of repeating base64 images inside their HTML. This reduced their HTML documents from 235,350 to 15,424 bytes (93%) and from 146,873 to 14,609 bytes (90%) respectively, without altering the images. External files can be cached and lazy-loaded by the browser.
