"""Makes HOLDOUT's people and exports them for the engine.

    python art/build_characters.py [KIND ...] [--preview]

For each kind (by default all of them) it runs art/characters/people.py in Blender to make
`build/characters/KIND.blend`, then the engine's export tool, which bakes the materials down to
the textures the engine reads, writes `build/characters/KIND.glb`, and checks it.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
ENGINE = os.path.join(ROOT, 'engine')
BLENDER = os.environ.get('BLENDER', 'D:/Blender/blender.exe')
KINDS = ['soldier', 'rebel_a', 'rebel_b', 'arms']


def run(command, quiet_prefixes=('[INFO', 'INFO:', 'OBJ ')):
    print('+', ' '.join(command), flush=True)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               errors='replace')
    for line in process.stdout:
        line = line.rstrip()
        if line and not line.startswith(quiet_prefixes) and '| INFO' not in line and 'Fra:' not in line:
            print('  ' + line, flush=True)
    if process.wait() != 0:
        sys.exit(f'failed: {command[0]}')


def main():
    args = sys.argv[1:]
    preview = '--preview' in args
    kinds = [a for a in args if not a.startswith('--')] or KINDS
    out = os.path.join(ROOT, 'build', 'characters')
    os.makedirs(out, exist_ok=True)
    # Forward slashes: the export tool splits the command as a POSIX shell would.
    checker = os.path.join(ENGINE, 'target', 'release', 'bake.exe').replace(os.sep, '/')
    roles = os.path.join(ENGINE, 'characters', 'rigs', 'game_engine.roles')
    export_only = '--export-only' in args
    for kind in kinds:
        blend = os.path.join(out, f'{kind}.blend')
        glb = os.path.join(out, f'{kind}.glb')
        # The people need MPFB, which needs the user's preferences: no factory startup here.
        make = [BLENDER, '--background', '--python-exit-code', '1', '--python',
                os.path.join(HERE, 'characters', 'people.py'), '--', kind, blend]
        if preview:
            make.append('--preview')
        if not (export_only and os.path.exists(blend)):
            run(make)
        run([BLENDER, '--background', '--factory-startup', '--python-exit-code', '1', blend, '--python',
             os.path.join(ENGINE, 'tools', 'blender', 'solstice_export.py'), '--', glb, '--roles', roles,
             '--texture-size', '1024', '--checker', f'"{checker}"' if ' ' in checker else checker])
        print(f'{kind}: {os.path.getsize(glb) / 1e6:.1f} MB')


main()
