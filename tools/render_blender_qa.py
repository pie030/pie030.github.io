"""Render neutral QA views of recovered .blend files with Blender Cycles CPU.

These views verify that geometry and materials can be opened and rendered; they
are not replacements for the authored portfolio renders.

Usage:
  blender --background --factory-startup --python-exit-code 1 \
    --python tools/render_blender_qa.py -- --blend-dir blender --output-dir blender/qa
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
MODELS = (
    'Creekside_Cottage_Watchtower',
    'Coastal_Fishing_Hut_Pier',
    'Rural_Railway_Stop_Freight_Wagon',
)
VIEWS = {
    'three_quarter': (1.2, -1.6, 1.05),
    'opposite': (-1.3, 1.5, 0.9),
    'aerial': (0.2, -0.3, 1.7),
}


def configure_scene(scene, center, size):
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 8
    # Ubuntu's Blender package lacks OpenImageDenoiser; render without it.
    for layer in scene.view_layers:
        layer.cycles.use_denoising = False
    scene.render.resolution_x = 960
    scene.render.resolution_y = 600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    world = scene.world or bpy.data.worlds.new('QA World')
    scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value = (0.21, 0.25, 0.28, 1)
    background.inputs['Strength'].default_value = 0.75

    light_data = bpy.data.lights.new('QA Area Light', type='AREA')
    light = bpy.data.objects.new('QA Area Light', light_data)
    scene.collection.objects.link(light)
    light.location = center + Vector((0.7, -0.8, 1.7)) * size
    light.rotation_euler = (center - light.location).to_track_quat('-Z', 'Y').to_euler()
    light_data.energy = 1200 * max(1.0, size / 20)
    light_data.shape = 'DISK'
    light_data.size = max(4.0, size)


def make_camera(scene, center, corners, direction, name):
    camera_data = bpy.data.cameras.new('QA Camera ' + name)
    camera = bpy.data.objects.new('QA Camera ' + name, camera_data)
    scene.collection.objects.link(camera)
    extent = max((point - center).length for point in corners)
    camera.location = center + Vector(direction).normalized() * max(5, extent * 4)
    camera.rotation_euler = (center - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.type = 'ORTHO'
    scene.camera = camera
    bpy.context.view_layer.update()
    projected = [camera.matrix_world.inverted() @ point for point in corners]
    x_size = max(p.x for p in projected) - min(p.x for p in projected)
    y_size = max(p.y for p in projected) - min(p.y for p in projected)
    aspect = scene.render.resolution_x / scene.render.resolution_y
    camera_data.ortho_scale = max(y_size, x_size / aspect) * 1.18
    return camera


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--blend-dir', default='blender')
    parser.add_argument('--output-dir', default='blender/qa')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    blend_dir = (ROOT / args.blend_dir).resolve()
    output_dir = (ROOT / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {}

    for name in MODELS:
        blend_path = blend_dir / (name + '.blend')
        if not blend_path.is_file():
            raise FileNotFoundError(blend_path)
        bpy.ops.wm.open_mainfile(filepath=str(blend_path))
        scene = bpy.context.scene
        meshes = [obj for obj in scene.objects if obj.type == 'MESH']
        if not meshes:
            raise RuntimeError(f'No meshes in {blend_path}')
        corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
        if not all(math.isfinite(float(v)) for p in corners for v in p):
            raise RuntimeError(f'Non-finite world-space bounds: {name}')
        low = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
        high = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
        center = (low + high) / 2
        size = max(high[i] - low[i] for i in range(3))
        if size < 0.1 or size > 1000:
            raise RuntimeError(f'Unexpected scene size: {name} {size}')
        configure_scene(scene, center, size)
        report[name] = {'world_bounds': [list(low), list(high)], 'views': {}}
        for view, direction in VIEWS.items():
            camera = make_camera(scene, center, corners, direction, view)
            image_path = output_dir / f'{name}_{view}.png'
            scene.render.filepath = str(image_path)
            bpy.ops.render.render(write_still=True)
            if not image_path.is_file() or image_path.stat().st_size < 2000:
                raise RuntimeError(f'Render is missing or too small: {image_path}')
            if image_path.open('rb').read(8) != b'\x89PNG\r\n\x1a\n':
                raise RuntimeError(f'Invalid render header: {image_path}')
            report[name]['views'][view] = {
                'file': image_path.name,
                'bytes': image_path.stat().st_size,
                'sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
            }
            print(f'QA RENDER {name} / {view}: {image_path.stat().st_size} bytes')
            bpy.data.objects.remove(camera, do_unlink=True)
    (output_dir / 'qa_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('QA renders complete:', sum(len(x['views']) for x in report.values()))


if __name__ == '__main__':
    main()
