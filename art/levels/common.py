"""What every HOLDOUT level file starts with: the kits, the people's clips, and the pools of
hidden things the game draws from. Level scripts write the rest.

A level script builds a list of lines and writes it to build/levels/NAME.txt, which `levelc`
compiles. Paths in the file are relative to build/levels.
"""

import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
LEVELS = os.path.join(ROOT, 'build', 'levels')

ROLES = '../../engine/characters/rigs/game_engine.roles'
UAL_ROLES = '../../engine/characters/rigs/ual.roles'
UAL1 = '../ual/ual1/UAL1_Standard.glb'
UAL2 = '../ual/ual2/UAL2_Standard.glb'

# The game's name for each clip, where it comes from, and whether it loops.
CLIPS = [
    ('idle', UAL1, 'Idle_Loop', True),
    ('walk', UAL1, 'Walk_Loop', True),
    ('jog', UAL1, 'Jog_Fwd_Loop', True),
    ('sprint', UAL1, 'Sprint_Loop', True),
    ('crouch_idle', UAL1, 'Crouch_Idle_Loop', True),
    ('crouch_walk', UAL1, 'Crouch_Fwd_Loop', True),
    ('death', UAL1, 'Death01', False),
    ('hit_chest', UAL1, 'Hit_Chest', False),
    ('hit_head', UAL1, 'Hit_Head', False),
    ('roll', UAL1, 'Roll', False),
    ('talk', UAL1, 'Idle_Talking_Loop', True),
    ('sit', UAL1, 'Sitting_Idle_Loop', True),
    ('fix', UAL1, 'Fixing_Kneeling', True),
    ('knockback', UAL2, 'Hit_Knockback', False),
    ('lay_to_idle', UAL2, 'LayToIdle', False),
    ('throw', UAL2, 'OverhandThrow', False),
    ('melee', UAL2, 'Melee_Hook', False),
    ('fold_arms', UAL2, 'Idle_FoldArms_Loop', True),
    ('phone', UAL2, 'Idle_TalkingPhone_Loop', True),
]


class Level:
    def __init__(self, name, texture_size=1024):
        self.name = name
        self.lines = [f'# {name}: written by art/levels/{name}.py. Do not edit: edit the script.',
                      f'texture_size {texture_size}']

    def add(self, line):
        self.lines.append(line)

    def kit(self, alias, path, skinned=False):
        suffix = f' skinned roles={ROLES}' if skinned else ''
        self.add(f'kit {alias} {path}{suffix}')

    def person(self, alias, count, clips=None):
        """A kind of character: its kit, its clips, and `count` bodies waiting to be used."""
        self.kit(alias, f'../characters/{alias}.glb', skinned=True)
        wanted = CLIPS if clips is None else [c for c in CLIPS if c[0] in clips]
        for name, source, source_clip, loops in wanted:
            self.add(f'clip {alias} {name} {source} {source_clip}{" loop" if loops else ""} roles={UAL_ROLES}')
        if count:
            self.add(f'pool {alias} {alias} {count}')

    def place(self, target, x, y, z, yaw=0.0, **options):
        words = [f'place {target} {x:.4f} {y:.4f} {z:.4f} {yaw:.3f}']
        words += [f'{key}={value}' for key, value in options.items() if value is not None]
        self.add(' '.join(words))

    def pool(self, name, target, count):
        self.add(f'pool {name} {target} {count}')

    def marker(self, marker_kind, name, x, y, z, yaw=0.0, **options):
        words = [f'meta marker {marker_kind} {name} {x:.3f} {y:.3f} {z:.3f} {yaw:.2f}']
        words += [f'{key}={value}' for key, value in options.items()]
        self.add(' '.join(words))

    def setting(self, key, value):
        self.add(f'meta set {key} {value}')

    def blocker(self, x, y, z, sx, sy, sz, yaw=0.0, surface=None):
        """A box, centred, of this full size. With no surface it is an invisible wall that
        stops people only; with one it is solid, and made of that."""
        self.add(f'meta blocker {x:.3f} {y:.3f} {z:.3f} {sx:.3f} {sy:.3f} {sz:.3f} {yaw:.2f}'
                 + (f' {surface}' if surface else ''))

    def standard(self, soldiers=8, rebels=2):
        """The kits and pools every playable level needs: the player's weapon and arms, the
        people, and what effects are drawn with."""
        self.kit('carbine', '../kits/carbine.glb')
        self.kit('fx', '../kits/fx.glb')
        # The player's own arms hold no clips: they are posed entirely by where the weapon is.
        self.kit('arms', '../characters/arms.glb', skinned=True)
        self.pool('fp_arms', 'arms', 1)
        for part in ('body', 'mag', 'bolt', 'charge', 'dot'):
            self.pool(f'fp_carbine_{part}', f'carbine:carbine_{part}', 1)
        self.kit('pistol', '../kits/pistol.glb')
        for part in ('body', 'mag', 'slide'):
            self.pool(f'fp_pistol_{part}', f'pistol:pistol_{part}', 1)
        self.person('soldier', soldiers)
        if rebels:
            self.person('rebel_a', (rebels + 1) // 2)
            self.person('rebel_b', rebels // 2)
        self.pool('npc_rifle', 'carbine:carbine_whole', soldiers + rebels)
        self.pool('tracer', 'fx:tracer', 16)
        self.pool('decal_hole', 'fx:decal_hole', 64)
        self.pool('decal_scorch', 'fx:decal_scorch', 4)
        self.pool('casing', 'carbine:casing_556', 28)
        # Grenades in the air: each waits out of sight until it is thrown.
        for _ in range(4):
            self.add('place fx:grenade 0 -400 0 0 collide=none tag=grenade surface=metal')
        self.add('dlight flash 6')

    def write(self):
        os.makedirs(LEVELS, exist_ok=True)
        path = os.path.join(LEVELS, f'{self.name}.txt')
        with open(path, 'w', encoding='utf-8', newline='\n') as file:
            file.write('\n'.join(self.lines) + '\n')
        print(f'wrote {path}: {len(self.lines)} lines')
        return path
