"""A tiny Blender plate for the CI smoke test of the CC0 asset path: a Poly Haven HDRI lights a sphere on a floor with
an ambientCG material, rendered by Cycles. Takes the plate contract (--out DIR --frames A-B) plus --hdri and
--material specs; crewcut_assets comes from the plate bootstrap (crewcut/render/plate_quality.py).

blender -b --factory-startup --python hdri_plate.py -- --out DIR --frames 1-1 --hdri studio_small_09 --material Paper005
"""
import argparse
import os
import sys

import bpy
import crewcut_assets as ca

a = argparse.ArgumentParser()
a.add_argument("--out", required=True)
a.add_argument("--frames", default="1-1")
a.add_argument("--hdri", default="studio_small_09")
a.add_argument("--material", default="Paper005")
a.add_argument("--res", default="1k")
A = a.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.render.film_transparent = False
sc.render.image_settings.file_format = "PNG"

ca.world_hdri(ca.hdri(A.hdri, A.res), strength=1.0, rotation=200)
paper = ca.material_from(ca.material(A.material, A.res.upper()), name="paper", scale=2.0, tint="#FAF9F5")

bpy.ops.mesh.primitive_plane_add(size=8, location=(0, 0, 0))
floor = bpy.context.active_object
floor.data.materials.append(paper)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.8, location=(0, 0, 0.8), segments=48, ring_count=24)
ball = bpy.context.active_object
blue = bpy.data.materials.new("accent")
blue.use_nodes = True
bsdf = blue.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0.017, 0.015, 0.67, 1.0)   # #2320D6 in linear light
bsdf.inputs["Roughness"].default_value = 0.35
ball.data.materials.append(blue)
bpy.ops.object.shade_smooth()

bpy.ops.object.camera_add(location=(0, -5.2, 2.2), rotation=(1.2, 0, 0))
sc.camera = bpy.context.active_object

first, last = (int(x) for x in A.frames.split("-"))
os.makedirs(A.out, exist_ok=True)
for f in range(first, last + 1):
    sc.frame_set(f)
    sc.render.filepath = os.path.join(A.out, f"{f:04d}.png")
    bpy.ops.render.render(write_still=True)
