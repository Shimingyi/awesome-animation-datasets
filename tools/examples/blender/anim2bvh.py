"""Blender (headless): the animation of a rigged FBX / glTF -> BVH whose zero pose is the armature's rest (= the mesh's bind pose).

blender -b --factory-startup --python space/tools/anim2bvh.py -- in.(fbx|glb|gltf) out.bvh [action name]
Vendor BVHs often use a different zero pose than their FBX meshes; exporting the FBX's own action keeps the clip and the mesh
consistent, so the viewer can drive the mesh with the decoded joints. Prints 'ANIM2BVH {...}' (bones, frames, fps).
"""
import json
import sys

import bpy

args = sys.argv[sys.argv.index('--') + 1:]
src, dst = args[:2]
want = args[2] if len(args) > 2 else None
bpy.ops.wm.read_factory_settings(use_empty=True)
import io_scene_fbx.import_fbx as _imp           # noqa: E402  (see fbx2glb.py: Blender 5.x FBX light import)
_read_light = _imp.blen_read_light


def _safe_light(fbx_tmpl, fbx_obj, settings):
    try:
        return _read_light(fbx_tmpl, fbx_obj, settings)
    except AttributeError:
        return bpy.data.lights.new('light', 'POINT')


_imp.blen_read_light = _safe_light
if src.lower().endswith(('.glb', '.gltf')):
    bpy.context.scene.render.fps = 30             # glTF keys are in seconds: sample them at 30 fps
    bpy.context.scene.render.fps_base = 1.0
    bpy.ops.import_scene.gltf(filepath=src)
else:
    bpy.ops.import_scene.fbx(filepath=src)
arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
if not arms:
    print('ANIM2BVH ' + json.dumps(dict(error='no armature'))); sys.exit(0)
arm = max(arms, key=lambda a: len(a.data.bones))
# Blender's BVH exporter writes ARMATURE space (it ignores the object transform): bake the armature's world rotation and scale
# into the rig first (lifting it out of any parent empties), so the clip lives in world orientation like the exported mesh
while arm.parent is not None:
    mw = arm.matrix_world.copy(); arm.parent = arm.parent.parent; arm.matrix_world = mw
for o in bpy.context.view_layer.objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)   # scale stays: root location keys are not rescaled by Blender
acts = [a for a in bpy.data.actions if any('pose.bones' in fc.data_path for fc in getattr(a, 'fcurves', []))] or list(bpy.data.actions)
if want:
    acts = [a for a in acts if a.name == want] or acts
if not acts:
    print('ANIM2BVH ' + json.dumps(dict(error='no action'))); sys.exit(0)
act = max(acts, key=lambda a: a.frame_range[1] - a.frame_range[0])
if arm.animation_data is None:
    arm.animation_data_create()
for t in arm.animation_data.nla_tracks:           # glTF imports every clip as an NLA track: play only the chosen action
    t.mute = True
arm.animation_data.action = act
if hasattr(arm.animation_data, 'action_slot') and getattr(act, 'slots', None):   # Blender 4.4+ slotted actions
    try:
        arm.animation_data.action_slot = act.slots[0]
    except Exception:  # noqa
        pass
f0, f1 = int(round(act.frame_range[0])), int(round(act.frame_range[1]))
sc = bpy.context.scene
sc.frame_start, sc.frame_end = f0, f1
for o in bpy.context.view_layer.objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = arm
arm.select_set(True)
bpy.ops.export_anim.bvh(filepath=dst, frame_start=f0, frame_end=f1, root_transform_only=True, rotate_mode='NATIVE')
fps = sc.render.fps / sc.render.fps_base
print('ANIM2BVH ' + json.dumps(dict(bones=len(arm.data.bones), frames=f1 - f0 + 1, fps=fps, action=act.name)))
