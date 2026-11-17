"""Photoreal meadow (beat 2 iris and beat 3): low camera inside the grass, big blurred foreground blades in the lower
half, horizon at ~40 % from the top, deep natural greens with yellow-green backlit tips, real petal daisies and blue
cornflowers, HDRI sky with real clouds, sun as back light, wind. Cycles on the GPU. The film used Poly Haven's HDRI
"Kloofendal 48d Partly Cloudy (Pure Sky)" (CC0, Greg Zaal and Jarod Guest), downloaded at run time by plates.sh.

blender -b --factory-startup --python meadow3d.py -- --out DIR --hdri FILE.hdr [--frames 1-45 | --frame N]
   [--samples 64] [--half] [--t0 2.03] [--drift 0.4] [--hdri-rot 205] [--res 2304x1296]
Frame f shows comp time t0 + (f-1)/60.

The landing page's web meadow uses the same scene with a still camera and a seamless loop (site/tools/meadow/web.sh):
   --loop 240 --fps 30   the wind noise runs on a circle (W and Z of the 4D noise are cos and sin of 2 pi f / 240), so
                         frame 241 equals frame 1: render 1-240 and the clip loops with no cut and no dissolve
   --field wide --cam-z 0.8 --lens 24 --shift-y -0.07 --fstop 8 --focus 9 --res 3840x2160
                         a higher, wider still camera, the ground zones sized to its view, the horizon at about 38 %
   --sun-match AZ        turns the HDRI so its sun stands AZ degrees left of straight ahead, and puts the sun lamp there
   --haze M              aerial haze: far grass fades towards --haze-color (about 63 % at M metres)
Without these options the film's plate comes out as before."""
import bpy, bmesh, sys, math, random, os, argparse

a = argparse.ArgumentParser()
a.add_argument("--out", required=True); a.add_argument("--hdri", required=True)
a.add_argument("--frames", default="1-45"); a.add_argument("--frame", type=int)
a.add_argument("--samples", type=int, default=64); a.add_argument("--half", action="store_true")
a.add_argument("--t0", type=float, default=2.03); a.add_argument("--drift", type=float, default=0.4)
a.add_argument("--hdri-rot", type=float, default=205.0); a.add_argument("--hdri-strength", type=float, default=1.0)
a.add_argument("--res", default="2304x1296"); a.add_argument("--exposure", type=float, default=0.6)
a.add_argument("--blades", type=float, default=1700.0, help="blades per m2 near the camera"); a.add_argument("--seed", type=int, default=11)
a.add_argument("--fps", type=int, default=60); a.add_argument("--loop", type=int, default=0, help="seamless wind loop of N frames, still camera")
a.add_argument("--wind-speed", type=float, default=0.6, help="noise units per second"); a.add_argument("--wind", type=float, default=1.0)
a.add_argument("--field", default="film", choices=["film", "wide"]); a.add_argument("--cam-z", type=float, default=0.36)
a.add_argument("--lens", type=float, default=30.0); a.add_argument("--shift-y", type=float, default=0.0); a.add_argument("--yaw", type=float, default=0.0)
a.add_argument("--focus", type=float, default=2.2); a.add_argument("--fstop", type=float, default=2.8)
a.add_argument("--sun-elev", type=float, default=16.0); a.add_argument("--sun-az", type=float, default=22.0)
a.add_argument("--sun-energy", type=float, default=2.6); a.add_argument("--sun-color", default="1.0,0.93,0.82")
a.add_argument("--sun-match", type=float, default=None, help="put the HDRI's sun this many degrees left of straight ahead")
a.add_argument("--haze", type=float, default=0.0); a.add_argument("--haze-color", default="0.62,0.70,0.80"); a.add_argument("--haze-max", type=float, default=0.7)
a.add_argument("--look", default="AgX - Medium High Contrast")
a.add_argument("--sky-grade", default="", help="cool colour the sky turns to above about 18 deg, e.g. 0.30,0.40,0.80 (a deeper sky at sunset)")
a.add_argument("--sky-warm", default="1.0,0.93,0.86", help="colour of the sky at the horizon when --sky-grade is on")
a.add_argument("--grid", default="", help='framing tests in one session: JSON list of {"name", "hdri_rot", "cam_z", "lens", "shift_y"}')
a.add_argument("--exposures", default="", help="framing tests: save each render at these exposures too, e.g. 0,0.6,1.2")
A = a.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
FPS = A.fps
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
    col = hue.outputs["Color"]
    if A.field == "wide":   # lighter, yellower and darker patches across the meadow (20 m noise on the blade's place)
        oi2 = N.new("ShaderNodeObjectInfo"); ps = N.new("ShaderNodeVectorMath"); ps.operation = "SCALE"; ps.inputs["Scale"].default_value = 0.05
        L.new(oi2.outputs["Location"], ps.inputs[0]); pn = N.new("ShaderNodeTexNoise"); pn.inputs["Detail"].default_value = 1.0
        L.new(ps.outputs[0], pn.inputs["Vector"]); pr = N.new("ShaderNodeValToRGB"); L.new(pn.outputs["Fac"], pr.inputs[0])
        pr.color_ramp.elements[0].position = 0.36; pr.color_ramp.elements[0].color = (0.78, 0.82, 0.74, 1)
        pr.color_ramp.elements[1].position = 0.68; pr.color_ramp.elements[1].color = (1.14, 1.10, 0.88, 1)
        pm = N.new("ShaderNodeVectorMath"); pm.operation = "MULTIPLY"; L.new(col, pm.inputs[0]); L.new(pr.outputs["Color"], pm.inputs[1])
        col = pm.outputs[0]
    pb = N.new("ShaderNodeBsdfPrincipled"); L.new(col, pb.inputs["Base Color"])
    pb.inputs["Roughness"].default_value = 0.55; pb.inputs["Specular IOR Level"].default_value = 0.3
    tr = N.new("ShaderNodeBsdfTranslucent"); L.new(col, tr.inputs["Color"])
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
def hazed(m):
    if A.haze <= 0: return m
    N = m.node_tree.nodes; L = m.node_tree.links; out = N["Material Output"]; src = out.inputs["Surface"].links[0].from_socket
    cd = N.new("ShaderNodeCameraData"); dv = N.new("ShaderNodeMath"); dv.operation = "DIVIDE"; dv.inputs[1].default_value = -A.haze
    L.new(cd.outputs["View Distance"], dv.inputs[0]); ex = N.new("ShaderNodeMath"); ex.operation = "EXPONENT"; L.new(dv.outputs[0], ex.inputs[0])
    k = N.new("ShaderNodeMath"); k.operation = "MULTIPLY_ADD"; k.inputs[1].default_value = -A.haze_max; k.inputs[2].default_value = A.haze_max
    L.new(ex.outputs[0], k.inputs[0])                       # haze_max * (1 - exp(-d / haze))
    em = N.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*[float(v) for v in A.haze_color.split(",")], 1)
    mx = N.new("ShaderNodeMixShader"); L.new(k.outputs[0], mx.inputs[0]); L.new(src, mx.inputs[1]); L.new(em.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"]); return m
M_GRASS = grass_mat(); M_PETAL = flat("petal", "#F7F6EE", 0.45, sss=0.4); M_EYE = flat("eye", "#E8A80F", 0.7)
M_BLUE = flat("blue", "#3E6FE0", 0.45, sss=0.3); M_STEM = flat("stem", "#2F6A1C", 0.6)
for _m in (M_GRASS, M_PETAL, M_EYE, M_BLUE, M_STEM): hazed(_m)

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
soil = hazed(flat("soil", "#25361A", 0.95))
def ground(name, sx, sy, cy, z=0.0):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0)); g = bpy.context.active_object; g.name = name
    g.scale = (sx, sy, 1); g.location = (0, cy, z)
    bpy.ops.object.transform_apply(scale=True)          # keep this on its own line (17.11.: a comment once swallowed it)
    g.data.materials.append(soil); return g
def terrain(name, sx, sy, cy, z, cell):
    """A ground grid that rolls gently: up to about 0.5 m in the middle distance and 5 m on the horizon, nothing near the
    camera, so the near zone (flat) meets it without a step."""
    from mathutils import Vector, noise as mn
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=max(2, int(sx / cell)), y_segments=max(2, int(sy / cell)), size=0.5)
    x0, x1 = min(v.co.x for v in bm.verts), max(v.co.x for v in bm.verts); y0, y1 = min(v.co.y for v in bm.verts), max(v.co.y for v in bm.verts)
    for v in bm.verts:
        x, y = ((v.co.x - x0) / (x1 - x0) - 0.5) * sx, ((v.co.y - y0) / (y1 - y0) - 0.5) * sy + cy; d = y - CAM_Y
        ramp = min(1.0, max(0.0, (d - 12.0) / 58.0)); ramp = ramp * ramp * (3 - 2 * ramp)
        hill = min(1.0, max(0.0, 0.5 + 1.8 * mn.noise(Vector((x / 150.0, y / 150.0, 0.3))))); bump = 0.5 * (1 + mn.noise(Vector((x / 22.0, y / 22.0, 7.1))))
        v.co = Vector((x, y, z + ramp * (5.0 * hill * min(1.0, d / 250.0) + 0.5 * bump)))
    bm.to_mesh(me); bm.free()
    g = bpy.data.objects.new(name, me); sc.collection.objects.link(g); g.data.materials.append(soil); return g
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
    nz = N.new("ShaderNodeTexNoise"); nz.noise_dimensions = "4D"
    if A.loop:   # a circle through (Z, W): the same speed as a straight line in W, and frame 1 + loop equals frame 1
        R = A.wind_speed * A.loop / A.fps / (2 * math.pi)
        ph = N.new("ShaderNodeMath"); ph.operation = "MULTIPLY"; ph.inputs[1].default_value = 2 * math.pi / A.loop; L.new(st.outputs["Frame"], ph.inputs[0])
        co_ = N.new("ShaderNodeMath"); co_.operation = "COSINE"; L.new(ph.outputs[0], co_.inputs[0])
        si_ = N.new("ShaderNodeMath"); si_.operation = "SINE"; L.new(ph.outputs[0], si_.inputs[0])
        cz = N.new("ShaderNodeMath"); cz.operation = "MULTIPLY"; cz.inputs[1].default_value = R; L.new(co_.outputs[0], cz.inputs[0])
        sw = N.new("ShaderNodeMath"); sw.operation = "MULTIPLY"; sw.inputs[1].default_value = R; L.new(si_.outputs[0], sw.inputs[0])
        cxyz = N.new("ShaderNodeCombineXYZ"); L.new(cz.outputs[0], cxyz.inputs["Z"])
        vin = N.new("ShaderNodeVectorMath"); vin.operation = "ADD"; L.new(sc4.outputs[0], vin.inputs[0]); L.new(cxyz.outputs[0], vin.inputs[1])
        L.new(vin.outputs[0], nz.inputs["Vector"]); L.new(sw.outputs[0], nz.inputs["W"])
    else:
        tm = N.new("ShaderNodeMath"); tm.operation = "MULTIPLY"; tm.inputs[1].default_value = A.wind_speed; L.new(st.outputs["Seconds"], tm.inputs[0])
        L.new(sc4.outputs[0], nz.inputs["Vector"]); L.new(tm.outputs[0], nz.inputs["W"])
    cen = N.new("ShaderNodeVectorMath"); cen.operation = "SUBTRACT"; cen.inputs[1].default_value = (0.5, 0.5, 0.5); L.new(nz.outputs["Color"], cen.inputs[0])
    amp = N.new("ShaderNodeVectorMath"); amp.operation = "MULTIPLY"; amp.inputs[1].default_value = (0.14 * wind * A.wind, 0.14 * wind * A.wind, 0.0); L.new(cen.outputs[0], amp.inputs[0])
    add = N.new("ShaderNodeVectorMath"); add.operation = "ADD"; L.new(rr.outputs[0], add.inputs[0]); L.new(amp.outputs[0], add.inputs[1])
    jg = N.new("GeometryNodeJoinGeometry")
    L.new(gi.outputs[0], dp.inputs["Mesh"]); L.new(dp.outputs["Points"], ip.inputs["Points"]); L.new(ci.outputs[0], ip.inputs["Instance"])
    L.new(add.outputs[0], ip.inputs["Rotation"]); L.new(rs.outputs[1], ip.inputs["Scale"]); L.new(ri.outputs[2], ip.inputs["Instance Index"])
    L.new(gi.outputs[0], jg.inputs[0]); L.new(ip.outputs[0], jg.inputs[0]); L.new(jg.outputs[0], go.inputs[0])
    obj.modifiers.new(f"scatter_{coll.name}_{seed}", "NODES").node_group = ng
CAM_Y = -2.0
if A.field == "wide":   # a higher, wider camera sees about 0.75 m to each side per metre of distance
    near = ground("Near", 20, 11, CAM_Y + 0.5 + 5.5)            # 0.5 .. 11.5 m in front, densest
    mid = terrain("Mid", 72, 36, CAM_Y + 11.5 + 18.0, -0.005, 1.5)    # 11.5 .. 47.5 m
    far = terrain("Far", 460, 280, CAM_Y + 47.5 + 140.0, -0.02, 5.0)  # 47.5 .. 327.5 m, rolling towards the horizon
    scatter(near, blade_coll, A.blades, 0.85, 0.45, 1)
    scatter(near, daisy_coll, 5.0, 0.9, 0.3, 2, tilt=0.15); scatter(near, corn_coll, 2.2, 0.9, 0.3, 3, tilt=0.15)
    scatter(mid, blade_coll, A.blades * 0.2, 1.25, 0.45, 4)
    scatter(mid, daisy_coll, 1.6, 1.0, 0.3, 5, tilt=0.15); scatter(mid, corn_coll, 0.7, 1.0, 0.3, 6, tilt=0.15)
    scatter(far, blade_coll, 11.0, 2.8, 0.5, 7, wind=0.4)
    scatter(far, daisy_coll, 0.08, 1.6, 0.3, 8, tilt=0.15)
else:
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
for i, (x, y, sz, kind) in enumerate([] if A.field == "wide" else [(-0.34, 0.55, 2.4, "d"), (-0.52, 0.9, 1.5, "c"), (-0.22, 1.25, 1.8, "d"), (0.36, 0.5, 2.6, "d"),
                                      (0.55, 0.85, 1.6, "c"), (0.28, 1.15, 1.9, "d"), (0.7, 1.4, 2.0, "d"), (-0.68, 1.5, 1.4, "c")]):
    src = (daisy_coll if kind == "d" else corn_coll).objects[i % 3]
    o = bpy.data.objects.new(f"near{i}", src.data); sc.collection.objects.link(o)
    o.location = (x, CAM_Y + y, 0); o.scale = (sz, sz, sz); o.rotation_euler = (random.uniform(-0.2, 0.2), random.uniform(-0.25, 0.25), random.uniform(0, 6.28))

# ── sky: HDRI (Poly Haven, CC0) + sun as back light ─────────────────────
wo = bpy.data.worlds.new("Sky"); sc.world = wo; wo.use_nodes = True; N = wo.node_tree.nodes; Lk = wo.node_tree.links
env = N.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(A.hdri)
tc = N.new("ShaderNodeTexCoord"); mp = N.new("ShaderNodeMapping"); mp.inputs["Rotation"].default_value = (0, 0, math.radians(A.hdri_rot))
Lk.new(tc.outputs["Generated"], mp.inputs["Vector"]); Lk.new(mp.outputs["Vector"], env.inputs["Vector"])
bg = N["Background"]; bg.inputs["Strength"].default_value = A.hdri_strength
if A.sky_grade:   # a deeper, cooler sky higher up, warm at the horizon: it also lights the scene that way
    sxz = N.new("ShaderNodeSeparateXYZ"); Lk.new(tc.outputs["Generated"], sxz.inputs[0])
    mr = N.new("ShaderNodeMapRange"); mr.interpolation_type = "SMOOTHSTEP"; mr.inputs["From Min"].default_value = 0.035; mr.inputs["From Max"].default_value = 0.31
    Lk.new(sxz.outputs["Z"], mr.inputs["Value"]); rp = N.new("ShaderNodeValToRGB"); Lk.new(mr.outputs[0], rp.inputs[0])
    rp.color_ramp.elements[0].color = (*[float(v) for v in A.sky_warm.split(",")], 1); rp.color_ramp.elements[1].color = (*[float(v) for v in A.sky_grade.split(",")], 1)
    mu = N.new("ShaderNodeVectorMath"); mu.operation = "MULTIPLY"; Lk.new(env.outputs["Color"], mu.inputs[0]); Lk.new(rp.outputs["Color"], mu.inputs[1])
    Lk.new(mu.outputs[0], bg.inputs["Color"])
else:
    Lk.new(env.outputs["Color"], bg.inputs["Color"])
sun = bpy.data.lights.new("Sun", "SUN"); sun.energy = A.sun_energy; sun.color = tuple(float(v) for v in A.sun_color.split(",")); sun.angle = math.radians(3)
so = bpy.data.objects.new("Sun", sun); sc.collection.objects.link(so)
so.rotation_euler = (math.radians(-(90 - A.sun_elev)), 0, math.radians(A.sun_az))   # film: light towards the camera, 16 deg down, front left
if A.sun_match is not None:   # find the HDRI's sun (brightest spot), turn the sky so it stands sun_match deg left of ahead
    import numpy as np
    from mathutils import Vector
    img = env.image; w_, h_ = img.size; px = np.empty(w_ * h_ * 4, dtype=np.float32); img.pixels.foreach_get(px)
    lum = px.reshape(h_, w_, 4)[..., :3].sum(-1); y_, x_ = np.unravel_index(int(np.argmax(lum)), lum.shape)
    az = -2 * math.pi * ((x_ + 0.5) / w_ - 0.5); el = math.pi * ((y_ + 0.5) / h_ - 0.5)   # Cycles equirect: u = 0.5 - atan2(y, x) / 2pi
    d_tex = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    want = math.radians(90 + A.sun_match)                     # world azimuth (from +X) of "sun_match deg left of +Y"
    rot = math.atan2(d_tex.y, d_tex.x) - want; mp.inputs["Rotation"].default_value = (0, 0, rot)
    d_world = Vector((math.cos(want) * math.cos(el), math.sin(want) * math.cos(el), math.sin(el)))
    so.rotation_euler = (-d_world).to_track_quat("-Z", "Y").to_euler()
    print(f"SUN_MATCH elevation {math.degrees(el):.1f} deg, sky turned {math.degrees(rot):.1f} deg")

# ── camera: low inside the grass ────────────────────────────────────────
cam = bpy.data.cameras.new("Cam"); cam.lens = A.lens; cam.sensor_width = 36; cam.shift_y = A.shift_y
co = bpy.data.objects.new("Cam", cam); sc.collection.objects.link(co); sc.camera = co
cam.dof.use_dof = True; cam.dof.focus_distance = A.focus; cam.dof.aperture_fstop = A.fstop
def F(t): return 1 + round((t - A.t0) * FPS)
if A.loop:   # a still, level camera (vertical blades stay vertical); --shift-y places the horizon
    co.location = (0, CAM_Y, A.cam_z); co.rotation_euler = (math.radians(90), 0, math.radians(A.yaw))
else:
    co.location = (0, CAM_Y, A.cam_z); co.keyframe_insert("location", frame=1)
    co.location = (0.03, CAM_Y + A.drift, A.cam_z + 0.01); co.keyframe_insert("location", frame=F(A.t0 + 8.0))
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
    if hasattr(cy, "denoising_use_gpu"): cy.denoising_use_gpu = True
except Exception as e: print("GPU setup failed", e)
cy.max_bounces = 6; cy.diffuse_bounces = 2; cy.glossy_bounces = 2; cy.transmission_bounces = 4; cy.transparent_max_bounces = 8
cy.caustics_reflective = False; cy.caustics_refractive = False
sc.render.use_persistent_data = True; sc.render.use_motion_blur = False
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = A.look; sc.view_settings.exposure = A.exposure
sc.render.image_settings.file_format = "JPEG"; sc.render.image_settings.quality = 95
os.makedirs(A.out, exist_ok=True)
if A.grid:   # framing tests: the scene is built once, each test only moves the camera or turns the sky
    import json
    sc.frame_set(A.frame or 1); ex = [float(v) for v in A.exposures.split(",")] if A.exposures else [A.exposure]
    for g in json.loads(A.grid):
        if "hdri_rot" in g: mp.inputs["Rotation"].default_value = (0, 0, math.radians(g["hdri_rot"]))
        if "cam_z" in g: co.location.z = g["cam_z"]
        if "lens" in g: cam.lens = g["lens"]
        if "shift_y" in g: cam.shift_y = g["shift_y"]
        bpy.ops.render.render()
        for e in ex:
            sc.view_settings.exposure = e
            bpy.data.images["Render Result"].save_render(os.path.join(A.out, f"{g['name']}_e{e:+.1f}.jpg"), scene=sc)
        print("GRID_DONE", g["name"], flush=True)
elif A.frame:
    sc.frame_set(A.frame); sc.render.filepath = os.path.join(A.out, f"meadow_{A.frame:04d}.jpg"); bpy.ops.render.render(write_still=True)
else:
    s, e2 = (int(x) for x in A.frames.split("-")); sc.frame_start, sc.frame_end = s, e2
    sc.render.use_overwrite = False; sc.render.use_placeholder = True   # several processes can share one frame range
    sc.render.filepath = os.path.join(A.out, "meadow_####"); bpy.ops.render.render(animation=True)
print("MEADOW_DONE")
