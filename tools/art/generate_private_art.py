#!/usr/bin/env python3
"""Build server-private PNGs from synthetic identities in a public renderer.

No observation, save, player ID, credential, or network input is accepted.
Only public drawing code and literal catalogue/color data are loaded; the engine
is never imported or executed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import types

from PIL import Image, ImageColor, ImageDraw, __version__ as PILLOW_VERSION

SCHEMA_VERSION = 1
EXPECTED_COUNT = 24
CONSTANTS = {
    'BG', 'PANEL', 'PANEL2', 'INK', 'MUTED', 'TEAL', 'GOLD', 'LILAC',
    'RED', 'LINE', 'RARITIES', 'ITEM_ART_NAMES', 'ITEM_ART_IDS',
}
HELPERS = {'as_dict', 'safe_color'}
DRAWING_METHODS = {
    '__init__', 'rect', 'line', 'ellipse', 'polygon', 'star', 'item_art',
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_public_paint_catalog(catalog_path: Path):
    """Read public catalogue/color literals without importing the engine."""
    parsed = ast.parse(catalog_path.read_bytes(), filename='public_catalog_source.py')
    literals = {}
    for node in parsed.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {'CATALOG', 'COLORS'}:
                    literals[target.id] = ast.literal_eval(node.value)
    colors = literals.get('COLORS')
    rows = literals.get('CATALOG')
    if not isinstance(colors, dict) or not isinstance(rows, list):
        raise ValueError('Expected literal public CATALOG and COLORS definitions')
    if set(colors) != {'common', 'rare', 'legendary'} or any(
            not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value)
            for value in colors.values()):
        raise ValueError('Invalid public rarity color mapping')
    paint = {}
    for row in rows:
        if (not isinstance(row, (tuple, list)) or len(row) < 4
                or not all(isinstance(value, str) for value in row[:4])):
            raise ValueError('Invalid public catalogue row')
        identity, name, rarity, kind = row[:4]
        if identity in paint or rarity not in colors:
            raise ValueError('Duplicate identity or unknown rarity')
        # Copy public paint fields only. Do not retain values or descriptions.
        paint[identity] = {'art_id': identity, 'name': name, 'rarity': rarity,
                           'kind': kind, 'color': colors[rarity], 'discovered': True}
    canonical = json.dumps(paint, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return paint, colors, sha256(canonical)


def load_public_drawing_code(renderer_path: Path):
    """Extract drawing code, so reader/GUI/engine code is never imported or run."""
    source = renderer_path.read_bytes()
    parsed = ast.parse(source, filename='public_spectator_renderer.py')
    selected = []
    found_constants, found_helpers, found_methods = set(), set(), set()
    for node in parsed.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names and names <= CONSTANTS:
                selected.append(node)
                found_constants |= names
        elif isinstance(node, ast.FunctionDef) and node.name in HELPERS:
            selected.append(node)
            found_helpers.add(node.name)
        elif isinstance(node, ast.ClassDef) and node.name == 'Renderer':
            methods = [method for method in node.body
                       if isinstance(method, ast.FunctionDef) and method.name in DRAWING_METHODS]
            found_methods = {method.name for method in methods}
            selected.append(ast.ClassDef(name='Renderer', bases=[], keywords=[],
                                         body=methods, decorator_list=[]))
    if (found_constants != CONSTANTS or found_helpers != HELPERS
            or found_methods != DRAWING_METHODS):
        raise ValueError('Public drawing interface changed; review the generator before rebuilding')
    module = types.ModuleType('public_drawing_only')
    module.ImageColor = ImageColor
    code = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(code, 'public_spectator_renderer.py', 'exec'), module.__dict__)
    identities = sorted(module.ITEM_ART_IDS)
    if len(identities) != EXPECTED_COUNT or any(not re.fullmatch(r'[a-z][a-z0-9_-]*', identity)
                                               for identity in identities):
        raise ValueError('Expected exactly 24 safe public illustration IDs')
    return module, sha256(source)


def render_png(renderer, identity: str, size: int = 512, *, paint: dict) -> bytes:
    if identity not in renderer.ITEM_ART_IDS:
        raise ValueError('Unknown public illustration ID')
    canvas = renderer.Renderer()
    canvas.image = Image.new('RGBA', (size * 2, size * 2), (0, 0, 0, 0))
    canvas.draw = ImageDraw.Draw(canvas.image)
    # These values are constructed paint inputs, not a claim about player discovery.
    item = paint[identity]
    if item.get('art_id') != identity or item.get('discovered') is not True:
        raise ValueError('Invalid synthetic public paint')
    canvas.item_art(0, 0, size * 2, item)
    picture = canvas.image.resize((size, size), Image.Resampling.LANCZOS)
    output = BytesIO()
    picture.save(output, 'PNG', optimize=True, compress_level=9)
    return output.getvalue()


def generate(renderer_path: Path, catalog_path: Path, output_dir: Path, size: int = 512):
    if size not in (256, 512, 1024):
        raise ValueError('Use 256, 512, or 1024 pixels')
    if output_dir.is_symlink():
        raise ValueError('Symlink output folders are not supported')
    renderer, renderer_hash = load_public_drawing_code(renderer_path)
    paint, colors, paint_hash = load_public_paint_catalog(catalog_path)
    if set(paint) != renderer.ITEM_ART_IDS:
        raise ValueError('Public catalogue identities do not match the renderer')
    output_dir.mkdir(parents=True, exist_ok=True)
    png_dir = output_dir / 'png'
    if png_dir.is_symlink():
        raise ValueError('Symlink PNG folders are not supported')
    png_dir.mkdir(exist_ok=True)
    manifest = {
        'schema_version': SCHEMA_VERSION,
        'visibility': 'server-private',
        'source': 'synthetic-public-renderer-items',
        'renderer_sha256': renderer_hash,
        'pillow_version': PILLOW_VERSION,
        'width': size,
        'height': size,
        'format': 'PNG',
        'transparent': True,
        'paint_policy': 'canonical-public-rarity-colors',
        'public_paint_sha256': paint_hash,
        'rarity_colors': colors,
        'item_count': EXPECTED_COUNT,
        'total_png_bytes': 0,
        'art': {},
        'items': [],
    }
    for identity in sorted(renderer.ITEM_ART_IDS):
        data = render_png(renderer, identity, size, paint=paint)
        filename = f'png/{identity}.png'
        target = output_dir / filename
        if target.is_symlink() or (target.exists() and target.stat().st_nlink != 1):
            raise ValueError('Unsafe PNG target')
        target.write_bytes(data)
        manifest['art'][identity] = filename
        manifest['items'].append({
            'art_id': identity,
            'filename': filename,
            'sha256': sha256(data),
            'bytes': len(data),
            'rarity': paint[identity]['rarity'],
            'paint_color': paint[identity]['color'],
        })
        manifest['total_png_bytes'] += len(data)
    manifest_path = output_dir / 'manifest.json'
    if manifest_path.is_symlink() or (manifest_path.exists() and manifest_path.stat().st_nlink != 1):
        raise ValueError('Unsafe manifest target')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renderer', required=True, type=Path)
    parser.add_argument('--catalog', required=True, type=Path,
                        help='Public source file containing literal CATALOG and COLORS definitions')
    parser.add_argument('--output', required=True, type=Path,
                        help='Private server source directory; never use a static/public directory')
    parser.add_argument('--size', default=512, type=int, choices=(256, 512, 1024))
    args = parser.parse_args()
    manifest = generate(args.renderer, args.catalog, args.output, args.size)
    print(json.dumps({key: manifest[key] for key in
                      ('item_count', 'width', 'height', 'total_png_bytes', 'renderer_sha256')}, indent=2))


if __name__ == '__main__':
    main()
