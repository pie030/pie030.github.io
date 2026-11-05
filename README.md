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

This is a static website: there is no build step, backend, or package installation. To preview locally, download the repository and open `index.html`, keeping the directory structure intact.

## Deployment

Pushes to `main` trigger the GitHub Pages workflow in `.github/workflows/pages.yml`. GitHub Pages must be enabled with **GitHub Actions** as its source in the repository settings.

## Project links

- https://github.com/pie030/Wildgrade
- https://github.com/pie030/Dungeon-Descent
- https://pie030.github.io/projects/creekside-cottage-watchtower.html
- https://pie030.github.io/projects/coastal-fishing-hut-pier.html
- https://pie030.github.io/projects/rural-railway-stop-freight-wagon.html

The public project repositories are showcases; they do not expose the full game source code.

## Interactive 3D previews

The Creekside, Coastal and Rural Railway case studies offer opt-in, interactive inspection of their actual downloadable GLB assets. Static posters and direct downloads remain available if WebGL is unsupported or a third-party viewer library cannot load. The preview uses the open-source Google model-viewer component loaded on demand from a CDN; no build step is needed.
