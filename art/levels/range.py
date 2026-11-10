"""A firing range: flat ground, a few things to shoot at and hide behind, and a rank of
soldiers. For trying the weapons, the effects and the people out, not part of the game.

    python art/levels/range.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Level  # noqa: E402


def main():
    level = Level('range')
    level.add('camera 0 1.7 6 0 -0.05')
    level.kit('t', '../kits/test_kit.glb')
    level.standard(soldiers=6, rebels=2)
    level.place('t:ground', 0, 0, 0, 0, collide='coarse', surface='asphalt')
    level.place('t:barrier', 3, 0, -6, 20, surface='concrete')
    level.place('t:barrier', -3.5, 0, -9, -8, surface='concrete')
    level.place('t:crate', -2, 0, -5, 15, surface='wood')
    level.place('t:crate', -2.1, 0.9, -5.05, 40, scale=0.8, surface='wood')
    level.place('t:drum', 1.2, 0, -5.5, 0, surface='metal')
    level.place('t:drum', 1.9, 0, -5.2, 70, surface='metal')
    level.place('t:house', 0, 0.12, -22, 0, surface='wood')
    level.place('t:sheet', 5, 0, -8, 30, pitch=-12, surface='metal')
    level.add('tree oak 9 0.02 -14 variant=0')
    level.add('tree birch -9 0.02 -15 variant=1')
    level.marker('player', 'start', 0, 0.05, 2, 0)
    # A squad downrange that fights, two of the resistance beside the player, and a mannequin.
    level.marker('npc', 'a', -6.0, 0, -16, 180, ai=1)
    level.marker('npc', 'b', -2.0, 0, -18, 180, ai=1)
    level.marker('npc', 'c', 2.0, 0, -17, 180, ai=1)
    level.marker('npc', 'd', 6.0, 0, -15, 180, ai=1)
    level.marker('npc', 'e', 0.0, 0, -12, 180, shouldered=1)
    level.marker('npc', 'g', -2.5, 0, 3.5, 0, kind='rebel_a', ai=1, follow=1)
    level.marker('npc', 'h', 2.5, 0, 3.5, 0, kind='rebel_b', ai=1, follow=1)
    level.setting('time', 16.6)
    level.setting('weather', 'fair')
    level.write()


main()
