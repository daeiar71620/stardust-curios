#!/usr/bin/env python3
"""Export only observed/discovered illustrations; never read engine/private state.

Run with Python + Pillow. The renderer module is strictly read-only and does not
import the engine. Output contains known art only; do not ship this script or
renderer source as client code because their implementations include other art.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import uuid
from pathlib import Path
import re
import sys

from PIL import Image, ImageDraw

sys.dont_write_bytecode = True

FIELDS = ('art_id', 'name', 'kind', 'rarity', 'color')


def load_renderer(path):
    spec = importlib.util.spec_from_file_location('public_spectator_art', path)
    if spec is None or spec.loader is None:
        raise ValueError('Public renderer could not be loaded')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def known_items(observation, renderer):
    """Catalog identities need explicit True; possessed items are already known.

    Process the codex first, then let inventory/cabinet supply their public paint.
    A false discovered marker always fails closed. Never scan logs, crates,
    engine catalogs, aliases, or other files to infer an unobserved identity.
    """
    result = {}

    def add(row, source):
        if not isinstance(row, dict) or row.get('discovered') is False:
            return
        item = {key: row[key] for key in FIELDS if isinstance(row.get(key), str)}
        identity = item.get('art_id')
        if identity not in renderer.ITEM_ART_IDS:
            identity = renderer.ITEM_ART_NAMES.get(item.get('name'))
        if not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', identity):
            return
        item['art_id'] = identity
        item['discovered'] = True
        existing = result.get(identity, {})
        sources = existing.get('_sources', [])
        result[identity] = {**existing, **item, '_sources': list(dict.fromkeys([*sources, source]))}

    codex = observation.get('codex')
    entries = codex.get('entries', []) if isinstance(codex, dict) else []
    if isinstance(entries, list):
        for row in entries:
            projected = renderer.public_catalog_entry(row)
            if projected['discovered'] is True:
                add(projected, 'discovered')
    for key in ('inventory', 'collection'):
        rows = observation.get(key, [])
        if isinstance(rows, list):
            for row in rows:
                add(row, key)
    return dict(sorted(result.items()))


def export(observation_path, renderer_path, output_dir, size=512):
    if observation_path.is_symlink() or not (observation_path.name.endswith('.observation.json') or observation_path.name == 'observation.json'):
        raise ValueError('Input must be an explicitly supplied public .observation.json file')
    if observation_path.resolve().name.lower() in {'save.json', 'state.json'}:
        raise ValueError('Private save/state files are forbidden')
    if output_dir.is_symlink():
        raise ValueError('Symlink output folder is forbidden')
    if output_dir.resolve() in {observation_path.parent.resolve(), renderer_path.parent.resolve()}:
        raise ValueError('Choose a separate output folder')
    renderer = load_renderer(renderer_path)
    reader = renderer.ObservationReader(observation_path)
    if not reader.poll() or reader.observation is None:
        raise ValueError(reader.error or 'Invalid public observation')
    observation = reader.observation
    items = known_items(observation, renderer)
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_pngs = {f'{identity}.png' for identity in items} | {'known-art-preview.png'}
    stale_pngs = [path.name for path in output_dir.glob('*.png') if path.name not in expected_pngs]
    if stale_pngs:
        raise ValueError('Output contains art outside the current known set; use a fresh output folder')
    manifest = {'schema_version': 1,
                'observation_revision': observation.get('revision'),
                'observation_day': observation.get('day'),
                'width': size, 'height': size, 'transparent': True,
                'art': {}, 'items': []}
    sheet = Image.new('RGB', (1024, ((len(items)+3)//4)*294), renderer.BG)
    sheet_draw = ImageDraw.Draw(sheet)
    for index, (identity, item) in enumerate(items.items()):
        canvas = renderer.Renderer()
        canvas.image = Image.new('RGBA', (size*2, size*2), (0, 0, 0, 0))
        canvas.draw = ImageDraw.Draw(canvas.image)
        canvas.item_art(0, 0, size*2, item)
        picture = canvas.image.resize((size, size), Image.Resampling.LANCZOS)
        filename = f'{identity}.png'
        path = output_dir / filename
        if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
            raise ValueError('Unsafe artwork output file')
        temporary = path.with_name('.' + identity + '.' + uuid.uuid4().hex + '.tmp')
        try:
            picture.save(temporary, 'PNG', optimize=True)
            with Image.open(temporary) as check:
                check.verify()
            fd = os.open(temporary, os.O_RDONLY)
            try: os.fsync(fd)
            finally: os.close(fd)
            os.replace(temporary, path)
            fd = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally:
            if temporary.exists(): temporary.unlink()
        manifest['art'][identity] = filename
        manifest['items'].append({'art_id': identity, 'name': item.get('name', identity),
                                  'filename': filename, 'known_from': item['_sources'],
                                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        tile = picture.resize((240, 240), Image.Resampling.LANCZOS)
        x, y = (index % 4)*256+8, (index//4)*294
        sheet.paste(tile, (x, y), tile)
        sheet_draw.text((x+120, y+249), item.get('name', identity), font=renderer.font(18), fill=renderer.INK, anchor='mt')
        sheet_draw.text((x+120, y+273), identity, font=renderer.font(13), fill=renderer.MUTED, anchor='mt')
    (output_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if items:
        sheet.save(output_dir / 'known-art-preview.png')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observation', type=Path, required=True)
    parser.add_argument('--renderer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--size', type=int, default=512, choices=(256, 512, 1024))
    args = parser.parse_args()
    print(json.dumps(export(args.observation, args.renderer, args.output, args.size), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
