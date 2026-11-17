"""3D Slate for beat 2: extruded, bevelled Slate from the brand SVG, glossy white + mint, studio light with a
moving highlight strip, pop + slow turn, then bristles grow out of it and it disintegrates into thousands of white/mint
flakes that spiral towards the camera (authored paths in Geometry Nodes, no physics), Cycles with depth of field,
motion blur, RGBA. Rendered backwards with the green logo, the same flakes converge into it (beat 7).

blender -b --factory-startup --python slate3d.py -- --svg slate-white.svg --out DIR [--frames 1-150 | --frame N]
   [--samples 64] [--half] [--t0 1.15] [--tin 1.20] [--tshatter 2.20] [--width 330] [--count 1400]
   [--flakes "#FFFFFF,#7FE0C6"] [--seed 3]
(or `bash bl.sh slate3d.py ...`, see plates.sh). Times are global comp seconds: --tin the pop, --tshatter the start
of the bristles. Frame f (1-based) shows comp time t0 + (f-1)/60. Output: DIR/slate_####.png (RGBA)."""
import bpy, sys, math, random, os, argparse
from mathutils import Vector

a = argparse.ArgumentParser()
a.add_argument("--svg", required=True); a.add_argument("--out", required=True)
a.add_argument("--frames", default="1-150"); a.add_argument("--frame", type=int)
a.add_argument("--samples", type=int, default=128); a.add_argument("--half", action="store_true")
a.add_argument("--t0", type=float, default=1.15); a.add_argument("--tin", type=float, default=1.20)
a.add_argument("--tshatter", type=float, default=2.20); a.add_argument("--width", type=float, default=330)
a.add_argument("--count", type=int, default=1400)
a.add_argument("--flakes", default="#FFFFFF,#7FE0C6", help="main,accent flake colours"); a.add_argument("--seed", type=int, default=3)
A = a.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
FPS = 60
def F(t): return 1 + round((t - A.t0) * FPS)          # comp time -> Blender frame

bpy.context.preferences.edit.keyframe_new_interpolation_type = "BEZIER"
sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
sc.render.fps = FPS; sc.frame_start = 1; sc.frame_end = 200
random.seed(A.seed)

# ── import the SVG and sort the curves by role ──────────────────────────
import addon_utils; addon_utils.enable("io_curve_svg", default_set=True)
bpy.ops.import_curve.svg(filepath=A.svg)
curves = [o for o in bpy.data.objects if o.type == "CURVE"]
def col(o):
    m = o.data.materials[0] if o.data.materials else None
    return tuple(m.diffuse_color[:3]) if m else (1, 1, 1)
# normalise: centre and scale to width 2.0
mn = Vector((1e9, 1e9, 0)); mx = Vector((-1e9, -1e9, 0))
for o in curves:
    for v in o.bound_box:
        w = o.matrix_world @ Vector(v); mn.x = min(mn.x, w.x); mn.y = min(mn.y, w.y); mx.x = max(mx.x, w.x); mx.y = max(mx.y, w.y)
size = mx.x - mn.x; cen = (mn + mx) / 2; k = 2.0 / size
root = bpy.data.objects.new("Slate", None); sc.collection.objects.link(root)

def mat(name, rgb, rough, coat=0.0, emit=0.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1); b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat; b.inputs["Coat Roughness"].default_value = 0.08
    return m
def srgb(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)
M_WHITE = mat("white", srgb("#F7FAF9"), 0.16, coat=0.9)
M_MINT = mat("mint", srgb("#34C3A4"), 0.28, coat=0.4)
M_GREEN = mat("green", srgb("#0F6E5C"), 0.7, coat=0.0)

DEPTH = 0.2; BEV = 0.05
front = DEPTH + BEV                                    # the base's front face (extrude + bevel)
layer_z = {"base": 0.0, "stripe": front + 0.004, "face": front + 0.004, "pupil": front + 0.016}
rank = 0
for i, o in enumerate(sorted(curves, key=lambda o: o.name)):
    r, g, b = col(o)
    o.data.dimensions = "2D"
    area = (o.dimensions.x * o.dimensions.y) * k * k
    # importer colours are linear: mint ~ (0.03, 0.55, 0.37), deep green ~ (0.005, 0.16, 0.11), white (1, 1, 1)
    m = M_MINT if (r < 0.2 and g > 0.35) else M_GREEN if r < 0.2 else M_WHITE
    if area > 0.5: role = "base"                          # body and bar, whatever their colour (white or green Slate)
    elif m is M_MINT: role = "stripe"
    else: role = "face"; rank += 1                        # eyes, pupils, smile: later SVG elements sit higher
    o.data.materials.clear(); o.data.materials.append(m)
    o.location = (o.location - cen) * k; o.scale = o.scale * k
    o.data.extrude = (DEPTH if role == "base" else 0.012) / k
    o.data.bevel_depth = (BEV if role == "base" else 0.006) / k
    o.data.bevel_resolution = 6
    o.location.z = layer_z[role] + (0.006 * rank if role == "face" else 0.0)
    o.parent = root
bpy.context.view_layer.update()
# one mesh (particle emitter and dissolve shader need a mesh)
for o in curves: o.select_set(True)
bpy.context.view_layer.objects.active = curves[0]
bpy.ops.object.convert(target="MESH")
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in meshes: o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
bpy.ops.object.join()
logo = bpy.context.view_layer.objects.active; logo.name = "SlateMesh"
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
logo.location = (0, 0, 0)
bpy.ops.object.shade_auto_smooth(angle=math.radians(35))

# dissolve: every material fades out where a noisy radial front has passed (edges first, centre last)
def add_dissolve(m):
    nt = m.node_tree; N = nt.nodes; L = nt.links
    out = N["Material Output"]; bsdf = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord"); sep = N.new("ShaderNodeSeparateXYZ"); L.new(tc.outputs["Object"], sep.inputs[0])
    vl = N.new("ShaderNodeVectorMath"); vl.operation = "LENGTH"; L.new(tc.outputs["Object"], vl.inputs[0])
    nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 9; L.new(tc.outputs["Object"], nz.inputs["Vector"])
    mix = N.new("ShaderNodeMath"); mix.operation = "MULTIPLY_ADD"; mix.inputs[1].default_value = 0.35
    L.new(nz.outputs["Fac"], mix.inputs[0]); L.new(vl.outputs["Value"], mix.inputs[2])
    thr = N.new("ShaderNodeValue"); thr.name = "front"; thr.outputs[0].default_value = 9.0
    cmp = N.new("ShaderNodeMath"); cmp.operation = "LESS_THAN"; L.new(mix.outputs[0], cmp.inputs[0]); L.new(thr.outputs[0], cmp.inputs[1])
    L.new(cmp.outputs[0], bsdf.inputs["Alpha"])
    return thr
fronts = [add_dissolve(m) for m in (M_WHITE, M_MINT, M_GREEN)]
for t, v in ((A.tshatter + 0.34, 2.2), (A.tshatter + 0.42, 0.0)):
    for fr in fronts:
        fr.outputs[0].default_value = v; fr.outputs[0].keyframe_insert("default_value", frame=F(t))

# ── animation: pop with overshoot, slow turn, tilt ──────────────────────
pivot = bpy.data.objects.new("Pivot", None); sc.collection.objects.link(pivot); logo.parent = pivot
def key(o, path, f, v):
    setattr(o, path, v); o.keyframe_insert(path, frame=f)
key(pivot, "scale", F(A.tin), (0.17, 0.17, 0.17))
key(pivot, "scale", F(A.tin + 0.25), (1, 1, 1))
key(pivot, "rotation_euler", F(A.tin), (math.radians(10), math.radians(540), 0))
key(pivot, "rotation_euler", F(A.tin + 0.25), (math.radians(9), math.radians(-18), 0))
key(pivot, "rotation_euler", F(A.tshatter), (math.radians(-5), math.radians(17), 0))   # visible turn during the hold
pivot.scale = (0.001, 0.001, 0.001); pivot.keyframe_insert("scale", frame=F(A.tin) - 1)
# strong ease-out on the entrance keys (fast start, long settle): bezier handles via the layered action
def ease_out_entrance(ob):
    act = ob.animation_data.action
    curves = []
    try:
        for lay in act.layers:
            for st in lay.strips:
                cb = st.channelbag(ob.animation_data.action_slot); curves += list(cb.fcurves)
    except Exception:
        curves = list(getattr(act, "fcurves", []))
    for fc in curves:
        kps = fc.keyframe_points
        for i, kp in enumerate(kps):
            kp.interpolation = "BEZIER"
            if i + 1 < len(kps):
                nx = kps[i + 1]; dt = nx.co.x - kp.co.x
                kp.handle_right_type = "FREE"; nx.handle_left_type = "FREE"
                kp.handle_right = (kp.co.x + dt * 0.05, kp.co.y + (nx.co.y - kp.co.y) * 0.35)   # leaves fast
                nx.handle_left = (nx.co.x - dt * 0.75, nx.co.y)                               # long settle
ease_out_entrance(pivot)

# ── flakes: authored paths in Geometry Nodes (no physics): bristles 20 frames, release 5, swirl ─────────
flakes = bpy.data.collections.new("Flakes"); sc.collection.children.link(flakes)
_fc = A.flakes.split(","); M_FW = mat("flakeMain", srgb(_fc[0]), 0.4); M_FM = mat("flakeAccent", srgb(_fc[1]), 0.4)
for j in range(5):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    p = bpy.context.active_object; p.name = f"flake{j}"; p.scale = (0.35, 0.12, 1.0); bpy.ops.object.transform_apply(scale=True)
    for v in p.data.vertices: v.co *= 1 + random.uniform(-0.15, 0.15)
    p.data.materials.append(M_FM if j == 4 else M_FW)
    for uc in list(p.users_collection): uc.objects.unlink(p)
    flakes.objects.link(p)
bpy.context.view_layer.layer_collection.children["Flakes"].exclude = True
bpy.ops.object.select_all(action="DESELECT"); logo.select_set(True); bpy.context.view_layer.objects.active = logo
bpy.ops.object.transform_apply(scale=True)

def build_flakes(sc, logo, coll, f_s, count, cam_d, fps=60.0):
    """Flakes as a function of time. tau = seconds since tS. World: logo in the XY plane, camera on +Z."""
    ng = bpy.data.node_groups.new("FlakeSwirl", "GeometryNodeTree"); ng.is_modifier = True
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    N, L = ng.nodes, ng.links
    def node(t, **kw):
        n = N.new(t)
        for k, v in kw.items(): setattr(n, k, v)
        return n
    def sock(n, name): return [s for s in n.inputs if s.enabled and s.name == name][0]
    def put(x, s):
        if hasattr(x, "is_linked"): L.new(x, s)
        else: s.default_value = x
    def M(op, a, b=None, c=None, clamp=False):
        n = node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, x in enumerate((a, b, c)):
            if x is not None: put(x, n.inputs[i])
        return n.outputs[0]
    def V(op, a, b=None, scale=None):
        n = node("ShaderNodeVectorMath", operation=op); put(a, n.inputs[0])
        if b is not None: put(b, n.inputs[1])
        if scale is not None: put(scale, n.inputs["Scale"])
        return n.outputs[0]
    def R(seed):
        n = node("FunctionNodeRandomValue", data_type="FLOAT"); n.inputs["Seed"].default_value = seed
        return [o for o in n.outputs if o.enabled][0]
    oi = node("GeometryNodeObjectInfo", transform_space="ORIGINAL"); oi.inputs["Object"].default_value = logo
    dp = node("GeometryNodeDistributePointsOnFaces", distribute_method="RANDOM")
    dp.inputs["Density"].default_value = count / sum(p.area for p in logo.data.polygons); dp.inputs["Seed"].default_value = 3
    L.new(oi.outputs["Geometry"], dp.inputs["Mesh"])
    tau = M("DIVIDE", M("SUBTRACT", node("GeometryNodeInputSceneTime").outputs["Frame"], f_s), fps)
    r1, r2, r3, r4 = R(11), R(12), R(13), R(14)
    g = M("DIVIDE", M("SUBTRACT", tau, M("MULTIPLY", r1, 0.10)), 0.30, clamp=True)
    length = M("MULTIPLY", M("MULTIPLY_ADD", M("POWER", r2, 3.0), 0.60, 0.05), M("POWER", g, 1.5))
    p_loc = V("ADD", node("GeometryNodeInputPosition").outputs[0], V("SCALE", dp.outputs["Normal"], scale=length))
    tp = node("FunctionNodeTransformPoint"); L.new(p_loc, tp.inputs["Vector"]); L.new(oi.outputs["Transform"], tp.inputs["Transform"])
    u = M("DIVIDE", M("MAXIMUM", M("SUBTRACT", tau, M("MULTIPLY_ADD", r3, 0.05, 0.34)), 0.0), 0.12)
    w = M("ADD", M("POWER", M("MINIMUM", u, 1.0), 2.0), M("MULTIPLY", M("MAXIMUM", M("SUBTRACT", u, 1.0), 0.0), 2.0))
    vr = node("ShaderNodeVectorRotate", rotation_type="Z_AXIS"); L.new(tp.outputs[0], vr.inputs["Vector"])
    L.new(M("MULTIPLY", M("MULTIPLY_ADD", r4, 0.9, 1.1), w), vr.inputs["Angle"])
    cz = node("ShaderNodeCombineXYZ")
    L.new(M("MULTIPLY", M("MULTIPLY_ADD", r1, 0.20, 0.05), M("MULTIPLY", w, cam_d)), cz.inputs["Z"])
    p_fin = V("ADD", V("SCALE", vr.outputs[0], scale=M("MULTIPLY_ADD", w, 2.4, 1.0)), cz.outputs[0])   # cloud leaves the disc (~2.5x logo)
    sp = node("GeometryNodeSetPosition"); L.new(dp.outputs["Points"], sp.inputs["Geometry"]); L.new(p_fin, sp.inputs["Position"])
    ci = node("GeometryNodeCollectionInfo"); ci.inputs["Collection"].default_value = coll
    ci.inputs["Separate Children"].default_value = True; ci.inputs["Reset Children"].default_value = True
    ip = node("GeometryNodeInstanceOnPoints"); ip.inputs["Pick Instance"].default_value = True
    L.new(sp.outputs["Geometry"], ip.inputs["Points"]); L.new(ci.outputs[0], ip.inputs["Instance"])
    ax = node("FunctionNodeRandomValue", data_type="FLOAT_VECTOR"); sock(ax, "Min").default_value = (-1, -1, -1); ax.inputs["Seed"].default_value = 15
    aa = node("FunctionNodeAxisAngleToRotation"); L.new([o for o in ax.outputs if o.enabled][0], aa.inputs["Axis"])
    L.new(M("MULTIPLY", w, M("MULTIPLY_ADD", r2, 4.0, 1.5)), aa.inputs["Angle"])
    rl = node("FunctionNodeRotateRotation", rotation_space="LOCAL"); L.new(dp.outputs["Rotation"], rl.inputs["Rotation"]); L.new(aa.outputs[0], rl.inputs["Rotate By"])
    rg = node("FunctionNodeRotateRotation", rotation_space="GLOBAL"); L.new(rl.outputs[0], rg.inputs["Rotation"]); L.new(oi.outputs["Rotation"], rg.inputs["Rotate By"])
    L.new(rg.outputs[0], ip.inputs["Rotation"])
    L.new(M("MULTIPLY", M("MULTIPLY_ADD", M("POWER", r3, 2.0), 0.12, 0.06), M("MULTIPLY", g, 5.0, clamp=True)), ip.inputs["Scale"])   # chunky chips
    out = node("NodeGroupOutput"); L.new(ip.outputs[0], out.inputs[0])
    ob = bpy.data.objects.new("FlakeCloud", bpy.data.meshes.new("FlakeCloud")); sc.collection.objects.link(ob)
    ob.modifiers.new("swirl", "NODES").node_group = ng
    return ob

# ── camera, light, world ────────────────────────────────────────────────
W, H = (1920, 1080)
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.resolution_percentage = 50 if A.half else 100
cam_d = 16.0; lens = 50.0
cam = bpy.data.cameras.new("Cam"); cam.lens = lens; cam.sensor_width = 36
# logo width 2.0 BU should be A.width px of 1920
cam_d = 2.0 * W / A.width * lens / 36.0
co = bpy.data.objects.new("Cam", cam); sc.collection.objects.link(co); co.location = (0, 0, cam_d); sc.camera = co
cam.dof.use_dof = True; cam.dof.focus_distance = cam_d; cam.dof.aperture_fstop = 2.8
cam.clip_start = 0.05; cam.clip_end = 400
build_flakes(sc, logo, flakes, F(A.tshatter), A.count, cam_d)     # camera stays fixed: the comp does the push

def area(name, loc, rot, size, energy, color=(1, 1, 1)):
    l = bpy.data.lights.new(name, "AREA"); l.size = size; l.energy = energy; l.color = color
    o = bpy.data.objects.new(name, l); sc.collection.objects.link(o); o.location = loc; o.rotation_euler = rot; return o
area("key", (-6, 7, 12), (math.radians(-30), math.radians(-25), 0), 9, 1100, (1.0, 0.97, 0.93))
area("rim", (8, -2, -3), (math.radians(0), math.radians(110), 0), 5, 1500, (0.85, 0.95, 1.0))
area("fill", (5, -6, 10), (math.radians(30), math.radians(20), 0), 10, 470, (1.0, 0.92, 0.95))
sweep = area("sweep", (-9, 0, 6), (0, math.radians(-30), 0), 1, 2600)
sweep.data.shape = "RECTANGLE"; sweep.data.size = 0.35; sweep.data.size_y = 14
sweep.location.x = -9; sweep.keyframe_insert("location", frame=F(A.tin + 0.3))
sweep.location.x = 9; sweep.keyframe_insert("location", frame=F(A.tshatter - 0.05))
wo = bpy.data.worlds.new("W"); sc.world = wo; wo.use_nodes = True
bg = wo.node_tree.nodes["Background"]; bg.inputs[0].default_value = (0.95, 0.9, 0.92, 1); bg.inputs[1].default_value = 0.35

# ── render ──────────────────────────────────────────────────────────────
sc.render.engine = "CYCLES"; cy = sc.cycles
cy.samples = A.samples; cy.use_denoising = True
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences; prefs.compute_device_type = "OPTIX"; prefs.get_devices()
    for d in prefs.devices: d.use = d.type in ("OPTIX", "CUDA")
    cy.device = "GPU"; cy.denoiser = "OPTIX"
except Exception as e:
    print("GPU setup failed", e)
sc.render.film_transparent = True; sc.render.use_motion_blur = True; sc.render.motion_blur_shutter = 0.25; sc.render.motion_blur_position = "CENTER"
sc.render.image_settings.file_format = "PNG"; sc.render.image_settings.color_mode = "RGBA"; sc.render.image_settings.color_depth = "8"
sc.view_settings.view_transform = "Standard"; sc.view_settings.look = "Medium High Contrast"; sc.view_settings.exposure = 0.0
os.makedirs(A.out, exist_ok=True)
# no simulation to bake: every frame is a function of time, so any frame can be rendered on its own
sc.render.filepath = os.path.join(A.out, "slate_####")
if A.frame:
    sc.frame_set(A.frame); sc.render.filepath = os.path.join(A.out, f"slate_{A.frame:04d}.png"); bpy.ops.render.render(write_still=True)
else:
    s, e = (int(x) for x in A.frames.split("-")); sc.frame_start, sc.frame_end = s, e
    bpy.ops.render.render(animation=True)
print("SLATE3D_DONE")
