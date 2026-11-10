"""Prints the size of every part of a kit: its bounds in the engine's axes (X right, Y up,
Z toward the back of the part).

    python tools/kit_sizes.py build/kits/props.glb [NAME...]
"""

import json
import struct
import sys


def parts(path):
    with open(path, 'rb') as file:
        magic, _, _ = struct.unpack('<4sII', file.read(12))
        assert magic == b'glTF'
        length, kind = struct.unpack('<I4s', file.read(8))
        document = json.loads(file.read(length))
    found = {}
    for node in document['nodes']:
        if 'mesh' not in node:
            continue
        lo = [1e9] * 3
        hi = [-1e9] * 3
        for primitive in document['meshes'][node['mesh']]['primitives']:
            accessor = document['accessors'][primitive['attributes']['POSITION']]
            for axis in range(3):
                lo[axis] = min(lo[axis], accessor['min'][axis])
                hi[axis] = max(hi[axis], accessor['max'][axis])
        found[node['name']] = (lo, hi)
    return found


def main():
    path = sys.argv[1]
    wanted = sys.argv[2:]
    for name, (lo, hi) in parts(path).items():
        if wanted and not any(name.startswith(w) for w in wanted):
            continue
        print(f'{name:22s} x {lo[0]:7.2f}..{hi[0]:6.2f}  y {lo[1]:6.2f}..{hi[1]:6.2f}  z {lo[2]:7.2f}..{hi[2]:6.2f}')


main()
