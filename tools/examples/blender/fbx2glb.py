"""Blender (headless): rigged FBX / glTF -> skinned, Draco-compressed, textured GLB for the demo viewer (bind pose, no animation).

blender -b --factory-startup --python space/tools/fbx2glb.py -- in.(fbx|glb|gltf) out.glb
Textures are kept but downscaled (base colour <= MAX_TEX px, other maps <= MAX_TEX_AUX) and stored as WebP; meshes over
MAX_VERTS are decimated (vertex groups = skin weights survive the collapse). Prints one line 'FBX2GLB {...}' with counts and
the bind-pose world position of every bone in glTF (Y-up) coordinates, for the build's rest-pose fit check.
"""
import json
import os
import sys

import bpy

MAX_VERTS = 150000
MAX_TEX = 1024
MAX_TEX_AUX = 512

src, dst = sys.argv[sys.argv.index('--') + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
import io_scene_fbx.import_fbx as _imp           # noqa: E402  Blender 5.x: its FBX light import sets a Cycles property that no
_read_light = _imp.blen_read_light                # longer exists; lights are dropped below anyway, so a failed light is a stub


def _safe_light(fbx_tmpl, fbx_obj, settings):
    try:
        return _read_light(fbx_tmpl, fbx_obj, settings)
    except AttributeError:
        return bpy.data.lights.new('light', 'POINT')


_imp.blen_read_light = _safe_light
if src.lower().endswith(('.glb', '.gltf')):
    bpy.ops.import_scene.gltf(filepath=src)
else:
    bpy.ops.import_scene.fbx(filepath=src)
    # FBX texture paths are often absolute paths from the author's machine: look next to the FBX (and in tex/ textures/)
    base = os.path.dirname(os.path.abspath(src))
    for img in bpy.data.images:
        if img.source == 'FILE' and not img.packed_file and not os.path.exists(bpy.path.abspath(img.filepath)):
            name = os.path.basename(img.filepath.replace('\\', '/'))
            stem = os.path.splitext(name)[0].lower()
            dirs = [d for d in (base, os.path.join(base, 'tex'), os.path.join(base, 'textures'), os.path.join(base, 'Textures')) if os.path.isdir(d)]
            hit = next((os.path.join(d, name) for d in dirs if os.path.exists(os.path.join(d, name))), None)
            if hit is None:                       # renamed on disk (e.g. Wolf_Fur.jpg -> Wolf_Fur_Alpha_3.png): same stem prefix
                hit = next((os.path.join(d, f) for d in dirs for f in sorted(os.listdir(d))
                            if f.lower().startswith(stem) and f.lower().endswith(('.png', '.jpg', '.jpeg', '.tga'))), None)
            if hit:
                img.filepath = hit
for ob in bpy.data.objects:                       # bind pose only: drop every action, show the rest position
    if ob.animation_data:
        ob.animation_data_clear()
    if ob.type == 'ARMATURE':
        ob.data.pose_position = 'REST'
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
# only armatures and their meshes survive: first lift kept objects out of the empties that are about to go (keeping their
# world transform), hang every skinned mesh on its armature, and drop meshes that belong to no rig (e.g. a stray sphere)
keep = [o for o in bpy.data.objects if o.type in ('ARMATURE', 'MESH')]
for o in keep:
    while o.parent is not None and o.parent.type not in ('ARMATURE', 'MESH'):
        mw = o.matrix_world.copy(); o.parent = o.parent.parent; o.matrix_world = mw
for o in keep:
    mod = next((md for md in getattr(o, 'modifiers', []) if md.type == 'ARMATURE' and md.object), None)
    if o.type == 'MESH' and mod and o.parent is not mod.object:
        mw = o.matrix_world.copy(); o.parent = mod.object; o.matrix_parent_inverse = mod.object.matrix_world.inverted(); o.matrix_world = mw
for ob in list(bpy.data.objects):
    rigged = ob.type == 'MESH' and (any(md.type == 'ARMATURE' for md in ob.modifiers) or (ob.parent and ob.parent.type == 'ARMATURE'))
    if ob.type not in ('ARMATURE', 'MESH') or (ob.type == 'MESH' and not rigged and any(o.type == 'ARMATURE' for o in bpy.data.objects)):
        bpy.data.objects.remove(ob, do_unlink=True)
for m in [o for o in bpy.data.objects if o.type == 'MESH']:
    n = len(m.data.vertices)
    if n > MAX_VERTS:
        bpy.context.view_layer.objects.active = m
        mod = m.modifiers.new('decimate', 'DECIMATE'); mod.ratio = MAX_VERTS / n
        while m.modifiers[0].name != 'decimate':   # before the Armature modifier, then bake it into the mesh
            bpy.ops.object.modifier_move_up(modifier='decimate')
        bpy.ops.object.modifier_apply(modifier='decimate')
if not src.lower().endswith(('.glb', '.gltf')):   # FBX has no PBR: the importer's defaults export as metallic 1 / specular 2
    for mat in bpy.data.materials:
        if mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type == 'BSDF_PRINCIPLED':
                    for name, val in (('Metallic', 0.0), ('Specular IOR Level', 0.5), ('Roughness', 0.65)):
                        inp = node.inputs.get(name)
                        if inp is not None and not inp.links:
                            inp.default_value = val
                    a_in = node.inputs.get('Alpha')         # Unity / Max FBX 'TransparencyFactor' often lands as alpha 0
                    if a_in is not None and not a_in.links and a_in.default_value < 0.05:
                        a_in.default_value = 1.0
# cut-out textures (fur cards, feathers, leaves): FBX import leaves the image's alpha unconnected -> wire it to the BSDF alpha
# (the glTF exporter then writes alphaMode MASK/BLEND); only for images that really carry transparency
def _has_alpha(img):
    try:
        if img.size[0] == 0:
            img.reload()
        if img.channels < 4 or img.depth not in (32, 64, 128):
            return False
        px = img.pixels[:]
        return any(px[i] < 0.98 for i in range(3, len(px), 4 * max(1, len(px) // 4 // 20000)))
    except Exception:  # noqa
        return False


for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    for node in mat.node_tree.nodes:
        if node.type != 'BSDF_PRINCIPLED' or node.inputs['Alpha'].links:
            continue
        for link in node.inputs['Base Color'].links:
            tex = link.from_node
            if tex.type == 'TEX_IMAGE' and tex.image and _has_alpha(tex.image):
                mat.node_tree.links.new(tex.outputs['Alpha'], node.inputs['Alpha'])
                if hasattr(mat, 'surface_render_method'):
                    mat.surface_render_method = 'DITHERED'
# textures: which images are base colour (kept larger) vs normal / roughness / ... (smaller)
base_imgs = set()
for mat in bpy.data.materials:
    if mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                for link in node.inputs['Base Color'].links:
                    if link.from_node.type == 'TEX_IMAGE' and link.from_node.image:
                        base_imgs.add(link.from_node.image.name)
n_tex = 0
for img in bpy.data.images:
    try:
        if img.size[0] == 0:
            img.reload()
        w, h = img.size
    except Exception:  # noqa
        continue
    if not w:
        continue
    cap = MAX_TEX if img.name in base_imgs else MAX_TEX_AUX
    if max(w, h) > cap:
        s = cap / max(w, h)
        img.scale(max(1, int(w * s)), max(1, int(h * s)))
    n_tex += 1
bpy.ops.export_scene.gltf(filepath=dst, export_format='GLB', export_animations=False, export_skins=True, export_yup=True,
                          export_materials='EXPORT', export_image_format='WEBP', export_image_quality=80, export_morph=False,
                          export_apply=False, export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
                          export_draco_position_quantization=16, export_draco_normal_quantization=10,
                          export_draco_texcoord_quantization=12, export_draco_generic_quantization=12)
arm = [o for o in bpy.data.objects if o.type == 'ARMATURE']
mesh = [o for o in bpy.data.objects if o.type == 'MESH']
bones = {}
for a in arm:
    mw = a.matrix_world
    for b in a.data.bones:
        p = mw @ b.head_local
        bones[b.name] = [p.x, p.z, -p.y]          # Blender Z-up -> glTF Y-up (export_yup)
print('FBX2GLB ' + json.dumps(dict(armatures=len(arm), bones=sum(len(a.data.bones) for a in arm), meshes=len(mesh),
                                   verts=sum(len(m.data.vertices) for m in mesh), textures=n_tex, bone_world=bones)))
