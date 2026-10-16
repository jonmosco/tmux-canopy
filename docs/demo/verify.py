#!/usr/bin/env python3
"""Coalesce demo GIFs and make numbered contact sheets for human review."""
import argparse
from pathlib import Path
import shutil
import subprocess as sp
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('gifs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='review frames and sheets outside docs/assets')
    args = parser.parse_args()
    if not shutil.which('magick'):
        sys.exit('ImageMagick magick is required to inspect coalesced GIF frames')
    output = args.output.resolve()
    for gif in args.gifs:
        if not gif.is_file():
            parser.error(f'GIF not found: {gif}')
        folder = output / gif.stem
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob('frame-*.png'):
            old.unlink()
        for old in folder.glob('sheet-*.png'):
            old.unlink()
        sp.run(['magick', str(gif), '-coalesce', str(folder / 'frame-%03d.png')], check=True)
        frames = sorted(folder.glob('frame-*.png'))
        if len(frames) < 2:
            raise RuntimeError(f'{gif}: no reviewable animation frames')
        # At half size the sheet shows timing/layout; full-size PNGs are also
        # retained so a reviewer can read every label and inspect any defect.
        for offset in range(0, len(frames), 10):
            sp.run(['magick', 'montage', *map(str, frames[offset:offset + 10]),
                    '-set', 'label', '%t', '-font', 'DejaVu-Sans', '-pointsize', '12',
                    '-geometry', '480x282+4+16', '-tile', '2x', '-background', '#171921',
                    str(folder / f'sheet-{offset // 10:02d}.png')], check=True)
        print(f'{gif}: {len(frames)} complete frames; review {folder}/sheet-*.png and frame-*.png')


if __name__ == '__main__':
    main()
