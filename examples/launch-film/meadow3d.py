"""Photoreal meadow (beat 2 iris and beat 3): low camera inside the grass, big blurred foreground blades in the lower
half, horizon at ~40 % from the top, deep natural greens with yellow-green backlit tips, real petal daisies and blue
cornflowers, HDRI sky with real clouds, sun as back light, wind. Cycles on the GPU. The film used Poly Haven's HDRI
"Kloofendal 48d Partly Cloudy (Pure Sky)" (CC0, Greg Zaal and Jarod Guest), downloaded at run time by plates.sh.

blender -b --factory-startup --python meadow3d.py -- --out DIR --hdri FILE.hdr [--frames 1-45 | --frame N]
   [--samples 64] [--half] [--t0 2.03] [--drift 0.4] [--hdri-rot 205] [--res 2304x1296]
Frame f shows comp time t0 + (f-1)/60."""
import bpy, bmesh, sys, math, random, os, argparse

a = argparse.ArgumentParser()
a.add_argument("--out", required=True); a.add_argument("--hdri", required=True)
a.add_argument("--frames", default="1-45"); a.add_argument("--frame", type=int)
a.add_argument("--samples", type=int, default=64); a.add_argument("--half", action="store_true")
a.add_argument("--t0", type=float, default=2.03); a.add_argument("--drift", type=float, default=0.4)
a.add_argument("--hdri-rot", type=float, default=205.0); a.add_argument("--hdri-strength", type=float, default=1.0)
a.add_argument("--res", default="2304x1296"); a.add_argument("--exposure", type=float, default=0.6)
a.add_argument("--blades", type=float, default=1700.0, help="blades per m2 near the camera"); a.add_argument("--seed", type=int, default=11)
A = a.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
FPS = 60
random.seed(A.seed)
sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
sc.render.fps = FPS

def srgb(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)

# ── materials ───────────────────────────────────────────────────────────
def grass_mat():
    m = bpy.data.materials.new("grass"); m.use_nodes = True; N = m.node_tree.nodes; L = m.node_tree.links
    for n in list(N):
        if n.type != "OUTPUT_MATERIAL": N.remove(n)
    tc = N.new("ShaderNodeTexCoord"); sep = N.new("ShaderNodeSeparateXYZ"); L.new(tc.outputs["UV"], sep.inputs[0])
    ramp = N.new("ShaderNodeValToRGB"); cr = ramp.color_ramp
    cr.elements[0].color = (*srgb("#03190A"), 1); cr.elements[1].position = 1.0; cr.elements[1].color = (*srgb("#86AE36"), 1)
    e = cr.elements.new(0.55); e.color = (*srgb("#1F5E19"), 1)   # deep, muted greens; dark roots = shadows between blades
    L.new(sep.outputs["Y"], ramp.inputs[0])
    oi = N.new("ShaderNodeObjectInfo"); hue = N.new("ShaderNodeHueSaturation"); L.new(ramp.outputs["Color"], hue.inputs["Color"]); hue.inputs["Saturation"].default_value = 1.0
    mr = N.new("ShaderNodeMapRange"); mr.inputs["To Min"].default_value = 0.47; mr.inputs["To Max"].default_value = 0.53
    L.new(oi.outputs["Random"], mr.inputs["Value"]); L.new(mr.outputs[0], hue.inputs["Hue"])
    mv = N.new("ShaderNodeMapRange"); mv.inputs["To Min"].default_value = 0.5; mv.inputs["To Max"].default_value = 0.9   # blades darker overall
    L.new(oi.outputs["Random"], mv.inputs["Value"]); L.new(mv.outputs[0], hue.inputs["Value"])
    pb = N.new("ShaderNodeBsdfPrincipled"); L.new(hue.outputs["Color"], pb.inputs["Base Color"])
    pb.inputs["Roughness"].default_value = 0.55; pb.inputs["Specular IOR Level"].default_value = 0.3
    tr = N.new("ShaderNodeBsdfTranslucent"); L.new(hue.outputs["Color"], tr.inputs["Color"])
    ms = N.new("ShaderNodeMixShader"); ms.inputs[0].default_value = 0.35
    L.new(pb.outputs[0], ms.inputs[1]); L.new(tr.outputs[0], ms.inputs[2])
    L.new(ms.outputs[0], N["Material Output"].inputs["Surface"])
    return m
def flat(name, hexc, rough=0.5, trans=0.0, sss=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True; b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*srgb(hexc), 1); b.inputs["Roughness"].default_value = rough
    b.inputs["Transmission Weight"].default_value = trans
    if sss: b.inputs["Subsurface Weight"].default_value = sss; b.inputs["Subsurface Radius"].default_value = (0.02, 0.02, 0.02)
    return m
M_GRASS = grass_mat(); M_PETAL = flat("petal", "#F7F6EE", 0.45, sss=0.4); M_EYE = flat("eye", "#E8A80F", 0.7)
M_BLUE = flat("blue", "#3E6FE0", 0.45, sss=0.3); M_STEM = flat("stem", "#2F6A1C", 0.6)

lib = bpy.data.collections.new("Lib"); sc.collection.children.link(lib)
def mkobj(name, me, mat=None):
    o = bpy.data.objects.new(name, me); lib.objects.link(o)
    if mat: o.data.materials.append(mat)
    return o

# ── blades: curved, tapered strips with 7 segments ──────────────────────
def blade(name, h, w, bend, twist):
    me = bpy.data.meshes.new(name); bm = bmesh.new(); seg = 7; uv = bm.loops.layers.uv.new(); rows = []
    for i in range(seg + 1):
        t = i / seg; z = h * (t - 0.18 * bend * bend * t * t); x = bend * h * t * t; ww = w * (1 - t) ** 0.7
        ang = twist * t; cx, cy = math.cos(ang) * ww / 2, math.sin(ang) * ww / 2
        rows.append((bm.verts.new((x - cx, -cy, z)), bm.verts.new((x + cx, cy, z)), t))
    for i in range(seg):
        f = bm.faces.new((rows[i][0], rows[i][1], rows[i + 1][1], rows[i + 1][0]))
        for lp, vt in zip(f.loops, (rows[i][2], rows[i][2], rows[i + 1][2], rows[i + 1][2])): lp[uv].uv = (0.5, vt)
    bm.to_mesh(me); bm.free(); return mkobj(name, me, M_GRASS)
blade_coll = bpy.data.collections.new("Blades"); lib.children.link(blade_coll)
for i in range(12):
    o = blade(f"blade{i}", random.uniform(0.18, 0.42), random.uniform(0.008, 0.016), random.uniform(-0.45, 0.45), random.uniform(-0.6, 0.6))
    lib.objects.unlink(o); blade_coll.objects.link(o)

# ── flowers with real petals ────────────────────────────────────────────
def petal_ring(bm, n, length, width, cup, z, mat_index, jitter=0.15, tip=0.4):
    for i in range(n):
        ang = 2 * math.pi * (i + random.uniform(-jitter, jitter)) / n
        ca, sa = math.cos(ang), math.sin(ang); L = length * random.uniform(0.85, 1.1)
        pts = []
        for k, (u, wv) in enumerate(((0.0, 0.25), (0.35, 1.0), (0.75, 0.9), (1.0, tip))):
            r = 0.006 + L * u; h = z + cup * L * u * u
            for s_ in (-1, 1):
                px, py = r * ca - s_ * width * wv / 2 * sa, r * sa + s_ * width * wv / 2 * ca
                pts.append(bm.verts.new((px, py, h)))
        for k in range(3):
            f = bm.faces.new((pts[2 * k], pts[2 * k + 1], pts[2 * k + 3], pts[2 * k + 2])); f.material_index = mat_index
def flower(name, kind, h):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    if kind == "daisy":
        petal_ring(bm, random.randint(18, 24), 0.024, 0.0055, 0.25, h, 0)
        bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=0.0075, matrix=__import__("mathutils").Matrix.Translation((0, 0, h)) @ __import__("mathutils").Matrix.Diagonal((1, 1, 0.55, 1)))
    else:
        petal_ring(bm, 11, 0.02, 0.008, 0.9, h, 0, tip=0.9)
        petal_ring(bm, 7, 0.011, 0.006, 1.4, h + 0.003, 0, tip=0.9)
    st = bmesh.ops.create_cone(bm, segments=6, radius1=0.0025, radius2=0.0018, depth=h, cap_ends=False,
                               matrix=__import__("mathutils").Matrix.Translation((0, 0, h / 2)))
    bm.to_mesh(me); bm.free()
    o = mkobj(name, me)
    o.data.materials.append(M_PETAL if kind == "daisy" else M_BLUE); o.data.materials.append(M_EYE); o.data.materials.append(M_STEM)
    # centre sphere -> eye material, stem -> stem material (by height and radius)
    for p in o.data.polygons:
        c = p.center
        if abs(c.z - h) < 0.006 and math.hypot(c.x, c.y) < 0.007 and kind == "daisy": p.material_index = 1
        elif c.z < h - 0.004 and math.hypot(c.x, c.y) < 0.004: p.material_index = 2
    return o
daisy_coll = bpy.data.collections.new("Daisies"); lib.children.link(daisy_coll)
corn_coll = bpy.data.collections.new("Corn"); lib.children.link(corn_coll)
for i in range(4):
    o = flower(f"daisy{i}", "daisy", random.uniform(0.16, 0.3)); lib.objects.unlink(o); daisy_coll.objects.link(o)
for i in range(3):
    o = flower(f"corn{i}", "corn", random.uniform(0.2, 0.34)); lib.objects.unlink(o); corn_coll.objects.link(o)
bpy.context.view_layer.layer_collection.children["Lib"].exclude = True

# ── ground + scatter (Geometry Nodes, wind) ─────────────────────────────
soil = flat("soil", "#25361A", 0.95)
def ground(name, sx, sy, cy, z=0.0):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0)); g = bpy.context.active_object; g.name = name
    g.scale = (sx, sy, 1); g.location = (0, cy, z)
    bpy.ops.object.transform_apply(scale=True)          # keep this on its own line (17.11.: a comment once swallowed it)
    g.data.materials.append(soil); return g
def scatter(obj, coll, density, size, rnd, seed, tilt=0.3, wind=1.0):
    ng = bpy.data.node_groups.new(f"scatter_{coll.name}_{seed}", "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N = ng.nodes; L = ng.links; gi = N.new("NodeGroupInput"); go = N.new("NodeGroupOutput")
    dp = N.new("GeometryNodeDistributePointsOnFaces"); dp.inputs["Density"].default_value = density; dp.inputs["Seed"].default_value = seed
    ci = N.new("GeometryNodeCollectionInfo"); ci.inputs["Collection"].default_value = coll
    ci.inputs["Separate Children"].default_value = True; ci.inputs["Reset Children"].default_value = True
    ip = N.new("GeometryNodeInstanceOnPoints"); ip.inputs["Pick Instance"].default_value = True
    rr = N.new("FunctionNodeRandomValue"); rr.data_type = "FLOAT_VECTOR"
    rr.inputs["Min"].default_value = (-tilt, -tilt, 0); rr.inputs["Max"].default_value = (tilt, tilt, 2 * math.pi); rr.inputs["Seed"].default_value = seed + 1
    rs = N.new("FunctionNodeRandomValue"); rs.data_type = "FLOAT"; rs.inputs["Min"].default_value = size * (1 - rnd); rs.inputs["Max"].default_value = size * (1 + rnd); rs.inputs["Seed"].default_value = seed + 2
    ri = N.new("FunctionNodeRandomValue"); ri.data_type = "INT"; ri.inputs["Min"].default_value = 0; ri.inputs["Max"].default_value = 99; ri.inputs["Seed"].default_value = seed + 3
    pos = N.new("GeometryNodeInputPosition"); st = N.new("GeometryNodeInputSceneTime")
    sc4 = N.new("ShaderNodeVectorMath"); sc4.operation = "SCALE"; sc4.inputs["Scale"].default_value = 0.4; L.new(pos.outputs[0], sc4.inputs[0])
    tm = N.new("ShaderNodeMath"); tm.operation = "MULTIPLY"; tm.inputs[1].default_value = 0.6; L.new(st.outputs["Seconds"], tm.inputs[0])
    nz = N.new("ShaderNodeTexNoise"); nz.noise_dimensions = "4D"; L.new(sc4.outputs[0], nz.inputs["Vector"]); L.new(tm.outputs[0], nz.inputs["W"])
    cen = N.new("ShaderNodeVectorMath"); cen.operation = "SUBTRACT"; cen.inputs[1].default_value = (0.5, 0.5, 0.5); L.new(nz.outputs["Color"], cen.inputs[0])
    amp = N.new("ShaderNodeVectorMath"); amp.operation = "MULTIPLY"; amp.inputs[1].default_value = (0.14 * wind, 0.14 * wind, 0.0); L.new(cen.outputs[0], amp.inputs[0])
    add = N.new("ShaderNodeVectorMath"); add.operation = "ADD"; L.new(rr.outputs[0], add.inputs[0]); L.new(amp.outputs[0], add.inputs[1])
    jg = N.new("GeometryNodeJoinGeometry")
    L.new(gi.outputs[0], dp.inputs["Mesh"]); L.new(dp.outputs["Points"], ip.inputs["Points"]); L.new(ci.outputs[0], ip.inputs["Instance"])
    L.new(add.outputs[0], ip.inputs["Rotation"]); L.new(rs.outputs[1], ip.inputs["Scale"]); L.new(ri.outputs[2], ip.inputs["Instance Index"])
    L.new(gi.outputs[0], jg.inputs[0]); L.new(ip.outputs[0], jg.inputs[0]); L.new(jg.outputs[0], go.inputs[0])
    obj.modifiers.new(f"scatter_{coll.name}_{seed}", "NODES").node_group = ng
CAM_Y = -2.0
near = ground("Near", 6, 6, CAM_Y + 0.25 + 3.0)               # 0.25 m .. 6.25 m in front of the lens, densest
mid = ground("Mid", 16, 20, CAM_Y + 6.25 + 10.0, -0.005)
far = ground("Far", 120, 90, CAM_Y + 26.25 + 45.0, -0.02)
scatter(near, blade_coll, A.blades, 0.8, 0.45, 1)
scatter(near, daisy_coll, 8.0, 0.85, 0.3, 2, tilt=0.15); scatter(near, corn_coll, 3.5, 0.85, 0.3, 3, tilt=0.15)
scatter(mid, blade_coll, A.blades * 0.45, 1.05, 0.45, 4)
scatter(mid, daisy_coll, 4.0, 0.9, 0.3, 5, tilt=0.15); scatter(mid, corn_coll, 1.6, 0.9, 0.3, 6, tilt=0.15)
scatter(far, blade_coll, 60.0, 1.9, 0.5, 7, wind=0.4)
scatter(far, daisy_coll, 0.35, 1.3, 0.3, 8, tilt=0.15)
# a few big flowers and tall blades right at the lens, left and right (they make the depth)
for i, (x, y, sz, kind) in enumerate([(-0.34, 0.55, 2.4, "d"), (-0.52, 0.9, 1.5, "c"), (-0.22, 1.25, 1.8, "d"), (0.36, 0.5, 2.6, "d"),
                                      (0.55, 0.85, 1.6, "c"), (0.28, 1.15, 1.9, "d"), (0.7, 1.4, 2.0, "d"), (-0.68, 1.5, 1.4, "c")]):
    src = (daisy_coll if kind == "d" else corn_coll).objects[i % 3]
    o = bpy.data.objects.new(f"near{i}", src.data); sc.collection.objects.link(o)
    o.location = (x, CAM_Y + y, 0); o.scale = (sz, sz, sz); o.rotation_euler = (random.uniform(-0.2, 0.2), random.uniform(-0.25, 0.25), random.uniform(0, 6.28))

# ── sky: HDRI (Poly Haven, CC0) + sun as back light ─────────────────────
wo = bpy.data.worlds.new("Sky"); sc.world = wo; wo.use_nodes = True; N = wo.node_tree.nodes; Lk = wo.node_tree.links
env = N.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(A.hdri)
tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Rotation"].default_value = (0, 0, math.radians(A.hdri_rot))
Lk.new(tc.outputs["Generated"], mp.inputs["Vector"]); Lk.new(mp.outputs["Vector"], env.inputs["Vector"])
bg = N["Background"]; Lk.new(env.outputs["Color"], bg.inputs["Color"]); bg.inputs["Strength"].default_value = A.hdri_strength
sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = 2.6; sun.color = (1.0, 0.93, 0.82); sun.angle = math.radians(3)
so = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(so)
so.rotation_euler = (math.radians(-74), 0, math.radians(22))     # light travels towards the camera, 16 deg down, from front left

# ── camera: low inside the grass ────────────────────────────────────────
cam = bpy.data.cameras.new("Cam"); cam.lens = 30; cam.sensor_width = 36
co = bpy.data.objects.new("Cam", cam); sc.collection.objects.link(co); sc.camera = co
cam.dof.use_dof = True; cam.dof.focus_distance = 2.2; cam.dof.aperture_fstop = 2.8
def F(t): return 1 + round((t - A.t0) * FPS)
co.location = (0, CAM_Y, 0.36); co.keyframe_insert("location", frame=1)
co.location = (0.03, CAM_Y + A.drift, 0.37); co.keyframe_insert("location", frame=F(A.t0 + 8.0))
co.rotation_euler = (math.radians(86.3), 0, math.radians(-0.8)); co.keyframe_insert("rotation_euler", frame=1)   # horizon ~40 % from the top
co.rotation_euler = (math.radians(86.1), 0, math.radians(0.6)); co.keyframe_insert("rotation_euler", frame=F(A.t0 + 8.0))

# ── render ──────────────────────────────────────────────────────────────
rx, ry = (int(v) for v in A.res.split("x"))
sc.render.resolution_x, sc.render.resolution_y = rx, ry; sc.render.resolution_percentage = 50 if A.half else 100
sc.render.engine = "CYCLES"; cy = sc.cycles; cy.samples = A.samples; cy.use_denoising = True
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences; prefs.compute_device_type = "OPTIX"; prefs.get_devices()
    for d in prefs.devices: d.use = d.type in ("OPTIX", "CUDA")
    cy.device = "GPU"; cy.denoiser = "OPENIMAGEDENOISE"
except Exception as e: print("GPU setup failed", e)
cy.max_bounces = 6; cy.diffuse_bounces = 2; cy.glossy_bounces = 2; cy.transmission_bounces = 4; cy.transparent_max_bounces = 8
cy.caustics_reflective = False; cy.caustics_refractive = False
sc.render.use_persistent_data = True; sc.render.use_motion_blur = False
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Medium High Contrast"; sc.view_settings.exposure = A.exposure
sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 95
os.makedirs(A.out, exist_ok=True)
if A.frame:
    sc.frame_set(A.frame); sc.render.filepath = os.path.join(A.out, f"meadow_{A.frame:04d}.jpg"); bpy.ops.render.render(write_still=True)
else:
    s, e2 = (int(x) for x in A.frames.split("-")); sc.frame_start, sc.frame_end = s, e2
    sc.render.filepath = os.path.join(A.out, "meadow_####"); bpy.ops.render.render(animation=True)
print("MEADOW_DONE")
