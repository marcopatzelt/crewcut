"""Beat 6 in Blender: chunky 3D type "Video!" (Manrope ExtraBold, extruded, bevelled, glossy near-black) whose glyphs
smash in from the camera one after another with squash and a small bounce; a puffy lilac 3D flower (top left) and a
yellow 3D star (bottom right, close to the lens, out of focus) pop in and turn. Fixed camera with a slow push; the comp
adds the splash. Cycles, RGBA, motion blur.

blender -b --factory-startup --python type3d.py -- --font F.otf --out DIR [--frames 1-170 | --frame N] [--half]
   [--text "Video!"] [--t0 0.0] [--tsmash 1.0]   (frame f = local time t0 + (f-1)/60)"""
import bpy, sys, math, random, os, argparse
from mathutils import Vector

a = argparse.ArgumentParser()
a.add_argument("--font", required=True); a.add_argument("--out", required=True); a.add_argument("--text", default="Video!")
a.add_argument("--frames", default="1-170"); a.add_argument("--frame", type=int); a.add_argument("--half", action="store_true")
a.add_argument("--samples", type=int, default=96); a.add_argument("--t0", type=float, default=0.0); a.add_argument("--tsmash", type=float, default=1.0)
a.add_argument("--width", type=float, default=760, help="text width in px at the end")
A = a.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
FPS = 60; random.seed(4)
bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
sc.render.fps = FPS
def F(t): return 1 + round((t - A.t0) * FPS)
def srgb(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)
def mat(name, hexc, rough, coat=0.0, sss=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb(hexc), 1); b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat; b.inputs["Coat Roughness"].default_value = 0.05
    if sss: b.inputs["Subsurface Weight"].default_value = sss; b.inputs["Subsurface Radius"].default_value = (0.3, 0.3, 0.3)
    return m

# ── type: one object per glyph, origin at its own centre ───────────────
font = bpy.data.fonts.load(A.font)
cu = bpy.data.curves.new("T", "FONT"); cu.body = A.text; cu.font = font; cu.size = 1.0; cu.align_x = "CENTER"; cu.align_y = "CENTER"
cu.extrude = 0.14; cu.bevel_depth = 0.022; cu.bevel_resolution = 4
to = bpy.data.objects.new("T", cu); sc.collection.objects.link(to)
bpy.context.view_layer.objects.active = to; to.select_set(True)
bpy.ops.object.convert(target="MESH")
bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.mesh.separate(type="LOOSE"); bpy.ops.object.mode_set(mode="OBJECT")
parts = [o for o in sc.objects if o.type == "MESH"]
for o in parts:
    bpy.context.view_layer.objects.active = o; bpy.ops.object.select_all(action="DESELECT"); o.select_set(True)
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    bpy.ops.object.shade_auto_smooth(angle=math.radians(40))
M_INK = mat("ink", "#15171B", 0.28, coat=0.8)
for o in parts: o.data.materials.clear(); o.data.materials.append(M_INK)
parts.sort(key=lambda o: o.location.x)
# glyphs of one letter (i and its dot) smash together: group parts by x overlap
groups = []
for o in parts:
    if groups and abs(groups[-1][0].location.x - o.location.x) < 0.12: groups[-1].append(o)
    else: groups.append([o])
xmin = min(o.location.x - o.dimensions.x / 2 for o in parts); xmax = max(o.location.x + o.dimensions.x / 2 for o in parts)
TW = xmax - xmin
for gi, g in enumerate(groups):
    t = A.tsmash + 0.035 * gi; sgn = -1 if gi % 2 else 1
    for o in g:
        home = o.location.copy(); rot0 = o.rotation_euler.copy()
        o.location = home + Vector((0.4 * sgn, 0.25, 3.2)); o.rotation_euler = (math.radians(-35), math.radians(25 * sgn), math.radians(18 * sgn)); o.scale = (1.6, 1.6, 1.6)
        for p in ("location", "rotation_euler", "scale"): o.keyframe_insert(p, frame=F(t - 0.12))
        o.location = home; o.rotation_euler = rot0; o.scale = (1.12, 0.84, 1.0)                       # impact squash
        for p in ("location", "rotation_euler", "scale"): o.keyframe_insert(p, frame=F(t))
        o.scale = (0.95, 1.07, 1.0); o.keyframe_insert("scale", frame=F(t + 0.07))
        o.scale = (1.0, 1.0, 1.0); o.keyframe_insert("scale", frame=F(t + 0.16))
        o.hide_render = True; o.keyframe_insert("hide_render", frame=F(t - 0.13)); o.hide_render = False; o.keyframe_insert("hide_render", frame=F(t - 0.12))

# ── 3D shapes: puffy flower (lilac) and star (yellow) ────────────────────
def flower(name, hexc, r):
    parts_ = []
    for i in range(5):
        a_ = 2 * math.pi * i / 5
        bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(math.cos(a_) * r * 0.95, math.sin(a_) * r * 0.95, 0), segments=32, ring_count=16)
        p = bpy.context.active_object; p.scale = (1.0, 0.82, 0.5); parts_.append(p)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r * 0.62, location=(0, 0, r * 0.12), segments=32, ring_count=16); c = bpy.context.active_object; c.scale = (1, 1, 0.6); parts_.append(c)
    for p in parts_: p.select_set(True)
    bpy.context.view_layer.objects.active = parts_[0]; bpy.ops.object.join(); o = bpy.context.active_object; o.name = name
    bpy.ops.object.shade_smooth(); o.data.materials.append(mat(name, hexc, 0.35, coat=0.3, sss=0.15)); return o
def star(name, hexc, r):
    bpy.ops.mesh.primitive_circle_add(vertices=8, radius=r, fill_type="NGON"); o = bpy.context.active_object; o.name = name
    for i, v in enumerate(o.data.vertices):
        k = 1.0 if i % 2 == 0 else 0.42; v.co.x *= k; v.co.y *= k
    sol = o.modifiers.new("solid", "SOLIDIFY"); sol.thickness = r * 0.45; sol.offset = 0
    bev = o.modifiers.new("bev", "BEVEL"); bev.width = r * 0.16; bev.segments = 6
    sub = o.modifiers.new("sub", "SUBSURF"); sub.levels = 2; sub.render_levels = 3
    bpy.ops.object.shade_smooth(); o.data.materials.append(mat(name, hexc, 0.3, coat=0.4, sss=0.1)); return o
fl = flower("Flower", "#A68CFF", 0.22); st = star("Star", "#FFC94D", 0.6)
def pop(o, at, home, s, spin):
    o.location = home; o.scale = (0.001, 0.001, 0.001); o.rotation_euler = (math.radians(30), math.radians(-20), 0)
    for p in ("scale", "rotation_euler"): o.keyframe_insert(p, frame=F(at))
    o.scale = (s * 1.15, s * 1.15, s * 1.15); o.keyframe_insert("scale", frame=F(at + 0.14))
    o.scale = (s, s, s); o.keyframe_insert("scale", frame=F(at + 0.3))
    o.rotation_euler = (math.radians(14), math.radians(10), math.radians(spin)); o.keyframe_insert("rotation_euler", frame=F(at + 2.0))

# ── camera: fixed, slow push; text width A.width px of 1920 at the end ──
cam = bpy.data.cameras.new("Cam"); cam.lens = 50; cam.sensor_width = 36
d = TW * 1920 / A.width * 50 / 36
co = bpy.data.objects.new("Cam", cam); sc.collection.objects.link(co); sc.camera = co
co.location = (0, -0.05, d * 1.08); co.keyframe_insert("location", frame=F(A.tsmash - 0.2))
co.location = (0, -0.05, d * 0.94); co.keyframe_insert("location", frame=F(A.tsmash + 1.8))
cam.dof.use_dof = True; cam.dof.focus_distance = d; cam.dof.aperture_fstop = 3.2
def frame_xy(fx, fy, z):        # point at fractions of the visible half-frame (end of the push), depth z
    hw = (d * 0.94 - z) * 0.36; return Vector((fx * hw, fy * hw * 1080 / 1920, z))
pop(fl, A.tsmash + 0.05, frame_xy(-0.8, 0.66, 0.2), 1.0, 70)       # top left, in the text plane
pop(st, A.tsmash + 0.1, frame_xy(0.84, -0.66, 1.8), 1.0, -45)      # bottom right, close to the lens (soft)
def area(name, loc, rot, size, energy, color=(1, 1, 1)):
    l = bpy.data.lights.new(name, "AREA"); l.size = size; l.energy = energy; l.color = color
    o = bpy.data.objects.new(name, l); sc.collection.objects.link(o); o.location = loc; o.rotation_euler = rot; return o
area("key", (-5, 6, 9), (math.radians(-35), math.radians(-28), 0), 8, 900, (1.0, 0.97, 0.93))
area("rim", (6, 3, -2), (math.radians(-60), math.radians(115), 0), 4, 700, (0.85, 0.95, 1.0))
area("fill", (4, -6, 8), (math.radians(35), math.radians(25), 0), 9, 300)
wo = bpy.data.worlds.new("W"); sc.world = wo; wo.use_nodes = True
wo.node_tree.nodes["Background"].inputs[0].default_value = (0.95, 0.95, 0.96, 1); wo.node_tree.nodes["Background"].inputs[1].default_value = 0.5

print("LAYOUT TW", round(TW, 3), "d", round(d, 3), "xmin", round(xmin, 3), "xmax", round(xmax, 3), "groups", len(groups))
for o in sc.objects:
    if o.type == "MESH" and o.name in ("Flower", "Star"): print("LAYOUT", o.name, tuple(round(v, 2) for v in o.location), tuple(round(v, 2) for v in o.dimensions), o.hide_render)
# ── render ──────────────────────────────────────────────────────────────
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080; sc.render.resolution_percentage = 50 if A.half else 100
sc.render.engine = "CYCLES"; cy = sc.cycles; cy.samples = A.samples; cy.use_denoising = True
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences; prefs.compute_device_type = "OPTIX"; prefs.get_devices()
    for dv in prefs.devices: dv.use = dv.type in ("OPTIX", "CUDA")
    cy.device = "GPU"; cy.denoiser = "OPTIX"
except Exception as e: print("GPU setup failed", e)
sc.render.film_transparent = True; sc.render.use_motion_blur = True; sc.render.motion_blur_shutter = 0.4
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "Medium High Contrast"
os.makedirs(A.out, exist_ok=True)
if A.frame:
    sc.frame_set(A.frame); sc.render.filepath = os.path.join(A.out, f"type_{A.frame:04d}.png"); bpy.ops.render.render(write_still=True)
else:
    s_, e_ = (int(x) for x in A.frames.split("-")); sc.frame_start, sc.frame_end = s_, e_
    sc.render.filepath = os.path.join(A.out, "type_####"); bpy.ops.render.render(animation=True)
print("TYPE3D_DONE")
