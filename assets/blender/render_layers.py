"""Render the combat arena's layers from assets/blender/arena.blend.

    python assets/blender/render_layers.py [--preview] [--out DIR] [LAYER ...]

(needs `pip install bpy pillow`: Blender renders a lossless PNG, Pillow
encodes the WebP with its slowest, smallest settings)

Every layer is a full 1920x800 frame from the same camera, so the frontend
can stack them 1:1 (see frontend/src/components/CombatArena.tsx):

- background     the lab, the rift and the machine world - no fighters
- rig            Dr. Chronos' pult, keyboard and the cable into the rift
- player         Dr. Chronos at the keys (frame 1)
- player-typing  the same with his hands lifted off the keys (frame 2)

The foreground layers are transparent and lit by the same lights, but only
show their own objects. The lab floor becomes a shadow catcher, so the
fighter brings his own soft contact shadow along when the UI animates him;
the rest of the lab is left out of these layers, or its shadows would land
in the catcher too. The rig is held out of the player layer where it stands
in front of him.

Bloom and a violet depth haze are added in the compositor, so the glow of
the rift and the racks sits in the frame the same way the UI's glows do.
"""

import argparse
import sys
import tempfile
from pathlib import Path

import bpy
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
BLEND = Path(__file__).with_name("arena.blend")
OUT = ROOT / "frontend" / "public" / "assets"

LAYERS = ("background", "rig", "player", "player-typing")
HAZE = (0.028, 0.016, 0.14, 1.0)  # linear #2e1f6a-ish, the page's violet


def collections():
    return {c.name: c for c in bpy.data.collections}


def set_visibility(layer: str):
    """Configure objects for one layer; returns the frame to render."""
    colls = collections()
    fighters = set(colls["Player"].all_objects)
    rig = set(colls["RigLines"].all_objects) | set(colls["RigGlow"].all_objects)
    enemy = set(colls["Enemy"].all_objects)
    floor = bpy.data.objects["GroundLab"]

    s = bpy.context.scene
    vl = s.view_layers["ViewLayer"]
    for other in s.view_layers:
        other.use = other.name == vl.name
    for lc in vl.layer_collection.children:
        lc.exclude = lc.name == "Enemy"
        for child in lc.children:
            child.exclude = False

    for obj in bpy.data.objects:
        if obj.type not in {"MESH", "CURVE", "EMPTY"}:
            continue
        obj.is_holdout = False
        obj.is_shadow_catcher = False
        obj.visible_camera = True
        if obj in enemy:
            obj.hide_render = True
            continue
        if layer == "background":
            # the fighters are separate layers: leave them out entirely,
            # shadows included, so they never appear twice
            obj.hide_render = obj in fighters or obj in rig or obj.get("_hidden", False)
        else:
            obj.hide_render = obj.get("_hidden", False)
            own = fighters if layer.startswith("player") else rig
            if obj in own:
                continue
            if layer.startswith("player") and obj in rig:
                obj.is_holdout = True
            elif obj == floor:
                obj.is_shadow_catcher = True
            else:
                # anything else would cast its own shadow into the catcher
                obj.hide_render = True

    s.render.film_transparent = layer != "background"
    return 2 if layer == "player-typing" else 1


def compositor(layer: str):
    s = bpy.context.scene
    tree = bpy.data.node_groups.get("ArenaComp") or bpy.data.node_groups.new(
        "ArenaComp", "CompositorNodeTree"
    )
    tree.nodes.clear()
    for item in list(tree.interface.items_tree):
        tree.interface.remove(item)
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    rl = tree.nodes.new("CompositorNodeRLayers")
    out = tree.nodes.new("NodeGroupOutput")
    img = rl.outputs["Image"]

    if layer == "background":
        # depth haze: the far wall and the racks sink into the page violet
        mix = tree.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.clamp_factor = True
        mul = tree.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = 0.55
        tree.links.new(rl.outputs["Mist"], mul.inputs[0])
        tree.links.new(mul.outputs[0], mix.inputs["Factor"])
        tree.links.new(img, mix.inputs["A"])
        mix.inputs["B"].default_value = HAZE
        img = mix.outputs["Result"]

    glare = tree.nodes.new("CompositorNodeGlare")
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Quality"].default_value = "High"
    glare.inputs["Threshold"].default_value = 1.0
    glare.inputs["Strength"].default_value = 0.6 if layer == "background" else 0.35
    glare.inputs["Size"].default_value = 0.6
    tree.links.new(img, glare.inputs["Image"])
    img = glare.outputs["Image"]

    if layer != "background":
        # keep the alpha the render produced (bloom must not fill the frame)
        sa = tree.nodes.new("CompositorNodeSetAlpha")
        sa.inputs["Type"].default_value = "Replace Alpha"
        tree.links.new(img, sa.inputs["Image"])
        tree.links.new(rl.outputs["Alpha"], sa.inputs["Alpha"])
        img = sa.outputs["Image"]

    tree.links.new(img, out.inputs[0])
    s.compositing_node_group = tree
    s.render.use_compositing = True


def render(layer: str, out_dir: Path, preview: bool):
    s = bpy.context.scene
    s.frame_set(set_visibility(layer))
    compositor(layer)
    s.render.resolution_x, s.render.resolution_y = 1920, 800
    s.render.resolution_percentage = 50 if preview else 100
    s.cycles.samples = 48 if preview else 256
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGB" if layer == "background" else "RGBA"
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / f"{layer}.png"
        s.render.filepath = str(png)
        bpy.ops.render.render(write_still=True)
        # q82 is where the renders stop showing artifacts at 1920 wide; the
        # empty areas of the transparent layers cost next to nothing
        Image.open(png).save(
            out_dir / f"lab-{layer}.webp", "WEBP", quality=82, method=6, alpha_quality=80
        )


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("layers", nargs="*", default=list(LAYERS))
    ap.add_argument("--preview", action="store_true", help="half size, few samples")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--blend", type=Path, default=BLEND)
    args = ap.parse_args(argv)

    bpy.ops.wm.open_mainfile(filepath=str(args.blend))
    # objects hidden on purpose in the blend (his raygun and flask) stay hidden
    for obj in bpy.data.objects:
        obj["_hidden"] = obj.hide_render
    args.out.mkdir(parents=True, exist_ok=True)
    for layer in args.layers:
        render(layer, args.out, args.preview)


if __name__ == "__main__":
    main()
