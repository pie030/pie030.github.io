"""Build a minimal GitHub Pages directory from an explicit allowlist.

Only files needed by the public portfolio are published. Test screenshots,
CI configuration, source utilities, documentation and repository metadata are
intentionally excluded. The source files are never modified.

Usage: python tools/build_public_site.py --output /tmp/portfolio-public-site
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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


def build(output, source=ROOT):
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
    for relative in files:
        origin = source / relative
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, destination)
        original_hash = hashlib.sha256(origin.read_bytes()).digest()
        copied_hash = hashlib.sha256(destination.read_bytes()).digest()
        if original_hash != copied_hash:
            raise ValueError(f"Copy verification failed: {relative}")
        total_bytes += destination.stat().st_size
    actual = {p.relative_to(output) for p in output.rglob("*") if p.is_file()}
    if actual != set(files):
        raise ValueError("Published file list does not match the allowlist")
    return {"files": len(files), "bytes": total_bytes, "megabytes": round(total_bytes / 1048576, 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Directory outside the repository")
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))


if __name__ == "__main__":
    main()
