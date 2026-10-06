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


def fingerprint(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def art_source_key(observation):
    """Hash effective public paint, not prices, logs or duplicate possessions.

    Merge in the same codex/inventory/cabinet order as known_items. Moving a
    second identical instance must not spawn an exporter if its paint is
    unchanged. Legacy name-only rows retain a conservative fallback key.
    """
    paint, legacy = {}, []
    codex = observation.get('codex') or {}
    for source in ('codex', 'inventory', 'collection'):
        rows = codex.get('entries', []) if source == 'codex' else observation.get(source, [])
        fields = FIELDS[:-1] if source == 'codex' else FIELDS
        for row in rows:
            if not isinstance(row, dict) or not (row.get('discovered') is True if source == 'codex' else row.get('discovered') is not False):
                continue
            item = {key: row[key] for key in fields if isinstance(row.get(key), str)}
            identity = item.get('art_id')
            if not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', identity):
                legacy.append([source, item])
                continue
            paint[identity] = {**paint.get(identity, {}), **item}
    return fingerprint({'paint': paint, 'legacy': legacy})


def cache_ready(observation, renderer_path, output_dir, size=512):
    """Cheap per-action fast path; any uncertainty falls back to full export.

    All PNG bytes and the public renderer content are checked. No process-wide
    or timestamp-only cache can hide a replacement renderer or damaged image.
    """
    if output_dir.is_symlink():
        raise ValueError('Symlink output folder is forbidden')
    manifest_path = output_dir / 'manifest.json'
    safe_output(manifest_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('schema_version') != 2 or manifest.get('source_paint_key') != art_source_key(observation):
            return False
        if manifest.get('renderer_sha256') != hashlib.sha256(renderer_path.read_bytes()).hexdigest():
            return False
        if manifest.get('width') != size or manifest.get('height') != size:
            return False
        entries = manifest.get('items', [])
        identities = [row['art_id'] for row in entries]
        if len(set(identities)) != len(identities) or any(not isinstance(identity, str) or not re.fullmatch(r'[a-z][a-z0-9_-]*', identity) for identity in identities):
            return False
        codex = observation.get('codex') or {}
        rows = [*observation.get('inventory', []), *observation.get('collection', []),
                *(row for row in codex.get('entries', []) if row.get('discovered') is True)]
        expected = {row['art_id'] for row in rows if row.get('discovered') is not False and isinstance(row.get('art_id'), str)}
        if set(identities) != expected or manifest.get('art') != {identity: identity+'.png' for identity in identities}:
            return False
        allowed = {identity+'.png' for identity in identities} | {'known-art-preview.png'}
        if any(path.name not in allowed for path in output_dir.glob('*.png')):
            return False
        return all(isinstance(row.get('render_key'), str) and cached_art(output_dir/(row['art_id']+'.png'), row, row['render_key'], size) is not None for row in entries)
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        return False


def safe_output(path):
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError('Unsafe artwork output file')


def atomic_output(path, writer):
    """Keep existing acknowledged artwork intact until its replacement is ready."""
    safe_output(path)
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        writer(temporary)
        fd = os.open(temporary, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def cached_art(path, entry, key, size):
    """Manifest metadata alone never permits reuse of an unverified image."""
    safe_output(path)
    if entry.get('render_key') != key or not path.is_file():
        return None
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry.get('sha256'):
            return None
        with Image.open(path) as image:
            if image.format != 'PNG' or image.size != (size, size):
                return None
            image.verify()
        return digest
    except (OSError, ValueError, SyntaxError):
        return None


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


def export(observation_path, renderer_path, output_dir, size=512, preview=True):
    if observation_path.is_symlink() or not (observation_path.name.endswith('.observation.json') or observation_path.name == 'observation.json'):
        raise ValueError('Input must be an explicitly supplied public .observation.json file')
    if observation_path.resolve().name.lower() in {'save.json', 'state.json'}:
        raise ValueError('Private save/state files are forbidden')
    if output_dir.is_symlink():
        raise ValueError('Symlink output folder is forbidden')
    if output_dir.resolve() in {observation_path.parent.resolve(), renderer_path.parent.resolve()}:
        raise ValueError('Choose a separate output folder')
    if size not in (256, 512, 1024):
        raise ValueError('Unsupported artwork size')
    renderer_hash = hashlib.sha256(renderer_path.read_bytes()).hexdigest()
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
    manifest_path = output_dir / 'manifest.json'
    safe_output(manifest_path)
    try:
        prior = json.loads(manifest_path.read_text(encoding='utf-8'))
        entries = {row['art_id']: row for row in prior.get('items', []) if isinstance(row, dict) and isinstance(row.get('art_id'), str)}
    except (OSError, ValueError, AttributeError, TypeError):
        prior, entries = {}, {}
    manifest = {'schema_version': 2, 'renderer_sha256': renderer_hash,
                'source_paint_key': art_source_key(observation),
                'observation_revision': observation.get('revision'),
                'observation_day': observation.get('day'),
                'width': size, 'height': size, 'transparent': True,
                'art': {}, 'items': []}
    changed = False
    for index, (identity, item) in enumerate(items.items()):
        filename = f'{identity}.png'
        path = output_dir / filename
        key = fingerprint({'renderer': renderer_hash, 'size': size,
                           'paint': {field: item.get(field) for field in FIELDS}})
        image_hash = cached_art(path, entries.get(identity, {}), key, size)
        if image_hash is None:
            changed = True
            canvas = renderer.Renderer()
            canvas.image = Image.new('RGBA', (size*2, size*2), (0, 0, 0, 0))
            canvas.draw = ImageDraw.Draw(canvas.image)
            canvas.item_art(0, 0, size*2, item)
            picture = canvas.image.resize((size, size), Image.Resampling.LANCZOS)
            def write_picture(temporary):
                picture.save(temporary, 'PNG', optimize=True)
                with Image.open(temporary) as check:
                    check.verify()
            atomic_output(path, write_picture)
            image_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest['art'][identity] = filename
        manifest['items'].append({'art_id': identity, 'name': item.get('name', identity),
                                  'filename': filename, 'known_from': item['_sources'],
                                  'sha256': image_hash, 'render_key': key})
    preview_path = output_dir / 'known-art-preview.png'
    # A no-preview export may update individual PNGs/manifest while leaving an
    # older sheet in place. Track that sheet independently from the art cache.
    preview_key = fingerprint({'renderer': renderer_hash, 'size': size,
                               'items': manifest['items']})
    if prior.get('preview_key') is not None:
        manifest['preview_key'] = prior['preview_key']
    if preview:
        safe_output(preview_path)
    if preview and items and (changed or prior.get('preview_key') != preview_key or not preview_path.exists()):
        sheet = Image.new('RGB', (1024, ((len(items)+3)//4)*294), renderer.BG)
        sheet_draw = ImageDraw.Draw(sheet)
        for index, (identity, item) in enumerate(items.items()):
            with Image.open(output_dir / f'{identity}.png') as picture:
                tile = picture.resize((240, 240), Image.Resampling.LANCZOS)
            x, y = (index % 4)*256+8, (index//4)*294
            sheet.paste(tile, (x, y), tile)
            sheet_draw.text((x+120, y+249), item.get('name', identity), font=renderer.font(18), fill=renderer.INK, anchor='mt')
            sheet_draw.text((x+120, y+273), identity, font=renderer.font(13), fill=renderer.MUTED, anchor='mt')
        atomic_output(preview_path, lambda temporary: sheet.save(temporary, 'PNG'))
        manifest['preview_key'] = preview_key
    if manifest != prior:
        atomic_output(manifest_path, lambda temporary: temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8'))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observation', type=Path, required=True)
    parser.add_argument('--renderer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--size', type=int, default=512, choices=(256, 512, 1024))
    parser.add_argument('--no-preview', action='store_true', help='Skip the contact sheet during per-action synchronization')
    args = parser.parse_args()
    print(json.dumps(export(args.observation, args.renderer, args.output, args.size, preview=not args.no_preview), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
