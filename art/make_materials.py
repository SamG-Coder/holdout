"""Synthesises every tiling material into build/tex, and a contact sheet to look them over.

    blender --background --factory-startup --python art/make_materials.py -- [--size 1024]
        [--only NAME,NAME] [--out build/tex]

Run with Blender's Python because it brings numpy. A material is skipped when its files are
newer than the code that makes it, unless --force is given.
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402

from lib import materials, tex  # noqa: E402


def arguments():
    args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    options = {'size': 1024, 'only': None, 'out': os.path.join(HERE, '..', 'build', 'tex'), 'force': False}
    index = 0
    while index < len(args):
        if args[index] == '--size':
            options['size'] = int(args[index + 1])
            index += 2
        elif args[index] == '--only':
            options['only'] = args[index + 1].split(',')
            index += 2
        elif args[index] == '--out':
            options['out'] = args[index + 1]
            index += 2
        elif args[index] == '--force':
            options['force'] = True
            index += 1
        else:
            raise SystemExit(f'unknown argument {args[index]}')
    return options


def main():
    options = arguments()
    out = os.path.abspath(options['out'])
    os.makedirs(out, exist_ok=True)
    code_time = max(os.path.getmtime(os.path.join(HERE, 'lib', name)) for name in ('tex.py', 'materials.py'))
    previews = []
    for make in materials.ALL:
        name = make.__name__
        if options['only'] and name not in options['only']:
            continue
        colour_path = os.path.join(out, f'{name}_color.png')
        fresh = os.path.exists(colour_path) and os.path.getmtime(colour_path) > code_time
        if fresh and not options['force'] and not options['only']:
            continue
        start = time.time()
        default_small = name in ('glass', 'plastic', 'rubber')
        size = min(options['size'], 512) if default_small else options['size']
        made = make(n=size)
        made.write(out)
        print(f'{name}: {size}px, tile {made.tile_metres} m, {time.time() - start:.1f}s', flush=True)
        preview = made.preview()
        step = max(preview.shape[0] // 384, 1)
        small = preview[::step, ::step][:384, :384]
        if small.shape[0] < 384:
            small = np.pad(small, ((0, 384 - small.shape[0]), (0, 384 - small.shape[1]), (0, 0)))
        previews.append((name, small))
    if previews:
        columns = 6
        rows = (len(previews) + columns - 1) // columns
        sheet = np.zeros((rows * 384, columns * 384, 3), dtype=np.float32)
        for index, (_, small) in enumerate(previews):
            r, c = divmod(index, columns)
            sheet[r * 384:(r + 1) * 384, c * 384:(c + 1) * 384] = small
        tex.write_png(os.path.join(out, '_sheet.png'), sheet, is_colour=True)
        print('sheet:', ', '.join(name for name, _ in previews))


main()
