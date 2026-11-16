"""A stand-in for Blender's bpy, bmesh and mathutils: just enough to run the 3D scene scripts frame by frame without
Blender. It catches errors in the scene logic (names, maths, data keys). It says nothing about the real Blender API
or the picture. Usage: python fake_bpy.py <scene.py> -- [scene args]; prints the number of rendered frames."""

import math
import runpy
import sys
import types


def _v(o):
    return o.v if isinstance(o, Vector) else list(o)


class Vector:
    def __init__(self, v=(0, 0, 0)):
        self.v = [float(x) for x in v]

    x = property(lambda s: s.v[0])
    y = property(lambda s: s.v[1])
    z = property(lambda s: s.v[2])

    def __add__(self, o):
        return Vector([a + b for a, b in zip(self.v, _v(o), strict=True)])

    def __sub__(self, o):
        return Vector([a - b for a, b in zip(self.v, _v(o), strict=True)])

    def __mul__(self, k):
        return Vector([a * k for a in self.v])

    def __getitem__(self, i):
        return self.v[i]

    def __setitem__(self, i, val):
        self.v[i] = float(val)

    def __iter__(self):
        return iter(self.v)

    def __len__(self):
        return 3

    @property
    def length(self):
        return math.sqrt(sum(a * a for a in self.v))

    def lerp(self, o, t):
        return Vector([a + (b - a) * t for a, b in zip(self.v, _v(o), strict=True)])

    def to_track_quat(self, *a):
        return types.SimpleNamespace(to_euler=lambda: Euler((0.1, 0.2, 0.3)))


class Euler(Vector):
    pass


class Matrix:
    def __matmul__(self, o):
        return Vector(o)


class Bag:
    """An object that grows any attribute it is asked for."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        b = Bag()
        setattr(self, k, b)
        return b


class Inputs(dict):
    def __getitem__(self, k):
        if not dict.__contains__(self, k):
            dict.__setitem__(self, k, Bag(default_value=0))
        return dict.__getitem__(self, k)

    def __contains__(self, k):
        return True


class Node(Bag):
    def __init__(self, type_):
        super().__init__(type=type_, name=type_)
        self.inputs = Inputs()
        self.outputs = [Bag(), Bag()]


TYPES = {"ShaderNodeBsdfPrincipled": "BSDF_PRINCIPLED", "ShaderNodeOutputMaterial": "OUTPUT_MATERIAL",
         "ShaderNodeEmission": "EMISSION", "ShaderNodeBsdfTransparent": "BSDF_TRANSPARENT",
         "ShaderNodeMixShader": "MIX_SHADER", "ShaderNodeBackground": "BACKGROUND", "ShaderNodeOutputWorld": "OUTPUT_WORLD"}


class Nodes(list):
    def new(self, t):
        n = Node(TYPES[t])
        self.append(n)
        return n

    def __getitem__(self, k):
        if isinstance(k, str):
            for n in self:
                if n.name == k:
                    return n
            raise KeyError(k)
        return list.__getitem__(self, k)


class Tree(Bag):
    def __init__(self, kinds):
        super().__init__()
        self.nodes = Nodes()
        self.links = Bag(new=lambda a, b: None)
        for k in kinds:
            self.nodes.new(k)


class Obj(Bag):
    def __init__(self, data=None):
        super().__init__()
        self.location = Vector()
        self.rotation_euler = Euler()
        self.scale = Vector((1, 1, 1))
        self.dimensions = Vector((1.0, 0.3, 0.1))
        self.data = data if data is not None else Bag(materials=[], polygons=[])
        self.parent = None
        self.matrix_world = Matrix()
        self.modifiers = Bag(new=lambda n, t: Bag())

    def __setattr__(self, k, val):
        if k in ("location", "scale") and not isinstance(val, Vector):
            val = Vector(val)
        if k == "rotation_euler" and not isinstance(val, Vector):
            val = Euler(val)
        object.__setattr__(self, k, val)


class Objects(list):
    def new(self, name, data):
        return Obj(data)


renders = []
data = Bag(objects=Objects())
data.materials = Bag(new=lambda name: Bag(name=name, node_tree=Tree(["ShaderNodeBsdfPrincipled", "ShaderNodeOutputMaterial"])))
data.meshes = Bag(new=lambda name: Bag(polygons=[Bag()], materials=[]))
data.worlds = Bag(new=lambda name: Bag(node_tree=Tree(["ShaderNodeBackground", "ShaderNodeOutputWorld"])))
data.curves = Bag(new=lambda name, kind: Bag(body="", size=1, materials=[]))
data.fonts = Bag(load=lambda p: Bag(path=p))
ctx = Bag(scene=Bag(render=Bag(resolution_x=1920, resolution_y=1080, image_settings=Bag()), cycles=Bag(),
                    view_settings=Bag()))
ctx.collection = Bag(objects=Bag(link=lambda o: data.objects.append(o)))
ctx.view_layer = Bag(update=lambda: None)
ctx.preferences = Bag(addons={"cycles": Bag(preferences=Bag(devices=[], refresh_devices=lambda: None))})


def _add(**kw):
    o = Obj()
    o.location = Vector(kw.get("location", (0, 0, 0)))
    if "rotation" in kw:
        o.rotation_euler = Euler(kw["rotation"])
    data.objects.append(o)
    ctx.object = o
    return o


def _camera():
    o = _add()
    o.data = Bag(sensor_height=24.0, lens=50, dof=Bag(), sensor_fit="AUTO")
    return o


def _light(**kw):
    o = _add(**kw)
    o.data = Bag()
    return o


ops = Bag()
ops.mesh = Bag(primitive_cube_add=_add, primitive_cylinder_add=_add, primitive_uv_sphere_add=_add, primitive_torus_add=_add)
ops.object = Bag(transform_apply=lambda **kw: None, shade_smooth=lambda: None, empty_add=_add, light_add=_light,
                 camera_add=_camera)
ops.render = Bag(render=lambda write_still=False: renders.append(ctx.scene.render.filepath))


class BMesh:
    def __init__(self):
        self.verts = Bag(new=lambda co: co)
        self.faces = Bag(new=lambda vs: vs)

    def normal_update(self):
        pass

    def to_mesh(self, me):
        pass

    def free(self):
        pass


bpy = types.ModuleType("bpy")
bpy.data, bpy.context, bpy.ops = data, ctx, ops
bmesh = types.ModuleType("bmesh")
bmesh.new = BMesh
mathutils = types.ModuleType("mathutils")
mathutils.Vector, mathutils.Matrix = Vector, Matrix
sys.modules.update(bpy=bpy, bmesh=bmesh, mathutils=mathutils)

if __name__ == "__main__":
    scene = sys.argv[1]
    rest = sys.argv[2:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    sys.argv = ["blender", "-b", "--python", scene, "--", *rest]
    runpy.run_path(scene, run_name="__main__")
    print("RENDERS", len(renders), renders[:1], renders[-1:])
