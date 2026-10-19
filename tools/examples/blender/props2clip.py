"""Blender (headless): a character + animated objects file (glTF / FBX, e.g. HUMOTO) -> what the viewer plays.

blender -b --factory-startup --python props2clip.py -- in.(glb|fbx) <out dir>

Writes into <out dir>:
  character.bvh   the armature's action, zero pose = the armature rest (as anim2bvh.py)
  character.glb   the armature and its skinned meshes only (no props), for the viewer's rig fit
  props.glb       every other mesh object at the identity transform, Blender axes (Z-up, export_yup off), node name = object
  props.npz       names (n,), mats (T, n, 4, 4): each prop's transform per frame in the BVH's space (armature space)
Prints 'PROPS2CLIP {...}'. Objects are props when they are not part of the armature (not parented to it, no Armature modifier).
"""
import json
import os
import sys

import bpy
import numpy as np

args = sys.argv[sys.argv.index('--') + 1:]
src, out = args[:2]
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
if src.lower().endswith(('.glb', '.gltf')):
    sc.render.fps, sc.render.fps_base = 30, 1.0      # glTF keys are in seconds: sample them at 30 fps
    bpy.ops.import_scene.gltf(filepath=src)
else:
    bpy.ops.import_scene.fbx(filepath=src)
arm = max((o for o in bpy.data.objects if o.type == 'ARMATURE'), key=lambda a: len(a.data.bones))


def rigged(o):
    p = o
    while p is not None:
        if p == arm:
            return True
        p = p.parent
    return any(m.type == 'ARMATURE' for m in getattr(o, 'modifiers', []))


shapes = {b.custom_shape for b in arm.pose.bones if b.custom_shape}   # bone display shapes the glTF importer adds
props = [o for o in bpy.data.objects if o.type == 'MESH' and not rigged(o) and o not in shapes]


def play(o, prefer=None):
    """make the object's own action the active one (glTF puts each clip on an NLA track)"""
    if o.animation_data is None:
        return None
    for t in o.animation_data.nla_tracks:
        t.mute = True
    acts = [a for a in bpy.data.actions if a.name.split('|')[0] == (prefer or o.name)]
    act = o.animation_data.action or (max(acts, key=lambda a: a.frame_range[1] - a.frame_range[0]) if acts else None)
    if act is not None:
        o.animation_data.action = act
        if hasattr(o.animation_data, 'action_slot') and getattr(act, 'slots', None):
            try:
                o.animation_data.action_slot = act.slots[0]
            except Exception:  # noqa
                pass
    return act


# the armature's world rotation goes into the rig (as anim2bvh.py), so the BVH lives in world orientation
while arm.parent is not None:
    mw = arm.matrix_world.copy(); arm.parent = arm.parent.parent; arm.matrix_world = mw
for o in bpy.context.view_layer.objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = arm; arm.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
act = play(arm, arm.name) or play(arm)
# leaf bones come out of glTF import with arbitrary lengths (metres-long tails): the BVH writes them as End Sites, so shorten
# them to a few cm (skinning does not depend on a leaf's tail)
bpy.ops.object.mode_set(mode='EDIT')
for b in arm.data.edit_bones:
    if not b.children and b.length > 0:
        b.tail = b.head + (b.tail - b.head).normalized() * min(b.length, 5.0 / max(arm.scale[0], 1e-9) * 0.01)
bpy.ops.object.mode_set(mode='OBJECT')
for o in props:
    play(o)
f0, f1 = (int(round(x)) for x in act.frame_range)
sc.frame_start, sc.frame_end = f0, f1

# props per frame, in armature space (what the BVH exporter writes)
mats = np.zeros((f1 - f0 + 1, len(props), 4, 4), np.float32)
for i, f in enumerate(range(f0, f1 + 1)):
    sc.frame_set(f)
    inv = arm.matrix_world.inverted()
    for k, o in enumerate(props):
        mats[i, k] = np.array(inv @ o.matrix_world)
np.savez_compressed(os.path.join(out, 'props.npz'), names=np.array([o.name for o in props]), mats=mats,
                    fps=np.float64(sc.render.fps / sc.render.fps_base))

for o in bpy.context.view_layer.objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = arm; arm.select_set(True)
bpy.ops.export_anim.bvh(filepath=os.path.join(out, 'character.bvh'), frame_start=f0, frame_end=f1, root_transform_only=True,
                        rotate_mode='NATIVE')
# Blender writes the root's absolute location into its position channels on top of OFFSET (the hips height would count
# twice and the body would float above its props): make the channels relative to OFFSET, as the BVH convention reads them
bp = os.path.join(out, 'character.bvh')
lines = open(bp).read().split('\n')
off = [float(v) for v in next(ln for ln in lines if ln.strip().startswith('OFFSET')).split()[1:4]]
m = lines.index('MOTION') + 3
for i in range(m, len(lines)):
    v = lines[i].split()
    if len(v) >= 3:
        lines[i] = ' '.join(['%.6f' % (float(v[a]) - off[a]) for a in range(3)] + v[3:])
open(bp, 'w').write('\n'.join(lines))

sc.frame_set(f0)
for o in props:                                     # props: mesh at the identity, their motion is in props.npz
    if o.animation_data:
        o.animation_data_clear()
    o.parent = None
    o.matrix_world.identity()
for o in bpy.context.view_layer.objects:
    o.select_set(o in props)
bpy.ops.export_scene.gltf(filepath=os.path.join(out, 'props.glb'), export_format='GLB', use_selection=True, export_yup=False,
                          export_animations=False, export_skins=False)
for o in bpy.context.view_layer.objects:            # the character: armature + skinned meshes, nothing else
    o.select_set(o == arm or (o.type == 'MESH' and rigged(o)))
bpy.ops.export_scene.gltf(filepath=os.path.join(out, 'character.glb'), export_format='GLB', use_selection=True, export_animations=False)
print('PROPS2CLIP ' + json.dumps(dict(frames=f1 - f0 + 1, fps=sc.render.fps / sc.render.fps_base, props=[o.name for o in props],
                                      action=act.name)))
