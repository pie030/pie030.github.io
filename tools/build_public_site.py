"""Build a minimal GitHub Pages directory from an explicit allowlist.

Only files needed by the public portfolio are published. The three legacy
GLB materials are normalized from sRGB-authored values to glTF linear values
in the output copy only; original geometry and repository files are untouched.
Test screenshots,
CI configuration, source utilities, documentation and repository metadata are
intentionally excluded. The source files are never modified.

Usage: python tools/build_public_site.py --output /tmp/portfolio-public-site
"""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from convert_gltf_colors import convert_glb  # noqa: E402
ROOT_FILES = (
    ".nojekyll",
    "404.html",
    "index.html",
    "favicon.svg",
    "favicon.ico",
    "apple-touch-icon.png",
    "robots.txt",
    "sitemap.xml",
)
LOCAL_VIEWER = Path("js/model-viewer.min.js")
COLOR_CORRECTED_GLB = frozenset({
    'assets/creekside-yup-v03.glb',
    'assets/coastal-fishing-hut-pier-yup.glb',
    'assets/rural-railway-stop-freight-wagon-yup.glb',
})
DIRECTORIES = {
    "assets": frozenset({".webp", ".jpg", ".jpeg", ".png", ".glb", ".mp4"}),
    "css": frozenset({".css"}),
    "js": frozenset({".js"}),
    "projects": frozenset({".html"}),
}


def public_files(source=ROOT):
    """Enumerate public files; reject unexpected structures and missing inputs."""
    source = Path(source).resolve()
    result = []
    for name in ROOT_FILES:
        item = source / name
        if not item.is_file() or item.is_symlink():
            raise ValueError(f"Missing or unsafe public file: {item}")
        result.append(Path(name))
    for folder, extensions in DIRECTORIES.items():
        directory = source / folder
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"Missing or unsafe public directory: {directory}")
        for item in sorted(directory.iterdir()):
            if not item.is_file() or item.is_symlink() or item.suffix.lower() not in extensions:
                raise ValueError(f"Unexpected public directory entry: {item}")
            result.append(item.relative_to(source))
    return tuple(result)


def build(output, source=ROOT, viewer_bundle=None):
    source = Path(source).resolve()
    output = Path(output).resolve()
    if output == source or source in output.parents or output in source.parents:
        raise ValueError("Output must be a separate directory outside the repository")
    files = public_files(source)
    if output.exists():
        if output.is_symlink() or not output.is_dir():
            raise ValueError(f"Unsafe output location: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)
    total_bytes = 0
    corrected_count = 0
    for relative in files:
        origin = source / relative
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination)
        original_hash = hashlib.sha256(origin.read_bytes()).digest()
        copied_hash = hashlib.sha256(destination.read_bytes()).digest()
        if original_hash != copied_hash:
            raise ValueError(f"Copy verification failed: {relative}")
        if relative.as_posix() in COLOR_CORRECTED_GLB:
            converted, materials = convert_glb(origin.read_bytes())
            destination.write_bytes(converted)
            corrected_count += 1
            if materials < 1:
                raise ValueError(f"No material colors corrected: {relative}")
        total_bytes += destination.stat().st_size
    expected = set(files)
    bundle_size = 0
    if viewer_bundle is not None:
        bundle = Path(viewer_bundle)
        if not bundle.is_file() or bundle.is_symlink():
            raise ValueError(f"Missing or unsafe local 3D viewer bundle: {bundle}")
        # CI installs the exact @google/model-viewer@3.5.0 release.
        if bundle.stat().st_size < 100_000:
            raise ValueError(f"Unexpectedly small 3D viewer bundle: {bundle}")
        destination = output / LOCAL_VIEWER
        shutil.copy2(bundle, destination)
        if hashlib.sha256(bundle.read_bytes()).digest() != hashlib.sha256(destination.read_bytes()).digest():
            raise ValueError("Local 3D viewer bundle failed integrity verification")
        bundle_size = destination.stat().st_size
        total_bytes += bundle_size
        expected.add(LOCAL_VIEWER)
    actual = {p.relative_to(output) for p in output.rglob("*") if p.is_file()}
    if actual != expected:
        raise ValueError("Published file list does not match the allowlist")
    if corrected_count != len(COLOR_CORRECTED_GLB):
        raise ValueError('Not all required GLBs were color-corrected')
    return {"files": len(files), "bytes": total_bytes, "megabytes": round(total_bytes / 1048576, 2),
            "color_corrected_glbs": corrected_count, "local_viewer_bytes": bundle_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Directory outside the repository")
    parser.add_argument("--viewer-bundle", type=Path, help="Pinned local model-viewer distribution to include")
    args = parser.parse_args()
    print(json.dumps(build(args.output, viewer_bundle=args.viewer_bundle), indent=2))


if __name__ == "__main__":
    main()
