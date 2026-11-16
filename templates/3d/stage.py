"""Crewcut 3D stage for Blender (Cycles): stage, materials, light, text, camera and render settings.

Every look comes from the brand tokens (--brand tokens.json, written from crewcut.brand.Pack.render_tokens()); the
neutral defaults below mirror packs/neutral/brand.json "stage3d". Scenes in this folder import everything from here.

Run a scene:
  blender -b --factory-startup --python templates/3d/<scene>.py -- --data d.json --brand tokens.json \
      --out <dir> --anim --from A --to B [--gpu] [--samples N]
  one still:  ... --out still.png --frame N [--scale 50]
Arguments after "--" belong to the scene; Blender ignores them.
"""

import glob
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
FORMATS = {"landscape": (1920, 1080), "portrait": (1080, 1920)}
NEUTRAL_STAGE = {"background": "#EFEFEC", "material": "matte", "base": "#F7F7F5", "accent": "#E4572E", "font": None,
                 "samples": 128, "light": "soft", "text": None}
NEUTRAL_MOTION = {"entrance_frames": 10, "entrance_from": 0.94, "decor": "none"}


def arg(name, default=None):
    return ARGS[ARGS.index(name) + 1] if name in ARGS and ARGS.index(name) + 1 < len(ARGS) else default


def flag(name):
    return name in ARGS


def _load(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def data(**defaults):
    """Scene data: the scene's defaults, then --data. Cues are merged key by key."""
    given = _load(arg("--data"))
    d = dict(defaults)
    d.update({k: v for k, v in given.items() if k != "cues"})
    d["cues"] = {**(defaults.get("cues") or {}), **(given.get("cues") or {})}
    d.setdefault("format", "landscape")
    if d["format"] not in FORMATS:
        d["format"] = "landscape"
    d["frames"] = int(d.get("frames") or 75)
    d["fps"] = int(d.get("fps") or 25)
    return d


def tokens():
    """Brand tokens with neutral defaults for every stage value (a null in the pack keeps the default)."""
    t = _load(arg("--brand"))
    stage = dict(NEUTRAL_STAGE)
    stage.update({k: v for k, v in (t.get("stage3d") or {}).items() if v is not None})
    motion = dict(NEUTRAL_MOTION)
    motion.update({k: v for k, v in (t.get("motion") or {}).items() if v is not None})
    colors = t.get("colors") or {}
    if not stage.get("text"):
        stage["text"] = colors.get("ink") or "#111111"
    return {"stage3d": stage, "motion": motion, "colors": colors, "fonts": t.get("fonts") or {}}


TOK = tokens()
STAGE = TOK["stage3d"]
MOTION = TOK["motion"]

# ---- maths ------------------------------------------------------------------------------------------------------


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease(x):
    """Fast start, soft end (quartic)."""
    return 1 - (1 - clamp(x)) ** 4


def smooth(x):
    y = clamp(x)
    return y * y * (3 - 2 * y)


def spring(x, over=1.4):
    """0..1 with a small overshoot at the end, like a part that clicks into place."""
    x = clamp(x) - 1
    return 1 + x * x * ((over + 1) * x + over)


def linear(hexc):
    """#RRGGBB to linear RGB for Blender (sRGB transfer removed)."""
    h = str(hexc).lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def shade(hexc, k):
    """A colour k times as bright (k < 1 darker)."""
    h = str(hexc).lstrip("#")
    r, g, b = (min(255, max(0, round(int(h[i:i + 2], 16) * k))) for i in (0, 2, 4))
    return f"#{r:02X}{g:02X}{b:02X}"


# ---- fonts ------------------------------------------------------------------------------------------------------
FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.local/share/fonts"),
             os.path.expanduser("~/.fonts"), "/Library/Fonts", "/System/Library/Fonts"]
WEIGHT_NAMES = {900: ["Black", "Heavy"], 800: ["ExtraBold", "Extra Bold", "Heavy", "Black"], 700: ["Bold"],
                600: ["SemiBold", "Semi Bold", "DemiBold"], 500: ["Medium"], 400: ["Regular", "Book"]}


def find_system_font(family="Inter", weight=800, dirs=None):
    """A font file of this family on the system, closest to the weight. Variable fonts are the second choice."""
    fam = family.replace(" ", "").lower()
    files = []
    for d in dirs or FONT_DIRS:
        for ext in ("ttf", "otf", "TTF", "OTF"):
            files += glob.glob(os.path.join(d, "**", f"*.{ext}"), recursive=True)
    mine = [f for f in files if os.path.basename(f).replace(" ", "").lower().startswith(fam)
            and "italic" not in os.path.basename(f).lower()]
    if not mine:
        return None
    order = []
    for w in sorted(WEIGHT_NAMES, key=lambda w: (abs(w - int(weight)), -w)):
        order += WEIGHT_NAMES[w]
    for name in order:
        key = name.replace(" ", "").lower()
        hits = sorted(f for f in mine if os.path.splitext(os.path.basename(f))[0].replace(" ", "").lower().endswith(key))
        if hits:
            return hits[0]
    var = sorted(f for f in mine if "variable" in f.lower() or "[" in f)
    return var[0] if var else sorted(mine)[0]


def font_file():
    """The 3D text font: the pack's stage3d.font, else the display font file of the pack, else the system font."""
    f = STAGE.get("font")
    if f and os.path.isfile(f):
        return f
    disp = (TOK["fonts"] or {}).get("display") or {}
    for p in disp.get("files") or []:
        if os.path.isfile(p):
            return p
    return find_system_font(disp.get("family") or "Inter", disp.get("weight") or 800)


def load_font():
    """A Blender font, or None for Blender's built-in font."""
    p = font_file()
    if p:
        try:
            return bpy.data.fonts.load(p)
        except Exception as e:
            print("font not loadable, using the built-in font:", p, e)
    else:
        print("no font file found, using Blender's built-in font")
    return None


# ---- scene building ---------------------------------------------------------------------------------------------
def clear():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)


def _nodes(owner):
    try:
        owner.use_nodes = True          # deprecated (always on) in newer Blender versions
    except Exception:
        pass
    return owner.node_tree


def _principled(m):
    nt = _nodes(m)
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            return n
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    out = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None) or nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(b.outputs[0], out.inputs[0])
    return b


def _set(node, name, value):
    if name in node.inputs:
        node.inputs[name].default_value = value


def material(name, hexc, rough=0.6, sss=0.0, coat=0.0, glow=0.0):
    m = bpy.data.materials.new(name)
    b = _principled(m)
    _set(b, "Base Color", (*linear(hexc), 1))
    _set(b, "Roughness", rough)
    if sss:
        _set(b, "Subsurface Weight", sss)
        _set(b, "Subsurface Radius", (0.03, 0.03, 0.03))
    if coat:
        _set(b, "Coat Weight", coat)
    if glow:                    # a little self light keeps the accent its own colour in shadow
        _set(b, "Emission Color", (*linear(hexc), 1))
        _set(b, "Emission Strength", glow)
    return m


PRESETS = {  # base roughness, base subsurface, accent roughness, accent coat
    "matte": (0.62, 0.06, 0.48, 0.0),
    "clay": (0.72, 0.14, 0.55, 0.0),
    "gloss": (0.28, 0.0, 0.22, 0.5),
}
_P = PRESETS.get(str(STAGE.get("material")), PRESETS["matte"])
BASE = material("base", STAGE["base"], _P[0], sss=_P[1])
BASE_DEEP = material("base_deep", shade(STAGE["base"], 0.9), _P[0] + 0.05, sss=_P[1] * 0.6)
ACCENT = material("accent", STAGE["accent"], _P[2], coat=_P[3], glow=0.3)
ACCENT_GLOSS = material("accent_gloss", STAGE["accent"], max(0.18, _P[2] - 0.2), coat=max(0.4, _P[3]), glow=0.3)


def box(size, loc, m, bevel=0.002, seg=2, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.scale = size
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        bv = o.modifiers.new("bevel", "BEVEL")
        bv.width = bevel
        bv.segments = seg
        bpy.ops.object.shade_smooth()
    o.data.materials.append(m)
    if parent:
        o.parent = parent
    return o


def cylinder(r, h, loc, m, rot=(0, 0, 0), verts=64, parent=None, bevel=0.001):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=h, vertices=verts, location=loc, rotation=rot)
    o = bpy.context.object
    if bevel:
        bv = o.modifiers.new("bevel", "BEVEL")
        bv.width = bevel
        bv.segments = 2
        bv.limit_method = "ANGLE"
    bpy.ops.object.shade_smooth()
    o.data.materials.append(m)
    if parent:
        o.parent = parent
    return o


def sphere(r, loc, m, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=loc, segments=96, ring_count=48)
    o = bpy.context.object
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth()
    if parent:
        o.parent = parent
    return o


def empty(loc=(0, 0, 0), parent=None):
    bpy.ops.object.empty_add(location=loc)
    e = bpy.context.object
    if parent:
        e.parent = parent
    return e


def sheet(bx=0.3, by=0.4, th=0.016):
    """A document: a slab with an accent heading bar and five line bars. No text. Lies flat, centred at the origin."""
    e = empty()
    box((bx, by, th), (0, 0, 0), BASE, bevel=min(0.004, th * 0.25), seg=3, parent=e)
    box((bx * 0.44, by * 0.06, 0.004), (-bx * 0.2, by * 0.35, th / 2 + 0.001), ACCENT, bevel=0.0015, parent=e)
    for k in range(5):
        w = bx * (0.5 if k % 3 == 2 else 0.76)
        box((w, by * 0.03, 0.003), (-bx * 0.38 + w / 2, by * (0.2 - k * 0.105), th / 2 + 0.0005), BASE_DEEP, bevel=0.001,
            parent=e)
    return e


def stage(sc):
    """A cove: floor from y -8 to 4, a curve of radius 1.6 up into a wall to z 8. World light from the background colour."""
    me = bpy.data.meshes.new("stage")
    bm = bmesh.new()
    n, R = 28, 1.6
    prof = [(-8.0, 0.0), (4.0, 0.0)]
    prof += [(4 + R * math.sin(i / n * math.pi / 2), R - R * math.cos(i / n * math.pi / 2)) for i in range(1, n + 1)]
    prof += [(4 + R, 8.0)]
    rows = [[bm.verts.new((x, y, z)) for x in (-10, 10)] for y, z in prof]
    for a, b in zip(rows, rows[1:], strict=False):
        bm.faces.new((a[0], a[1], b[1], b[0]))
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new("stage", me)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(material("stage", STAGE["background"], 0.55))
    w = bpy.data.worlds.new("world")
    sc.world = w
    nt = _nodes(w)
    bg = next((n for n in nt.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        bg = nt.nodes.new("ShaderNodeBackground")
        out = next((n for n in nt.nodes if n.type == "OUTPUT_WORLD"), None) or nt.nodes.new("ShaderNodeOutputWorld")
        nt.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs[0].default_value = (*linear(STAGE["background"]), 1)
    bg.inputs[1].default_value = 0.35
    return o


def light(kind, loc, target, energy, **kw):
    bpy.ops.object.light_add(type=kind, location=loc)
    lo = bpy.context.object
    lo.data.energy = energy
    for k, v in kw.items():
        setattr(lo.data, k, v)
    lo.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return lo


LIGHTS = {  # key (location, energy, size), fill (location, energy, size) or None, wall energy
    "soft": (((2.2, -1.4, 3.0), 70, 2.2), ((-2.6, -2.8, 1.6), 16, 3.5), 280),
    "hard": (((2.0, -0.8, 2.6), 90, 0.5), None, 200),
}


def lights(target=(0, 0, 0.2), preset=None):
    """Key light from the right and above (shadows fall to the front left), optional fill, a light on the wall."""
    key, fill, wall = LIGHTS.get(preset or str(STAGE.get("light")), LIGHTS["soft"])
    light("AREA", key[0], target, key[1], size=key[2])
    if fill:
        light("AREA", fill[0], target, fill[1], size=fill[2])
    light("AREA", (0, 1.2, 6.8), (0, 5.4, 2.0), wall, size=6.0)


def camera(sc, loc, target, lens=80, fstop=3.2, portrait=False, focus=None):
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    sc.camera = cam
    cam.data.sensor_fit = "VERTICAL"
    cam.data.lens = lens
    loc, target = Vector(loc), Vector(target)
    cam.location = loc
    cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = fstop
    cam.data.dof.focus_distance = focus or (target - loc).length
    sc.render.resolution_x, sc.render.resolution_y = FORMATS["portrait" if portrait else "landscape"]
    bpy.context.view_layer.update()
    return cam


def screen_point(cam, u, v, d, sc=None):
    """The point in space at screen position u, v (-1..1, centre 0) at distance d in front of the camera."""
    sc = sc or bpy.context.scene
    hh = cam.data.sensor_height / 2 / cam.data.lens
    hw = hh * sc.render.resolution_x / sc.render.resolution_y
    return cam.matrix_world @ Vector((u * hw * d, v * hh * d, -d))


def screen_width(cam, d, sc=None):
    sc = sc or bpy.context.scene
    return 2 * d * cam.data.sensor_height / 2 / cam.data.lens * sc.render.resolution_x / sc.render.resolution_y


def text_material(hexc=None):
    """Emitting text with a fade (node 'Mix', input 0: 0 hidden, 1 shown)."""
    m = bpy.data.materials.new("text")
    nt = _nodes(m)
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    mx.name = "Mix"
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    e.inputs[0].default_value = (*linear(hexc or STAGE["text"]), 1)
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(e.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs[0])
    mx.inputs[0].default_value = 1.0
    return m


def text(cam, body, u, v, d, width, font, max_height=None, color=None):
    """Flat, sharp text facing the camera. width = share of the frame width; max_height = share of the frame height
    (short words would be huge otherwise). Casts no shadow."""
    c = bpy.data.curves.new("text", "FONT")
    c.body = str(body)
    if font is not None:
        c.font = font
    c.align_x = "CENTER"
    c.align_y = "CENTER"
    o = bpy.data.objects.new("text", c)
    bpy.context.collection.objects.link(o)
    o.data.materials.append(text_material(color))
    bpy.context.view_layer.update()
    c.size = width * screen_width(cam, d) / max(1e-6, o.dimensions.x)
    if max_height:
        bpy.context.view_layer.update()
        sc = bpy.context.scene
        fh = screen_width(cam, d) * sc.render.resolution_y / sc.render.resolution_x
        if o.dimensions.y > max_height * fh:
            c.size *= max_height * fh / o.dimensions.y
    o.location = screen_point(cam, u, v, d)
    o.rotation_euler = cam.rotation_euler
    o.visible_shadow = False
    o.visible_diffuse = False
    o.visible_glossy = False
    return o


def show_text(o, x):
    """Entrance of text: x 0..1 over the entrance frames, from the pack's entrance scale and no opacity."""
    a = ease(x)
    o.data.materials[0].node_tree.nodes["Mix"].inputs[0].default_value = a
    s = float(MOTION.get("entrance_from", 0.94))
    o.scale = (s + (1 - s) * a,) * 3


ENTER = int(MOTION.get("entrance_frames", 10))


# ---- decor (only when the pack asks for it) ---------------------------------------------------------------------
def _no_shadow(o):
    o.visible_shadow = False
    return o


def decor(cam):
    """Floating accent shapes at the frame edges when brand motion.decor is not "none". Returns drift(t)."""
    if str(MOTION.get("decor", "none")) == "none":
        return lambda t: None
    parts = []
    bpy.ops.mesh.primitive_torus_add(major_radius=0.08, minor_radius=0.018, major_segments=96, minor_segments=24,
                                     rotation=(math.radians(70), 0.3, 0.2))
    t1 = _no_shadow(bpy.context.object)
    t1.data.materials.append(ACCENT)
    bpy.ops.object.shade_smooth()
    parts.append((t1, -0.95, 0.8, 1.6, 0.007, -0.005))
    p = empty()
    p.rotation_euler = (0.3, math.radians(18), 0.4)
    for size in ((0.12, 0.035, 0.035), (0.035, 0.035, 0.12)):
        _no_shadow(box(size, (0, 0, 0), ACCENT, bevel=0.004, seg=3, parent=p))
    parts.append((p, 0.9, 0.62, 2.8, -0.006, 0.006))
    s = _no_shadow(sphere(0.035, (0, 0, 0), ACCENT))
    parts.append((s, 0.7, -0.75, 2.2, 0.008, 0.004))

    def drift(t):
        for o, u, v, d, du, dv in parts:
            o.location = screen_point(cam, u + du * t, v + dv * t, d)
    return drift


# ---- render -----------------------------------------------------------------------------------------------------
def _gpu(cy):
    """Use the first GPU type Cycles finds (OptiX, CUDA, HIP, Metal, oneAPI). False: no GPU, CPU renders."""
    try:
        pr = bpy.context.preferences.addons["cycles"].preferences
    except Exception:
        return False
    for dt in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            pr.compute_device_type = dt
            (getattr(pr, "refresh_devices", None) or pr.get_devices)()
        except Exception:
            continue
        devs = [d for d in pr.devices if d.type == dt]
        if devs:
            for d in pr.devices:
                d.use = d.type != "CPU"
            cy.device = "GPU"
            print("GPU:", dt, ", ".join(d.name for d in devs))
            return True
    print("no GPU found for Cycles; rendering on the CPU")
    return False


def setup_render(sc, samples=128, gpu=False, scale=100, fps=25):
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = int(samples)
    cy.use_denoising = True
    try:
        cy.denoiser = "OPENIMAGEDENOISE"
    except Exception as e:
        print("denoiser not available:", e)
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.01
    cy.max_bounces = 8
    if gpu:
        _gpu(cy)
    sc.view_settings.view_transform = "Standard"    # brand colours stay the colours the pack names
    try:
        sc.view_settings.look = "None"
    except Exception:
        pass
    sc.render.use_persistent_data = True
    sc.render.resolution_percentage = int(scale)
    sc.render.fps = int(fps)
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.film_transparent = False


def run(sc, pose, d, still=None):
    """Render --anim (frames --from to --to into the folder --out) or one still (--frame N into the file --out)."""
    setup_render(sc, samples=arg("--samples", STAGE.get("samples") or 128), gpu=flag("--gpu"),
                 scale=arg("--scale", 100), fps=d["fps"])
    frames = d["frames"]
    if flag("--anim"):
        out = arg("--out", "out")
        os.makedirs(out, exist_ok=True)
        for fr in range(int(arg("--from", 0)), int(arg("--to", frames - 1)) + 1):
            pose(fr)
            sc.render.filepath = os.path.join(out, f"{fr:04d}.png")
            bpy.ops.render.render(write_still=True)
    else:
        fr = int(arg("--frame", still if still is not None else frames // 2))
        pose(fr)
        out = arg("--out", "still.png")
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        sc.render.filepath = out
        bpy.ops.render.render(write_still=True)
    print("DONE")
