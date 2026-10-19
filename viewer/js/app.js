// Motion Viewer: example clips of every dataset (static mode, viewer/examples/manifest.json) or a whole local motion
// vault (local mode, `python -m tools.vault.server`: the page finds api/catalog and lists every clip).
// Left: datasets / clips. Right: three.js player (skeleton, capsules, SMPL bodies, rigged GLB meshes with textures).
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import * as RIG from './rig.js';

const $ = (s) => document.querySelector(s);
const fmt = (n) => n >= 1e9 ? (n / 1e9).toFixed(2) + ' GB' : n >= 1e6 ? (n / 1e6).toFixed(1) + ' MB' : (n / 1e3).toFixed(0) + ' kB';
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmtH = (h) => h == null ? '–' : (h >= 100 ? h.toFixed(0) : h >= 10 ? h.toFixed(1) : h >= 1 ? h.toFixed(1) : h.toFixed(2)) + ' h';
const fmtN = (n) => n == null ? '–' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e4 ? (n / 1e3).toFixed(0) + 'k' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'k' : String(n);
const MAXSEL = 6;
const PARAMS = new URLSearchParams(location.search);
const THUMB = PARAMS.get('thumb');                     // thumbnail mode: render one example, no UI (tools/examples/thumbs.py)
if (THUMB) $('#app').classList.add('thumb');
if (PARAMS.get('theme')) document.documentElement.dataset.theme = PARAMS.get('theme');

// ------------------------------------------------------------------ options (remembered per browser)
const DEF = { skeleton: true, joints: false, ends: false, capsules: true, wire: false, axes: false, mesh: true, tex: true,
              loop: true, inplace: false, onfloor: true, track: true, radius: 0.025, spacing: -1, trail: true, trailLen: 3 };
const OPT_KEY = 'aad-viewer-opts-v2';
let opt = { ...DEF };
try { Object.assign(opt, JSON.parse(localStorage.getItem(OPT_KEY) || '{}')); } catch (e) { /* private mode */ }
if (THUMB) Object.assign(opt, { skeleton: true, joints: false, ends: false, capsules: true, wire: false, axes: false, mesh: true, tex: true, inplace: false, trail: false, track: true });
const saveOpt = () => { if (THUMB) return; try { localStorage.setItem(OPT_KEY, JSON.stringify(opt)); } catch (e) { /* ignore */ } };

// ------------------------------------------------------------------ data sources
// static: examples/<part>.json + .bin (+ .smpl.bin, meshes/<sha>.glb); api: the local vault server
let MODE = 'static', MAN = null, DS = [], EX = new Map(), byDs = new Map();
const SUBJ = new Map();
async function boot() {
  let api = null;
  if (!THUMB) try { const r = await fetch('api/catalog'); if (r.ok && (r.headers.get('content-type') || '').includes('json')) api = await r.json(); } catch (e) { /* static */ }
  if (api) {
    MODE = 'api';
    DS = api.datasets.map(d => ({ id: d.name, name: d.name, examples: d.clips.map(c => ({ ...c, id: c.id, label: c.name, parts: [c.id], dataset: d.name })) }));
    $('#tagline').innerHTML = `Local vault <b>${esc(api.root || '')}</b>: every clip of every dataset.`;
    $('#tabs').style.display = 'none';
  } else {
    MAN = await (await fetch('examples/manifest.json')).json();
    DS = MAN.datasets; MAN.subjects.forEach(s => SUBJ.set(s.id, s));
    $('#hint').textContent = 'click a dataset, then an example · ⌘/ctrl/shift-click: compare (up to 6) · H: hide panels · space: pause';
  }
  for (const d of DS) { byDs.set(d.id, d); for (const e of d.examples) { e.dataset = d.id; EX.set(e.id, e); e._s = (e.label + ' ' + (e.desc || '') + ' ' + e.id).toLowerCase(); } }
  const counted = DS.filter(d => !d.derived_from && d.review?.verdict !== 'caution');     // as the README: above the quality bar
  const hours = counted.reduce((a, d) => a + (d.stats?.hours || 0), 0);
  $('#stats').textContent = MODE === 'api'
    ? `${EX.size} clips · ${DS.length} datasets · ${fmtH(DS.reduce((a, d) => a + d.examples.reduce((b, c) => b + (c.duration || 0), 0), 0) / 3600)}`
    : `${DS.filter(d => d.review?.verdict !== 'caution').length} datasets · ${fmtH(hours)} · ${EX.size} examples`;
  if (THUMB) { await setSelection([THUMB]); return; }
  const ids = location.hash.slice(1).split(',').map(decodeURIComponent).filter(i => EX.has(i)).slice(0, MAXSEL);
  buildTabs();
  if (ids.length) { ids.forEach(i => openKeys.add('ds:' + EX.get(i).dataset)); if (ids.every(i => poor(byDs.get(EX.get(i).dataset)))) tab = 'caution'; buildTabs(); setSelection(ids); }
  else if (MODE === 'static') { const first = (MAN.start && byDs.get(EX.get(MAN.start)?.dataset)) || DS.find(d => d.examples.length && !poor(d)); if (first) { openKeys.add('ds:' + first.id); setSelection([first.examples[0].id]); } }
  else draw();
}

async function loadPart(part) {
  if (MODE === 'api') {
    const q = encodeURIComponent(part);
    const [meta, buf] = await Promise.all([fetch('api/clip?id=' + q).then(r => r.json()), fetch('api/motion?id=' + q).then(r => r.arrayBuffer())]);
    return { meta, buf, meshBuf: meta.kind === 'smpl' ? await (await fetch('api/mesh?id=' + q)).arrayBuffer() : null };
  }
  const [meta, buf] = await Promise.all([fetch(`examples/${part}.json`).then(r => r.json()), fetch(`examples/${part}.bin`).then(r => r.arrayBuffer())]);
  return { meta, buf, meshBuf: meta.kind === 'smpl' ? await (await fetch(`examples/${part}.smpl.bin`)).arrayBuffer() : null,
           propsBuf: meta.props ? await (await fetch(`examples/${part}.props.bin`)).arrayBuffer() : null };
}
function parseSmplMesh(ab) {                           // see tools/vault/server.py smpl_mesh() for the layout
  const hl = new DataView(ab).getUint32(0, true);
  const h = JSON.parse(new TextDecoder().decode(new Uint8Array(ab, 4, hl))), { V, K, F } = h; let o = 4 + hl;
  const verts = new Float32Array(ab, o, V * 3); o += V * 12;
  const widx = new Uint8Array(ab, o, V * K); o += (V * K + 3) & ~3;
  const wval = new Float32Array(ab, o, V * K); o += V * K * 4;
  return { V, K, F, verts, widx, wval, faces: new Uint32Array(ab, o, F * 3) };
}
const draco = new DRACOLoader().setDecoderPath('https://cdn.jsdelivr.net/npm/three@0.169.0/examples/jsm/libs/draco/gltf/');
const gltfLoader = new GLTFLoader().setDRACOLoader(draco);
const gltfCache = new Map();
const loadGltf = (url) => { if (!gltfCache.has(url)) gltfCache.set(url, gltfLoader.loadAsync(url)); return gltfCache.get(url); };

const dataCache = new Map();
async function loadExample(id) {                        // -> [{meta, motion, mesh, rig}] one per performer
  if (dataCache.has(id)) return dataCache.get(id);
  const ex = EX.get(id);
  const parts = await Promise.all(ex.parts.map(loadPart));
  const out = [];
  for (const { meta, buf, meshBuf, propsBuf } of parts) {
    const d = { meta, motion: new Float32Array(buf), mesh: meshBuf ? parseSmplMesh(meshBuf) : null, rig: null, props: null };
    if (propsBuf) {                                     // objects the performer handles: meshes + a 4x4 per frame, in the clip's space
      try { d.props = { gltf: await loadGltf('examples/' + meta.props.mesh), names: meta.props.names, mats: new Float32Array(propsBuf) }; }
      catch (e) { console.error('props failed to load', e); }
    }
    if (meta.mesh && meta.mesh !== 'smpl' && meta.kind === 'bvh') {
      try { const g = await loadGltf('examples/' + meta.mesh); d.rig = meta.bone_map ? RIG.prepareAimRig(g, meta, meta.bone_map) : RIG.prepareRig(g, meta, d.motion); }
      catch (e) { d.rig = { error: 'mesh failed to load: ' + e.message }; console.error(e); }
    }
    out.push(d);
  }
  dataCache.set(id, out);
  if (dataCache.size > 16) dataCache.delete(dataCache.keys().next().value);
  return out;
}

// ------------------------------------------------------------------ list (left)
let sel = [], tab = 'all';
// datasets whose quality fell short of our bar leave their subject and get a group (and tab) of their own
const CAUTION = { id: 'caution', name: 'Use with caution', description: 'motion quality fell short when we inspected it: read the reason before using it' };
const poor = (d) => d.review?.verdict === 'caution';
const groupOf = (d) => (poor(d) ? 'caution' : d.subject);
// tabs across subjects: a dataset keeps its subject and also shows here (caution ones included, marked)
const VIEWS = [{ id: 'multi', name: 'Multi-person', description: 'takes with two or more performers moving together', has: (d) => d.examples.some(e => e.parts.length > 1) }];
const inSection = (s, d) => (s.has ? s.has(d) : groupOf(d) === s.id);
const openKeys = new Set(), lim = new Map(), colorSlot = new Map();
const ROWS = 400;
const swatch = (id) => colorSlot.has(id) ? `background:var(--c${colorSlot.get(id)})` : '';
function buildTabs() {
  if (MODE !== 'static') return;
  const n = (s) => DS.filter(d => inSection(s, d)).length;
  const tabs = [['all', 'All', DS.filter(d => !poor(d)).length], ...[...MAN.subjects, ...VIEWS, CAUTION].filter(s => n(s)).map(s => [s.id, s.name, n(s)])];
  $('#tabs').innerHTML = tabs.map(([k, l, c]) => `<button data-tab="${k}" class="${k === tab ? 'on' : ''}">${esc(l)} <span style="opacity:.6">${c}</span></button>`).join('');
}
$('#tabs').addEventListener('click', (e) => { const b = e.target.closest('[data-tab]'); if (!b) return; tab = b.dataset.tab; buildTabs(); draw(); });

function licenceLine(d) {
  const l = d.license || {}, c = l.commercial === true ? '<span class="yes">commercial ok</span>' : l.commercial === false ? '<span class="no">non-commercial</span>' : 'commercial use unclear';
  return `${l.url ? `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.name)}</a>` : esc(l.name || '?')} · ${c}`;
}
function infoBlock(d) {
  const s = d.stats || {}, L = d.links || {}, subj = SUBJ.get(d.subject)?.name || d.subject;
  const cname = (k) => MAN.content.find(f => f.id === k)?.name || k, c = d.content || 'general';
  const foc = typeof c === 'string' ? cname(c) : Object.entries(c).map(([k, v]) => `${cname(k).toLowerCase()} ${Math.round(100 * v)}%`).join(', ');
  const kv = [['size', [s.hours != null ? fmtH(s.hours) : null, s.clips != null ? fmtN(s.clips) + ' clips' : null, s.subjects ? s.subjects + ' subjects' : null].filter(Boolean).join(' · ') || '–'],
              ['kind', `${esc(subj)} · ${esc(foc)}`], ['data', esc([(d.representation || []).join(', '), d.skeleton?.joints ? d.skeleton.joints + ' joints' : '', d.fps ? d.fps + ' fps' : ''].filter(Boolean).join(' · '))],
              ['licence', licenceLine(d)], ['access', esc(d.access || '–')]];
  const links = Object.entries(L).map(([k, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(k)}</a>`).join('');
  return `<div class="info"><div class="full">${esc(d.full_name || d.name)}${d.year ? ` (${d.year})` : ''}</div>` +
    (d.good_for ? `<div class="note" style="margin-top:4px">${esc(d.good_for)}</div>` : '') +
    `<div class="kv">${kv.map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('')}</div>` +
    (links ? `<div class="links">${links}</div>` : '') +
    reviewBlock(d) +
    (d.derived_from ? `<div class="note">derived from ${d.derived_from.map(x => esc(byDs.get(x)?.name || x)).join(', ')} (not counted twice in the totals)</div>` : '') +
    (d.examples_note ? `<div class="note">${esc(d.examples_note)}</div>` : '') +
    cards(d.examples) + '</div>';
}
function reviewBlock(d) {
  const r = d.review; if (!r) return '';
  const v = MAN.review_verdicts.find(x => x.id === r.verdict), iss = (r.issues || []).map(i => MAN.review_issues.find(x => x.id === i)?.name || i);
  return `<div class="note review ${esc(r.verdict)}"><b>${esc(v?.mark || '')} ${esc(v?.name || r.verdict)}</b>${iss.length ? ' — ' + esc(iss.join(', ').toLowerCase()) : ''}${r.note ? `<br>${esc(r.note)}` : ''}</div>`;
}
const BODY = { smpl: 'SMPL', smplh: 'SMPL-H', smplx: 'SMPL-X' };
const smplBadge = (d) => { const b = (d.representation || []).filter(r => BODY[r]).map(r => BODY[r]); return b.length ? ` <span class="badge" title="ships ${b.join(' / ')} body-model parameters">${b[b.length - 1]}</span>` : ''; };
const mark = (d) => d.review ? (MAN.review_verdicts.find(x => x.id === d.review.verdict)?.mark || '') : '';
function cards(exs) {
  if (!exs.length) return '<div class="note">no examples baked yet</div>';
  return '<div class="cards">' + exs.map(e => `<button class="card${sel.includes(e.id) ? ' sel' : ''}" data-id="${esc(e.id)}" title="${esc(e.label + (e.desc ? ' — ' + e.desc : ''))}">` +
    `<img loading="lazy" src="examples/${esc(e.thumb)}" alt="" onerror="this.outerHTML='<div class=ph>${esc(e.kind)}</div>'">` +
    `<span class="chk"></span><span class="t"><span>${esc(e.label)}</span></span></button>`).join('') + '</div>';
}

function draw() {
  if (THUMB) return;
  const q = $('#q').value.trim().toLowerCase(), box = $('#list'), keep = box.scrollTop, h = [];
  const row = (cls, name, count, attrs, chev) =>
    `<button class="row ${cls}" ${attrs}>${chev ? '<span class="chev">▸</span>' : cls.includes('clip') ? '<span class="chk"></span>' : ''}<span class="n">${name}</span>${count != null ? `<span class="c">${count}</span>` : ''}</button>`;
  const clipRow = (c, tag, extra = '') => row('clip' + extra + (sel.includes(c.id) ? ' sel' : ''), esc(c.label), tag ?? c.frames, `data-id="${esc(c.id)}"`);
  if (MODE === 'static') {
    const terms = q ? q.split(/\s+/) : [];
    const dsText = (d) => [d.id, d.name, d.full_name, d.subject, ...Object.keys(typeof d.content === 'object' ? d.content : { [d.content]: 1 }), ...(d.tags || [])].join(' ').toLowerCase();
    let any = false;
    for (const s of [...MAN.subjects, ...VIEWS, CAUTION]) {
      if (tab !== 'all' && tab !== s.id) continue;
      if (tab === 'all' && (s === CAUTION && !terms.length || s.has)) continue;   // 'All' = above the bar by subject; views are their own tabs
      const list = DS.filter(d => inSection(s, d)).map(d => {
        if (!terms.length) return [d, d.examples, false];
        const dsHit = terms.every(t => dsText(d).includes(t)), exHits = d.examples.filter(e => terms.every(t => e._s.includes(t)));
        return dsHit ? [d, d.examples, false] : exHits.length ? [d, exHits, true] : null;
      }).filter(Boolean);
      if (!list.length) continue;
      any = true;
      const hrs = list.filter(([d]) => !d.derived_from).reduce((a, [d]) => a + (d.stats?.hours || 0), 0);
      h.push(`<div class="lab">${esc(s.name)} · ${fmtH(hrs)}</div>` + (s === CAUTION || s.has ? `<div class="empty" style="padding:0 0 4px">${esc(s.description)}</div>` : ''));
      for (const [d, exs, forced] of list) {
        const key = 'ds:' + d.id, isOpen = openKeys.has(key) || forced;
        h.push(row('ds' + (isOpen ? ' open' : ''), (mark(d) ? `<span class="mk">${mark(d)}</span> ` : '') + esc(d.name) + smplBadge(d), d.stats?.hours != null ? fmtH(d.stats.hours) : fmtN(d.stats?.clips), `data-g="${esc(key)}"`, true));
        if (isOpen) h.push(infoBlock({ ...d, examples: exs }));
      }
    }
    if (!any) h.push('<div class="empty">nothing matches</div>');
  } else if (q) {
    const terms = q.split(/\s+/), hits = [...EX.values()].filter(c => terms.every(t => c._s.includes(t)));
    h.push(`<div class="lab">${hits.length} match${hits.length === 1 ? '' : 'es'}</div>`);
    hits.slice(0, 300).forEach(c => h.push(clipRow(c, esc((c.collection || c.dataset).split('/').pop()))));
    if (hits.length > 300) h.push('<div class="empty">… refine the search to see the rest</div>');
    if (!hits.length) h.push('<div class="empty">nothing matches</div>');
  } else {
    for (const d of DS) {                               // local vault: dataset > collection > group > clip, paged
      const dsKey = 'ds:' + d.id, dsOpen = openKeys.has(dsKey);
      h.push(row('ds' + (dsOpen ? ' open' : ''), esc(d.name), d.examples.length, `data-g="${esc(dsKey)}"`, true));
      if (!dsOpen) continue;
      const cols = new Map();
      for (const c of d.examples) { const k = c.collection || ''; if (!cols.has(k)) cols.set(k, new Map()); const g = cols.get(k); if (!g.has(c.group)) g.set(c.group, []); g.get(c.group).push(c); }
      const groupRows = (col, groups, colKey) => {
        const limit = lim.get(colKey) || ROWS; let shown = 0, left = 0;
        for (const [g, cs] of groups) {
          if (shown >= limit) { left += cs.length; continue; }
          if (cs.length === 1) { h.push(clipRow(cs[0], undefined, ' g1')); shown++; continue; }
          const key = d.id + '|' + col + '|' + g, isOpen = openKeys.has(key);
          h.push(row('grp' + (isOpen ? ' open' : ''), esc(g), cs.length, `data-g="${esc(key)}"`, true)); shown++;
          if (isOpen) cs.forEach(c => h.push(clipRow(c)));
        }
        if (left) h.push(`<button class="row more" data-more="${esc(colKey)}"><span class="n">show ${Math.min(ROWS, left)} more</span><span class="c">${left} left</span></button>`);
      };
      const rootGroups = cols.get('');
      if (rootGroups) {
        const n = [...rootGroups.values()].reduce((a, cs) => a + cs.length, 0);
        if (n <= 50) for (const cs of rootGroups.values()) cs.forEach(c => h.push(clipRow(c, undefined, ' top')));
        else groupRows('', rootGroups, 'col:' + d.id + '|');
      }
      for (const [col, groups] of cols) {
        if (col === '') continue;
        const colKey = 'col:' + d.id + '|' + col, colOpen = openKeys.has(colKey);
        h.push(row('col' + (colOpen ? ' open' : ''), esc(col), [...groups.values()].reduce((a, cs) => a + cs.length, 0), `data-g="${esc(colKey)}"`, true));
        if (colOpen) groupRows(col, groups, colKey);
      }
    }
  }
  box.innerHTML = h.join('');
  box.scrollTop = keep;
  box.querySelectorAll('.sel').forEach(r => { const c = r.querySelector('.chk'); if (c) c.style.cssText = swatch(r.dataset.id); });
  if (!box._seen) { const s = box.querySelector('.sel'); if (s) { s.scrollIntoView({ block: 'center' }); box._seen = true; } }
}
$('#list').addEventListener('click', (e) => {
  if (e.target.closest('a')) return;
  const b = e.target.closest('.row, .card'); if (!b) return;
  if (b.dataset.more) { lim.set(b.dataset.more, (lim.get(b.dataset.more) || ROWS) + ROWS); draw(); return; }
  if (b.dataset.g) {
    const was = openKeys.has(b.dataset.g); was ? openKeys.delete(b.dataset.g) : openKeys.add(b.dataset.g); draw();
    const d = MODE === 'static' && !was && byDs.get(b.dataset.g.slice(3));      // opening a dataset plays its first example
    if (d && d.examples.length && !sel.some(i => EX.get(i).dataset === d.id)) setSelection([d.examples[0].id]);
    return;
  }
  const id = b.dataset.id; if (!id) return;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.target.classList.contains('chk')) {
    if (sel.includes(id)) { if (sel.length > 1) setSelection(sel.filter(x => x !== id)); }
    else if (sel.length < MAXSEL) setSelection([...sel, id]);
  } else setSelection([id]);
});
$('#q').addEventListener('input', draw);
addEventListener('keydown', (e) => {
  if (e.target.id === 'q') return;
  if (e.key === 'h' || e.key === 'H') $('#app').classList.toggle('nohud');
  if (e.code === 'Space') { e.preventDefault(); togglePlay(); }
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'ArrowLeft' || e.key === 'ArrowRight') && sel.length) {
    const vis = [...document.querySelectorAll('#list .row.clip, #list .card')].map(b => b.dataset.id);
    const fwd = e.key === 'ArrowDown' || e.key === 'ArrowRight';
    const n = vis[vis.indexOf(sel[sel.length - 1]) + (fwd ? 1 : -1)];
    if (n) { e.preventDefault(); setSelection([n]); document.querySelector(`#list [data-id="${CSS.escape(n)}"]`)?.scrollIntoView({ block: 'nearest' }); }
  }
});

// ------------------------------------------------------------------ scene
const view = $('#view');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: !!THUMB });
renderer.setPixelRatio(THUMB ? 1 : Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
view.prepend(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.05, 600);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = !THUMB; controls.dampingFactor = 0.12;
const hemi = new THREE.HemisphereLight(0xffffff, 0x9a9a9a, 1.1); scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffffff, 1.5);
sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); sun.shadow.bias = -0.0004; sun.shadow.radius = 3;
Object.assign(sun.shadow.camera, { left: -9, right: 9, top: 9, bottom: -9, near: 0.5, far: 40 });
scene.add(sun, sun.target);
// soft studio reflections for the textured / PBR materials of rigged meshes only (a scene-wide environment overrides every
// material's envMapIntensity and washed the light floor out to white)
const ENV = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
const axes = new THREE.AxesHelper(1); scene.add(axes); axes.visible = !THUMB;
let gridLines, checker, checkerTex;
const GROUND = 120;
function makeGround() {
  const n = 60, pts = [];
  for (let i = -n; i <= n; i++) pts.push(-n, 0, i, n, 0, i, i, 0, -n, i, 0, n);
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3));
  gridLines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0x888888 })); gridLines.visible = false; scene.add(gridLines);
  checkerTex = new THREE.CanvasTexture(document.createElement('canvas'));
  checkerTex.wrapS = checkerTex.wrapT = THREE.RepeatWrapping; checkerTex.magFilter = THREE.NearestFilter; checkerTex.minFilter = THREE.NearestFilter;
  checkerTex.colorSpace = THREE.SRGBColorSpace; checkerTex.repeat.set(GROUND / 2, GROUND / 2);
  checker = new THREE.Mesh(new THREE.PlaneGeometry(GROUND, GROUND).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ map: checkerTex, roughness: 1, metalness: 0 }));
  checker.receiveShadow = true; checker.position.y = -0.002; scene.add(checker);
}
const palette = () => [0, 1, 2, 3, 4, 5].map(i => new THREE.Color(css('--c' + i)));
function applyTheme() {
  const bg = new THREE.Color(css('--bg')); scene.background = bg; scene.fog = new THREE.Fog(bg, 14, 70);
  const cv = checkerTex.image; cv.width = cv.height = 2; const x = cv.getContext('2d');
  x.fillStyle = css('--gnd-a'); x.fillRect(0, 0, 2, 2); x.fillStyle = css('--gnd-b'); x.fillRect(0, 0, 1, 1); x.fillRect(1, 1, 1, 1);
  checkerTex.needsUpdate = true;
  gridLines.material.color = new THREE.Color(css('--line2'));
  const pal = palette(); P.forEach(p => recolor(p, pal));
}
makeGround();
window.__viewer = { scene, camera, renderer, get players() { return P; }, select: (ids) => setSelection(ids) };      // for debugging from the console
function resize() { const w = view.clientWidth, h = view.clientHeight; if (!w || !h) return; renderer.setSize(w, h); camera.aspect = w / h; camera.updateProjectionMatrix(); }
new ResizeObserver(resize).observe(view);

// ------------------------------------------------------------------ players (one per performer of each selected example)
let P = [];
const AXV = { X: new THREE.Vector3(1, 0, 0), Y: new THREE.Vector3(0, 1, 0), Z: new THREE.Vector3(0, 0, 1) };
const _q = new THREE.Quaternion(), _q2 = new THREE.Quaternion(), _m = new THREE.Matrix4(), _p = new THREE.Vector3(), _s = new THREE.Vector3(1, 1, 1);
const _a = new THREE.Vector3(), _b = new THREE.Vector3(), _d = new THREE.Vector3(), _mid = new THREE.Vector3(), UP = new THREE.Vector3(0, 1, 0);
const cylGeo = new THREE.CylinderGeometry(1, 1, 1, 14, 1, true), sphGeo = new THREE.SphereGeometry(1, 16, 10);
const ringGeo = new THREE.RingGeometry(0.055, 0.085, 40).rotateX(-Math.PI / 2);

function plan(meta) {
  const J = meta.joint_names.length, pl = [], idx = new Map(meta.joint_names.map((n, i) => [n, i]));
  for (let j = 0; j < J; j++) pl.push({ pos: [-1, -1, -1], rot: [] });
  meta.channel_name.forEach((c, k) => {
    const j = idx.get(meta.channel_joint[k]), kind = c.slice(1);
    if (kind === 'position') pl[j].pos['XYZ'.indexOf(c[0])] = k; else if (kind === 'rotation') pl[j].rot.push([c[0], k]);
  });
  return pl;
}
function localMat(p, j, base, out) {
  if (p.smpl) {                                         // [trans(3), axis-angle(3 per joint)]; rest offsets from the shaped model
    const off = p.meta.offsets[j], m = p.motion, o = base + 3 + 3 * j, x = m[o], y = m[o + 1], z = m[o + 2], a = Math.hypot(x, y, z);
    _p.set(off[0] + (j === 0 ? m[base] : 0), off[1] + (j === 0 ? m[base + 1] : 0), off[2] + (j === 0 ? m[base + 2] : 0));
    if (a < 1e-9) _q.identity(); else { _a.set(x / a, y / a, z / a); _q.setFromAxisAngle(_a, a); }
    return out.compose(_p, _q, _s);
  }
  const pl = p.plan[j], off = p.meta.offsets[j], m = p.motion;
  _p.set(off[0] + (pl.pos[0] >= 0 ? m[base + pl.pos[0]] : 0), off[1] + (pl.pos[1] >= 0 ? m[base + pl.pos[1]] : 0), off[2] + (pl.pos[2] >= 0 ? m[base + pl.pos[2]] : 0));
  _q.identity();
  for (const [ax, k] of pl.rot) { _q2.setFromAxisAngle(AXV[ax], m[base + k] * Math.PI / 180); _q.multiply(_q2); }
  return out.compose(_p, _q, _s);
}
function fk(p, f) {                                     // p.W: joint world matrices (up-fixed, unscaled); p.world: display positions
  const base = f * p.C, par = p.meta.parents, J = par.length, e = p.world;
  if (p.joints) {
    for (let j = 0; j < J; j++) { _p.set(p.motion[base + j * 3], p.motion[base + j * 3 + 1], p.motion[base + j * 3 + 2]).applyMatrix4(p.U);
      e[j * 3] = _p.x * p.scale; e[j * 3 + 1] = _p.y * p.scale - p.floor; e[j * 3 + 2] = _p.z * p.scale; }
    return;
  }
  for (let j = 0; j < J; j++) {
    localMat(p, j, base, _m);
    if (par[j] >= 0) p.W[j].multiplyMatrices(p.W[par[j]], _m); else p.W[j].multiplyMatrices(p.U, _m);
    const el = p.W[j].elements;
    e[j * 3] = el[12] * p.scale; e[j * 3 + 1] = el[13] * p.scale - p.floor; e[j * 3 + 2] = el[14] * p.scale;
  }
}
const _t1 = new THREE.Matrix4(), _t2 = new THREE.Matrix4(), _t3 = new THREE.Matrix4();
function jointTrack(p, j) {                             // display position of joint j at every frame (cached; ancestors only)
  p.tracks ||= new Map();
  if (p.tracks.has(j)) return p.tracks.get(j);
  const out = new Float32Array(p.T * 3);
  if (p.joints) {
    for (let f = 0; f < p.T; f++) { const b = f * p.C + j * 3; _p.set(p.motion[b], p.motion[b + 1], p.motion[b + 2]).applyMatrix4(p.U);
      out[f * 3] = _p.x * p.scale; out[f * 3 + 1] = _p.y * p.scale - p.floor; out[f * 3 + 2] = _p.z * p.scale; }
  } else {
    const chain = []; for (let k = j; k >= 0; k = p.meta.parents[k]) chain.unshift(k);
    for (let f = 0; f < p.T; f++) {
      _t1.copy(p.U);
      for (const k of chain) { localMat(p, k, f * p.C, _t3); _t2.multiplyMatrices(_t1, _t3); _t1.copy(_t2); }
      const el = _t1.elements; out[f * 3] = el[12] * p.scale; out[f * 3 + 1] = el[13] * p.scale - p.floor; out[f * 3 + 2] = el[14] * p.scale;
    }
  }
  p.tracks.set(j, out); return out;
}
function skin(p) {                                      // SMPL: linear blend skinning of the shaped template into p.vpos
  const M = p.mesh, W = p.W, J = W.length, A = p.Aarr, rest = p.meta.rest;
  for (let j = 0; j < J; j++) {
    const e = W[j].elements, rx = rest[j][0], ry = rest[j][1], rz = rest[j][2], o = j * 16;
    for (let k = 0; k < 12; k++) A[o + k] = e[k];
    A[o + 12] = e[12] - (e[0] * rx + e[4] * ry + e[8] * rz); A[o + 13] = e[13] - (e[1] * rx + e[5] * ry + e[9] * rz); A[o + 14] = e[14] - (e[2] * rx + e[6] * ry + e[10] * rz);
  }
  const vs = M.verts, wi = M.widx, wv = M.wval, K = M.K, out = p.vpos, fl = p.floor, sc = p.scale;
  for (let i = 0; i < M.V; i++) {
    const x = vs[i * 3], y = vs[i * 3 + 1], z = vs[i * 3 + 2]; let ox = 0, oy = 0, oz = 0;
    for (let k = 0; k < K; k++) {
      const w = wv[i * K + k]; if (w === 0) continue; const o = wi[i * K + k] * 16;
      ox += w * (A[o] * x + A[o + 4] * y + A[o + 8] * z + A[o + 12]); oy += w * (A[o + 1] * x + A[o + 5] * y + A[o + 9] * z + A[o + 13]); oz += w * (A[o + 2] * x + A[o + 6] * y + A[o + 10] * z + A[o + 14]);
    }
    out[i * 3] = ox * sc; out[i * 3 + 1] = oy * sc - fl; out[i * 3 + 2] = oz * sc;
  }
}
// rigged mesh: the clip's joint transforms in clip space (the rig fit is made there): undo the up fix of p.W
const _wq = new THREE.Quaternion(), _wp = new THREE.Vector3(), _ws = new THREE.Vector3();
function driveRig(p) {
  p.meshRoot.updateMatrixWorld(true);
  RIG.drive(p.rig, p.inst,
    (j, out) => out.setFromMatrixPosition(p.W[j]).applyQuaternion(p.Uqi),
    (j, out) => { p.W[j].decompose(_wp, _wq, _ws); return out.copy(p.Uqi).multiply(_wq); });
}

// the up axis: SMPL from pelvis->head, a rigged mesh from its bind pose (glTF +Y), Z-up BVH from the joint spread
// joints that are not part of the body (a root left at the origin while its child moves the body): neither drawn nor measured
function translationOnly(meta, motion) {
  const J = meta.joint_names.length, hide = new Uint8Array(J);
  if (meta.kind && meta.kind !== 'bvh') return hide;
  const C = meta.channel_name.length, T = Math.floor(motion.length / C), idx = new Map(meta.joint_names.map((n, i) => [n, i]));
  const bone = meta.offsets.map(o => Math.hypot(...o)).filter(x => x > 0).sort((x, y) => x - y), typical = bone[bone.length >> 1] || 1;
  const travels = new Uint8Array(J);                     // position channels that really move (more than a fifth of a typical bone)
  meta.channel_name.forEach((c, k) => {
    if (!c.endsWith('position')) return;
    let lo = Infinity, hi = -Infinity;
    for (let f = 0; f < T; f += Math.max(1, T >> 6)) { const v = motion[f * C + k]; lo = Math.min(lo, v); hi = Math.max(hi, v); }
    if (hi - lo > 0.2 * typical) travels[idx.get(meta.channel_joint[k])] = 1;
  });
  const kids = (j) => meta.joint_names.map((m, i) => i).filter(i => meta.parents[i] === j && !meta.joint_names[i].endsWith('_End'));
  for (let j = 0; j < J; j++) {
    if (meta.parents[j] >= 0) continue;
    if (kids(j).some(i => travels[i])) { hide[j] = 1; continue; }
    // exporter roots (GLTF_created_0_rootJoint, Armature, ...): a chain of zero-length joints, then one bone many times longer
    // than any other: the body sits far from the origin and that bone is not part of it
    const chain = [j];
    for (let c = j; ;) {
      const k = kids(c); if (k.length !== 1) break;
      const len = Math.hypot(...meta.offsets[k[0]]);
      if (len > 8 * typical) { chain.forEach(x => { hide[x] = 1; }); break; }
      if (len > 1e-6 * typical) break;
      chain.push(c = k[0]);
    }
  }
  return hide;
}
// the up axis. A rigged mesh knows it (glTF +Y); `up: z` in the example spec forces it; otherwise, for bodies with a head,
// it is where pelvis -> head points over the clip (only when that is clear: an animal's head points forward, not up)
function headJoint(names) {
  const low = names.map(n => n.toLowerCase().replace(/^.*[:|]/, ''));
  for (const re of [/^head$/, /(^|[^a-z])head$/, /head/, /neck/]) { const j = low.findIndex((n, i) => re.test(n) && !names[i].endsWith('_End') && !/end|top|site/.test(n)); if (j >= 0) return j; }
  return -1;
}
const AXES = [new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 1)];
const UPS = { '+y': [0, 1, 0], '-y': [0, -1, 0], '+z': [0, 0, 1], '-z': [0, 0, -1], '+x': [1, 0, 0], '-x': [-1, 0, 0] };
const upName = (v) => Object.keys(UPS).find(k => new THREE.Vector3(...UPS[k]).distanceTo(v) < 1e-6) || '?';
let upOverride = '';                                     // the 'up' selector: '' = as configured / detected
function setUp(p, v, how) { p.U.makeRotationFromQuaternion(new THREE.Quaternion().setFromUnitVectors(v.clone().normalize(), UP)); p.upLabel = upName(v) + ' ' + how; }
function autoUp(p) {
  const h = headJoint(p.meta.joint_names); if (h < 0) return;
  let r = h; while (p.meta.parents[r] >= 0 && !p.hide[p.meta.parents[r]]) r = p.meta.parents[r];
  const v = new THREE.Vector3(), w = p.world;
  for (let k = 0; k < 9; k++) { fk(p, Math.floor((p.T - 1) * k / 8)); v.x += w[h * 3] - w[r * 3]; v.y += w[h * 3 + 1] - w[r * 3 + 1]; v.z += w[h * 3 + 2] - w[r * 3 + 2]; }
  if (v.lengthSq() < 1e-12) return;
  v.normalize();
  const c = [Math.abs(v.x), Math.abs(v.y), Math.abs(v.z)], ax = c.indexOf(Math.max(...c));
  if (c[ax] < 0.75 || (ax === 1 && v.y > 0)) return;
  setUp(p, AXES[ax].clone().multiplyScalar(Math.sign(v.getComponent(ax))), '(detected)');
}
// autoscale: every clip is shown about 1.7 units tall (or long, for animals), measured over the whole clip; floor = lowest point
function measure(p, n = 17) {
  let lo = Infinity, ext = 0; const box = new THREE.Box3(), J = p.meta.joint_names.length;
  for (let k = 0; k < n; k++) {
    fk(p, Math.floor((p.T - 1) * k / (n - 1))); box.makeEmpty();
    for (let j = 0; j < J; j++) if (!p.hide[j]) box.expandByPoint(_a.fromArray(p.world, j * 3));
    const sz = box.getSize(_b); ext = Math.max(ext, sz.y, 0.6 * Math.max(sz.x, sz.z)); lo = Math.min(lo, box.min.y);
  }
  return { lo, ext };
}

function makePlayer(exId, data, slot, shared, part = 0) {
  const { meta, motion, mesh, rig } = data, J = meta.joint_names.length, smpl = meta.kind === 'smpl', joints = meta.kind === 'joints';
  const hasRig = rig && !rig.error;
  const p = { exId, meta, motion, mesh, smpl, joints, rig: hasRig ? rig : null, rigError: rig?.error, slot, part, props: data.props,
              C: smpl ? 3 + 3 * J : joints ? 3 * J : meta.channel_name.length, T: meta.frames, ft: meta.frame_time,
              plan: smpl || joints ? null : plan(meta), world: new Float32Array(J * 3), W: Array.from({ length: J }, () => new THREE.Matrix4()),
              U: new THREE.Matrix4(), scale: 1, floor: 0, isEnd: meta.joint_names.map(n => n.endsWith('_End')), hide: translationOnly(meta, motion),
              group: new THREE.Group(), frame: 0, vpos: smpl ? new Float32Array(mesh.V * 3) : null, Aarr: smpl ? new Float32Array(J * 16) : null };
  p.anchor = Math.max(0, p.hide.findIndex(h => !h));     // the first joint that moves with the body
  const subject = byDs.get(EX.get(exId)?.dataset)?.subject;
  if (hasRig && rig.aim && !rig.fit) {                  // retargeted mesh: fit the clip's mid pose to the bind pose first
    fk(p, Math.floor(p.T / 2)); RIG.fitAimRig(rig, (j, out) => out.setFromMatrixPosition(p.W[j]));
  }
  if (shared) { p.U.copy(shared.U); p.scale = shared.scale; p.floor = shared.floor; p.upLabel = shared.upLabel; }
  else {
    const want = upOverride || (meta.up ? (/^[+-]/.test(meta.up) ? meta.up : '+' + meta.up) : '');
    p.upLabel = '+y';
    if (UPS[want]) setUp(p, new THREE.Vector3(...UPS[want]), upOverride ? '(set)' : '(dataset)');
    else if (hasRig) setUp(p, rig.upAxis, '(mesh)');
    else if (!['animal', 'object', 'robot'].includes(subject)) autoUp(p);
    if (!smpl) {                                        // SMPL is in metres already
      const m = measure(p);
      p.scale = m.ext > 1e-6 ? 1.7 / m.ext : 0.01;
    }
  }
  p.Uqi = new THREE.Quaternion().setFromRotationMatrix(p.U).invert();
  fk(p, 0);
  scene.add(p.group); build(p);
  lowestPoints(p);
  return p;
}
// the lowest points of the whole clip, display units with the floor at the data's y = 0: joints, and the body where
// there is one (SMPL: up to ~120 frames skinned; a rigged mesh: its frame-0 margin below the joints, carried over)
function lowestPoints(p) {
  const J = p.meta.joint_names.length, keep = p.floor; p.floor = 0;
  const lowJ = () => { let lo = Infinity; for (let j = 0; j < J; j++) if (!p.hide[j]) lo = Math.min(lo, p.world[j * 3 + 1]); return lo; };
  let lo = Infinity;
  for (let f = 0; f < p.T; f++) { fk(p, f); lo = Math.min(lo, lowJ()); }
  p.lowJoints = lo; p.lowMesh = null;
  if (p.smpl) {
    let m = Infinity;
    for (let f = 0, st = Math.max(3, Math.ceil(p.T / 120)); f < p.T; f += st) { fk(p, f); skin(p); for (let i = 1; i < p.vpos.length; i += 3) m = Math.min(m, p.vpos[i]); }
    p.lowMesh = m;
  }
  if (p.rig) {
    fk(p, 0); p.meshRoot.position.y = 0; p.meshRoot.updateMatrixWorld(true); driveRig(p);
    const b = meshBox(p).min.y; if (isFinite(b)) p.lowMesh = lo + (b - lowJ());
  }
  p.floor = keep; fk(p, 0);
}
// on floor: the take's lowest point over the clip (capsule radius / mesh included) touches y = 0; off: the data's own y = 0
function applyFloor(g) {
  let lo = Infinity;
  for (const p of g) lo = Math.min(lo, meshOn(p) && p.lowMesh != null ? Math.min(p.lowMesh, p.lowJoints) : p.lowJoints - (opt.capsules ? opt.radius : 0));
  const f = opt.onfloor && isFinite(lo) ? lo : 0;
  for (const p of g) { if (p.floor !== f) p.tracks = null; p.floor = f; if (p.meshRoot) p.meshRoot.position.y = -f; if (p.propRoot) p.propRoot.position.y = -f; }
}
function meshBox(p) {
  const box = new THREE.Box3();
  p.inst.scene.traverse(o => { if (o.isSkinnedMesh) { o.computeBoundingBox(); box.union(o.boundingBox.clone().applyMatrix4(o.matrixWorld)); } });
  return box;
}
function build(p) {
  const J = p.meta.joint_names.length, par = p.meta.parents, col = slotColor(p);
  p.bones = []; for (let j = 0; j < J; j++) if (par[j] >= 0 && !p.hide[par[j]] && !p.hide[j]) p.bones.push(j);
  const mk = (geo, mat, n, shadow) => { const m = new THREE.InstancedMesh(geo, mat, n); m.frustumCulled = false; m.castShadow = shadow; p.group.add(m); return m; };
  const std = () => new THREE.MeshStandardMaterial({ color: col, roughness: 0.55, metalness: 0 });
  const wire = () => new THREE.MeshBasicMaterial({ color: 0x3a3a3a, wireframe: true });
  p.cyl = mk(cylGeo, std(), Math.max(1, p.bones.length), true); p.sph = mk(sphGeo, std(), J, true);
  p.cylW = mk(cylGeo, wire(), Math.max(1, p.bones.length), false); p.sphW = mk(sphGeo, wire(), J, false);
  p.cylW.instanceMatrix = p.cyl.instanceMatrix; p.sphW.instanceMatrix = p.sph.instanceMatrix;
  const lg = new THREE.BufferGeometry(); lg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(Math.max(1, p.bones.length) * 6), 3));
  p.lines = new THREE.LineSegments(lg, new THREE.LineBasicMaterial({ color: col })); p.lines.frustumCulled = false; p.group.add(p.lines);
  const pg = new THREE.BufferGeometry(); pg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(J * 3), 3));
  p.pts = new THREE.Points(pg, new THREE.PointsMaterial({ color: css('--ink'), size: 5, sizeAttenuation: false })); p.pts.frustumCulled = false; p.group.add(p.pts);
  const tg = new THREE.BufferGeometry(), tp = new Float32Array(J * 18), tc = new Float32Array(J * 18);
  for (let j = 0; j < J; j++) for (let a = 0; a < 3; a++) for (let k = 0; k < 2; k++) tc[j * 18 + a * 6 + k * 3 + a] = 1;
  tg.setAttribute('position', new THREE.BufferAttribute(tp, 3)); tg.setAttribute('color', new THREE.BufferAttribute(tc, 3));
  p.tf = new THREE.LineSegments(tg, new THREE.LineBasicMaterial({ vertexColors: true })); p.tf.frustumCulled = false; p.group.add(p.tf);
  if (p.smpl) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(p.vpos, 3).setUsage(THREE.DynamicDrawUsage)); g.setIndex(new THREE.BufferAttribute(p.mesh.faces, 1));
    p.meshObj = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: col, roughness: 0.6, metalness: 0, side: THREE.DoubleSide }));
    p.meshObj.frustumCulled = false; p.meshObj.castShadow = true; p.group.add(p.meshObj);
    p.meshWire = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0x3a3a3a, wireframe: true })); p.meshWire.frustumCulled = false; p.group.add(p.meshWire);
  }
  if (p.rig) {                                          // meshRoot = display transform (feet on 0, scale, up fix); holder = GLB -> clip space
    p.inst = RIG.instantiate(p.rig, col, ENV);
    p.meshRoot = new THREE.Group(); p.meshRoot.position.y = -p.floor; p.meshRoot.scale.setScalar(p.scale); p.meshRoot.quaternion.setFromRotationMatrix(p.U);
    p.meshRoot.add(p.inst.holder); p.group.add(p.meshRoot);
  }
  if (p.props) {                                        // propRoot = display transform; each prop's matrix = its pose in clip space
    p.propRoot = new THREE.Group(); p.propRoot.position.y = -p.floor; p.propRoot.scale.setScalar(p.scale); p.propRoot.quaternion.setFromRotationMatrix(p.U);
    p.propObjs = p.props.names.map(n => {
      const src = p.props.gltf.scene.getObjectByName(n) || p.props.gltf.scene.getObjectByName(n.replace(/[^\w-]/g, '_'));
      const o = src ? src.clone(true) : new THREE.Group();
      o.matrixAutoUpdate = false;
      o.traverse(m => { if (m.isMesh) { m.castShadow = true; m.frustumCulled = false; if (m.material?.isMeshStandardMaterial) { m.material = m.material.clone(); m.material.envMap = ENV; } } });
      p.propRoot.add(o); return o;
    });
    p.group.add(p.propRoot);
  }
  // the trajectory on the floor: a flat ribbon (WebGL lines are 1 px) fading into the background, and a ring under the joint now
  const MAXT = 500, trg = new THREE.BufferGeometry(), tix = [];
  trg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(MAXT * 6), 3)); trg.setAttribute('color', new THREE.BufferAttribute(new Float32Array(MAXT * 6), 3));
  for (let i = 0; i < MAXT - 1; i++) { const a = 2 * i; tix.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
  trg.setIndex(tix);
  p.trail = new THREE.Mesh(trg, new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide })); p.trail.frustumCulled = false; p.group.add(p.trail); p.maxTrail = MAXT;
  p.ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: col, side: THREE.DoubleSide })); p.ring.frustumCulled = false; p.group.add(p.ring);
}
function slotColor(p, base) {                           // the example's colour; further performers of a take a lighter shade
  const c = (base || new THREE.Color(css('--c' + p.slot))).clone();
  if (p.part) c.offsetHSL(0, -0.15, 0.18 * Math.min(2, p.part));
  return c;
}
function recolor(p, pal) {
  const c = slotColor(p, pal[p.slot]);
  [p.cyl, p.sph, p.meshObj, p.ring].forEach(m => m && m.material.color.copy(c)); p.lines.material.color.copy(c); p.pts.material.color = new THREE.Color(css('--ink'));
  if (p.inst) RIG.setFlatColor(p.inst, c);
}
function dispose(p) {
  scene.remove(p.group);
  p.group.traverse(o => { if (o.geometry && o.geometry !== cylGeo && o.geometry !== sphGeo && o.geometry !== ringGeo && !o.isSkinnedMesh) o.geometry.dispose(); });
}

// ------------------------------------------------------------------ per-frame drawing
const frameOf = (p, t) => Math.max(0, Math.min(p.T - 1, Math.floor(t / p.ft + 1e-6)));
const meshOn = (p) => opt.mesh && (p.smpl || p.rig);
function updatePlayer(p, t) {
  const f = p.frame = frameOf(p, t); fk(p, f);
  const w = p.world, par = p.meta.parents, J = par.length, showEnd = opt.ends;
  if (p.smpl && opt.mesh) { skin(p); const g = p.meshObj.geometry; g.attributes.position.needsUpdate = true; g.computeVertexNormals(); }
  if (p.rig && opt.mesh) driveRig(p);
  if (p.propObjs) { const n = p.propObjs.length; p.propObjs.forEach((o, k) => o.matrix.fromArray(p.props.mats, (f * n + k) * 16)); }
  const vis = (j) => showEnd || !p.isEnd[j];
  let n = 0; const lp = p.lines.geometry.attributes.position.array;
  for (const j of p.bones) { if (!vis(j)) continue; const a = par[j] * 3, b = j * 3; lp[n++] = w[a]; lp[n++] = w[a + 1]; lp[n++] = w[a + 2]; lp[n++] = w[b]; lp[n++] = w[b + 1]; lp[n++] = w[b + 2]; }
  p.lines.geometry.setDrawRange(0, n / 3); p.lines.geometry.attributes.position.needsUpdate = true;
  const pp = p.pts.geometry.attributes.position.array; let k = 0;
  for (let j = 0; j < J; j++) if (vis(j) && !p.hide[j]) { pp[k++] = w[j * 3]; pp[k++] = w[j * 3 + 1]; pp[k++] = w[j * 3 + 2]; }
  p.pts.geometry.setDrawRange(0, k / 3); p.pts.geometry.attributes.position.needsUpdate = true;
  if (opt.capsules && !meshOn(p)) {
    let nb = 0;
    for (const j of p.bones) {
      if (!vis(j)) continue;
      _a.fromArray(w, par[j] * 3); _b.fromArray(w, j * 3); _d.subVectors(_b, _a); const len = _d.length();
      if (len < 1e-6) continue;
      const r = Math.min(opt.radius, 0.45 * len);
      _q.setFromUnitVectors(UP, _d.multiplyScalar(1 / len)); _mid.addVectors(_a, _b).multiplyScalar(0.5); _p.set(r, len, r);
      _m.compose(_mid, _q, _p); p.cyl.setMatrixAt(nb++, _m);
    }
    p.cyl.count = p.cylW.count = nb; p.cyl.instanceMatrix.needsUpdate = true;
    let ns = 0;
    for (let j = 0; j < J; j++) { if (!vis(j) || p.isEnd[j] || p.hide[j]) continue; _a.fromArray(w, j * 3); _p.setScalar(opt.radius); _q.identity(); _m.compose(_a, _q, _p); p.sph.setMatrixAt(ns++, _m); }
    p.sph.count = p.sphW.count = ns; p.sph.instanceMatrix.needsUpdate = true;
  }
  if (opt.axes && !p.joints) {
    const tp = p.tf.geometry.attributes.position.array;
    for (let j = 0; j < J; j++) {
      const e = p.W[j].elements;
      for (let a = 0; a < 3; a++) { const o = j * 18 + a * 6; tp[o] = w[j * 3]; tp[o + 1] = w[j * 3 + 1]; tp[o + 2] = w[j * 3 + 2];
        tp[o + 3] = w[j * 3] + e[a * 4] * 0.1; tp[o + 4] = w[j * 3 + 1] + e[a * 4 + 1] * 0.1; tp[o + 5] = w[j * 3 + 2] + e[a * 4 + 2] * 0.1; }
    }
    p.tf.geometry.attributes.position.needsUpdate = true;
  }
  const L = opt.trailLen, tj = Math.max(0, p.meta.joint_names.indexOf(trailJoint));
  if (opt.trail) {
    const tr = jointTrack(p, tj), maxF = L >= TRAIL_ALL ? f : Math.round(L / p.ft), f0 = Math.max(0, f - maxF), cnt = f - f0 + 1;
    p.ring.position.set(tr[f * 3], 0.005, tr[f * 3 + 2]);
    const stride = Math.max(1, Math.ceil(cnt / (p.maxTrail - 1))), pos = p.trail.geometry.attributes.position.array, cl = p.trail.geometry.attributes.color.array;
    const bg = scene.background, c0 = new THREE.Color(css('--c' + p.slot)), hw = 0.012, idx = [];
    for (let g = f; g >= f0 && idx.length < p.maxTrail; g -= stride) idx.push(g);
    const m = L > 0 ? idx.length : 0;
    for (let i = 0; i < m; i++) {
      const g = idx[i], a0 = idx[Math.max(0, i - 1)], a1 = idx[Math.min(m - 1, i + 1)];
      let dx = tr[a0 * 3] - tr[a1 * 3], dz = tr[a0 * 3 + 2] - tr[a1 * 3 + 2]; const len = Math.hypot(dx, dz);
      if (len > 1e-9) { dx /= len; dz /= len; } else { dx = 1; dz = 0; }
      const x = tr[g * 3], z = tr[g * 3 + 2], nx = -dz * hw, nz = dx * hw, o = i * 6;
      pos[o] = x + nx; pos[o + 1] = 0.004; pos[o + 2] = z + nz; pos[o + 3] = x - nx; pos[o + 4] = 0.004; pos[o + 5] = z - nz;
      const a = Math.pow(1 - (f - g) / Math.max(1, f - f0 + 1), 1.2);
      for (const q of [o, o + 3]) { cl[q] = bg.r + (c0.r - bg.r) * a; cl[q + 1] = bg.g + (c0.g - bg.g) * a; cl[q + 2] = bg.b + (c0.b - bg.b) * a; }
    }
    p.trail.geometry.setDrawRange(0, Math.max(0, m - 1) * 6); p.trail.geometry.attributes.position.needsUpdate = true; p.trail.geometry.attributes.color.needsUpdate = true;
  }
}
function applyVisibility() {
  groups.forEach(applyFloor);
  P.forEach(p => {
    const mesh = meshOn(p);
    const caps = opt.capsules && !mesh;
    p.lines.visible = opt.skeleton && !caps && !(mesh && p.rig?.aim);   // a retargeted mesh has other proportions than the clip
    p.pts.visible = opt.joints && !mesh;
    p.cyl.visible = p.sph.visible = caps; p.cylW.visible = p.sphW.visible = caps && opt.wire;
    p.tf.visible = opt.axes && !p.joints; p.trail.visible = opt.trail && opt.trailLen > 0; p.ring.visible = opt.trail;
    if (p.smpl) { p.meshObj.visible = opt.mesh; p.meshWire.visible = opt.mesh && opt.wire; }
    if (p.rig) { p.meshRoot.visible = opt.mesh; RIG.setTextured(p.inst, opt.tex && p.inst.hasTex); }
  });
  $('#meshBtn').disabled = !P.some(p => p.smpl || p.rig);
  $('#texBtn').disabled = !P.some(p => p.inst?.hasTex);
}

// ------------------------------------------------------------------ playback + camera
let t = 0, D = 0, playing = false, last = 0, trailJoint = '', trackJoint = '', follow = false;
const lastT = new THREE.Vector3(), tgt = new THREE.Vector3();
const TRAIL_ALL = 30;
let groups = [];                                        // [[players of example 0], [players of example 1], ...]
function layout() {                                     // examples side by side along x; performers of one take stay together
  const n = groups.length, sp = opt.spacing < 0 ? (n > 1 ? 1.6 : 0) : opt.spacing;
  groups.forEach((g, i) => g.forEach(p => { p._off = (i - (n - 1) / 2) * sp; }));
}
function trackPos(out) {
  out.set(0, 0, 0); let c = 0;
  for (const p of P) {
    const j = Math.max(0, p.meta.joint_names.indexOf(trackJoint));
    out.x += p.world[j * 3] + p.group.position.x; out.y += p.world[j * 3 + 1]; out.z += p.world[j * 3 + 2] + p.group.position.z; c++;
  }
  return c ? out.multiplyScalar(1 / c) : out;
}
function setTime(v) {
  t = Math.max(0, Math.min(D, v));
  for (const g of groups) {
    const r = g[0], a = r.anchor * 3;
    for (const p of g) updatePlayer(p, t);
    const rx = r.world[a], rz = r.world[a + 2];         // in place: the take's first moving root stays in the middle
    for (const p of g) p.group.position.set(p._off - (opt.inplace ? rx : 0), 0, opt.inplace ? -rz : 0);
  }
  trackPos(tgt);
  if (opt.track && follow) { const d = tgt.clone().sub(lastT); d.y = 0; camera.position.add(d); controls.target.add(d); }
  lastT.copy(tgt); follow = true;
  const gx = Math.round(tgt.x / 2) * 2, gz = Math.round(tgt.z / 2) * 2;
  checker.position.set(gx, -0.002, gz); gridLines.position.set(gx, 0, gz);
  sun.position.set(tgt.x + 3.5, 8, tgt.z + 2.5); sun.target.position.set(tgt.x, 0, tgt.z); sun.target.updateMatrixWorld();
  $('#seek').value = Math.round(t * 1000);
  $('#time').textContent = `${t.toFixed(2)} / ${D.toFixed(2)} s` + (P.length === 1 ? ` · f ${P[0].frame}` : '');
}
function togglePlay(v) {
  if (!P.length) return;
  playing = v ?? !playing; last = performance.now();
  if (playing && t >= D) t = 0;
  $('#play').textContent = playing ? 'pause' : 'play';
}
function bodyBox() {                                    // display-space box of every joint (and mesh) right now
  const box = new THREE.Box3();
  for (const p of P) {
    for (let j = 0; j < p.world.length / 3; j++) if (!p.hide[j]) box.expandByPoint(_a.fromArray(p.world, j * 3).add(p.group.position));
    if (p.inst && opt.mesh) { p.group.updateMatrixWorld(true); box.union(meshBox(p)); }
    if (p.smpl && opt.mesh) { const v = p.vpos; for (let i = 0; i < v.length; i += 3) box.expandByPoint(_a.set(v[i], v[i + 1], v[i + 2]).add(p.group.position)); }
  }
  return box;
}
function frameCamera(reset) {
  trackPos(tgt); lastT.copy(tgt);
  if (!reset) return;
  const box = bodyBox(), size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
  const ext = Math.max(size.y, size.x, size.z * 0.8, 1.2), dist = ext / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) * (THUMB ? (P.some(p => p.rig?.aim) ? 1.7 : 1.25) : 1.9);
  const dir = new THREE.Vector3(0.62, 0.32, 0.78).normalize();
  controls.target.set(c.x, Math.max(0.4, c.y), c.z); camera.position.copy(controls.target).addScaledVector(dir, dist);
  camera.near = dist / 100; camera.far = dist * 60; camera.updateProjectionMatrix(); controls.update();
}

// ------------------------------------------------------------------ selection -> players
let token = 0;
async function setSelection(ids) {
  sel = ids; if (!THUMB) history.replaceState(null, '', '#' + ids.map(encodeURIComponent).join(','));
  [...colorSlot.keys()].forEach(k => { if (!sel.includes(k)) colorSlot.delete(k); });
  for (const id of sel) if (!colorSlot.has(id)) { const used = new Set(colorSlot.values()); let s = 0; while (used.has(s)) s++; colorSlot.set(id, s); }
  draw();
  const my = ++token; $('#busy').textContent = 'loading…'; $('#busy').classList.remove('off');
  let datas;
  try { datas = await Promise.all(sel.map(loadExample)); }
  catch (e) { console.error(e); $('#busy').textContent = 'failed to load: ' + e.message; return; }
  if (my !== token) return;
  const old = new Map(groups.map(g => [g[0].exId, g]));
  groups.filter(g => !sel.includes(g[0].exId)).forEach(g => g.forEach(dispose));
  const fresh = sel.some(id => !old.has(id));
  groups = sel.map((id, i) => {
    if (old.has(id)) return old.get(id);
    const g = []; datas[i].forEach((d, k) => { const p = makePlayer(id, d, colorSlot.get(id), k ? g[0] : null, k); g.push(p); }); return g;
  });
  P = groups.flat();
  D = Math.max(...P.map(p => (p.T - 1) * p.ft));
  layout(); fillJointSelects(); draw(); applyVisibility();
  document.querySelector('#bar [data-s="spacing"]').closest('.sl').style.opacity = groups.length > 1 ? 1 : 0.4;
  $('#seek').max = Math.round(D * 1000); $('#seek').disabled = false; $('#play').disabled = false;
  const dl = $('#dl'); dl.hidden = MODE !== 'api' || sel.length !== 1;
  if (!dl.hidden) { const p = P[0], sm = p.smpl || p.joints; dl.textContent = sm ? 'download .npz' : 'download .bvh'; dl.href = (sm ? 'api/npz?id=' : 'api/bvh?id=') + encodeURIComponent(sel[0]); dl.download = EX.get(sel[0]).label + (sm ? '.npz' : '.bvh'); }
  const dsName = (e) => byDs.get(e.dataset)?.name || e.dataset;
  $('#title').innerHTML = groups.map(g => { const e = EX.get(g[0].exId);
    return `<div><i style="background:var(--c${g[0].slot})"></i><b>${esc(e.label)}</b><span>${esc([dsName(e), g.length > 1 ? g.length + ' performers' : '', e.desc].filter(Boolean).join(' · '))}</span>${groups.length > 1 ? `<button data-x="${esc(e.id)}" title="remove">×</button>` : ''}</div>`; }).join('');
  const e = EX.get(sel[sel.length - 1]), p0 = groups[groups.length - 1][0];
  const meshKind = p0.smpl ? (p0.meta.model || 'smpl').toUpperCase() : p0.rig ? 'rigged' : '–';
  const tiles = [...(groups.length > 1 ? [['clips', groups.length]] : []), ['frames', p0.T], ['fps', (1 / p0.ft).toFixed(0)], ['length', ((p0.T - 1) * p0.ft).toFixed(1) + ' s'],
    ['joints', p0.meta.joint_names.filter(n => !n.endsWith('_End')).length], ['mesh', meshKind], ['up', p0.upLabel.split(' ')[0]]];
  $('#hud').innerHTML = tiles.map(([k, v]) => `<div><span class="k">${k}</span><b>${v}</b></div>`).join('');
  const d = byDs.get(e.dataset), notes = [];
  if (e.credit) notes.push('model: ' + esc(e.credit));
  const rv = '<a id="renderView" href="#" title="save this view as an MP4: the whole clip, rendered frame by frame">render view</a>';
  if (MODE === 'static' && d) notes.push(`${esc(d.name)} · ${licenceLine(d)}${d.links?.homepage ? ` · <a href="${esc(d.links.homepage)}" target="_blank" rel="noopener">get the data</a>` : ''}${rv}`);
  else notes.push(rv);
  const errs = P.filter(p => p.rigError).map(p => p.rigError); if (errs.length) notes.push('mesh not shown: ' + esc(errs[0]));
  $('#note').innerHTML = notes.join('<br>');
  $('#renderView').onclick = (ev) => { ev.preventDefault(); renderView(ev.currentTarget); };
  follow = false; t = Math.min(t, D); setTime(t); frameCamera(fresh);
  $('#busy').classList.add('off');
  if (THUMB) { playing = false; window.__info = { duration: D, fps: 1 / P[0].ft }; window.__ready = true; return; }
  togglePlay(true);
}
$('#title').addEventListener('click', (e) => { const x = e.target.closest('[data-x]'); if (x && sel.length > 1) setSelection(sel.filter(i => i !== x.dataset.x)); });

// thumbnails (tools/examples/thumbs.py): window.__frame(t) poses everything at time t and renders once
window.__frame = (time) => { setTime(time); frameCamera(false); controls.update(); renderer.render(scene, camera); return true; };

// render view: the whole clip from the current camera, frame by frame (not a screen capture, so no dropped frames),
// encoded in the browser (WebCodecs H.264 + mp4-muxer) -> MP4; browsers without WebCodecs record a WebM in real time
let rendering = false;
const VFPS = 30, VMAX = 1920;
async function renderView(btn) {
  if (rendering || !P.length) return;
  const label = btn.textContent, aspect = camera.aspect > 0 && isFinite(camera.aspect) ? camera.aspect : 16 / 9;   // the camera's shape (the view can be 0 px in a hidden tab)
  let w = aspect >= 1 ? VMAX : Math.round(VMAX * aspect), h = aspect >= 1 ? Math.round(VMAX / aspect) : VMAX;   // long side 1920, the view's shape
  w -= w % 2; h -= h % 2;                                 // H.264 wants even sides
  const e = EX.get(sel[0]), ds = byDs.get(e.dataset)?.name || e.dataset;
  const name = `${e.dataset}-${e.label}`.replace(/[^\w.-]+/g, '_');
  const mark = `${ds} · ${sel.length > 1 ? sel.length + ' clips' : e.label}`;
  const c2 = Object.assign(document.createElement('canvas'), { width: w, height: h }), g2 = c2.getContext('2d');
  const compose = () => {                                 // the frame + a small caption: where the clip comes from
    g2.drawImage(renderer.domElement, 0, 0, w, h);
    const fs = Math.round(h / 48), pad = Math.round(fs * 0.9);
    g2.font = `500 ${fs}px "JetBrains Mono", ui-monospace, monospace`; g2.textBaseline = 'bottom';
    const right = 'Awesome Animation Datasets', wl = g2.measureText(mark).width, wr = g2.measureText(right).width;
    g2.fillStyle = 'rgba(12,14,18,.55)';
    g2.fillRect(pad - fs * .5, h - pad - fs * 1.45, wl + fs, fs * 1.8); g2.fillRect(w - pad - wr - fs * .5, h - pad - fs * 1.45, wr + fs, fs * 1.8);
    g2.fillStyle = '#f4f6f8'; g2.fillText(mark, pad, h - pad); g2.fillText(right, w - pad - wr, h - pad);
  };
  const was = { playing, t, ratio: renderer.getPixelRatio() };
  rendering = true; playing = false; $('#play').textContent = 'play';
  renderer.setPixelRatio(1); renderer.setSize(w, h, false);  // render big, keep the page layout
  const N = Math.max(1, Math.round(D * VFPS) + 1);
  const shoot = (i) => { setTime(Math.min(D, i / VFPS)); controls.update(); renderer.render(scene, camera); compose(); };
  let blob;
  try {
    if (window.VideoEncoder) {
      const { Muxer, ArrayBufferTarget } = await import('https://cdn.jsdelivr.net/npm/mp4-muxer@5.1.5/build/mp4-muxer.mjs');
      let codec = 'avc1.640033';                          // High 5.1: up to 4K; fall back to Main 4.0
      if (!(await VideoEncoder.isConfigSupported({ codec, width: w, height: h })).supported) codec = 'avc1.4d0028';
      const muxer = new Muxer({ target: new ArrayBufferTarget(), video: { codec: 'avc', width: w, height: h, frameRate: VFPS }, fastStart: 'in-memory' });
      let fail = null;
      const enc = new VideoEncoder({ output: (ch, meta) => muxer.addVideoChunk(ch, meta), error: (er) => { fail = er; } });
      enc.configure({ codec, width: w, height: h, bitrate: Math.round(w * h * VFPS * 0.12), framerate: VFPS });
      for (let i = 0; i < N; i++) {
        if (fail) throw fail;
        shoot(i);
        const f = new VideoFrame(c2, { timestamp: Math.round(i * 1e6 / VFPS), duration: Math.round(1e6 / VFPS) });
        enc.encode(f, { keyFrame: i % (VFPS * 2) === 0 }); f.close();
        if (enc.encodeQueueSize > 8) await new Promise(r => enc.addEventListener('dequeue', r, { once: true }));
        if (i % 5 === 0) { btn.textContent = `rendering ${Math.round(100 * i / N)}%`; await new Promise(r => setTimeout(r)); }
      }
      await enc.flush(); muxer.finalize();
      blob = new Blob([muxer.target.buffer], { type: 'video/mp4' });
    } else {
      const rec = new MediaRecorder(c2.captureStream(VFPS), { mimeType: 'video/webm', videoBitsPerSecond: 12e6 }), parts = [];
      rec.ondataavailable = (ev) => parts.push(ev.data);
      const done = new Promise(r => { rec.onstop = r; }); rec.start();
      for (let i = 0; i < N; i++) { shoot(i); btn.textContent = `recording ${Math.round(100 * i / N)}%`; await new Promise(r => setTimeout(r, 1000 / VFPS)); }
      rec.stop(); await done;
      blob = new Blob(parts, { type: 'video/webm' });
    }
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name + (blob.type === 'video/mp4' ? '.mp4' : '.webm') });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  } catch (er) { console.error(er); alert('render view failed: ' + er.message); }
  finally {
    renderer.setPixelRatio(was.ratio); resize(); setTime(was.t); rendering = false; btn.textContent = label;
    if (was.playing) togglePlay(true);
  }
}

// ------------------------------------------------------------------ controls
$('#play').onclick = () => togglePlay();
$('#seek').oninput = (e) => { togglePlay(false); setTime(+e.target.value / 1000); };
const tog = (id, key) => { const b = $(id); b.classList.toggle('on', !!opt[key]); b.onclick = () => { opt[key] = !opt[key]; b.classList.toggle('on', opt[key]); saveOpt(); applyVisibility(); setTime(t); }; };
tog('#loop', 'loop'); tog('#inplace', 'inplace'); tog('#onfloor', 'onfloor');
let jointOpts = '';
function fillJointSelects() {
  const p0 = P[0], names = p0 ? p0.meta.joint_names.filter((n, j) => !n.endsWith('_End') && !p0.hide[j]) : [];
  if (!names.includes(trailJoint)) trailJoint = names[0]; if (!names.includes(trackJoint)) trackJoint = names[0];
  const html = names.map(n => `<option>${esc(n)}</option>`).join('');
  if (html !== jointOpts) { jointOpts = html; $('#trailJoint').innerHTML = html; $('#trackJoint').innerHTML = html; }
  $('#trailJoint').value = trailJoint; $('#trackJoint').value = trackJoint;
}
(function buildOpts() {
  const T = (key, label, extra = '') => `<button data-t="${key}" ${extra}>${label}</button>`;
  const S = (key, label, min, max, step, tip = '') => `<label class="sl" title="${tip}">${label}<input type="range" data-s="${key}" min="${min}" max="${max}" step="${step}"><output></output></label>`;
  $('#opts1').innerHTML =
    `<div class="g"><span class="gl">trajectory</span>${T('trail', 'show', 'title="the joint\'s path and position projected on the floor"')}<select id="trailJoint" title="joint whose path is drawn on the ground"></select>${S('trailLen', 'history', 0, TRAIL_ALL, 0.5, 'seconds of path behind the joint (right end = whole clip)')}</div>` +
    `<div class="g"><span class="gl">camera</span>${T('track', 'track')}<select id="trackJoint" title="joint the camera follows"></select><button id="resetCam" title="reset camera">reset</button></div>` +
    `<div class="g"><span class="gl">up</span><select id="upSel" title="which axis of the data points up (auto: the dataset's setting, the mesh, or detected from the head)"><option value="">auto</option>${Object.keys(UPS).map(k => `<option>${k}</option>`).join('')}</select></div>` +
    `<div class="g">${S('spacing', 'spacing', 0, 4, 0.1, 'distance between compared clips (0 = overlaid)')}</div>`;
  $('#opts2').innerHTML =
    `<div class="g"><span class="gl">draw</span>${T('mesh', 'mesh', 'id="meshBtn" disabled title="SMPL bodies and rigged meshes"')}${T('tex', 'texture', 'id="texBtn" disabled title="textured or flat-coloured mesh"')}${T('skeleton', 'skeleton')}${T('joints', 'joints')}${T('ends', 'end sites')}${T('capsules', 'capsules')}${T('wire', 'wireframe')}${T('axes', 'transforms')}${S('radius', 'radius', 0.005, 0.08, 0.001, 'capsule radius')}</div>`;
  document.querySelectorAll('#bar [data-t]').forEach(b => { const k = b.dataset.t; b.classList.toggle('on', !!opt[k]); b.onclick = () => { if (b.disabled) return; opt[k] = !opt[k]; b.classList.toggle('on', opt[k]); saveOpt(); applyVisibility(); setTime(t); }; });
  const showS = (el) => {
    const k = el.dataset.s, v = k === 'spacing' && opt[k] < 0 ? (groups.length > 1 ? 1.6 : 0) : opt[k]; el.value = v;
    el.nextElementSibling.textContent = k === 'trailLen' ? (v == 0 ? 'off' : v >= TRAIL_ALL ? 'all' : v + ' s') : k === 'radius' ? (v * 100).toFixed(1) + 'cm' : (+v).toFixed(1);
  };
  document.querySelectorAll('#bar [data-s]').forEach(el => {
    showS(el);
    el.oninput = () => { opt[el.dataset.s] = +el.value; saveOpt(); showS(el); if (el.dataset.s === 'spacing') layout(); applyVisibility(); setTime(t); };
  });
  $('#trailJoint').onchange = (e) => { trailJoint = e.target.value; setTime(t); };
  $('#trackJoint').onchange = (e) => { trackJoint = e.target.value; follow = false; frameCamera(true); setTime(t); };
  $('#resetCam').onclick = () => { follow = false; frameCamera(true); setTime(t); };
  $('#upSel').onchange = (e) => { upOverride = e.target.value; const ids = sel; groups.forEach(g => g.forEach(dispose)); groups = []; P = []; setSelection(ids); };
})();

function tick(now) {
  requestAnimationFrame(tick);
  if (THUMB || rendering) return;
  if (P.length && playing) {
    t += (now - last) / 1000 * (+$('#speed').value); last = now;
    if (t >= D) { if (opt.loop) { t = 0; } else { t = D; playing = false; $('#play').textContent = 'play'; } }
    setTime(t);
  }
  controls.update(); renderer.render(scene, camera);
}
resize(); applyTheme();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => setTimeout(applyTheme, 50));
requestAnimationFrame(tick);
boot().catch(e => { console.error(e); $('#busy').textContent = 'failed to start: ' + e.message; });
