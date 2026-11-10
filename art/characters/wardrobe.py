"""Renders MakeHuman's clothes side by side, to choose what the game's people wear.

    blender --background --python art/characters/wardrobe.py

Needs MPFB, so it runs without --factory-startup.
"""

import glob
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
from lib import preview  # noqa: E402

OUTFITS = ['male_casualsuit01', 'male_casualsuit02', 'male_casualsuit03', 'male_casualsuit04',
           'male_casualsuit05', 'male_casualsuit06', 'male_elegantsuit01', 'male_worksuit01']
SHOES = ['shoes01', 'shoes02', 'shoes03', 'shoes04', 'shoes05', 'shoes06', 'shoes02', 'shoes04']


def main():
    from bl_ext.blender_org.mpfb.services.humanservice import HumanService
    from bl_ext.blender_org.mpfb.services.locationservice import LocationService
    data = LocationService.get_user_data()

    def asset(pattern):
        return sorted(glob.glob(os.path.join(data, pattern)))[0]

    for thing in list(bpy.data.objects):
        bpy.data.objects.remove(thing)
    body = {"gender": 1.0, "age": 0.5, "muscle": 0.6, "weight": 0.5, "proportions": 0.5, "height": 0.55,
            "cupsize": 0.5, "firmness": 0.5, "race": {"asian": 0.33, "caucasian": 0.34, "african": 0.33}}
    made = []
    for index, (outfit, shoes) in enumerate(zip(OUTFITS, SHOES)):
        basemesh = HumanService.create_human(macro_detail_dict=body)
        basemesh.name = outfit
        HumanService.set_character_skin(asset('skins/young_caucasian_male/*.mhmat'), basemesh,
                                        skin_type='ENHANCED', material_instances=True)
        HumanService.add_mhclo_asset(asset(f'clothes/{outfit}/*.mhclo'), basemesh, asset_type='Clothes',
                                     subdiv_levels=0, material_type='MAKESKIN')
        HumanService.add_mhclo_asset(asset(f'clothes/{shoes}/*.mhclo'), basemesh, asset_type='Clothes',
                                     subdiv_levels=0, material_type='MAKESKIN')
        basemesh.location.x = (index - 3.5) * 0.9
        made.append(basemesh)
    preview.render(os.path.join(HERE, '..', '..', 'build', 'previews', 'wardrobe.png'),
                   [o for o in bpy.data.objects if o.type == 'MESH'], views=[(180, 5)], size=(2000, 800),
                   samples=24, zoom=1.0)


main()
