const stage = document.querySelector('three-d-stage');
const { THREE } = await stage.ready;

// ---- frei gewählte Maße des neutralen Artur-Demo-Smartphones (Meter) ----
const W = 0.073;
const H = 0.154;
const T = 0.0072;
const R = 0.0115;

// rounded-rectangle shape for the body cross-section (viewed face-on)
function roundedRect(w, h, r) {
  const s = new THREE.Shape();
  const x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h);
  s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r);
  s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

function roundedPath(w, h, r) {
  const p = new THREE.Path();
  const x = -w / 2, y = -h / 2;
  p.moveTo(x + r, y);
  p.lineTo(x + w - r, y); p.quadraticCurveTo(x + w, y, x + w, y + r);
  p.lineTo(x + w, y + h - r); p.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  p.lineTo(x + r, y + h); p.quadraticCurveTo(x, y + h, x, y + h - r);
  p.lineTo(x, y + r); p.quadraticCurveTo(x, y, x + r, y);
  return p;
}
function frameRing(w, h, r, thick) {
  const s = roundedRect(w, h, r);
  s.holes.push(roundedPath(w - 2 * thick, h - 2 * thick, Math.max(0.0008, r - thick)));
  return s;
}

const phone = new THREE.Group();
phone.name = 'artur_demo_smartphone';

// ---- materials (Space Black) ----
const matFrame = new THREE.MeshStandardMaterial({
  name: 'frame', color: 0x3c3c42, roughness: 0.28, metalness: 0.4 });
function makeBackTex(top, mid, bot) {
  const c = document.createElement('canvas'); c.width = 512; c.height = 1024;
  const g = c.getContext('2d');
  const base = g.createLinearGradient(0, 0, 0, 1024);
  base.addColorStop(0, top); base.addColorStop(0.5, mid); base.addColorStop(1, bot);
  g.fillStyle = base; g.fillRect(0, 0, 512, 1024);
  const sh = g.createLinearGradient(0, 0, 512, 1024);
  sh.addColorStop(0, 'rgba(255,255,255,0)'); sh.addColorStop(0.44, 'rgba(255,255,255,0.05)');
  sh.addColorStop(0.5, 'rgba(255,255,255,0.12)'); sh.addColorStop(0.56, 'rgba(255,255,255,0.05)');
  sh.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = sh; g.fillRect(0, 0, 512, 1024);
  const v = g.createRadialGradient(256, 512, 120, 256, 512, 640);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,0.28)');
  g.fillStyle = v; g.fillRect(0, 0, 512, 1024);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
function makeBrandShieldTex() {
  const c = document.createElement('canvas'); c.width = 512; c.height = 560;
  const g = c.getContext('2d');
  g.clearRect(0, 0, c.width, c.height);
  g.strokeStyle = 'rgba(98,213,255,0.82)';
  g.lineWidth = 22;
  g.lineJoin = 'round';
  g.lineCap = 'round';
  g.beginPath();
  g.moveTo(256, 38);
  g.lineTo(442, 106);
  g.lineTo(442, 252);
  g.bezierCurveTo(442, 382, 368, 478, 256, 522);
  g.bezierCurveTo(144, 478, 70, 382, 70, 252);
  g.lineTo(70, 106);
  g.closePath();
  g.stroke();
  g.fillStyle = 'rgba(98,213,255,0.88)';
  g.font = 'italic 270px Georgia, serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText('A', 248, 290);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}
const COLORS = {
  black: { frame: 0x3c3c42, cham: 0x8a8c94, plateau: 0x2a2b31, back: ['#22232a', '#181920', '#0e0f13'] },
  white: { frame: 0xe6e7ec, cham: 0xffffff, plateau: 0xd2d4da, back: ['#f4f5f8', '#e6e8ed', '#cfd2da'] },
  gold:  { frame: 0xd8c39a, cham: 0xf1e7cf, plateau: 0xcbb692, back: ['#efe4c8', '#e2d2ab', '#c9b487'] },
  blue:  { frame: 0x8ea6c6, cham: 0xd0dcec, plateau: 0x7f97b6, back: ['#c3d0e2', '#9fb2cc', '#7c93b2'] }
};
const matBack = new THREE.MeshStandardMaterial({
  name: 'back_glass', color: 0xffffff, map: makeBackTex('#22232a', '#181920', '#0e0f13'),
  roughness: 0.5, metalness: 0.24 });
const matScreen = new THREE.MeshStandardMaterial({
  name: 'screen', color: 0x040406, roughness: 0.12, metalness: 0.1 });
const matBezel = new THREE.MeshStandardMaterial({
  name: 'bezel', color: 0x08080a, roughness: 0.3, metalness: 0.2 });
const matPlateau = new THREE.MeshStandardMaterial({
  name: 'camera_bar', color: 0x2a2b31, roughness: 0.34, metalness: 0.5 });
const matLensRing = new THREE.MeshStandardMaterial({
  name: 'lens_ring', color: 0x141416, roughness: 0.28, metalness: 0.6 });
const matGlass = new THREE.MeshStandardMaterial({
  name: 'lens_glass', color: 0x0b1526, roughness: 0.05, metalness: 0.5 });
const matButton = new THREE.MeshStandardMaterial({
  name: 'button', color: 0x3c3c42, roughness: 0.28, metalness: 0.4 });
const matChamfer = new THREE.MeshStandardMaterial({
  name: 'chamfer', color: 0x8a8c94, roughness: 0.14, metalness: 0.9 });
const matAntenna = new THREE.MeshStandardMaterial({
  name: 'antenna', color: 0x1b1c21, roughness: 0.5, metalness: 0.3 });
const matFlash = new THREE.MeshStandardMaterial({
  name: 'flash', color: 0x6b6d72, roughness: 0.3, metalness: 0.2 });

// ---- body (titanium frame) via extruded rounded rect ----
const bodyGeo = new THREE.ExtrudeGeometry(roundedRect(W, H, R), {
  depth: T, bevelEnabled: true, bevelThickness: 0.0011,
  bevelSize: 0.0008, bevelSegments: 6, curveSegments: 28 });
bodyGeo.translate(0, 0, -T / 2);
const body = new THREE.Mesh(bodyGeo, matFrame);
body.name = 'frame';
phone.add(body);

// ---- diamond-cut polished chamfer rims (front & back edge highlight) ----
const chamFrontGeo = new THREE.ExtrudeGeometry(frameRing(W, H, R, 0.0013), {
  depth: 0.0006, bevelEnabled: false, curveSegments: 28 });
chamFrontGeo.translate(0, 0, T / 2 - 0.0003);
const chamFront = new THREE.Mesh(chamFrontGeo, matChamfer);
chamFront.name = 'chamfer_front'; phone.add(chamFront);
const chamBackGeo = new THREE.ExtrudeGeometry(frameRing(W, H, R, 0.0013), {
  depth: 0.0006, bevelEnabled: false, curveSegments: 28 });
chamBackGeo.translate(0, 0, -T / 2 - 0.0003);
const chamBack = new THREE.Mesh(chamBackGeo, matChamfer);
chamBack.name = 'chamfer_back'; phone.add(chamBack);

// ---- antenna lines (thin bands across the side rails) ----
function antenna(x, y) {
  const a = new THREE.Mesh(new THREE.BoxGeometry(0.0008, 0.0013, T * 1.08), matAntenna);
  a.position.set(x, y, 0); a.name = 'antenna'; return a;
}
phone.add(antenna(W / 2 + 0.0003, H * 0.34));
phone.add(antenna(W / 2 + 0.0003, -H * 0.39));
phone.add(antenna(-W / 2 - 0.0003, H * 0.34));
phone.add(antenna(-W / 2 - 0.0003, -H * 0.39));
// top-edge antenna band
const antTop = new THREE.Mesh(new THREE.BoxGeometry(0.02, 0.0008, T * 1.08), matAntenna);
antTop.position.set(0, H / 2 + 0.0004, 0); antTop.name = 'antenna_top'; phone.add(antTop);

// ---- back panel (slightly inset glass) ----
const backGeo = new THREE.ExtrudeGeometry(roundedRect(W - 0.0016, H - 0.0016, R - 0.0008), {
  depth: 0.0004, bevelEnabled: false, curveSegments: 24 });
backGeo.translate(0, 0, -T / 2 - 0.0002);
const back = new THREE.Mesh(backGeo, matBack);
back.name = 'back_glass';
phone.add(back);

// ---- front bezel (black surround, edge-to-edge over the titanium front) ----
const bezelGeo = new THREE.ExtrudeGeometry(roundedRect(W - 0.001, H - 0.001, R - 0.0005), {
  depth: 0.0006, bevelEnabled: false, curveSegments: 24 });
bezelGeo.translate(0, 0, T / 2 + 0.0008);
const bezel = new THREE.Mesh(bezelGeo, matBezel);
bezel.name = 'front_bezel';
phone.add(bezel);

// ---- screen (active display, thin even bezels, edge-to-edge) ----
const scrGeo = new THREE.ExtrudeGeometry(roundedRect(W - 0.0034, H - 0.0034, R - 0.002), {
  depth: 0.0003, bevelEnabled: false, curveSegments: 24 });
scrGeo.translate(0, 0, T / 2 + 0.0013);
const screen = new THREE.Mesh(scrGeo, matScreen);
screen.name = 'screen';
phone.add(screen);

// ---- Frontkamera und Statusbanner werden flach auf dem Display gezeichnet ----

// ---- rear camera plateau (smooth blended bump across the top) ----
const plateauW = W - 0.0075;
const plateauH = 0.021;
const plateauR = 0.0096;
// soft base that blends the bump into the back glass
const plateauBaseGeo = new THREE.ExtrudeGeometry(roundedRect(plateauW + 0.0022, plateauH + 0.0022, plateauR + 0.0011), {
  depth: 0.0009, bevelEnabled: true, bevelThickness: 0.0007,
  bevelSize: 0.0011, bevelSegments: 4, curveSegments: 28 });
const plateauBase = new THREE.Mesh(plateauBaseGeo, matBack);
plateauBase.position.set(0, H / 2 - 0.02, -T / 2 - 0.0002);
plateauBase.rotation.y = Math.PI;
plateauBase.name = 'plateau_base';
phone.add(plateauBase);
const plateauGeo = new THREE.ExtrudeGeometry(roundedRect(plateauW, plateauH, plateauR), {
  depth: 0.0016, bevelEnabled: true, bevelThickness: 0.0007,
  bevelSize: 0.0007, bevelSegments: 4, curveSegments: 28 });
const plateau = new THREE.Mesh(plateauGeo, matPlateau);
plateau.position.set(0, H / 2 - 0.02, -T / 2 - 0.0006);
plateau.rotation.y = Math.PI; // face the extrusion outward (−z)
plateau.name = 'camera_plateau';
phone.add(plateau);

// ---- camera lens (single, on the plateau — top-left seen from the back) ----
const camGroup = new THREE.Group();
camGroup.name = 'camera';
const lensY = H / 2 - 0.02;
const zc = -T / 2 - 0.0022;               // plateau front face
const lensX = plateauW / 2 - 0.012;       // local +x → appears LEFT viewing the back
// raised lens housing
const housing = new THREE.Mesh(
  new THREE.CylinderGeometry(0.0067, 0.0069, 0.0016, 44).rotateX(Math.PI / 2),
  new THREE.MeshStandardMaterial({ name: 'lens_housing', color: 0x303138, roughness: 0.3, metalness: 0.55 }));
housing.position.set(lensX, lensY, zc - 0.0008);
housing.name = 'lens_housing'; camGroup.add(housing);
// metal ring
const ring = new THREE.Mesh(
  new THREE.CylinderGeometry(0.0056, 0.006, 0.0014, 44).rotateX(Math.PI / 2), matLensRing);
ring.position.set(lensX, lensY, zc - 0.0018);
ring.name = 'lens_ring'; camGroup.add(ring);
// dark surround inside the ring
const surround = new THREE.Mesh(
  new THREE.CylinderGeometry(0.0048, 0.005, 0.0012, 44).rotateX(Math.PI / 2),
  new THREE.MeshStandardMaterial({ name: 'lens_surround', color: 0x0c0d11, roughness: 0.35, metalness: 0.3 }));
surround.position.set(lensX, lensY, zc - 0.0022);
surround.name = 'lens_surround'; camGroup.add(surround);
// sapphire glass + slight dome
const glass = new THREE.Mesh(
  new THREE.CylinderGeometry(0.0043, 0.0043, 0.0012, 44).rotateX(Math.PI / 2), matGlass);
glass.position.set(lensX, lensY, zc - 0.0024);
glass.name = 'lens_glass'; camGroup.add(glass);
const dome = new THREE.Mesh(new THREE.SphereGeometry(0.0044, 32, 20), matGlass);
dome.scale.set(1, 1, 0.35);
dome.position.set(lensX, lensY, zc - 0.0028);
dome.name = 'lens_dome'; camGroup.add(dome);
// aperture
const innerLens = new THREE.Mesh(
  new THREE.CylinderGeometry(0.0018, 0.0018, 0.001, 32).rotateX(Math.PI / 2),
  new THREE.MeshStandardMaterial({ name: 'inner_lens', color: 0x16233a, roughness: 0.04, metalness: 0.6 }));
innerLens.position.set(lensX, lensY, zc - 0.0026);
innerLens.name = 'inner_lens'; camGroup.add(innerLens);
// specular glint
const glint = new THREE.Mesh(
  new THREE.SphereGeometry(0.0009, 16, 12),
  new THREE.MeshBasicMaterial({ color: 0xaec2e6, transparent: true, opacity: 0.55 }));
glint.position.set(lensX - 0.0016, lensY + 0.0016, zc - 0.003);
glint.name = 'lens_glint'; camGroup.add(glint);
// flash + mic on the plateau (right side seen from the back)
const flash = new THREE.Mesh(
  new THREE.CylinderGeometry(0.0019, 0.0019, 0.0011, 28).rotateX(Math.PI / 2), matFlash);
flash.position.set(-plateauW / 2 + 0.013, lensY, zc - 0.0006);
flash.name = 'flash'; camGroup.add(flash);
const mic = new THREE.Mesh(
  new THREE.CylinderGeometry(0.0006, 0.0006, 0.001, 16).rotateX(Math.PI / 2), matLensRing);
mic.position.set(-plateauW / 2 + 0.006, lensY, zc - 0.0006);
mic.name = 'microphone'; camGroup.add(mic);
phone.add(camGroup);

// ---- Arturs eigenes A-Schild: dezente, klar eigenständige Rückseitenmarke ----
const brandShield = new THREE.Mesh(
  new THREE.PlaneGeometry(0.022, 0.024),
  new THREE.MeshBasicMaterial({
    name: 'artur_brand_shield',
    map: makeBrandShieldTex(),
    transparent: true,
    opacity: 0.72,
    depthTest: false,
    depthWrite: false,
    toneMapped: false
  })
);
brandShield.position.set(0, -0.012, -T / 2 - 0.00055);
brandShield.rotation.y = Math.PI;
brandShield.name = 'artur_brand_shield';
phone.add(brandShield);

// ---- side buttons (rounded pills, protruding from the frame rail) ----
const railX = W / 2 + 0.0009; // outer face of the beveled frame
function sideButton(len, name, x, y) {
  const b = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.0007, len, 6, 16), matButton);
  b.position.set(x, y, 0);
  b.name = name;
  return b;
}
const powerBtn = sideButton(0.018, 'power_button', railX + 0.0002, H * 0.20); phone.add(powerBtn);
const cameraCtrl = sideButton(0.006, 'camera_control', railX + 0.0002, H * 0.03); phone.add(cameraCtrl);
const actionBtn = sideButton(0.006, 'action_button', -railX - 0.0002, H * 0.30); phone.add(actionBtn);
const volUpBtn = sideButton(0.011, 'volume_up', -railX - 0.0002, H * 0.18); phone.add(volUpBtn);
const volDownBtn = sideButton(0.011, 'volume_down', -railX - 0.0002, H * 0.09); phone.add(volDownBtn);

// ---- bottom: USB-C port + speaker/mic holes ----
const botY = -H / 2 - 0.0009; // outer face of the beveled frame bottom
const portShape = roundedRect(0.0088, 0.0026, 0.0013);
const portGeo = new THREE.ExtrudeGeometry(portShape, {
  depth: 0.0002, bevelEnabled: false, curveSegments: 16 });
portGeo.rotateX(Math.PI / 2);
const port = new THREE.Mesh(portGeo, matBezel);
port.position.set(0, botY - 0.0001, 0);
port.name = 'usb_c_port';
phone.add(port);
for (let i = 0; i < 6; i++) {
  const hole = new THREE.Mesh(
    new THREE.CylinderGeometry(0.0004, 0.0004, 0.0004, 12), matBezel);
  hole.position.set(0.009 + i * 0.0024, botY - 0.0001, 0);
  hole.name = 'speaker_hole_' + i;
  phone.add(hole);
  const hole2 = hole.clone();
  hole2.position.x = -0.009 - i * 0.0024;
  hole2.name = 'mic_hole_' + i;
  phone.add(hole2);
}

// =====================================================================
//  INTERAKTIVES DISPLAY — neutrales Demo-System mit Startansicht,
//  Anfrage-Board und funktionierender Taschenlampe.
// =====================================================================
const scrW = W - 0.0034, scrH = H - 0.0034;
const cw = 660, ch = Math.round(cw * scrH / scrW);
const SCALE = 2; // Screen-Canvas in doppelter Aufloesung -> scharfe UI auf dem groesseren 3D-Handy
const cornerR = 96;
const ACCENT = '#62d5ff';   // Marken-Cyan (--signal) statt Violett — harmoniert mit der Seite
const ON_ACCENT = '#04222e'; // EINE Textfarbe auf Cyan-Flaechen (kein Violett-Rest)
const MARGIN = 50;           // EIN linker/rechter Seitenrand fuer Statusleiste + Inhalt
const BG_TOP = '#1a1f2b', BG_BOTTOM = '#0b0d14'; // gemeinsame Screen-Basis (ein einheitliches "OS")
function screenBG() {
  const g = cx.createLinearGradient(0, 0, 0, ch);
  g.addColorStop(0, BG_TOP); g.addColorStop(1, BG_BOTTOM);
  cx.fillStyle = g; cx.fillRect(0, 0, cw, ch);
}
const FONT = 'system-ui, "Segoe UI", Arial, sans-serif';

// ---- BEISPIEL-INHALT (Artur kann diese Texte gefahrlos aendern) ----
// Nur den Text ZWISCHEN den Anfuehrungszeichen aendern. NICHT: Apostrophe verwenden,
// eine ganze Zeile/das Feld loeschen, oder Anfuehrungszeichen/Komma am Zeilenende entfernen.
// Wird als Muster-Mitteilung auf dem Sperrbildschirm gezeigt, klar als "Beispiel" markiert.
const DEMO = {
  appLabel: 'Anfragen-System',
  badge: 'Beispiel',
  untertitel: 'Alle Anfragen an einem Ort. Nichts geht verloren.',
  // Sperrbildschirm-Mitteilung (nur Fallback-Zustand):
  titel: 'Neue Anfrage',
  zeile: 'Dach undicht, Chemnitz',
  // Anfragen-System-Board (direkt sichtbar). status-key: neu | pruefung | angebot
  anfragen: [
    { text: 'Dach undicht, Chemnitz', status: 'Neu', key: 'neu', zeit: 'vor 5 Min' },
    { text: 'Heizung ausgefallen, Zwickau', status: 'Wartend', key: 'wartend', zeit: 'Heute' },
    { text: 'Bad sanieren, Leipzig', status: 'Termin', key: 'termin', zeit: 'Gestern' }
  ]
};
// Status-Zyklus fuers Antippen der Board-Karten (nur Anzeige, sendet nichts).
// GLEICHES Vokabular wie die Kunden-App-Demo (app-demo.html): Neu -> Wartend -> Termin -> Auftrag.
const STAT_COLOR = { neu: '#ff7a6b', wartend: '#ffb84d', termin: '#4a90ff', auftrag: '#57d99a' };
const STAT_NEXT = { neu: 'wartend', wartend: 'termin', termin: 'auftrag', auftrag: 'neu' };
const STAT_LABEL = { neu: 'Neu', wartend: 'Wartend', termin: 'Termin', auftrag: 'Auftrag' };
function naechsterStatus(i) {
  var arr = Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [];
  var req = arr[i]; if (!req) return;
  req.key = STAT_NEXT[req.key] || 'neu';
  req.status = STAT_LABEL[req.key];
  statusMsg = 'Status: ' + req.status; statusMsgColor = STAT_COLOR[req.key] || '#cfd3dc';
  showStatusBanner();
  render();
}
let statusMsg = '', statusMsgColor = '#cfd3dc';

const cv = document.createElement('canvas'); cv.width = cw * SCALE; cv.height = ch * SCALE;
const cx = cv.getContext('2d');
const lerp = (a, b, t) => a + (b - a) * t;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const ease = t => 1 - Math.pow(1 - t, 3);
function rr(x, y, w, h, r) { cx.beginPath(); cx.roundRect(x, y, w, h, r); }
function darken(hex, f) {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) * f, g = ((n >> 8) & 255) * f, b = (n & 255) * f;
  return 'rgb(' + (r | 0) + ',' + (g | 0) + ',' + (b | 0) + ')';
}

// ---------- line-icon glyphs (drawn white, centred at x,y, half-size s) ----------
let GLYPH_COL = null; // optionale Farb-Uebersteuerung: vor dem G.*-Aufruf setzen, danach zuruecksetzen
function S(w) { cx.lineWidth = w; cx.strokeStyle = cx.fillStyle = GLYPH_COL || '#fff';
  cx.lineJoin = 'round'; cx.lineCap = 'round'; }
const G = {
  bubble(x, y, s) { S(s * 0.16); rr(x - s, y - s * 0.8, 2 * s, 1.5 * s, s * 0.55); cx.stroke();
    cx.beginPath(); cx.moveTo(x - s * 0.45, y + s * 0.55); cx.lineTo(x - s * 0.55, y + s);
    cx.lineTo(x - s * 0.05, y + s * 0.6); cx.stroke(); },
  calendar(x, y, s) { S(s * 0.13); rr(x - s, y - s * 0.85, 2 * s, 1.7 * s, s * 0.28); cx.stroke();
    cx.beginPath(); cx.moveTo(x - s, y - s * 0.25); cx.lineTo(x + s, y - s * 0.25); cx.stroke();
    for (let i = 0; i < 3; i++) for (let j = 0; j < 2; j++)
      { cx.beginPath(); cx.arc(x - s * 0.55 + i * s * 0.55, y + s * 0.35 + j * s * 0.5, s * 0.09, 0, 7); cx.fill(); } },
  photo(x, y, s) { S(s * 0.13); rr(x - s, y - s * 0.8, 2 * s, 1.6 * s, s * 0.24); cx.stroke();
    cx.beginPath(); cx.arc(x - s * 0.4, y - s * 0.2, s * 0.22, 0, 7); cx.stroke();
    cx.beginPath(); cx.moveTo(x - s * 0.85, y + s * 0.6); cx.lineTo(x - s * 0.1, y - s * 0.05);
    cx.lineTo(x + s * 0.35, y + s * 0.35); cx.lineTo(x + s * 0.65, y + s * 0.05);
    cx.lineTo(x + s * 0.85, y + s * 0.6); cx.stroke(); },
  camera(x, y, s) { S(s * 0.13); rr(x - s, y - s * 0.55, 2 * s, 1.3 * s, s * 0.28); cx.stroke();
    cx.beginPath(); cx.moveTo(x - s * 0.45, y - s * 0.55); cx.lineTo(x - s * 0.25, y - s * 0.85);
    cx.lineTo(x + s * 0.25, y - s * 0.85); cx.lineTo(x + s * 0.45, y - s * 0.55); cx.stroke();
    cx.beginPath(); cx.arc(x, y + s * 0.15, s * 0.42, 0, 7); cx.stroke(); },
  clock(x, y, s) { S(s * 0.12); cx.beginPath(); cx.arc(x, y, s * 0.95, 0, 7); cx.stroke();
    const d = new Date(); const hA = (d.getHours() % 12 + d.getMinutes() / 60) / 12 * 6.283 - 1.5708;
    const mA = d.getMinutes() / 60 * 6.283 - 1.5708;
    cx.beginPath(); cx.moveTo(x, y); cx.lineTo(x + Math.cos(hA) * s * 0.45, y + Math.sin(hA) * s * 0.45);
    cx.moveTo(x, y); cx.lineTo(x + Math.cos(mA) * s * 0.72, y + Math.sin(mA) * s * 0.72); cx.stroke(); },
  pin(x, y, s) { S(s * 0.13); cx.beginPath();
    cx.arc(x, y - s * 0.15, s * 0.6, Math.PI * 0.15, Math.PI * 0.85, true);
    cx.lineTo(x, y + s * 0.9); cx.closePath(); cx.stroke();
    cx.beginPath(); cx.arc(x, y - s * 0.15, s * 0.22, 0, 7); cx.stroke(); },
  weather(x, y, s) { S(s * 0.12); cx.beginPath(); cx.arc(x - s * 0.25, y - s * 0.25, s * 0.4, 0, 7); cx.stroke();
    cx.beginPath(); cx.arc(x + s * 0.15, y + s * 0.35, s * 0.42, Math.PI, 0); 
    cx.arc(x + s * 0.55, y + s * 0.3, s * 0.3, -Math.PI / 2, Math.PI / 2); cx.lineTo(x - s * 0.3, y + s * 0.6);
    cx.closePath(); cx.fillStyle = '#fff'; cx.fill(); },
  note(x, y, s) { S(s * 0.13); rr(x - s * 0.85, y - s * 0.9, 1.7 * s, 1.8 * s, s * 0.2); cx.stroke();
    for (let i = 0; i < 3; i++) { cx.beginPath(); cx.moveTo(x - s * 0.5, y - s * 0.35 + i * s * 0.5);
      cx.lineTo(x + s * 0.5, y - s * 0.35 + i * s * 0.5); cx.stroke(); } },
  list(x, y, s) { S(s * 0.13); for (let i = 0; i < 3; i++) { const yy = y - s * 0.6 + i * s * 0.6;
    cx.beginPath(); cx.arc(x - s * 0.6, yy, s * 0.12, 0, 7); cx.stroke();
    cx.beginPath(); cx.moveTo(x - s * 0.2, yy); cx.lineTo(x + s * 0.7, yy); cx.stroke(); } },
  chart(x, y, s) { S(s * 0.16); const hs = [0.5, 0.9, 0.35, 0.7];
    hs.forEach((hh, i) => { const xx = x - s * 0.7 + i * s * 0.5;
      cx.beginPath(); cx.moveTo(xx, y + s * 0.7); cx.lineTo(xx, y + s * 0.7 - s * 1.3 * hh); cx.stroke(); }); },
  torch(x, y, s) { S(s * 0.13); cx.beginPath(); cx.moveTo(x - s * 0.5, y - s * 0.8);
    cx.lineTo(x + s * 0.5, y - s * 0.8); cx.lineTo(x + s * 0.32, y - s * 0.4);
    cx.lineTo(x - s * 0.32, y - s * 0.4); cx.closePath(); cx.stroke();
    rr(x - s * 0.32, y - s * 0.35, s * 0.64, s * 1.15, s * 0.14); cx.stroke();
    cx.beginPath(); cx.moveTo(x, y - s * 0.8); cx.lineTo(x, y - s * 1.15); cx.stroke(); },
  gear(x, y, s) { S(s * 0.12); const R1 = s * 0.9, R2 = s * 0.62;
    cx.beginPath(); for (let i = 0; i < 16; i++) { const a = i / 16 * 6.283; const r = i % 2 ? R2 : R1;
      cx[i ? 'lineTo' : 'moveTo'](x + Math.cos(a) * r, y + Math.sin(a) * r); } cx.closePath(); cx.stroke();
    cx.beginPath(); cx.arc(x, y, s * 0.3, 0, 7); cx.stroke(); },
  music(x, y, s) { S(s * 0.13); cx.beginPath(); cx.moveTo(x - s * 0.35, y + s * 0.6);
    cx.lineTo(x - s * 0.35, y - s * 0.7); cx.lineTo(x + s * 0.55, y - s * 0.9); cx.lineTo(x + s * 0.55, y + s * 0.35);
    cx.stroke(); cx.beginPath(); cx.arc(x - s * 0.55, y + s * 0.6, s * 0.24, 0, 7);
    cx.arc(x + s * 0.35, y + s * 0.35, s * 0.24, 0, 7); cx.fillStyle = '#fff'; cx.fill(); },
  calc(x, y, s) { S(s * 0.12); rr(x - s * 0.85, y - s * 0.9, 1.7 * s, 1.8 * s, s * 0.2); cx.stroke();
    cx.beginPath(); cx.moveTo(x - s * 0.85, y - s * 0.35); cx.lineTo(x + s * 0.85, y - s * 0.35); cx.stroke();
    for (let i = 0; i < 2; i++) { cx.beginPath(); cx.moveTo(x - s * 0.3 + i * s * 0.6, y - s * 0.35);
      cx.lineTo(x - s * 0.3 + i * s * 0.6, y + s * 0.9); cx.stroke(); }
    cx.beginPath(); cx.moveTo(x - s * 0.85, y + s * 0.27); cx.lineTo(x + s * 0.85, y + s * 0.27); cx.stroke(); },
  compass(x, y, s) { S(s * 0.12); cx.beginPath(); cx.arc(x, y, s * 0.9, 0, 7); cx.stroke();
    cx.beginPath(); cx.moveTo(x, y - s * 0.5); cx.lineTo(x + s * 0.35, y); cx.lineTo(x, y + s * 0.5);
    cx.lineTo(x - s * 0.35, y); cx.closePath(); cx.stroke(); },
  card(x, y, s) { S(s * 0.13); rr(x - s, y - s * 0.65, 2 * s, 1.3 * s, s * 0.22); cx.stroke();
    cx.beginPath(); cx.moveTo(x - s, y - s * 0.15); cx.lineTo(x + s, y - s * 0.15); cx.stroke(); },
  phone(x, y, s) { S(s * 0.12); cx.save(); cx.translate(x, y); cx.rotate(-0.35);
    cx.beginPath(); cx.moveTo(-s * 0.6, -s * 0.85);
    cx.quadraticCurveTo(-s * 0.9, -s * 0.85, -s * 0.85, -s * 0.45);
    cx.quadraticCurveTo(-s * 0.6, s * 0.75, s * 0.5, s * 0.9);
    cx.quadraticCurveTo(s * 0.9, s * 0.9, s * 0.9, s * 0.55);
    cx.lineTo(s * 0.35, s * 0.2); cx.lineTo(s * 0.1, s * 0.55);
    cx.quadraticCurveTo(-s * 0.4, s * 0.2, -s * 0.25, -s * 0.35);
    cx.lineTo(s * 0.1, -s * 0.6); cx.closePath(); cx.stroke(); cx.restore(); },
  mail(x, y, s) { S(s * 0.13); rr(x - s, y - s * 0.7, 2 * s, 1.4 * s, s * 0.22); cx.stroke();
    cx.beginPath(); cx.moveTo(x - s, y - s * 0.5); cx.lineTo(x, y + s * 0.15);
    cx.lineTo(x + s, y - s * 0.5); cx.stroke(); }
};

// ---------- app catalogue ----------
const APPS = [
  { id: 'anfragen', name: 'Anfragen-System', color: '#3aa0d0', glyph: 'list' },
  { id: 'flashlight', name: 'Taschenlampe', color: '#2b2e37', glyph: 'torch' }
];
const DOCK = [];
const APP_BY_ID = {}; APPS.forEach(a => APP_BY_ID[a.id] = a); DOCK.forEach(a => { if (!APP_BY_ID[a.id]) APP_BY_ID[a.id] = a; });

// ---------- display plane (clean UVs → easy raycasting) ----------
const screenTex = new THREE.CanvasTexture(cv);
screenTex.colorSpace = THREE.SRGBColorSpace; screenTex.anisotropy = 8;
const matDisplay = new THREE.MeshBasicMaterial({ map: screenTex, transparent: true, alphaTest: 0.03, toneMapped: false });
const display = new THREE.Mesh(new THREE.PlaneGeometry(scrW, scrH), matDisplay);
display.position.set(0, 0, T / 2 + 0.00165); display.name = 'display';
phone.add(display);

// ---------- flashlight: a real light out of the rear LED ----------
function radialTex() {
  const c = document.createElement('canvas'); c.width = c.height = 64;
  const g = c.getContext('2d'); const rg = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  rg.addColorStop(0, 'rgba(255,255,255,1)'); rg.addColorStop(0.35, 'rgba(255,246,230,0.7)');
  rg.addColorStop(1, 'rgba(255,246,230,0)'); g.fillStyle = rg; g.fillRect(0, 0, 64, 64);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}
const torch = new THREE.SpotLight(0xfff3e0, 0, 1.1, Math.PI / 2.6, 0.85, 1.0);
torch.position.copy(flash.position);
const torchTarget = new THREE.Object3D();
torchTarget.position.set(flash.position.x, flash.position.y, flash.position.z - 0.5);
phone.add(torchTarget); torch.target = torchTarget; phone.add(torch);
const torchGlow = new THREE.PointLight(0xfff3e0, 0, 0.22, 2);
torchGlow.position.copy(flash.position); phone.add(torchGlow);
const torchSprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: radialTex(), color: 0xfff3e0,
  transparent: true, blending: THREE.AdditiveBlending, opacity: 0, depthWrite: false }));
torchSprite.scale.set(0.02, 0.02, 1);
torchSprite.position.set(flash.position.x, flash.position.y, flash.position.z - 0.0012);
phone.add(torchSprite);
// volumetric beam cone (apex at the LED, widening outward −z)
const torchBeam = new THREE.Mesh(
  new THREE.ConeGeometry(0.11, 0.16, 48, 1, true),
  new THREE.MeshBasicMaterial({ color: 0xfff2d8, transparent: true, opacity: 0,
    blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
torchBeam.rotation.x = Math.PI / 2;
torchBeam.position.set(flash.position.x, flash.position.y, flash.position.z - 0.08);
torchBeam.name = 'torch_beam';
phone.add(torchBeam);
let flashOn = false;
function setFlashlight(on) {
  flashOn = on;
  statusMsg = on ? '' : 'Taschenlampe aus'; statusMsgColor = '#cfd3dc';
  showStatusBanner(); // Statusbanner zeigt die Änderung sichtbar an.
  torch.intensity = on ? 6 : 0;
  torchGlow.intensity = on ? 2.2 : 0;
  torchSprite.material.opacity = on ? 1 : 0;
  torchBeam.material.opacity = on ? 0.1 : 0;
  matFlash.emissive.set(on ? 0xfff3e0 : 0x000000);
  matFlash.emissiveIntensity = on ? 2.4 : 0;
  matFlash.needsUpdate = true;
  render();
}

// ---------- OS state ----------
let state = 'lock';        // off | lock | home | app
let currentApp = null, openFrom = 'home';
let drag = null;           // { kind:'unlock'|'closeApp', p:0..1 }
let anim = null;           // { kind:'unlockP'|'appP', p0,p1,t,start,dur,onDone }
const regions = [];
let allowHit = true;
let volume = 0.6, muted = false, volumeHudUntil = 0, muteHudUntil = 0, _poking = false;
let battery = 0.86, charging = false, chargeTimer = null;
let wallpaperImg = null, currentColor = 'black', statusBannerUntil = 0;
function region(r) { if (allowHit) regions.push(r); }
function hitAt(px, py) {
  for (let i = regions.length - 1; i >= 0; i--) { const r = regions[i];
    if (r.shape === 'circle') { if (Math.hypot(px - r.cx, py - r.cy) <= r.r) return r; }
    else if (px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h) return r; }
  return null;
}

// ---------- shared chrome ----------
function indicators(alpha) {
  cx.globalAlpha = alpha; cx.fillStyle = '#fff';
  for (let i = 0; i < 4; i++) cx.fillRect(cw - 196 + i * 12, 46 - i * 5, 8, 8 + i * 5);
  cx.font = '600 25px ' + FONT; cx.textAlign = 'left'; cx.fillText('5G', cw - 138, 52);
  cx.strokeStyle = '#fff'; cx.lineWidth = 2.5; rr(cw - 96, 30, 54, 26, 8); cx.stroke();
  cx.fillRect(cw - 40, 37, 4, 12);
  cx.fillStyle = charging ? '#37cf6a' : '#fff'; rr(cw - 92, 34, Math.max(3, 40 * battery), 18, 5); cx.fill();
  // Keine Prozentzahl: So bleibt die kompakte Statuszeile überlappungsfrei.
  if (flashOn) { // Dauer-Feedback: Taschenlampen-Glyph in der Statusleiste, solange sie an ist
    GLYPH_COL = ACCENT; G.torch(cw - 232, 42, 13); GLYPH_COL = null;
  }
  if (charging) { cx.fillStyle = '#0e0f13'; const bx = cw - 72, by = 43;
    cx.beginPath(); cx.moveTo(bx + 3, by - 8); cx.lineTo(bx - 4, by + 1); cx.lineTo(bx, by + 1);
    cx.lineTo(bx - 3, by + 9); cx.lineTo(bx + 5, by - 1); cx.lineTo(bx, by - 1); cx.closePath(); cx.fill(); }
  cx.globalAlpha = 1;
}

// ---------- lock screen ----------
function drawLock(p) {
  const stable = p === 0;
  const shift = -p * ch * 0.5, alpha = 1 - clamp(p * 1.3, 0, 1);
  cx.save(); cx.globalAlpha = alpha; cx.translate(0, shift);
  if (wallpaperImg) drawCover(wallpaperImg); else screenBG(); // gleiche Basis wie Board/Home = EIN "OS"
  cx.save(); cx.globalAlpha = alpha * 0.1; cx.fillStyle = '#dfe4ee';
  cx.beginPath(); cx.moveTo(cw * 0.05, 0); cx.lineTo(cw * 0.3, 0);
  cx.lineTo(cw * 0.95, ch * 0.5); cx.lineTo(cw * 0.7, ch * 0.5); cx.closePath(); cx.fill(); cx.restore();
  indicators(alpha);
  // lock glyph + clock + date
  cx.strokeStyle = '#fff'; cx.fillStyle = '#fff'; cx.lineWidth = 3;
  cx.beginPath(); cx.arc(cw / 2, 108, 9, Math.PI, 0); cx.stroke();
  rr(cw / 2 - 14, 108, 28, 21, 5); cx.fill();
  const now = new Date();
  const days = ['So.', 'Mo.', 'Di.', 'Mi.', 'Do.', 'Fr.', 'Sa.'];
  const months = ['Januar', 'Februar', 'M\u00e4rz', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  cx.textAlign = 'center'; cx.fillStyle = '#fff';
  cx.font = '600 38px ' + FONT;
  cx.fillText(days[now.getDay()] + ' ' + now.getDate() + '. ' + months[now.getMonth()], cw / 2, 205);
  cx.font = '300 200px ' + FONT;
  cx.fillText(String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'), cw / 2, 380);
  // Beispiel-Anfrage als Mitteilungs-Karte (statt generisch "2 Mitteilungen") \u2014 der Ruhezustand verkauft.
  (function () {
    // String()-Guards: ein versehentlich geloeschtes/leeres DEMO-Feld ergibt hoechstens leeren Text, nie einen Absturz.
    var appL = String(DEMO.appLabel || ''), tit = String(DEMO.titel || ''),
        zei = String(DEMO.zeile || ''), bad = String(DEMO.badge || 'Beispiel');
    var cardW = cw * 0.86, cardX = (cw - cardW) / 2, cardY = ch - 348, cardH = 120, rad = 26;
    cx.save(); cx.globalAlpha = alpha * 0.95;
    cx.fillStyle = 'rgba(18,20,26,0.82)'; rr(cardX, cardY, cardW, cardH, rad); cx.fill();
    cx.save(); rr(cardX, cardY, cardW, cardH, rad); cx.clip(); // langer Beispiel-Text laeuft nicht ueber den Rand
    cx.fillStyle = ACCENT; rr(cardX + 22, cardY + 24, 44, 44, 13); cx.fill();
    // "BEISPIEL"-Pille (ACCENT-Fuellung, dunkler Text) — klar ein Hinweis, keine Uhrzeit.
    cx.font = '700 16px ' + FONT; var bw = cx.measureText(bad.toUpperCase()).width + 24;
    cx.fillStyle = ACCENT; rr(cardX + cardW - bw - 22, cardY + 22, bw, 28, 14); cx.fill();
    cx.fillStyle = ON_ACCENT; cx.textAlign = 'left'; cx.fillText(bad.toUpperCase(), cardX + cardW - bw - 10, cardY + 41);
    cx.fillStyle = 'rgba(255,255,255,0.6)'; cx.font = '600 20px ' + FONT;
    cx.fillText(appL.toUpperCase(), cardX + 82, cardY + 40);
    cx.fillStyle = '#fff'; cx.font = '600 25px ' + FONT;
    cx.fillText(tit, cardX + 82, cardY + 74);
    cx.fillStyle = 'rgba(255,255,255,0.62)'; cx.font = '400 21px ' + FONT;
    cx.fillText(zei, cardX + 82, cardY + 102);
    cx.restore(); cx.restore();
  })();
  cx.globalAlpha = alpha;
  // Schnellzugriff auf die Taschenlampe unten links
  const by = ch - 150, bx1 = cw * 0.17, br = 46;
  cx.fillStyle = flashOn ? '#fff' : 'rgba(70,72,82,0.72)';
  cx.beginPath(); cx.arc(bx1, by, br, 0, 7); cx.fill();
  if (flashOn) { GLYPH_COL = '#1a1a1f'; G.torch(bx1, by, 20); GLYPH_COL = null; } // dunkel auf weissem Knopf
  else G.torch(bx1, by, 20);
  if (stable) region({ shape: 'circle', cx: bx1, cy: by, r: br, action: () => setFlashlight(!flashOn) });
  // swipe-up hint + home indicator
  const pulse = 0.45 + 0.35 * Math.sin(Date.now() / 480);
  cx.globalAlpha = alpha * pulse; cx.fillStyle = '#fff';
  cx.font = '500 24px ' + FONT; cx.fillText('Nach oben ziehen zum \u00d6ffnen', cw / 2, ch - 66);
  cx.globalAlpha = alpha; cx.beginPath();
  cx.strokeStyle = '#fff'; cx.lineWidth = 4;
  cx.moveTo(cw / 2 - 14, ch - 96); cx.lineTo(cw / 2, ch - 108); cx.lineTo(cw / 2 + 14, ch - 96); cx.stroke();
  cx.fillStyle = 'rgba(255,255,255,0.9)'; rr(cw / 2 - 78, ch - 40, 156, 11, 6); cx.fill();
  cx.restore();
}

// ---------- home screen ----------
function appIcon(a, x, y, size, label) {
  const r = size * 0.235;
  const grad = cx.createLinearGradient(x - size / 2, y - size / 2, x + size / 2, y + size / 2);
  grad.addColorStop(0, a.color); grad.addColorStop(1, darken(a.color[0] === '#' ? a.color : '#333333', 0.72));
  cx.fillStyle = grad; rr(x - size / 2, y - size / 2, size, size, r); cx.fill();
  cx.save(); G[a.glyph](x, y, size * 0.3); cx.restore();
  if (label) { cx.fillStyle = 'rgba(255,255,255,0.92)'; cx.font = '500 21px ' + FONT;
    cx.textAlign = 'center'; cx.fillText(a.name, x, y + size / 2 + 26); }
}
function drawHome(push) {
  if (wallpaperImg) drawCover(wallpaperImg); else screenBG(); // gleiche Basis wie Board = EIN "OS"
  const rg = cx.createRadialGradient(cw * 0.7, ch * 0.15, 0, cw * 0.7, ch * 0.15, cw * 0.9);
  rg.addColorStop(0, 'rgba(98,213,255,0.22)'); rg.addColorStop(1, 'rgba(98,213,255,0)');
  cx.fillStyle = rg; cx.fillRect(0, 0, cw, ch);
  // status bar
  const now = new Date();
  cx.fillStyle = '#fff'; cx.textAlign = 'left'; cx.font = '600 26px ' + FONT;
  cx.fillText(String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'), 44, 52);
  indicators(1);
  // grid (centred rows)
  const side = 54, cellW = (cw - 2 * side) / 4, size = 128, rowH = 200;
  const perRow = Math.min(4, APPS.length), top = Math.round(ch * 0.32); // optisch mittig statt oben schwimmend
  APPS.forEach((a, i) => { const col = i % perRow, row = (i / perRow) | 0;
    const x = cw / 2 + (col - (perRow - 1) / 2) * cellW, y = top + row * rowH;
    appIcon(a, x, y, size, true);
    if (a.id === 'flashlight' && flashOn) { // An-Zustand sichtbar: cyaner Ring um die Kachel
      cx.strokeStyle = ACCENT; cx.lineWidth = 4; rr(x - size / 2 - 6, y - size / 2 - 6, size + 12, size + 12, 36); cx.stroke();
    }
    a.iconRect = { x: x - size / 2, y: y - size / 2, w: size, h: size };
    if (push) region({ shape: 'rect', x: x - size / 2, y: y - size / 2 - 4, w: size, h: size + 40,
      action: () => (a.id === 'flashlight' ? setFlashlight(!flashOn) : openApp(a.id)) }); });
  cx.fillStyle = 'rgba(255,255,255,0.42)'; cx.font = '400 24px ' + FONT; cx.textAlign = 'center';
  cx.fillText('Werkprobe — tippen zum Ausprobieren', cw / 2, top + 170);
  cx.textAlign = 'left';
  // page dots + dock (full layout only)
  if (DOCK.length) {
    cx.fillStyle = 'rgba(255,255,255,0.9)'; cx.beginPath(); cx.arc(cw / 2 - 12, ch - 262, 5, 0, 7); cx.fill();
    cx.fillStyle = 'rgba(255,255,255,0.35)'; cx.beginPath(); cx.arc(cw / 2 + 12, ch - 262, 5, 0, 7); cx.fill();
    const dockY = ch - 158, dh = 168;
    cx.fillStyle = 'rgba(120,124,140,0.22)'; rr(side - 8, ch - dh - 34, cw - 2 * (side - 8), dh, 46); cx.fill();
    DOCK.forEach((a, i) => { const x = side + cellW * (i + 0.5); appIcon(a, x, dockY, size, false);
      if (push) region({ shape: 'rect', x: x - size / 2, y: dockY - size / 2, w: size, h: size,
        action: () => (a.id === 'flashlight' ? setFlashlight(!flashOn) : openApp(a.id)) }); });
  }
  cx.fillStyle = 'rgba(255,255,255,0.9)'; rr(cw / 2 - 78, ch - 40, 156, 11, 6); cx.fill();
}

// ---------- app windows (drawn in full 0..cw / 0..ch space) ----------
function appHomeIndicator() { cx.fillStyle = 'rgba(255,255,255,0.85)'; rr(cw / 2 - 78, ch - 40, 156, 11, 6); cx.fill(); }
const APP_RENDER = {
  // Anfragen-System-Demo (direkt sichtbarer Start-Screen): Status-Board mit Beispiel-Anfragen.
  anfragen(a, p) {
    screenBG();
    var now = new Date();
    cx.fillStyle = '#fff'; cx.textAlign = 'left'; cx.font = '600 26px ' + FONT;
    cx.fillText(String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'), MARGIN, 52);
    indicators(1);
    // Kopf + BEISPIEL-Pille (eine Textfarbe auf Cyan, Pille voll rund)
    cx.fillStyle = '#fff'; cx.font = '700 42px ' + FONT; cx.fillText(String(DEMO.appLabel || ''), MARGIN, 150);
    cx.font = '700 18px ' + FONT; var bad = String(DEMO.badge || 'Beispiel').toUpperCase();
    var bw = cx.measureText(bad).width + 28;
    cx.fillStyle = ACCENT; rr(cw - bw - MARGIN, 118, bw, 34, 17); cx.fill();
    cx.fillStyle = ON_ACCENT; cx.fillText(bad, cw - bw - MARGIN + 14, 142);
    cx.fillStyle = 'rgba(255,255,255,0.6)'; cx.font = '400 26px ' + FONT;
    cx.fillText(String(DEMO.untertitel || ''), MARGIN, 204);
    // Beispiel-Anfragen als Status-Karten. Raster fuellt den Schirm (kein totes unteres Drittel).
    var arr = Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [];
    var n = Math.min(arr.length, 3);
    var startY = 268, pitch = 296, cardH = 214, cardX = MARGIN, cardW = cw - 2 * MARGIN;
    for (var i = 0; i < n; i++) {
      var req = arr[i] || {}, y = startY + i * pitch, col = STAT_COLOR[req.key] || '#8a9bab';
      cx.save(); rr(cardX, y, cardW, cardH, 24); cx.clip();
      cx.fillStyle = 'rgba(255,255,255,0.075)'; cx.fillRect(cardX, y, cardW, cardH);
      // Status-Streifen als frei sitzende Pille (wird nicht von der Kartenecke angeknabbert)
      cx.fillStyle = col; rr(cardX + 18, y + 20, 6, cardH - 40, 3); cx.fill();
      cx.fillStyle = '#fff'; cx.textAlign = 'left'; cx.font = '600 34px ' + FONT;
      cx.fillText(String(req.text || ''), cardX + 46, y + 74);
      cx.fillStyle = 'rgba(255,255,255,0.42)'; cx.font = '400 22px ' + FONT; cx.textAlign = 'right';
      cx.fillText(String(req.zeit || ''), cardX + cardW - 28, y + 74); cx.textAlign = 'left'; // gleiche Baseline wie Titel
      var st = String(req.status || ''); cx.font = '600 22px ' + FONT;
      var sw = cx.measureText(st).width + 54;
      cx.fillStyle = (col.charAt(0) === '#' && col.length === 7) ? col + '2b' : 'rgba(255,255,255,0.1)';
      rr(cardX + 46, y + 110, sw, 44, 22); cx.fill();
      cx.fillStyle = col; cx.beginPath(); cx.arc(cardX + 72, y + 132, 7, 0, 7); cx.fill();
      cx.fillStyle = '#fff'; cx.fillText(st, cardX + 90, y + 140);
      cx.fillStyle = 'rgba(255,255,255,0.42)'; cx.font = '400 22px ' + FONT;
      cx.fillText('Tippen: Status weiter', cardX + 46, y + 186);
      cx.restore();
      cx.strokeStyle = 'rgba(255,255,255,0.09)'; cx.lineWidth = 1;
      rr(cardX + 0.5, y + 0.5, cardW - 1, cardH - 1, 24); cx.stroke();
      // ANKLICKBAR: Tippen schaltet den Status weiter (nur Anzeige — sendet nichts)
      if (p >= 1) region({ shape: 'rect', x: cardX, y: y, w: cardW, h: cardH, action: naechsterStatus.bind(null, i) });
    }
    // EINE Fusszeile, unten verankert, Kontrast >= 0.42 (haelt im 3/4-Winkel)
    cx.textAlign = 'center';
    cx.fillStyle = 'rgba(255,255,255,0.55)'; cx.font = '500 26px ' + FONT;
    cx.fillText('Kein Anruf, keine WhatsApp geht mehr unter.', cw / 2, ch - 150);
    cx.textAlign = 'left';
    appHomeIndicator();
  },
  generic(a, p) {
    const base = a.color[0] === '#' ? a.color : '#2a2c33';
    const g = cx.createLinearGradient(0, 0, 0, ch);
    g.addColorStop(0, darken(base, 0.55)); g.addColorStop(1, '#0c0d11');
    cx.fillStyle = g; cx.fillRect(0, 0, cw, ch);
    cx.save(); cx.globalAlpha = 0.9; appIconGlyphOnly(a, cw / 2, 190, 120); cx.restore();
    cx.fillStyle = '#fff'; cx.textAlign = 'center'; cx.font = '700 44px ' + FONT;
    cx.fillText(a.name, cw / 2, 320);
    cx.fillStyle = 'rgba(255,255,255,0.5)'; cx.font = '400 24px ' + FONT;
    cx.fillText('ge\u00f6ffnet', cw / 2, 360);
    cx.textAlign = 'left';
    for (let i = 0; i < 4; i++) { cx.fillStyle = 'rgba(255,255,255,0.07)';
      rr(50, 430 + i * 130, cw - 100, 104, 22); cx.fill();
      cx.fillStyle = 'rgba(255,255,255,0.22)'; cx.beginPath(); cx.arc(108, 482 + i * 130, 34, 0, 7); cx.fill();
      cx.fillStyle = 'rgba(255,255,255,0.5)'; rr(166, 456 + i * 130, 260, 20, 10); cx.fill();
      cx.fillStyle = 'rgba(255,255,255,0.28)'; rr(166, 492 + i * 130, 360, 16, 8); cx.fill(); }
    appHomeIndicator();
  }
};
function appIconGlyphOnly(a, x, y, size) {
  const r = size * 0.235;
  cx.fillStyle = a.color[0] === '#' ? a.color : '#333';
  rr(x - size / 2, y - size / 2, size, size, r); cx.fill();
  cx.save(); G[a.glyph](x, y, size * 0.3); cx.restore();
}
function drawAppTransition(p) {
  const a = currentApp; if (!a) return;
  const ir = a.iconRect || { x: cw / 2 - 58, y: ch / 2 - 58, w: 116, h: 116 };
  const x = lerp(ir.x, 0, p), y = lerp(ir.y, 0, p), w = lerp(ir.w, cw, p), h = lerp(ir.h, ch, p);
  const rad = lerp(26, cornerR, p);
  cx.save(); cx.beginPath(); cx.roundRect(x, y, w, h, rad); cx.clip();
  cx.translate(x, y); cx.scale(w / cw, h / ch);
  (APP_RENDER[a.id] || APP_RENDER.generic)(a, p);
  cx.restore();
}
function drawBase(s) { if (s === 'home') drawHome(false); else if (s === 'lock') drawLock(0); }

// ---------- neutrale Lautstärke- und Lautlosanzeigen ----------
function drawBell(x, y, s) {
  cx.beginPath();
  cx.moveTo(x - s * 0.8, y + s * 0.5);
  cx.quadraticCurveTo(x - s * 0.8, y - s * 0.35, x - s * 0.34, y - s * 0.6);
  cx.quadraticCurveTo(x - s * 0.34, y - s * 0.9, x, y - s * 0.9);
  cx.quadraticCurveTo(x + s * 0.34, y - s * 0.9, x + s * 0.34, y - s * 0.6);
  cx.quadraticCurveTo(x + s * 0.8, y - s * 0.35, x + s * 0.8, y + s * 0.5);
  cx.closePath(); cx.stroke();
  cx.beginPath(); cx.moveTo(x - s * 0.9, y + s * 0.5); cx.lineTo(x + s * 0.9, y + s * 0.5); cx.stroke();
  cx.beginPath(); cx.arc(x, y + s * 0.8, s * 0.16, 0, 7); cx.fill();
}
function drawVolumeHud() {
  const w = 36, x = 40, h = ch * 0.44, y = (ch - h) / 2, r = w / 2;
  cx.save();
  cx.fillStyle = 'rgba(28,30,36,0.62)'; rr(x, y, w, h, r); cx.fill();
  const lvl = muted ? 0 : volume;
  const fh = lvl <= 0 ? 0 : Math.max(w, h * lvl);
  cx.save(); rr(x, y, w, h, r); cx.clip();
  cx.fillStyle = '#f4f5f8'; cx.fillRect(x, y + h - fh, w, fh); cx.restore();
  const gx = x + w / 2, gy = y + h - 26, dark = fh > 50;
  cx.fillStyle = dark ? '#20222a' : '#f4f5f8';
  cx.beginPath(); cx.moveTo(gx - 8, gy - 4); cx.lineTo(gx - 2, gy - 4); cx.lineTo(gx + 4, gy - 10);
  cx.lineTo(gx + 4, gy + 10); cx.lineTo(gx - 2, gy + 4); cx.lineTo(gx - 8, gy + 4); cx.closePath(); cx.fill();
  if (muted || volume <= 0) { cx.strokeStyle = dark ? '#20222a' : '#f4f5f8'; cx.lineWidth = 2.8; cx.lineCap = 'round';
    cx.beginPath(); cx.moveTo(gx + 7, gy - 8); cx.lineTo(gx + 15, gy + 8); cx.stroke(); }
  cx.restore();
}
function drawMuteHud() {
  const w = 300, h = 82, x = cw / 2 - w / 2, y = 132;
  cx.save();
  cx.fillStyle = 'rgba(18,19,24,0.94)'; rr(x, y, w, h, h / 2); cx.fill();
  const ix = x + 54, iy = y + h / 2, col = muted ? '#f5a623' : '#ffffff';
  cx.strokeStyle = col; cx.fillStyle = col; cx.lineWidth = 4; cx.lineJoin = 'round'; cx.lineCap = 'round';
  drawBell(ix, iy, 19);
  if (muted) { cx.beginPath(); cx.moveTo(ix - 17, iy - 17); cx.lineTo(ix + 17, iy + 17); cx.stroke(); }
  cx.fillStyle = '#fff'; cx.font = '600 34px ' + FONT; cx.textAlign = 'left';
  cx.fillText(muted ? 'Lautlos' : 'Klingeln', x + 96, iy + 12);
  cx.restore();
}

// ---------- eigenständige Frontkamera + getrenntes Statusbanner ----------
function drawStatusBanner() {
  cx.save();
  // Kleine runde Frontkamera. Sie bleibt unabhängig vom Statusbanner.
  const cameraX = cw / 2, cameraY = 48;
  cx.fillStyle = '#080b10'; cx.beginPath(); cx.arc(cameraX, cameraY, 12, 0, 7); cx.fill();
  cx.fillStyle = '#17243a'; cx.beginPath(); cx.arc(cameraX, cameraY, 7, 0, 7); cx.fill();
  cx.fillStyle = 'rgba(130,160,210,0.55)';
  cx.beginPath(); cx.arc(cameraX - 3, cameraY - 3, 2.4, 0, 7); cx.fill();

  const visible = performance.now() < statusBannerUntil;
  if (visible) {
    const w = 410, h = 88, x = cw / 2 - w / 2, y = 82, r = 22;
    cx.fillStyle = 'rgba(12,16,23,0.96)'; rr(x, y, w, h, r); cx.fill();
    cx.strokeStyle = 'rgba(255,255,255,0.12)'; cx.lineWidth = 2; cx.stroke();
    let label = 'artur.ae', col = '#cfd3dc', icon = 'dot';
    if (statusMsg) { label = statusMsg; col = statusMsgColor; icon = 'dot'; }
    else if (flashOn) { label = 'Taschenlampe an'; col = '#fff3d0'; icon = 'torch'; }
    else if (muted) { label = 'Lautlos'; col = '#f5a623'; icon = 'bell'; }
    else if (charging) { label = 'Wird geladen · ' + Math.round(battery * 100) + '%'; col = '#37cf6a'; icon = 'bolt'; }
    const ix = x + 46, iy = y + h / 2;
    cx.strokeStyle = col; cx.fillStyle = col; cx.lineWidth = 3.4; cx.lineJoin = 'round'; cx.lineCap = 'round';
    if (icon === 'torch') { GLYPH_COL = col; G.torch(ix, iy, 15); GLYPH_COL = null; }
    else if (icon === 'bell') { drawBell(ix, iy, 15); cx.beginPath(); cx.moveTo(ix - 13, iy - 13); cx.lineTo(ix + 13, iy + 13); cx.stroke(); }
    else if (icon === 'bolt') { cx.beginPath(); cx.moveTo(ix + 3, iy - 15); cx.lineTo(ix - 7, iy + 2); cx.lineTo(ix, iy + 2); cx.lineTo(ix - 3, iy + 15); cx.lineTo(ix + 8, iy - 3); cx.lineTo(ix + 1, iy - 3); cx.closePath(); cx.fill(); }
    else { cx.beginPath(); cx.arc(ix, iy, 8, 0, 7); cx.fill(); }
    cx.fillStyle = '#fff'; cx.font = '600 30px ' + FONT; cx.textAlign = 'left'; cx.fillText(label, x + 82, iy + 10);
    if (allowHit) {
      region({
        shape: 'rect', x: x, y: y, w: w, h: h,
        action: () => { statusMsg = ''; statusBannerUntil = 0; render(); }
      });
    }
  }
  cx.restore();
}

// ---------- compositor ----------
function render() {
  regions.length = 0;
  allowHit = !anim && !drag;
  cx.setTransform(SCALE, 0, 0, SCALE, 0, 0); // logische Koordinaten, physisch in SCALE-facher Aufloesung
  cx.clearRect(0, 0, cw, ch);
  cx.save(); cx.beginPath(); cx.roundRect(1, 1, cw - 2, ch - 2, cornerR); cx.clip();
  if (anim && anim.kind === 'unlockP') { const p = lerp(anim.p0, anim.p1, ease(anim.t));
    if (p > 0) drawHome(false); drawLock(p); }
  else if (anim && anim.kind === 'appP') { const p = lerp(anim.p0, anim.p1, ease(anim.t));
    if (p < 1) drawBase(openFrom); drawAppTransition(p); }
  else if (drag && drag.kind === 'unlock') { drawHome(false); drawLock(drag.p); }
  else if (drag && drag.kind === 'closeApp') { drawBase(openFrom); drawAppTransition(1 - drag.p); }
  else if (state === 'off') { /* dark glass shows through */ }
  else if (state === 'home') drawHome(true);
  else if (state === 'app') drawAppTransition(1);
  else drawLock(0);
  if (state !== 'off') drawStatusBanner();
  const _hn = performance.now();
  if (_hn < volumeHudUntil) drawVolumeHud();
  if (_hn < muteHudUntil) drawMuteHud();
  cx.restore();
  screenTex.needsUpdate = true;
  stage.requestRender();
}
function startAnim(kind, p0, p1, dur, onDone) {
  anim = { kind, p0, p1, t: 0, dur, start: performance.now(), onDone };
  requestAnimationFrame(animTick);
}
function animTick(now) {
  if (!anim) return;
  anim.t = clamp((now - anim.start) / anim.dur, 0, 1); render();
  if (anim.t < 1) requestAnimationFrame(animTick);
  else { const d = anim.onDone; anim = null; if (d) d(); render(); }
}
function togglePower() { state = (state === 'off') ? 'lock' : 'off'; render(); }
function pokeHud() {
  if (_poking) return; _poking = true;
  (function loop() { render();
    if (performance.now() < Math.max(volumeHudUntil, muteHudUntil, statusBannerUntil)) requestAnimationFrame(loop);
    else _poking = false; })();
}
function changeVolume(d) {
  volume = clamp(volume + d, 0, 1); if (volume > 0) muted = false;
  volumeHudUntil = performance.now() + 1200; pokeHud();
}
function toggleMute() { muted = !muted; muteHudUntil = performance.now() + 1500; pokeHud(); }
function drawCover(img) {
  const s = Math.max(cw / img.width, ch / img.height);
  const w = img.width * s, h = img.height * s;
  cx.drawImage(img, (cw - w) / 2, (ch - h) / 2, w, h);
}
function setWallpaper(url) {
  if (!url) { wallpaperImg = null; render(); return; }
  const im = new Image(); im.onload = () => { wallpaperImg = im; render(); }; im.src = url;
}
function setColor(v) {
  const c = COLORS[v] || COLORS.black; currentColor = v;
  matFrame.color.set(c.frame); matButton.color.set(c.frame);
  matChamfer.color.set(c.cham); matPlateau.color.set(c.plateau);
  matBack.map = makeBackTex(c.back[0], c.back[1], c.back[2]);
  matBack.map.needsUpdate = true; matBack.needsUpdate = true;
  if (stage._scene) stage._scene.background = new THREE.Color(v === 'white' ? 0x33363d : 0xececed);
}
function charge(on) {
  charging = on === undefined ? !charging : !!on;
  if (chargeTimer) { clearInterval(chargeTimer); chargeTimer = null; }
  if (charging) chargeTimer = setInterval(() => {
    battery = Math.min(1, battery + 0.02);
    if (battery >= 1) { clearInterval(chargeTimer); chargeTimer = null; }
    render();
  }, 400);
  render();
}
function showStatusBanner() { statusBannerUntil = performance.now() + 3200; pokeHud(); }
let demoOn = false, demoTimers = [];
function demo(on) {
  demoOn = on === undefined ? !demoOn : !!on;
  demoTimers.forEach(clearTimeout); demoTimers = [];
  if (!demoOn) return;
  const seq = [
    [100, () => { state = 'off'; render(); }],
    [800, () => { state = 'lock'; render(); }],
    [1800, () => { if (state === 'lock') startAnim('unlockP', 0, 1, 300, () => { state = 'home'; }); }],
    [3000, () => setFlashlight(true)],
    [4400, () => setFlashlight(false)],
    [5200, () => changeVolume(3 / 16)],
    [5900, () => changeVolume(3 / 16)],
    [7000, () => toggleMute()],
    [8200, () => showStatusBanner()],
    [11400, () => { if (muted) toggleMute(); state = 'lock'; render(); }]
  ];
  function run() {
    seq.forEach(([t, fn]) => demoTimers.push(setTimeout(fn, t)));
    demoTimers.push(setTimeout(() => { if (demoOn) run(); }, 12800));
  }
  run();
}
function openApp(id) {
  if (id === 'flashlight') { setFlashlight(!flashOn); return; }
  const a = APP_BY_ID[id]; if (!a) return; // unbekannte id: nichts tun statt schwarzem Screen
  currentApp = a; openFrom = (state === 'app') ? openFrom : state;
  startAnim('appP', 0, 1, 340, () => { state = 'app'; });
}
// gentle repaint for the lock-screen hint pulse + clock
setInterval(() => { if (state === 'lock' && !anim && !drag) render(); }, 200);
let _lastMin = -1; // minutengenaue Uhr: rendert genau beim Minutenwechsel (statt 20-s-Raster)
setInterval(() => { if (state === 'off') return; const m = new Date().getMinutes();
  if (m !== _lastMin) { _lastMin = m; render(); } }, 1000);

// ---------- pointer interaction (touch the screen = use it; elsewhere = orbit) ----------
const dom = stage._renderer.domElement, cam = stage._camera, controls = stage._controls;
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
let ptr = null;
function pick(e) {
  const rect = dom.getBoundingClientRect();
  ndc.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
  ray.setFromCamera(ndc, cam);
  const hits = ray.intersectObjects([display, powerBtn, cameraCtrl, volUpBtn, volDownBtn, actionBtn], false);
  if (!hits.length) return {};
  const h = hits[0];
  if (h.object === display && h.uv) return { hit: 'display', px: h.uv.x * cw, py: (1 - h.uv.y) * ch };
  return { hit: 'button', name: h.object.name };
}
dom.addEventListener('pointerdown', e => {
  if (e.button && e.button !== 0) return;
  const p = pick(e);
  if (p.hit === 'display' || p.hit === 'button') {
    controls.autoRotate = false;
    ptr = { sx: p.px || 0, sy: p.py || 0, moved: false, hit: p.hit, name: p.name };
    e.stopPropagation();
  } else ptr = null;
}, true);
window.addEventListener('pointermove', e => {
  if (!ptr || ptr.hit !== 'display') return;
  const p = pick(e); if (p.hit !== 'display') return;
  const dx = p.px - ptr.sx, dy = ptr.sy - p.py;
  if (Math.abs(dx) > 7 || Math.abs(dy) > 7) ptr.moved = true;
  if (state === 'lock' && dy > 0 && ptr.sy > ch * 0.28) { drag = { kind: 'unlock', p: clamp(dy / (ch * 0.42), 0, 1) }; render(); }
  else if (state === 'app' && dy > 0 && ptr.sy > ch * 0.72) { drag = { kind: 'closeApp', p: clamp(dy / (ch * 0.5), 0, 1) }; render(); }
});
window.addEventListener('pointerup', () => {
  if (!ptr) return;
  const P = ptr, D = drag; ptr = null; drag = null;
  if (P.hit === 'button') {
    if (P.name === 'power_button') setFlashlight(!flashOn);
    else if (P.name === 'camera_control') togglePower();
    else if (P.name === 'volume_up') changeVolume(1 / 16);
    else if (P.name === 'volume_down') changeVolume(-1 / 16);
    else if (P.name === 'action_button') toggleMute();
    return;
  }
  if (!P.moved) {
    if (state === 'off') { togglePower(); return; }
    const r = hitAt(P.sx, P.sy); if (r && r.action) r.action(); render(); return;
  }
  if (D && D.kind === 'unlock') {
    if (D.p > 0.26) startAnim('unlockP', D.p, 1, 260, () => { state = 'home'; });
    else startAnim('unlockP', D.p, 0, 200, null);
  } else if (D && D.kind === 'closeApp') {
    if (D.p > 0.3) startAnim('appP', 1 - D.p, 0, 260, () => { state = openFrom; });
    else startAnim('appP', 1 - D.p, 1, 200, () => { state = 'app'; });
  } else render();
});

// ---------- öffentliche API für die neutrale Produktdemo ----------
window.ArturDemoHandy = {
  wake() { if (state === 'off') { state = 'lock'; render(); } },
  sleep() { state = 'off'; render(); },
  lock() { state = 'lock'; render(); },
  unlock() { if (state === 'lock') startAnim('unlockP', 0, 1, 300, () => { state = 'home'; }); else { state = 'home'; render(); } },
  home() { if (state === 'app') startAnim('appP', 1, 0, 260, () => { state = openFrom === 'app' ? 'home' : openFrom; }); else { state = 'home'; render(); } },
  openApp: (id) => openApp(id),
  flashlight(on) { setFlashlight(on === undefined ? !flashOn : !!on); },
  volumeUp() { changeVolume(1 / 16); },
  volumeDown() { changeVolume(-1 / 16); },
  setVolume(v) { volume = clamp(v, 0, 1); if (volume > 0) muted = false; volumeHudUntil = performance.now() + 1200; pokeHud(); },
  mute(on) { muted = on === undefined ? !muted : !!on; muteHudUntil = performance.now() + 1500; pokeHud(); },
  setColor: (v) => setColor(v),
  setWallpaper: (u) => setWallpaper(u),
  charge: (on) => charge(on),
  demo: (on) => demo(on),
  showStatusBanner: () => showStatusBanner(),
  get state() { return state; },
  get flashlightOn() { return flashOn; },
  get volume() { return volume; },
  get muted() { return muted; }
};

// Direkt die Anfragen-System-Demo zeigen (kein Sperrbildschirm davor) — "die Demos direkt zeigen".
function zeigeStart() {
  var app = APP_BY_ID['anfragen'];
  if (app) { state = 'app'; currentApp = app; openFrom = 'home'; }
  render();
}
zeigeStart();

// ---- studio environment: real reflections on metal & glass ----
(function studioEnvironment() {
  const c = document.createElement('canvas'); c.width = 1024; c.height = 512;
  const g = c.getContext('2d');
  const grad = g.createLinearGradient(0, 0, 0, 512);
  grad.addColorStop(0, '#f2f5fb'); grad.addColorStop(0.42, '#aab0bd');
  grad.addColorStop(0.52, '#6d727e'); grad.addColorStop(1, '#26282d');
  g.fillStyle = grad; g.fillRect(0, 0, 1024, 512);
  g.fillStyle = 'rgba(255,255,255,0.98)';
  g.beginPath(); g.ellipse(300, 150, 190, 96, 0, 0, 7); g.fill();
  g.beginPath(); g.ellipse(770, 120, 150, 72, 0, 0, 7); g.fill();
  g.fillStyle = 'rgba(98,213,255,0.18)'; g.beginPath(); g.ellipse(560, 200, 240, 70, 0, 0, 7); g.fill();
  g.fillStyle = 'rgba(255,255,255,0.4)'; g.beginPath(); g.ellipse(520, 430, 300, 90, 0, 0, 7); g.fill();
  const eq = new THREE.CanvasTexture(c);
  eq.mapping = THREE.EquirectangularReflectionMapping; eq.colorSpace = THREE.SRGBColorSpace;
  const pmrem = new THREE.PMREMGenerator(stage._renderer);
  const env = pmrem.fromEquirectangular(eq).texture;
  stage._scene.environment = env;
  phone.traverse(o => { if (o.material && 'envMapIntensity' in o.material) o.material.envMapIntensity = 0.55; });
  matFrame.envMapIntensity = 1.25; matBack.envMapIntensity = 0.55; matGlass.envMapIntensity = 1.6;
  matLensRing.envMapIntensity = 1.3; matPlateau.envMapIntensity = 1.15;
  matChamfer.envMapIntensity = 2.1;
  phone.traverse(o => { if (o.material) o.material.needsUpdate = true; });
  eq.dispose(); pmrem.dispose();
})();

// stand it upright, centered, base at lowest y (already centered on origin)
stage.setObject(phone);
try { stage._controls.saveState(); } catch (e) {} // Kamera-Ausgangslage fuer den Reset-Knopf

// Sicherheits-Fit: die Buehne bootet, solange .hero-phone noch display:none ist (0 Groesse).
// Der ResizeObserver greift den Sichtbar-Wechsel normal auf; als Absicherung hier nachziehen.
function heroFit() {
  try {
    var w = stage.clientWidth, h = stage.clientHeight;
    if (w && h && stage._renderer) {
      stage._renderer.setSize(w, h);
      stage._camera.aspect = w / h; stage._camera.updateProjectionMatrix();
      stage._controls.update();
      stage.requestRender();
    }
  } catch (e) {}
}
setTimeout(heroFit, 40); setTimeout(heroFit, 300);

// ---- dezenter, EINMALIGER Reveal: leises Setzen (~8 Grad -> Ruhe in 600 ms), kein Spin, kein Auto-Dreh ----
stage._controls.autoRotate = false;
phone.scale.setScalar(0.99);
const introStart = performance.now();
(function intro(now) {
  const t = clamp((now - introStart) / 600, 0, 1), e = ease(t);
  phone.rotation.y = lerp(-0.14, 0, e); // ~8 Grad, laeuft ruhig in die Ausgangslage aus
  phone.scale.setScalar(lerp(0.99, 1, e));
  stage.requestRender();
  if (t < 1) requestAnimationFrame(intro);
  else { phone.rotation.y = 0; phone.scale.setScalar(1); }
})(introStart);

// ---- EIN Knopf "Ausgangsposition": Kamera in die Startlage, Screen sperren (kein Auto-Dreh) ----
window.__heroHandy = {
  reset: function () {
    try {
      stage._controls.reset();          // zurueck zur gemerkten Kamera-Ausgangslage
      phone.rotation.y = 0;
      zeigeStart();                     // zurueck zur Anfragen-System-Demo
    } catch (e) {}
  }
};
// Reset-Knopf war bis zum fertigen Laden disabled -> jetzt freigeben (kein toter Klick waehrend Three laedt).
(function () { var rb = document.querySelector('[data-hero-reset]'); if (rb) rb.disabled = false; })();
