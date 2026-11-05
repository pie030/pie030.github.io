"""Correct legacy sRGB-authored material RGB factors for glTF linear baseColorFactor.

Changes only JSON material RGB values; all BIN bytes, geometry and alpha stay intact.
Original files are never overwritten by this script.
"""
import argparse
import json
import math
import struct
from pathlib import Path


def srgb_to_linear(value):
    if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"Invalid sRGB component: {value!r}")
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def convert_glb(content):
    if len(content) < 28 or content[:4] != b'glTF':
        raise ValueError('Invalid GLB header')
    magic, version, total_length = struct.unpack_from('<4sII', content)
    if version != 2 or total_length != len(content):
        raise ValueError('Invalid GLB version or length')
    offset = 12
    chunks = []
    while offset < len(content):
        if offset + 8 > len(content):
            raise ValueError('Truncated chunk header')
        length, kind = struct.unpack_from('<I4s', content, offset)
        offset += 8
        if length % 4 or offset + length > len(content):
            raise ValueError('Invalid GLB chunk length')
        chunks.append((kind, content[offset:offset + length]))
        offset += length
    if len(chunks) != 2 or chunks[0][0] != b'JSON' or chunks[1][0] != b'BIN\x00':
        raise ValueError('Expected JSON + BIN GLB')
    document = json.loads(chunks[0][1])
    if document.get('asset', {}).get('version') != '2.0':
        raise ValueError('Expected glTF 2.0')
    updated = 0
    for material in document.get('materials', []):
        pbr = material.get('pbrMetallicRoughness', {})
        if 'baseColorFactor' not in pbr:
            continue
        rgba = pbr['baseColorFactor']
        if not isinstance(rgba, list) or len(rgba) != 4:
            raise ValueError('Expected RGBA factor')
        pbr['baseColorFactor'] = [srgb_to_linear(v) for v in rgba[:3]] + [rgba[3]]
        updated += 1
    if not updated:
        raise ValueError('No baseColorFactor materials to convert')
    encoded = json.dumps(document, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    encoded += b' ' * (-len(encoded) % 4)
    binary = chunks[1][1]
    result = (struct.pack('<4sII', b'glTF', 2, 12 + 8 + len(encoded) + 8 + len(binary))
              + struct.pack('<I4s', len(encoded), b'JSON') + encoded
              + struct.pack('<I4s', len(binary), b'BIN\x00') + binary)
    return result, updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    converted, count = convert_glb(args.source.read_bytes())
    args.destination.write_bytes(converted)
    print(f'{args.source.name}: converted {count} materials')


if __name__ == '__main__':
    main()
