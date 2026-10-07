#!/usr/bin/env python3
"""Optional local-only contact sheet. Never package its output with web assets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--art-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.art_dir.resolve()):
        raise ValueError('Contact sheets must be outside the deployable art directory')
    manifest = json.loads((args.art_dir / 'manifest.json').read_text(encoding='utf-8'))
    sheet = Image.new('RGB', (1080, 4 * 216 + 56), '#101c29')
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=14)
    draw.text((20, 15), 'PRIVATE QUALITY REVIEW | 24 public-renderer illustrations | synthetic paint',
              fill='#f4c77d', font=font)
    for index, row in enumerate(manifest['items']):
        x, y = 12 + (index % 6) * 180, 54 + (index // 6) * 216
        draw.rounded_rectangle((x, y, x + 166, y + 204), radius=16, fill='#1b2b37')
        with Image.open(args.art_dir / row['filename']) as picture:
            tile = picture.resize((160, 160), Image.Resampling.LANCZOS)
            sheet.paste(tile, (x + 3, y + 3), tile)
        draw.text((x + 83, y + 166), row['art_id'], anchor='mt', fill='#f6edda', font=font)
        draw.text((x + 83, y + 188), f"{row['bytes'] / 1024:.1f} KiB", anchor='mt', fill='#aec1bb', font=small)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, 'PNG', optimize=True)


if __name__ == '__main__':
    main()
