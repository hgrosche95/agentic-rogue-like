"""Turn the cel-shaded arena into a physically lit, finer scene.

One-time migration of assets/blender/arena.blend (run it on the old toon
version, it saves over the file):

    python assets/blender/restyle_realistic.py      # with `pip install bpy`

What changes, and what deliberately does not:

- Freestyle outlines and the toon ramps go; every material becomes a
  Principled BSDF with roughness/bump detail (wood grain, plank floor,
  brushed metal, cloth, skin with subsurface scattering).
- Dr. Chronos gets real hair (particle strands with a Principled Hair BSDF)
  instead of cones, fingers on his gloves, smooth-shaded, subdivided limbs.
- The light is rebuilt in the UI's "Rift" palette - amber/magenta for the
  lab, cyan/violet for the machine world, a violet world light for the
  shadows - so the renders sit in the page without a heavy CSS grade.
- Camera, object positions and the monitor stay exactly where they were:
  the UI overlays (combat log glass, cable pulse, fighter origins) are
  measured from this camera and must keep matching.

Rendering the layers is render_layers.py.
"""

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

BLEND = Path(__file__).with_name("arena.blend")


def lin(hex_color: str) -> tuple[float, float, float, float]:
    """sRGB hex -> linear RGBA, as Blender's color sockets expect."""
    h = hex_color.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


# --- material building blocks -------------------------------------------------


class Mat:
    """Small node-graph helper: a fresh tree with one Principled BSDF."""

    def __init__(self, mat: bpy.types.Material):
        mat.use_nodes = True
        self.mat = mat
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.out = self.node("ShaderNodeOutputMaterial", 600, 0)
        self.bsdf = self.node("ShaderNodeBsdfPrincipled", 300, 0)
        self.link(self.bsdf.outputs["BSDF"], self.out.inputs["Surface"])
        coord = self.node("ShaderNodeTexCoord", -900, 0)
        self.obj = coord.outputs["Object"]
        self.gen = coord.outputs["Generated"]

    def node(self, kind, x=0, y=0, **props):
        n = self.nt.nodes.new(kind)
        n.location = (x, y)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def link(self, a, b):
        self.nt.links.new(a, b)

    def set(self, **inputs):
        names = {
            "base": "Base Color",
            "rough": "Roughness",
            "metal": "Metallic",
            "coat": "Coat Weight",
            "coat_rough": "Coat Roughness",
            "sheen": "Sheen Weight",
            "sheen_rough": "Sheen Roughness",
            "sss": "Subsurface Weight",
            "sss_scale": "Subsurface Scale",
            "emit": "Emission Color",
            "emit_strength": "Emission Strength",
            "spec": "Specular IOR Level",
            "transmission": "Transmission Weight",
            "alpha": "Alpha",
        }
        for key, value in inputs.items():
            self.bsdf.inputs[names[key]].default_value = value
        return self

    def noise(self, scale, detail=6.0, roughness=0.55, vector=None, x=-600, y=0):
        n = self.node("ShaderNodeTexNoise", x, y)
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = roughness
        self.link(vector or self.obj, n.inputs["Vector"])
        return n

    def ramp(self, src, stops, x=-300, y=0):
        r = self.node("ShaderNodeValToRGB", x, y)
        els = r.color_ramp.elements
        while len(els) > len(stops):
            els.remove(els[-1])
        while len(els) < len(stops):
            els.new(0.5)
        for el, (pos, col) in zip(els, stops, strict=True):
            el.position = pos
            el.color = (col, col, col, 1.0) if isinstance(col, (int, float)) else col
        self.link(src, r.inputs["Fac"])
        return r

    def rough_from(self, src, lo, hi):
        r = self.ramp(src, [(0.3, lo), (0.7, hi)], y=-250)
        self.link(r.outputs["Color"], self.bsdf.inputs["Roughness"])

    def bump(self, height, strength, distance=0.05):
        b = self.node("ShaderNodeBump", 0, -450)
        b.inputs["Strength"].default_value = strength
        b.inputs["Distance"].default_value = distance
        self.link(height, b.inputs["Height"])
        self.link(b.outputs["Normal"], self.bsdf.inputs["Normal"])
        return b

    def color_mix(self, fac, a, b):
        r = self.ramp(fac, [(0.0, a), (1.0, b)], y=250)
        self.link(r.outputs["Color"], self.bsdf.inputs["Base Color"])
        return r


def emissive(mat, color, strength, base=None):
    m = Mat(mat).set(
        base=base or (0.02, 0.02, 0.02, 1), rough=0.35, emit=color, emit_strength=strength
    )
    return m


def metal(mat, color, rough, grit=0.15, scale=40.0, brushed=False):
    m = Mat(mat).set(base=color, metal=1.0, rough=rough)
    vec = m.obj
    if brushed:
        # stretch the noise along one axis: fine streaks like brushed metal
        mp = m.node("ShaderNodeMapping", -800, -200)
        mp.inputs["Scale"].default_value = (1.0, 1.0, 40.0)
        m.link(m.obj, mp.inputs["Vector"])
        vec = mp.outputs["Vector"]
    n = m.noise(scale, vector=vec)
    m.rough_from(n.outputs["Fac"], max(rough - grit, 0.05), rough + grit)
    m.bump(n.outputs["Fac"], 0.08)
    return m


def dielectric(mat, color, rough, grit=0.15, scale=25.0, bump=0.1, variation=None):
    m = Mat(mat).set(base=color, rough=rough)
    n = m.noise(scale)
    m.rough_from(n.outputs["Fac"], max(rough - grit, 0.05), min(rough + grit, 1.0))
    if variation:
        m.color_mix(m.noise(scale / 6, detail=3).outputs["Fac"], variation, color)
    m.bump(n.outputs["Fac"], bump)
    return m


def wood(mat, dark, light, rough=0.55, scale=0.35):
    m = Mat(mat).set(rough=rough)
    mp = m.node("ShaderNodeMapping", -900, 300)
    mp.inputs["Scale"].default_value = (1.0, 8.0, 1.0)
    m.link(m.obj, mp.inputs["Vector"])
    wave = m.node("ShaderNodeTexWave", -650, 300, wave_type="RINGS")
    wave.inputs["Scale"].default_value = scale
    wave.inputs["Distortion"].default_value = 6.0
    wave.inputs["Detail"].default_value = 4.0
    m.link(mp.outputs["Vector"], wave.inputs["Vector"])
    m.color_mix(wave.outputs["Fac"], dark, light)
    n = m.noise(30)
    m.rough_from(n.outputs["Fac"], rough - 0.1, rough + 0.12)
    m.bump(wave.outputs["Fac"], 0.12)
    return m


def planks(mat, dark, light):
    """Floorboards: a brick texture laid flat, each board its own tone."""
    m = Mat(mat).set(rough=0.45, coat=0.25, coat_rough=0.3)
    brick = m.node("ShaderNodeTexBrick", -600, 250)
    brick.offset = 0.37
    brick.squash = 1.0
    brick.inputs["Scale"].default_value = 0.09
    brick.inputs["Mortar Size"].default_value = 0.012
    brick.inputs["Brick Width"].default_value = 4.5
    brick.inputs["Row Height"].default_value = 0.55
    brick.inputs["Color1"].default_value = dark
    brick.inputs["Color2"].default_value = light
    brick.inputs["Mortar"].default_value = (0.004, 0.002, 0.002, 1)
    m.link(m.obj, brick.inputs["Vector"])
    grain = m.noise(2.0, detail=8, vector=None, y=-100)
    mp = m.node("ShaderNodeMapping", -900, -100)
    mp.inputs["Scale"].default_value = (0.25, 6.0, 1.0)
    m.link(m.obj, mp.inputs["Vector"])
    m.link(mp.outputs["Vector"], grain.inputs["Vector"])
    mix = m.node("ShaderNodeMix", -100, 250, data_type="RGBA", blend_type="MULTIPLY")
    mix.inputs["Factor"].default_value = 0.55
    m.link(brick.outputs["Color"], mix.inputs["A"])
    m.link(grain.outputs["Color"], mix.inputs["B"])
    m.link(mix.outputs["Result"], m.bsdf.inputs["Base Color"])
    m.rough_from(grain.outputs["Fac"], 0.32, 0.6)
    m.bump(brick.outputs["Fac"], 0.35)
    return m


def cloth(mat, color, rough=0.85, scale=180.0, sheen=0.4, variation=None):
    m = Mat(mat).set(base=color, rough=rough, sheen=sheen, sheen_rough=0.4, spec=0.3)
    weave = m.noise(scale, detail=2, roughness=0.7)
    folds = m.noise(3.0, detail=4, y=-300)
    add = m.node("ShaderNodeMath", -300, -350, operation="MULTIPLY_ADD")
    add.inputs[1].default_value = 0.25
    m.link(weave.outputs["Fac"], add.inputs[0])
    m.link(folds.outputs["Fac"], add.inputs[2])
    m.bump(add.outputs["Value"], 0.25)
    if variation:
        m.color_mix(folds.outputs["Fac"], variation, color)
    return m


def skin(mat):
    m = Mat(mat).set(base=lin("#d9a184"), rough=0.48, sss=0.35, sss_scale=0.08, spec=0.45)
    m.bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
    pores = m.noise(120, detail=3)
    blotch = m.noise(4, detail=3, y=-300)
    m.color_mix(blotch.outputs["Fac"], lin("#c98068"), lin("#e2b096"))
    m.rough_from(pores.outputs["Fac"], 0.4, 0.58)
    m.bump(pores.outputs["Fac"], 0.06)
    return m


def hair(mat, color, melanin=0.08):
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    h = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
    h.parametrization = "MELANIN"
    h.inputs["Melanin"].default_value = melanin
    h.inputs["Melanin Redness"].default_value = 0.2
    h.inputs["Roughness"].default_value = 0.35
    h.inputs["Radial Roughness"].default_value = 0.5
    h.inputs["Random Roughness"].default_value = 0.3
    h.inputs["Random Color"].default_value = 0.25
    info = nt.nodes.new("ShaderNodeHairInfo")
    nt.links.new(info.outputs["Random"], h.inputs["Random"])
    # meshes that keep this material (bushy roots) read it as a white matte
    mix = nt.nodes.new("ShaderNodeBsdfPrincipled")
    mix.inputs["Base Color"].default_value = color
    mix.inputs["Roughness"].default_value = 0.7
    mix.inputs["Sheen Weight"].default_value = 0.6
    ish = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(info.outputs["Is Strand"], ish.inputs["Fac"])
    nt.links.new(mix.outputs["BSDF"], ish.inputs[1])
    nt.links.new(h.outputs["BSDF"], ish.inputs[2])
    nt.links.new(ish.outputs["Shader"], out.inputs["Surface"])


def restyle_materials():
    M = bpy.data.materials

    # -- the lab: warm wood, iron, copper, brass
    planks(M["L_floor"], lin("#3a2418"), lin("#5a3a26"))
    wood(M["L_wall"], lin("#2a1a14"), lin("#43291d"), rough=0.7, scale=0.18)
    wood(M["L_wood"], lin("#3b2014"), lin("#6b3d22"))
    metal(M["L_iron"], lin("#4a4644"), 0.55, grit=0.2)
    metal(M["L_copper"], lin("#e0906a"), 0.32, brushed=True)
    metal(M["P_brass"], lin("#d8a95a"), 0.28, brushed=True)
    metal(M["L_dmetal"], lin("#2c2f3a"), 0.4, brushed=True)
    dielectric(
        M["L_board"], lin("#1d2a22"), 0.9, grit=0.08, scale=8, bump=0.05, variation=lin("#27362c")
    )
    dielectric(M["L_chalk"], lin("#d8d4c8"), 0.95, grit=0.02, scale=60, bump=0.2)
    dielectric(M["L_tile"], lin("#221814"), 0.6)
    # the monitor glass: near-black, glossy - the combat log is drawn over it
    Mat(M["L_screen"]).set(
        base=lin("#04050a"), rough=0.45, spec=0.2, emit=lin("#0a1a2a"), emit_strength=0.25
    )

    # -- lights and energy: emission, strong enough to bloom
    emissive(M["L_amber"], lin("#ffae5c"), 1.2)
    emissive(M["L_arc"], lin("#ffe7c2"), 7.0)
    emissive(M["L_green"], lin("#5dffb1"), 5.0)
    emissive(M["P_glow"], lin("#ffb86b"), 8.0)
    emissive(M["E_cyan"], lin("#3fd6e8"), 7.0)
    emissive(M["E_red"], lin("#ff4f8b"), 8.0)
    emissive(M["E_fire"], lin("#ff8a3d"), 8.0)
    emissive(M["R_cyan"], lin("#8ff2ef"), 6.0)
    emissive(M["R_orange"], lin("#ffb86b"), 6.0)
    emissive(M["R_core"], lin("#f5f2ff"), 6.0)
    emissive(M["R_cyan_dim"], lin("#1a6a7a"), 2.0)
    emissive(M["R_orange_dim"], lin("#7a3a1a"), 2.0)
    emissive(M["RIG_cyan"], lin("#3fd6e8"), 8.0)
    emissive(M["RIG_cyan_hot"], lin("#bff8ff"), 14.0)
    emissive(M["W7_cyan"], lin("#3fd6e8"), 6.0)
    emissive(M["W7_red"], lin("#ff4f8b"), 6.0)

    # -- the machine world: black anodized racks on a mirror floor, under a
    #    violet sky that is the page's own background
    m = metal(M["E_server"], lin("#1a1d2e"), 0.22, grit=0.08, brushed=True)
    m.set(coat=0.6, coat_rough=0.08)
    m = Mat(M["E_aifloor"]).set(
        base=lin("#0b0a1c"), rough=0.12, metal=0.3, coat=1.0, coat_rough=0.05
    )
    n = m.noise(6, detail=4)
    m.rough_from(n.outputs["Fac"], 0.06, 0.2)
    m = Mat(M["E_voxel"]).set(
        base=lin("#1b2a55"), rough=0.08, transmission=0.6, emit=lin("#3fd6e8"), emit_strength=0.8
    )
    Mat(M["E_coldsky"]).set(base=(0, 0, 0, 1), rough=1.0, emit=lin("#2a1d63"), emit_strength=1.0)
    Mat(M["E_towersil"]).set(base=lin("#100c2a"), rough=0.4, emit=lin("#1c1446"), emit_strength=0.6)

    # -- the rig: a dark console with glowing keys
    metal(M["RIG_case"], lin("#2a3348"), 0.3, brushed=True)
    dielectric(M["RIG_key"], lin("#1c2234"), 0.35, grit=0.05, bump=0.02)
    dielectric(M["RIG_cable"], lin("#15161e"), 0.4, grit=0.05, scale=80, bump=0.05)

    # -- Dr. Chronos
    skin(M["P_skin"])
    cloth(M["S_coat"], lin("#ece6d8"), variation=lin("#cfc6b2"))
    cloth(M["S_pants"], lin("#2a2320"), scale=260)
    m = dielectric(M["S_glove"], lin("#5a1c14"), 0.3, grit=0.1, bump=0.03)
    m.set(coat=0.4, coat_rough=0.2)
    m = dielectric(M["P_boots"], lin("#2a1810"), 0.35, grit=0.15, scale=40, bump=0.15)
    m.set(coat=0.5, coat_rough=0.15)
    cloth(M["S_tie"], lin("#5a0418"), rough=0.4, scale=300, sheen=0.05)
    dielectric(M["S_stain"], lin("#6a4a28"), 0.8, bump=0.02)
    dielectric(M["P_dark"], lin("#18140f"), 0.45, grit=0.1)
    hair(M["S_hair"], lin("#e9e7e2"))

    # W7 (the old mesh robot) is not rendered any more, but keep it sane
    for name, col in (("W7_body", "#28406a"), ("W7_dark", "#0e1624"), ("W7_plate", "#7a9ab8")):
        metal(M[name], lin(col), 0.3)


# --- geometry -------------------------------------------------------------------


def smooth(obj, angle=35):
    if obj.type != "MESH":
        return
    for p in obj.data.polygons:
        p.use_smooth = True
    # keep hard edges hard: only faces meeting at a shallow angle blend
    obj.data.set_sharp_from_angle(angle=math.radians(angle))


def add_mod(obj, kind, name=None, **props):
    mod = obj.modifiers.new(name or kind.title(), kind)
    for k, v in props.items():
        setattr(mod, k, v)
    return mod


def is_box(obj):
    return obj.type == "MESH" and len(obj.data.polygons) == 6


def refine_environment():
    for coll in ("Environment", "NoLines", "RigLines", "RigGlow"):
        for obj in bpy.data.collections[coll].all_objects:
            if obj.type != "MESH":
                continue
            smooth(obj)
            if is_box(obj) and not any(m.type == "BEVEL" for m in obj.modifiers):
                # real edges catch a highlight; a cube's never does
                width = min(0.12, min(d for d in obj.dimensions if d > 0) * 0.18)
                add_mod(obj, "BEVEL", width=width, segments=3, limit_method="ANGLE")
            for m in obj.modifiers:
                if m.type == "BEVEL":
                    m.segments = max(m.segments, 3)
                    m.harden_normals = False


def finger(name, parent, local_pos, direction, length, radius, mat):
    """A capsule for one finger, parented to its glove."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius, depth=length)
    f = bpy.context.active_object
    f.name = name
    for c in f.users_collection:
        c.objects.unlink(f)
    for c in parent.users_collection:
        c.objects.link(f)
    f.data.materials.append(mat)
    add_mod(f, "SUBSURF", levels=1, render_levels=2)
    for p in f.data.polygons:
        p.use_smooth = True
    d = direction.normalized()
    f.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    f.location = parent.matrix_world @ local_pos + d * (length / 2)
    f.parent = parent
    f.matrix_parent_inverse = parent.matrix_world.inverted()
    return f


def refine_player():
    objs = {o.name: o for o in bpy.data.collections["Player"].all_objects}
    organic = ("S_head", "S_nose", "S_ear", "S_neck", "S_glove", "S_moustache", "S_stain")
    tubes = ("S_leg", "S_sleeve", "S_coat", "S_pen", "S_bowtie", "S_pack_coil")
    for name, obj in objs.items():
        if obj.type != "MESH" or obj.hide_render:
            continue
        for p in obj.data.polygons:
            p.use_smooth = True
        if name.startswith(organic) and not any(m.type == "SUBSURF" for m in obj.modifiers):
            add_mod(obj, "SUBSURF", levels=1, render_levels=2)
        if name.startswith(tubes) and not any(m.type == "SUBSURF" for m in obj.modifiers):
            add_mod(obj, "BEVEL", width=0.08, segments=2, limit_method="ANGLE")
            add_mod(obj, "SUBSURF", levels=1, render_levels=2)
        if name.startswith("S_hair_spike"):
            # replaced by real strands below
            obj.hide_render = True
            obj.hide_viewport = True

    coat = objs["S_coat"]
    sub = next(m for m in coat.modifiers if m.type == "SUBSURF")
    sub.levels, sub.render_levels = 2, 3
    tex = bpy.data.textures.new("CoatFolds", "CLOUDS")
    tex.noise_scale = 1.4
    tex.noise_depth = 2
    add_mod(coat, "DISPLACE", texture=tex, strength=0.18, mid_level=0.5, texture_coords="OBJECT")

    # An open coat: a dark waistcoat with brass buttons down his front,
    # instead of one white shape from collar to hem.
    seam = objs["S_coat_seam"]
    head = objs["S_head"].matrix_world.translation
    nose = objs["S_nose"].matrix_world.translation
    facing = Vector((nose.x - head.x, nose.y - head.y, 0)).normalized()
    top = seam.matrix_world.translation + Vector((0, 0, 2.2))
    bpy.ops.mesh.primitive_cube_add(size=1)
    vest = bpy.context.active_object
    vest.name = "S_vest"
    vest.scale = (1.3, 0.4, 4.0)
    vest.rotation_euler = (0, 0, math.atan2(facing.y, facing.x) + math.pi / 2)
    vest.location = top + facing * 0.12
    vest.data.materials.append(bpy.data.materials["S_pants"])
    add_mod(vest, "BEVEL", width=0.2, segments=3)
    add_mod(vest, "SUBSURF", levels=2, render_levels=2)
    for p in vest.data.polygons:
        p.use_smooth = True
    buttons = [vest]
    for i in range(3):
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.13, segments=16, ring_count=8)
        b = bpy.context.active_object
        b.name = f"S_button{i}"
        b.scale = (1, 1, 0.5)
        b.rotation_euler = vest.rotation_euler.copy()
        b.rotation_euler.x = math.pi / 2
        b.location = top + facing * 0.34 + Vector((0, 0, 0.9 - i * 0.8))
        b.data.materials.append(bpy.data.materials["P_brass"])
        for p in b.data.polygons:
            p.use_smooth = True
        buttons.append(b)
    player = objs["Player"]
    for obj in buttons:
        for c in obj.users_collection:
            c.objects.unlink(obj)
        bpy.data.collections["Player"].objects.link(obj)
        world = obj.matrix_world.copy()
        obj.parent = player
        obj.matrix_world = world

    # Fingers: four per glove, pointing from the wrist over the keys.
    skin_mat = bpy.data.materials["S_glove"]
    bpy.context.scene.frame_set(1)
    for side, sleeve in (("r", "S_sleeve.001"), ("l", "S_sleeve.003")):
        glove = objs[f"S_glove_{side}"]
        wrist = objs[sleeve].matrix_world.translation
        centre = glove.matrix_world.translation
        forward = (centre - wrist).normalized()
        forward.z = 0  # flat over the keys: the keyboard top is level with the glove
        forward = (forward.normalized() + Vector((0, 0, -0.12))).normalized()
        across = forward.cross(Vector((0, 0, 1))).normalized()
        inv = glove.matrix_world.inverted()
        for i, t in enumerate((-1.5, -0.5, 0.5, 1.5)):
            start_world = centre + forward * 0.5 + across * t * 0.27 + Vector((0, 0, 0.12))
            finger(
                f"S_finger_{side}{i}",
                glove,
                inv @ start_world,
                forward,
                0.75 - abs(t) * 0.1,
                0.13,
                skin_mat,
            )
        thumb_world = centre + across * 0.55 + forward * 0.15 + Vector((0, 0, 0.2))
        finger(
            f"S_thumb_{side}",
            glove,
            inv @ thumb_world,
            (forward + across).normalized(),
            0.55,
            0.14,
            skin_mat,
        )


def hair_system(
    obj,
    name,
    count,
    length,
    children,
    kink_amp=0.0,
    rough=0.2,
    clump=0.0,
    radius=0.012,
    random=0.4,
    normal=1.0,
    tangent=0.0,
):
    mod = obj.modifiers.new(name, "PARTICLE_SYSTEM")
    ps = mod.particle_system.settings
    ps.name = name
    ps.type = "HAIR"
    ps.count = count
    ps.hair_length = length
    ps.hair_step = 6
    ps.emit_from = "FACE"
    ps.use_advanced_hair = True
    ps.normal_factor = normal
    ps.tangent_factor = tangent
    ps.factor_random = random
    ps.child_type = "INTERPOLATED"
    ps.child_percent = children
    ps.rendered_child_count = children
    ps.child_length = 1.0
    ps.clump_factor = clump
    ps.roughness_1 = rough
    ps.roughness_1_size = 0.6
    ps.roughness_endpoint = rough * 0.8
    ps.roughness_2 = rough * 0.5
    ps.roughness_2_size = 1.5
    if kink_amp:
        ps.kink = "CURL"
        ps.kink_amplitude = kink_amp
        ps.kink_frequency = 1.4
    ps.root_radius = 1.0
    ps.tip_radius = 0.2
    ps.radius_scale = radius
    ps.material_slot = obj.material_slots[0].name
    ps.display_step = 3
    ps.render_step = 5
    return ps


def scalp_group(obj, face_dir: Vector):
    """Weight the hair emitter so strands grow off the back, sides and top,
    never over his face (which looks toward the rift)."""
    group = obj.vertex_groups.new(name="Scalp")
    rot = obj.matrix_world.to_3x3()
    face_dir = face_dir.normalized()
    for v in obj.data.vertices:
        n = (rot @ v.normal).normalized()
        away = -n.dot(face_dir)  # 1 at the back of the head
        up = n.z
        w = max(0.0, min(1.0, (away + 0.15) * 1.6)) * max(0.0, min(1.0, (up + 0.35) * 1.8))
        if w > 0:
            group.add([v.index], w, "REPLACE")
    return group.name


def add_hair():
    objs = bpy.data.objects
    head = objs["S_head"].matrix_world.translation
    nose = objs["S_nose"].matrix_world.translation
    face_dir = Vector((nose.x - head.x, nose.y - head.y, 0))
    back = objs["S_hair_back"]
    # the famous white shock: spiky clumps standing off the back of his head
    ps = hair_system(
        back,
        "WildHair",
        count=520,
        length=0.85,
        children=18,
        kink_amp=0.05,
        rough=0.2,
        clump=0.75,
        radius=0.014,
        random=0.35,
    )
    ps.clump_shape = -0.4
    back.particle_systems["WildHair"].vertex_group_density = scalp_group(back, face_dir)
    for name in ("S_moustache", "S_moustache.001"):
        m = hair_system(
            objs[name],
            "Moustache",
            count=160,
            length=0.2,
            children=6,
            rough=0.03,
            clump=0.3,
            radius=0.009,
            random=0.15,
            normal=0.4,
        )
        m.use_hair_bspline = True


# --- light and world --------------------------------------------------------------


def area(name, loc, target, color, power, size, shape="RECTANGLE", size_y=None):
    data = bpy.data.lights.new(name, "AREA")
    data.shape = shape
    data.size = size
    data.size_y = size_y or size
    data.color = color[:3]
    data.energy = power
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return obj


def point(name, loc, color, power, radius):
    data = bpy.data.lights.new(name, "POINT")
    data.color = color[:3]
    data.energy = power
    data.shadow_soft_size = radius
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    return obj


def relight():
    for obj in list(bpy.data.objects):
        if obj.type == "LIGHT":
            bpy.data.objects.remove(obj)

    # the lab: a warm key from the upper left (the lamps and the coil),
    # magenta from behind for the rim, the rift's cyan on his face
    area("Key_lab", (-44, -30, 38), (-22, -2, 10), lin("#ffcaa0"), 26000, 18)
    area("Rim_lab", (-30, 18, 26), (-21, -2, 12), lin("#ff4fd8"), 4500, 10)
    area("Fill_violet", (-10, -60, 14), (-20, 0, 10), lin("#6f6cff"), 5500, 30)
    point("Coil_glow", (-35, 12, 16), lin("#ffb86b"), 3500, 2.5)
    point("Shelf_glow", (-38, 16, 18), lin("#ffae5c"), 1500, 3)
    point("Board_lamp", (-15, 14, 22), lin("#ffcf9a"), 1200, 2)

    # the rift: bright seam light spilling both ways
    area("Rift_human", (-1, 6, 12), (-20, -2, 10), lin("#ffb86b"), 7000, 4, size_y=24)
    area("Rift_ai", (1, 6, 12), (22, 5, 8), lin("#3fd6e8"), 9000, 4, size_y=24)
    point("Rift_core", (0, 12, 8), lin("#dff8ff"), 6000, 1.5)
    area("Kb_glow", (-15.2, -4.6, 11.5), (-17.5, -3, 15.5), lin("#3fd6e8"), 350, 1.6)

    # the machine world: cold top light over the racks, violet haze behind
    area("Key_ai", (26, -20, 44), (26, 10, 5), lin("#9fe8ff"), 22000, 30)
    area("Back_ai", (26, 32, 18), (26, 0, 6), lin("#6a4cff"), 16000, 40)
    area("Floor_ai", (26, -30, 3), (26, 10, 2), lin("#ff4fd8"), 3000, 30)

    world = bpy.data.worlds["ArenaWorld"]
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = lin("#2e1f6a")
    bg.inputs["Strength"].default_value = 0.35


def render_settings():
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = 256
    s.cycles.use_adaptive_sampling = True
    s.cycles.adaptive_threshold = 0.02
    s.cycles.use_denoising = True
    s.cycles.max_bounces = 8
    s.cycles.glossy_bounces = 4
    s.cycles.transmission_bounces = 6
    s.cycles.sample_clamp_indirect = 8.0
    s.cycles.blur_glossy = 1.0
    s.render.use_freestyle = False
    for vl in s.view_layers:
        vl.use_freestyle = False
        vl.use_pass_mist = True
    s.view_settings.view_transform = "AgX"
    s.view_settings.look = "AgX - Medium High Contrast"
    s.view_settings.exposure = 0.0
    s.world.mist_settings.start = 88
    s.world.mist_settings.depth = 40
    s.world.mist_settings.falloff = "QUADRATIC"


def main():
    # optional: `-- <out.blend>` to write somewhere else than over the source
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    out = Path(args[0]) if args else BLEND
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    restyle_materials()
    refine_environment()
    refine_player()
    add_hair()
    relight()
    render_settings()
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)


if __name__ == "__main__":
    main()
