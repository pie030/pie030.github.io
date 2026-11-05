"""Recover editable Blender scenes from the portfolio's existing GLB exports.

Usage:
  blender --background --factory-startup --python tools/recover_blender_projects.py -- --output-dir blender

This reconstructs Blender scenes from exported geometry/materials. It cannot
restore original modeling history, unapplied modifiers, or procedural setups.
Run locally with Blender 4.x; Blender is not required to serve the website.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "Creekside_Cottage_Watchtower": "assets/creekside-yup-v03.glb",
    "Coastal_Fishing_Hut_Pier": "assets/coastal-fishing-hut-pier-yup.glb",
    "Rural_Railway_Stop_Freight_Wagon": "assets/rural-railway-stop-freight-wagon-yup.glb",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="blender")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    destination = Path(args.output_dir)
    if not destination.is_absolute():
        destination = ROOT / destination
    destination.mkdir(parents=True, exist_ok=True)

    report = {}
    for name, source in MODELS.items():
        model_path = ROOT / source
        if not model_path.is_file():
            raise FileNotFoundError(model_path)

        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(model_path))
        meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
        if not meshes:
            raise RuntimeError(f"No mesh objects imported from {model_path}")

        vertex_count = sum(len(obj.data.vertices) for obj in meshes)
        polygon_count = sum(len(obj.data.polygons) for obj in meshes)
        if vertex_count <= 0 or polygon_count <= 0:
            raise RuntimeError(f"Imported scene is empty: {model_path}")
        for obj in meshes:
            for vertex in obj.data.vertices:
                if not all(math.isfinite(float(v)) for v in vertex.co):
                    raise ValueError(f"Non-finite coordinate in {obj.name}")

        output = destination / (name + ".blend")
        bpy.ops.wm.save_as_mainfile(filepath=str(output), check_existing=False)
        report[name] = {
            "source": source,
            "blend_file": str(output),
            "mesh_objects": len(meshes),
            "vertices": vertex_count,
            "polygons": polygon_count,
            "materials": len(bpy.data.materials),
        }
        print(f"Saved {output} ({len(meshes)} mesh objects, {polygon_count} polygons)")

    (destination / "import_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
