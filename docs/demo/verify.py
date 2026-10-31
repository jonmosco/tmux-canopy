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
    has_magick = bool(shutil.which('magick'))
    has_ffmpeg = bool(shutil.which('ffmpeg'))
    if not has_magick and not has_ffmpeg:
        sys.exit('ImageMagick magick or ffmpeg is required to inspect coalesced GIF frames')
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
        if has_magick:
            sp.run(['magick', str(gif), '-coalesce', str(folder / 'frame-%03d.png')], check=True)
        else:
            sp.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-i', str(gif),
                    '-fps_mode', 'passthrough', str(folder / 'frame-%03d.png')], check=True)
        frames = sorted(folder.glob('frame-*.png'))
        if len(frames) < 2:
            raise RuntimeError(f'{gif}: no reviewable animation frames')
        # At half size the sheet shows timing/layout; full-size PNGs are also
        # retained so a reviewer can read every label and inspect any defect.
        for offset in range(0, len(frames), 10):
            batch = frames[offset:offset + 10]
            sheet = folder / f'sheet-{offset // 10:02d}.png'
            if has_magick:
                sp.run(['magick', 'montage', *map(str, batch),
                        '-set', 'label', '%t', '-font', 'DejaVu-Sans', '-pointsize', '12',
                        '-geometry', '480x282+4+16', '-tile', '2x', '-background', '#171921',
                        str(sheet)], check=True)
            else:
                rows = (len(batch) + 1) // 2
                sp.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                        '-pattern_type', 'sequence', '-start_number', str(offset + 1),
                        '-i', str(folder / 'frame-%03d.png'),
                        '-vf', f'select=lt(n\\,{len(batch)}),scale=480:-1,pad=488:ih+8:4:4:color=#171921,tile=2x{rows}:color=#171921',
                        '-frames:v', '1', '-update', '1', str(sheet)], check=True)
        print(f'{gif}: {len(frames)} complete frames; review {folder}/sheet-*.png and frame-*.png')


if __name__ == '__main__':
    main()
