// Rigged meshes (GLB) driven by a clip's joints. Port of the Animation Codec viewer's rig code.
//
// A clip's joints are matched to the mesh's bones by name. The clip's rest skeleton (all rotations zero) is fitted to the
// bones' bind-pose positions with a similarity  b ~ s R a + t  (R one of the 24 axis-aligned rotations: rigs disagree on
// axes and units). Per frame, bone i (joint j) gets the world transform
//     position  s R p_j + t        rotation  R q_j R^-1 q_bind(i)
// where p_j, q_j are the joint's world position / rotation in clip space. Unmatched bones follow their parent rigidly.
import * as THREE from 'three';
import { clone as cloneSkinned } from 'three/addons/utils/SkeletonUtils.js';

export const sanitize = (n) => THREE.PropertyBinding.sanitizeNodeName(n).toLowerCase().replace(/^.*[:|]/, '');

function rotations24() {                               // proper signed permutation matrices (det +1)
  const out = [], perms = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
  for (const p of perms) for (let sg = 0; sg < 8; sg++) {
    const m = new THREE.Matrix3(), e = m.elements; e.fill(0);
    for (let r = 0; r < 3; r++) e[p[r] * 3 + r] = (sg >> r) & 1 ? -1 : 1;
    if (Math.abs(m.determinant() - 1) < 1e-6) out.push(m);
  }
  return out;
}
const ROT24 = rotations24();

export function fitRest(A, B) {                        // A: clip rest positions, B: bone bind positions (same order)
  const n = A.length, ca = new THREE.Vector3(), cb = new THREE.Vector3();
  A.forEach(a => ca.add(a)); B.forEach(b => cb.add(b)); ca.divideScalar(n); cb.divideScalar(n);
  let best = null; const ra = new THREE.Vector3(), rb = new THREE.Vector3();
  for (const R of ROT24) {
    let num = 0, den = 0;
    for (let i = 0; i < n; i++) { ra.copy(A[i]).sub(ca).applyMatrix3(R); rb.copy(B[i]).sub(cb); num += ra.dot(rb); den += ra.lengthSq(); }
    const s = num / Math.max(den, 1e-12); if (s <= 0) continue;
    let res = 0;
    for (let i = 0; i < n; i++) { ra.copy(A[i]).sub(ca).applyMatrix3(R).multiplyScalar(s).add(cb); res += ra.distanceToSquared(B[i]); }
    if (!best || res < best.res) best = { R, s, res };
  }
  if (!best) return null;
  let spread = 0; B.forEach(b => { spread = Math.max(spread, b.distanceTo(cb)); });
  const Q = new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().setFromMatrix3(best.R));
  const T = cb.clone().sub(ca.clone().applyMatrix3(best.R).multiplyScalar(best.s));
  return { Q, Qi: Q.clone().invert(), s: best.s, T, rel: Math.sqrt(best.res / n) / Math.max(spread, 1e-9) };
}

// rest skeletons of a BVH clip, clip units, no rotation: translations = offset + frame-0 position channels, or the bare
// OFFSETs (roots keep frame 0). A rig's bind pose equals one of them; both are fitted and the better one is kept.
export function restSkeletons(meta, motion) {
  const J = meta.joint_names.length, idx = new Map(meta.joint_names.map((n, i) => [n, i]));
  const t0 = meta.offsets.map(o => [...o]), t1 = meta.offsets.map(o => [...o]);
  meta.channel_name.forEach((c, k) => {
    if (!c.endsWith('position')) return;
    const j = idx.get(meta.channel_joint[k]), a = 'XYZ'.indexOf(c[0]);
    t0[j][a] += motion[k];
    if (meta.parents[j] < 0) t1[j][a] += motion[k];
  });
  const fk = (t) => { const out = []; for (let j = 0; j < J; j++) { const p = meta.parents[j], v = new THREE.Vector3(...t[j]); if (p >= 0) v.add(out[p]); out.push(v); } return out; };
  return [fk(t0), fk(t1)];
}

// -> rig template {src, bones, bind, fit, jointOf, n} or {error}
export function prepareRig(gltf, meta, motion) {
  const src = gltf.scene; src.updateMatrixWorld(true);
  const bones = []; src.traverse(o => { if (o.isBone) bones.push(o); });
  if (!bones.length) return { error: 'the mesh has no bones' };
  const byName = new Map(bones.map((b, i) => [sanitize(b.name), i]));
  const jointOf = new Int32Array(bones.length).fill(-1), J = [], B = [];
  const named = meta.joint_names.filter(n => !n.endsWith('_End')).length;
  meta.joint_names.forEach((n, j) => {
    if (n.endsWith('_End')) return;
    const i = byName.get(sanitize(n));
    if (i !== undefined && jointOf[i] < 0) { jointOf[i] = j; J.push(j); B.push(new THREE.Vector3().setFromMatrixPosition(bones[i].matrixWorld)); }
  });
  if (J.length < Math.max(3, 0.6 * named)) return { error: `${J.length} of ${named} joints match a bone` };
  const fits = restSkeletons(meta, motion).map(R => fitRest(J.map(j => R[j]), B)).filter(Boolean);
  if (!fits.length) return { error: 'no rest-pose fit' };
  const fit = fits.reduce((a, b) => (b.rel < a.rel ? b : a));
  if (fit.rel > 0.03) return { error: `the rest pose does not match the clip (${(100 * fit.rel).toFixed(1)} %)` };
  const bind = bones.map(b => { const p = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3(); b.matrixWorld.decompose(p, q, sc); return { q, sc, M: b.matrixWorld.clone() }; });
  const parentOf = bones.map(b => bones.indexOf(b.parent));
  const relBind = bones.map((b, i) => parentOf[i] >= 0 ? bind[parentOf[i]].M.clone().invert().multiply(bind[i].M) : null);
  // which clip axis is the mesh's up (glTF +Y)
  const up = new THREE.Vector3(0, 1, 0).applyQuaternion(fit.Qi), a = [Math.abs(up.x), Math.abs(up.y), Math.abs(up.z)];
  const ax = a.indexOf(Math.max(...a)), upAxis = new THREE.Vector3(); upAxis.setComponent(ax, Math.sign(up.getComponent(ax)));
  return { src, bones, bind, parentOf, relBind, fit, jointOf, n: J.length, upAxis };
}

// one driven copy of the mesh: {scene, bones, W, flatMats, texMats, hasTex}
export function instantiate(rig, color, env) {
  const scene = cloneSkinned(rig.src);
  const G = new THREE.Matrix4().compose(rig.fit.T, rig.fit.Q, new THREE.Vector3(rig.fit.s, rig.fit.s, rig.fit.s)).invert();   // GLB -> clip space
  const holder = new THREE.Group(); holder.matrixAutoUpdate = false; holder.matrix.copy(G); holder.add(scene);
  const bones = []; let hasTex = false;
  scene.traverse(o => {
    if (o.isBone) { bones.push(o); o.matrixAutoUpdate = false; o.matrixWorldAutoUpdate = false; }
    if (o.isMesh) {
      o.frustumCulled = false; o.castShadow = true;
      const mats = Array.isArray(o.material) ? o.material : [o.material];
      // its own look worth showing: textures, vertex colours, or coloured materials (a plain white/grey material is not)
      if (mats.some(m => m.map || m.vertexColors || (m.color && (() => { const h = {}; m.color.getHSL(h); return h.s > 0.15 && h.l > 0.05 && h.l < 0.95; })()))) hasTex = true;
      // the environment only on PBR materials: an unlit Basic material multiplies its colour by it (black)
      const own = mats.map(m => { const c = m.clone(); if (env && c.isMeshStandardMaterial) { c.envMap = env; c.envMapIntensity = 0.6; } return c; });
      o.material = Array.isArray(o.material) ? own : own[0];
      o.userData.tex = o.material;
      const flat = new THREE.MeshStandardMaterial({ color, roughness: 0.6, metalness: 0, side: THREE.DoubleSide, envMap: env || null, envMapIntensity: 0.3 });
      o.userData.flat = Array.isArray(o.material) ? mats.map(() => flat) : flat;
    }
  });
  return { holder, scene, bones, W: bones.map(() => new THREE.Matrix4()), hasTex };
}

const _q = new THREE.Quaternion(), _q1 = new THREE.Quaternion(), _p = new THREE.Vector3(), _s = new THREE.Vector3();
// jointPos(j, outVec3) / jointQuat(j, outQuat): world position / rotation of clip joint j in clip space (unscaled, no up fix)
export function drive(rig, inst, jointPos, jointQuat) {
  if (rig.aim) return driveAim(rig, inst, jointPos);
  const { fit, jointOf, bind, parentOf, relBind } = rig;
  inst.scene.updateWorldMatrix(true, false);
  const base = inst.scene.matrixWorld;
  for (let i = 0; i < inst.bones.length; i++) {
    const j = jointOf[i], W = inst.W[i];
    if (j >= 0) {
      jointQuat(j, _q);
      _q1.copy(fit.Q).multiply(_q).multiply(fit.Qi).multiply(bind[i].q);
      jointPos(j, _p); _p.applyQuaternion(fit.Q).multiplyScalar(fit.s).add(fit.T);
      W.compose(_p, _q1, bind[i].sc);
    } else if (parentOf[i] >= 0) W.multiplyMatrices(inst.W[parentOf[i]], relBind[i]);
    else W.copy(bind[i].M);
    inst.bones[i].matrixWorld.multiplyMatrices(base, W);
  }
}

export function setTextured(inst, on) {
  inst.scene.traverse(o => { if (o.isMesh && o.userData.tex) o.material = on ? o.userData.tex : o.userData.flat; });
}
export function setFlatColor(inst, color) {
  inst.scene.traverse(o => { if (o.isMesh && o.userData.flat) (Array.isArray(o.userData.flat) ? o.userData.flat : [o.userData.flat]).forEach(m => m.color.copy(color)); });
}

// ---------------------------------------------------------------------------------------------------- aim retargeting
// A mesh whose skeleton differs from the clip's (other bone names, proportions or rest pose; e.g. the MANN dog clips on
// the AI4Animation wolf): `bone_map` {clip joint: mesh bone} from the example spec. Every mapped bone is aimed along its
// clip bone (towards the next mapped joint below it; two of them fix the twist), unmapped bones follow their parent, and
// the mesh keeps its own bone lengths. The clip's pose at one frame is fitted to the bind pose with a free similarity.
function horn(A, B) {                                    // rotation R maximising sum b . (R a) for centred point sets (Horn 1987)
  let Sxx = 0, Sxy = 0, Sxz = 0, Syx = 0, Syy = 0, Syz = 0, Szx = 0, Szy = 0, Szz = 0;
  for (let i = 0; i < A.length; i++) { const a = A[i], b = B[i];
    Sxx += a.x * b.x; Sxy += a.x * b.y; Sxz += a.x * b.z; Syx += a.y * b.x; Syy += a.y * b.y; Syz += a.y * b.z; Szx += a.z * b.x; Szy += a.z * b.y; Szz += a.z * b.z; }
  const N = [[Sxx + Syy + Szz, Syz - Szy, Szx - Sxz, Sxy - Syx], [Syz - Szy, Sxx - Syy - Szz, Sxy + Syx, Szx + Sxz],
             [Szx - Sxz, Sxy + Syx, -Sxx + Syy - Szz, Syz + Szy], [Sxy - Syx, Szx + Sxz, Syz + Szy, -Sxx - Syy + Szz]];
  const shift = Math.abs(Sxx) + Math.abs(Syy) + Math.abs(Szz) + Math.abs(Sxy) + Math.abs(Sxz) + Math.abs(Syx) + Math.abs(Syz) + Math.abs(Szx) + Math.abs(Szy) + 1e-9;
  let q = [1, 0.1, 0.1, 0.1];                            // power iteration on N + shift I: the top eigenvector is the rotation
  for (let it = 0; it < 200; it++) {
    const r = N.map((row, i) => row.reduce((s, v, j) => s + v * q[j], 0) + shift * q[i]), n = Math.hypot(...r);
    q = r.map(v => v / n);
  }
  return new THREE.Quaternion(q[1], q[2], q[3], q[0]).normalize();
}

export function prepareAimRig(gltf, meta, boneMap) {
  const src = gltf.scene; src.updateMatrixWorld(true);
  const bones = []; src.traverse(o => { if (o.isBone) bones.push(o); });
  const byName = new Map(bones.map((b, i) => [sanitize(b.name), i]));
  const jointOf = new Int32Array(bones.length).fill(-1), jIdx = new Map(meta.joint_names.map((n, j) => [n, j]));
  for (const [jn, bn] of Object.entries(boneMap)) {
    const i = byName.get(sanitize(bn)), j = jIdx.get(jn);
    if (i !== undefined && j !== undefined) jointOf[i] = j;
  }
  const n = [...jointOf].filter(j => j >= 0).length;
  if (n < 4) return { error: `bone_map: only ${n} bones found in the mesh` };
  const bind = bones.map(b => { const p = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3(); b.matrixWorld.decompose(p, q, sc); return { p, q, sc, M: b.matrixWorld.clone() }; });
  const parentOf = bones.map(b => bones.indexOf(b.parent));
  const relBind = bones.map((b, i) => parentOf[i] >= 0 ? bind[parentOf[i]].M.clone().invert().multiply(bind[i].M) : null);
  const aims = bones.map((b, i) => {                     // the nearest mapped bones below each mapped bone (aim targets)
    if (jointOf[i] < 0) return [];
    const out = [], walk = (k) => { for (let c = 0; c < bones.length; c++) if (parentOf[c] === k) { if (jointOf[c] >= 0) out.push(c); else walk(c); } };
    walk(i); return out.slice(0, 2);
  });
  return { aim: true, src, bones, bind, parentOf, relBind, jointOf, aims, n };
}

// the similarity clip -> mesh bind space from one clip pose (jointPos(j, out) in clip space); sets fit + upAxis
export function fitAimRig(rig, jointPos) {
  const A = [], B = [];
  rig.jointOf.forEach((j, i) => { if (j >= 0) { A.push(jointPos(j, new THREE.Vector3())); B.push(rig.bind[i].p.clone()); } });
  const ca = A.reduce((s, v) => s.add(v), new THREE.Vector3()).divideScalar(A.length), cb = B.reduce((s, v) => s.add(v), new THREE.Vector3()).divideScalar(B.length);
  const a0 = A.map(v => v.clone().sub(ca)), b0 = B.map(v => v.clone().sub(cb));
  const Q = horn(a0, b0);
  let num = 0, den = 0; a0.forEach((a, k) => { const r = a.clone().applyQuaternion(Q); num += r.dot(b0[k]); den += r.lengthSq(); });
  const s = num / Math.max(den, 1e-12), T = cb.clone().sub(ca.clone().applyQuaternion(Q).multiplyScalar(s));
  rig.fit = { Q, Qi: Q.clone().invert(), s, T };
  const up = new THREE.Vector3(0, 1, 0).applyQuaternion(rig.fit.Qi), c = [Math.abs(up.x), Math.abs(up.y), Math.abs(up.z)], ax = c.indexOf(Math.max(...c));
  rig.upAxis = new THREE.Vector3(); rig.upAxis.setComponent(ax, Math.sign(up.getComponent(ax)));
}

const _f1 = new THREE.Matrix4(), _f2 = new THREE.Matrix4(), _d1 = new THREE.Vector3(), _d2 = new THREE.Vector3(), _b1 = new THREE.Vector3(), _b2 = new THREE.Vector3();
const _rc = new THREE.Quaternion(), _ri = new THREE.Quaternion(), _pp = new THREE.Vector3(), _pq = new THREE.Quaternion(), _ps = new THREE.Vector3();
function frame(u, v, out) {                              // rotation whose x axis is u, xy plane contains v
  const e1 = u.clone().normalize(), e3 = new THREE.Vector3().crossVectors(u, v).normalize(), e2 = new THREE.Vector3().crossVectors(e3, e1);
  return out.makeBasis(e1, e2, e3);
}
function driveAim(rig, inst, jointPos) {
  const { fit, jointOf, bind, parentOf, relBind, aims } = rig;
  inst.scene.updateWorldMatrix(true, false);
  const base = inst.scene.matrixWorld, P = (j, out) => jointPos(j, out).applyQuaternion(fit.Q).multiplyScalar(fit.s).add(fit.T);
  const rot = inst.rot || (inst.rot = bind.map(() => new THREE.Quaternion()));
  for (let i = 0; i < inst.bones.length; i++) {
    const p = parentOf[i], j = jointOf[i], W = inst.W[i];
    // rotation carried down from the parent (its change since the bind pose)
    _rc.copy(bind[i].q); if (p >= 0) _rc.premultiply(_ri.copy(bind[p].q).invert()).premultiply(rot[p]);
    if (j >= 0 && aims[i].length) {
      const c1 = jointOf[aims[i][0]];
      P(c1, _d1).sub(P(j, _pp)); _b1.subVectors(bind[aims[i][0]].p, bind[i].p);
      if (aims[i].length > 1) {                          // two targets: the full rotation (twist included)
        const c2 = jointOf[aims[i][1]];
        P(c2, _d2).sub(P(j, _pp)); _b2.subVectors(bind[aims[i][1]].p, bind[i].p);
        frame(_d1, _d2, _f1); frame(_b1, _b2, _f2);
        rot[i].setFromRotationMatrix(_f1.multiply(_f2.invert())).multiply(bind[i].q);
      } else {                                           // one target: swing the carried rotation onto it
        _b1.applyQuaternion(_ri.copy(_rc).multiply(_pq.copy(bind[i].q).invert()));
        rot[i].setFromUnitVectors(_b1.normalize(), _d1.normalize()).multiply(_rc);
      }
    } else rot[i].copy(_rc);
    if (p >= 0) { _f1.multiplyMatrices(inst.W[p], relBind[i]); _pp.setFromMatrixPosition(_f1); }
    else if (j >= 0) P(j, _pp);
    else _pp.copy(bind[i].p);
    W.compose(_pp, rot[i], bind[i].sc);
    inst.bones[i].matrixWorld.multiplyMatrices(base, W);
  }
}
