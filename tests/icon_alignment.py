#!/usr/bin/env python3
"""scripts/tree-source's per-app icon override loop and lib/tree-render.awk's
icon_keys list must list the same apps in the same order: tree-render.awk
reads override fields positionally ($(17+i)), so any drift silently shifts
every icon override past the point of divergence (see the "agent" desync
that broke lazygit appearance detection and the top/make/agy overrides)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source_text = (ROOT / 'scripts/tree-source').read_text()
    source_match = re.search(r'for app in ([\w ]+); do', source_text)
    assert source_match, 'could not find the tree-source app loop'
    source_apps = source_match.group(1).split()

    render_text = (ROOT / 'lib/tree-render.awk').read_text()
    render_match = re.search(r'nicons=split\("([\w ]+)",icon_keys', render_text)
    assert render_match, 'could not find tree-render.awk icon_keys list'
    render_apps = render_match.group(1).split()

    assert source_apps == render_apps, (
        'scripts/tree-source app loop and tree-render.awk icon_keys have drifted; '
        'they must list the same apps in the same order because icon overrides '
        f'are read positionally.\ntree-source: {source_apps}\ntree-render.awk: {render_apps}'
    )
    print('ok - scripts/tree-source app list matches tree-render.awk icon_keys order')


if __name__ == '__main__':
    main()
