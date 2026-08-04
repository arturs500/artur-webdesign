const stage = document.querySelector('three-d-stage');
const { THREE } = await stage.ready;

// ---- Maße des neutralen Artur-Demo-Smartphones (Meter) — bewusst extra-schlank ----
const W = 0.0747;   // Breite
const H = 0.1562;   // Höhe
const T = 0.00564;  // Dicke (die schlanke Silhouette ist Teil des Designs)
const R = 0.0125;   // Eckenradius

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
// ---- V8.47: GEHAEUSEFARBEN fuer den Einstellungen-Reiter ----------------------
// Fuenf gedeckte Toene. Sie faerben AUSSCHLIESSLICH das 3D-Geraet (Rahmen, Fase,
// Kamera-Sockel, Rueckseiten-Textur) — Screen, Board-Palette und Seitenfarben
// bleiben unangetastet ("kein Gold im Board": Sandgold ist die GEHAEUSE-Farbe, in
// der Oberflaeche bleibt der einzige Akzent das Seiten-Cyan).
// Erster Eintrag = Auslieferungszustand (identisch mit dem bisherigen Aussehen).
const GEHAEUSE = [
  { key: 'graphit', name: 'Graphit',
    frame: 0x3c3c42, cham: 0x8a8c94, plateau: 0x2a2b31,
    punkt: '#4a4b52', back: ['#22232a', '#181920', '#0e0f13'] },
  { key: 'titan', name: 'Titan-Grau',
    frame: 0x8b8d93, cham: 0xd9dbdf, plateau: 0x6e7076,
    punkt: '#9fa2a8', back: ['#b7bac1', '#a0a3ab', '#82858d'] },
  { key: 'mitternacht', name: 'Mitternachtsblau',
    frame: 0x2e3c54, cham: 0x91a6c4, plateau: 0x24303f,
    punkt: '#3a4c6a', back: ['#27344b', '#1c2535', '#121823'] },
  { key: 'sandgold', name: 'Sandgold',
    frame: 0xc9ab7c, cham: 0xefe0c2, plateau: 0xb2946a,
    punkt: '#c9ab7c', back: ['#ddc89f', '#cab285', '#ac9167'] },
  { key: 'silber', name: 'Silber',
    frame: 0xd7d9dd, cham: 0xffffff, plateau: 0xbec1c7,
    punkt: '#d7d9dd', back: ['#eaebef', '#d6d8de', '#b7bac2'] }
];
let gehaeuse = GEHAEUSE[0].key;   // nur im Arbeitsspeicher, nichts wird gespeichert
function gehaeuseNach(key) { for (var i = 0; i < GEHAEUSE.length; i++)
  if (GEHAEUSE[i].key === key) return GEHAEUSE[i]; return GEHAEUSE[0]; }
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

// ---- Frontkamera und Kamera-Pille werden flach auf dem Display gezeichnet (siehe drawIsland) ----

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
// SCHAERFE (V8.45): Die Screen-Textur wird NICHT mehr blind in doppelter Aufloesung
// gezeichnet. Gemessen (1440x900, devicePixelRatio 2): der Screen ist auf dem Schirm nur
// ~546 x 1150 echte Bildpunkte gross. Eine 1320 x 2828 grosse Textur ist dort 2,4-fach
// ueberabgetastet -> die GPU muss verkleinern, greift dafuer in die Mipmap-Stufen 1 UND 2
// (Stufe 2 = halbe Schirmaufloesung) und mischt sie ein: genau das war der matschige,
// "verpixelte" Eindruck. Deshalb folgt SCALE jetzt der ECHTEN Darstellungsgroesse
// (Messung nach dem Kamera-Fit und bei jedem Resize), Ziel ist 1 Texel = 1 Bildpunkt.
// Die Zeichen-Koordinaten bleiben unveraendert im 660er-System: render() setzt EINMAL
// cx.setTransform(...) — Schriftgroessen und Strichstaerken werden nirgends umgerechnet.
let SCALE = 2;                 // Startwert bis zur ersten Messung (wird sofort nachgezogen)
// Untergrenze bewusst niedrig: auf Bildschirmen ohne Retina (devicePixelRatio 1) ist der
// Screen nur ~575 Bildpunkte hoch. Eine hoehere Untergrenze wuerde dort wieder eine zu
// grosse Textur erzwingen (1,5-fach) — und genau das ist die schlechteste Lage, weil die
// GPU dann zur Haelfte aus Mipmap-Stufe 1 mischt. 0,3 deckt auch die kleinste Buehne ab.
const SCALE_MIN = 0.3;
const SCALE_MAX = 2.0;         // Obergrenze: 1320 x 2828 Texel (weit unter maxTextureSize)
const UEBERABTASTUNG = 1.0;    // 1 Texel = 1 Bildpunkt -> Mipmap-Stufe 0, kein Mip-Matsch
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
// Die DATENSAETZE (Name/Meta/Nachricht/Detail) sind ZEICHENGLEICH mit app-demo.html.
// V8.46 — app-demo.html ist nachgezogen. Gleich in BEIDEN Demos:
//   Datensaetze · Neuigkeiten-Zeile (gleiche Rechnung, gleiches Wording) ·
//   Anrufen/WhatsApp mit gleicher Ansage · Status "Verloren" · Vorfuehr-Knopf mit
//   demselben Beispiel-Vorgang ("Fr. Krause (Beispiel)") und derselben 1-mal-Grenze.
// BEWUSST NICHT gleich, damit hier nichts Falsches behauptet wird:
//   1) Der LOGIN-Schirm bleibt dem Handy vorbehalten. app-demo.html sagt oben
//      ausdruecklich "ohne Anmeldung" zu, und eine Maske, die nichts prueft, waere
//      dort nur eine Huerde. Die AUSSAGE des Login-Schirms ("Firmencode, PIN,
//      Fehlversuch-Sperre") steht dort stattdessen als Satz in der Seitenleiste.
//   2) Die Oberflaeche folgt hier Arturs kunden-app-v5-demo (dunkles Theme,
//      Gruppen-Koepfe, Filter, Statistik-Reiter) — app-demo.html ist die
//      Schreibtisch-Ansicht derselben Daten auf hellem Papier. Andere Bauform,
//      gleiche Inhalte; der Farb-/Layout-Unterschied ist eine offene Design-Frage
//      fuer Artur, keine stillschweigende Abweichung.
// Nichts erfunden, alles "(Beispiel)".
const DEMO = {
  appLabel: 'Anfragen-System',
  badge: 'Beispiel',
  boardTitel: 'Anfragen',
  boardHinweis: 'Frei erfundene Datensätze für diese Demo',
  // Sperrbildschirm-Mitteilung (nur Fallback-Zustand):
  titel: 'Neue Anfrage',
  zeile: 'Paula Beispiel · über Website',
  // Anfragen wie in app-demo.html (Name, Meta-Zeile, Nachricht, Startstatus, Beispielwert).
  // detail: ZEICHENGLEICH der "Anfragedetails"-Text derselben Karte in app-demo.html.
  anfragen: [
    { name: 'Paula Beispiel', meta: 'Privat · über Website · heute, 08:42 Uhr (Beispiel)',
      nachricht: 'Seit gestern bleibt das Wasser kalt. Können Sie diese Woche vorbeikommen?',
      detail: 'Gewünschter Rückruf: vormittags. Anhang: ein fiktives Beispielfoto. In einem echten Projekt werden nur vereinbarte Felder gespeichert.',
      status: 'Neu', key: 'neu', wert: 0 },
    { name: 'Beispielwerk GmbH (fiktiv)', meta: 'Gewerbe · über Website · gestern, 16:10 Uhr (Beispiel)',
      nachricht: 'Wir planen zwei neue Waschplätze. Bitte melden Sie sich für eine Vor-Ort-Aufnahme.',
      detail: 'Ansprechperson und Betriebsgröße sind in dieser Demo frei erfunden. Echte Daten werden nicht aus Vermutungen ergänzt.',
      status: 'Neu', key: 'neu', wert: 0 },
    { name: 'Karim Beispiel', meta: 'Privat · über Empfehlung · Montag, 11:25 Uhr (Beispiel)',
      nachricht: 'Wir möchten das Bad umbauen. Welche Angaben brauchen Sie für einen Besichtigungstermin?',
      detail: 'Beispiel-Automatik: Eine freigegebene Erinnerung könnte nach drei Tagen ohne Reaktion ausgelöst werden. Der konkrete Ablauf wird vereinbart.',
      status: 'Wartend', key: 'wartend', wert: 0, followup: true },
    { name: 'Musterhof Verwaltung (fiktiv)', meta: 'Gewerbe · über Website · Freitag, 09:05 Uhr (Beispiel)',
      nachricht: 'Für vier Wohnungen steht die jährliche Wartung an. Können wir einen Sammeltermin abstimmen?',
      detail: 'Fiktiver Termin: Dienstag, 10:00 Uhr. Es gibt in dieser Demo keine Kalender-Verbindung und keine echte Benachrichtigung.',
      status: 'Termin', key: 'termin', wert: 0 },
    { name: 'Nina Demo', meta: 'Privat · über Website · 8. Juli, 14:30 Uhr (Beispiel)',
      nachricht: 'Bitte erstellen Sie ein Angebot für den Austausch von Heizkörpern in drei Räumen.',
      detail: 'Frei erfundener Auftragswert: 3.200 €. Dieser Betrag belegt weder einen echten Auftrag noch einen Erfolg des Systems.',
      status: 'Auftrag', key: 'auftrag', wert: 3200 }
  ]
};
// Demo-Farbfamilie aus app-demo.html (--demo-red/-amber/-aqua-dark/-green) —
// gleiche Status-FUELLFARBEN wie die grosse Kunden-App-Demo, kein eigener Farbkreis.
// Status "Verloren" aus der kunden-app-v5-demo (ehrlich: nicht jede Anfrage wird
// ein Auftrag); Grau-Ton 1:1 aus der v5-Quelle (#3f3f46, kein Gold).
const STAT_COLOR = { neu: '#b43b33', wartend: '#a66500', termin: '#076f78', auftrag: '#176b4b', verloren: '#3f3f46' };
// V8.45: helle Text-/Streifen-Toene derselben Familien fuer das dunkle v5-Theme
// (lesbar auf der dunklen Karte). Bewusst KEIN v5-Gelb und kein Gold — Bernstein
// bleibt gedeckt; Gruen = das vorhandene Lade-Gruen der Statusleiste (#37cf6a).
const STAT_TEXT = { neu: '#f26d64', wartend: '#e39a3b', termin: '#39c4d1', auftrag: '#37cf6a', verloren: '#8890a8' };
const STAT_NEXT = { neu: 'wartend', wartend: 'termin', termin: 'auftrag', auftrag: 'verloren', verloren: 'neu' };
const STAT_LABEL = { neu: 'Neu', wartend: 'Wartend', termin: 'Termin', auftrag: 'Auftrag', verloren: 'Verloren' };
// V8.45: dunkle Oberflaeche 1:1 aus Arturs kunden-app-v5-demo (--bg/--card/--card2/
// --text/--dim) — "1 zu 1" auf dem Handy. EIN Akzent bleibt das Seiten-Cyan
// (kein v5-Fremdblau — Markenfarbe der Seite; die Abweichung liegt Artur offen vor).
const APP_BG = '#0a0a14', APP_CARD = '#1a1a2e', APP_CARD2 = '#22223e',
      APP_LINE = 'rgba(255,255,255,0.10)', APP_INK = '#e8eaf0', APP_MUTED = '#8890a8', APP_TEXT = '#a6adc4';
function hexRgba(hex, a) { var n = parseInt(hex.slice(1), 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')'; }
function naechsterStatus(i) {
  var arr = Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [];
  var req = arr[i]; if (!req) return;
  req.key = STAT_NEXT[req.key] || 'neu';
  req.status = STAT_LABEL[req.key];
  // GLEICHES Feedback-Wording wie der Demo-Toast in app-demo.html.
  islandMsg = 'Demo-Status geändert: ' + req.status + '.'; islandMsgCol = '#cfd3dc';
  expandIsland();
  render();
}
let islandMsg = '', islandMsgCol = '#cfd3dc';
// V8.44: Anruf/WhatsApp-Knoepfe auf der Karte — wie in der kunden-app-v5-demo nur
// eine ehrliche Demo-Ansage (dort: alert), hier ueber die Kamera-Pille (islandMsg).
function anrufHinweis() {
  islandMsg = 'Echte App: hier startet der Anruf. Es wird nichts gewählt.'; islandMsgCol = '#cfd3dc';
  expandIsland(); render();
}
function whatsappHinweis() {
  islandMsg = 'Echte App: hier öffnet sich WhatsApp. Es wird nichts versendet.'; islandMsgCol = '#cfd3dc';
  expandIsland(); render();
}
// V8.44: Vorfuehr-Knopf aus der kunden-app-v5-demo ("So kommt eine neue Anfrage an").
// GENAU EIN vorbereitetes Beispiel (die 6. Anfrage), Inhalt aus der v5-Quelle
// uebernommen und klar "(Beispiel)" gekennzeichnet; sim-Markierung fuer den Reset.
var simZaehler = 0;
const SIM_BEISPIEL = {
  name: 'Fr. Krause (Beispiel)',
  meta: 'Privat · über Google Ads · gerade eben, 21:48 Uhr (Beispiel)',
  nachricht: 'Guten Abend, ich habe alte Heizkörper, ca. 60 kg. Holen Sie so etwas ab?',
  detail: 'Diese Anfrage kam über den Vorführ-Knopf herein — ein frei erfundenes Beispiel dafür, wie eine neue Anfrage oben einsortiert wird.',
  status: 'Neu', key: 'neu', wert: 0, sim: true
};
function vorfuehrAnfrage() {
  if (state !== 'app' || appView !== 'board' || boardView !== 'liste' || boardTab !== 'anfragen') return;
  if (simZaehler >= 1) { // wie v5 nach dem letzten Beispiel: ehrlich sagen, wie man zuruecksetzt
    islandMsg = 'Genug Beispiele für diese Demo.'; islandMsgCol = '#cfd3dc';
    expandIsland(); return;
  }
  simZaehler++;
  DEMO.anfragen.unshift(Object.assign({}, SIM_BEISPIEL));
  detailIndex = 0;
  activeFilter = 'alle'; // die neue Anfrage ist IMMER sichtbar (nie hinter einem Filter)
  islandMsg = 'Neue Anfrage eingetroffen (Beispiel)'; islandMsgCol = '#cfd3dc';
  expandIsland();
  if (scrollY > 0) startAnim('boardScroll', scrollY, 0, 320, function () { pokeHud(); });
  else render();
}
// Reset-Knopf raeumt die Vorfuehr-Eintraege wieder aus (Status-Aenderungen der
// Bestandskarten bleiben bewusst erhalten — Verhalten wie bisher).
// V8.47: Urzustand der Beispiel-Datensaetze (nur key+status — Namen und Texte
// aendert ohnehin niemand zur Laufzeit). Vorher raeumte demoDatenReset() NUR den
// Vorfuehr-Eintrag weg: durchgetippte Status-Pillen blieben bis zum Neuladen der
// Seite stehen, und der Reset-Knopf log damit ein Stueck weit. Jetzt stellt er den
// Auslieferungsstand wirklich wieder her.
const DEMO_URZUSTAND = (Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [])
  .map(function (a) { return { key: a.key, status: a.status }; });
function demoDatenReset() {
  DEMO.anfragen = DEMO.anfragen.filter(function (a) { return !(a && a.sim); });
  for (var ui = 0; ui < DEMO.anfragen.length && ui < DEMO_URZUSTAND.length; ui++) {
    DEMO.anfragen[ui].key = DEMO_URZUSTAND[ui].key;
    DEMO.anfragen[ui].status = DEMO_URZUSTAND[ui].status;
  }
  simZaehler = 0;
  detailIndex = 0;
}

// ---- Board-Erlebniskette (A2/A4): Liste <-> Detail + scrollbare Karten-Liste ----
// Geometrie V8.46 [BERECHNET]: Kopfleiste (ab y 118, unter der Kamera-Pille) +
// Tab-Leiste (Icons + Labels, Linie y 264,5) + Neuigkeiten (280..388) +
// Filter-Pillen (404..448) -> Sichtfenster 460..1216 = 756 px. Gruppen-Kopf 36 + 8
// (wie die v5-Abschnitte), Abstand zwischen zwei Karten 14.
//
// V8.46 — zwei GEMESSENE Fehler der V8.45-Geometrie behoben:
// 1) Das Fenster endete bei 1300, der feste Vorfuehr-Knopf lag mit 90 % deckendem
//    Grund DARAUF (1216..1280). Die Karte wurde also nicht am Fensterrand, sondern
//    mitten im Bild vom Knopf abgeschnitten — hart durch die Schrift, weil der
//    Ausblend-Verlauf 58 px tiefer (1274..1300) und damit HINTER dem Knopf lag.
//    Unter dem Knopf lugte ein 6-px-Rest derselben Karte hervor (gemessen: 1278,9
//    bis 1284,5). Jetzt endet das Fenster 16 px UEBER dem Knopf, und der Verlauf
//    liegt genau auf dieser Schnittkante (1182..1216).
// 2) Karten ohne Zusatzzeile (Beispielwert/Follow-up) waren trotzdem 248 px hoch —
//    die 28 px unter den Knoepfen waren reine Leerflaeche, bei 3 von 5 Karten.
//    Die Hoehe folgt jetzt dem Inhalt (248 mit Zusatzzeile, 220 ohne).
// ALLE Tippziele enden bei 1296 und bleiben UNTER der App-Wischgrenze 0,93*ch (~1315).
const BOARD_VIEW_T = 460;
const SIM_H = 64, SIM_Y = 1232;         // fester Vorfuehr-Knopf (1232..1296)
const BOARD_VIEW_B = SIM_Y - 16;        // 1216 — die Liste endet UEBER dem Knopf
// V8.57 [GEMESSEN] — LESBARKEIT DER RUHEANSICHT. Die Vorfuehrung endet immer in der
// Listenansicht (messwerte(): boardView 'liste', vorfuehrFertig true) — genau dieses
// Bild steht danach dauerhaft im Hero. Gemessen wurde, wie gross seine Schrift auf
// dem Schirm WIRKLICH ist: __heroHandy.screenPunkt(0.06,y) und (0.94,y) liefern die
// Seitenpixel der Screen-Kanten; daraus die Skala Canvas-Einheit -> CSS-Pixel.
// Bei 1440x900 und devicePixelRatio 1 (Buehne 440x712): 0,4077.
// Damit war die V8.47-Karte: Meta-Zeile 19 px * 0,4077 = 7,7 CSS-px, Nachricht
// 21 -> 8,6, Name 27 -> 11,0. Der Projekt-Schriftboden ist 12 px; qa_v8.py kann das
// nicht sehen, weil der Text eine Three.js-Textur ist und nicht im DOM steht.
// Ursache -> Mechanismus -> Wirkung: Die Karte war nicht nur klein, sie war auch
// INNERHALB des Geraets zu klein gesetzt — die Reiter-Beschriftungen darueber messen
// 23 px, die Nachricht in der Karte nur 21. Auf einem echten Telefon ist es
// umgekehrt (Reiterleiste ~10 pt, Fliesstext ~17 pt). Deshalb wird die Karten-
// Typografie angehoben, nicht das Geraet vergroessert (die Buehne bleibt 438x709 —
// jede Vergroesserung dort verlaengert wieder die Startseite, siehe V8.56).
// Neue Werte und ihre Wirkung auf dem Schirm: Name 33 -> 13,5 CSS-px,
// Nachricht 31 -> 12,6, Zusatzzeile 30 -> 12,2, Knopftext 29 -> 11,8,
// Meta 27 -> 11,0 (jetzt ZWEIZEILIG statt hinter "…" abgeschnitten),
// Statuspille 27 -> 11,0.
// PREIS DIESER ENTSCHEIDUNG: Die Karte waechst von 198/226 auf 348/392 (die groessere
// Schrift braucht fuer die Nachricht eine dritte Zeile, sonst haette sie Inhalt gekostet).
// V8.58: dasselbe gilt fuer den Follow-up-Hinweis der wartenden Karte — er misst bei
// 27 px 683,6 px und hat nur 466 px Platz. Er wird jetzt UMGEBROCHEN (zwei Zeilen,
// Karte 426 px) statt kleingerechnet; siehe followupZeilen().
// Rechnung fuer das 756-px-Fenster (460..1216), Filter "Alle":
//   Kopf 38 + Karte 348 + 12 + Karte 348 = 746 <= 756 -> ZWEI volle Karten statt
// drei, die dritte Zeile steht angeschnitten im Ausblend-Verlauf ("es geht weiter").
// Das ist bewusst: eine dritte unlesbare Karte ist kein Gewinn.
const BOARD_CARD_H = 392;               // Karte mit EINER Zusatzzeile (Beispielwert)
const BOARD_CARD_H_KURZ = 348;          // Karte OHNE Zusatzzeile (12 px unter den Knoepfen)
const BOARD_ZUSATZ_ZEILE = 34;          // jede WEITERE Zusatzzeile verlaengert die Karte
const BOARD_CARD_W = cw - 2 * MARGIN;   // 560 — EIN Wert fuer Layout und Zeichnung
const BOARD_GAP = 12;                   // Abstand zwischen zwei Karten
const BOARD_FADE = 64;                  // Hoehe des Ausblend-Verlaufs an der Schnittkante
const BOARD_MAX_N = 6, BOARD_HDR_H = 32, BOARD_HDR_GAP = 6, BOARD_GRP_GAP = 4, BOARD_PAD_B = 90;
let boardView = 'liste';   // 'liste' | 'detail'
let boardTab = 'anfragen'; // 'anfragen' | 'statistik' | 'einst' — "Support" bleibt inaktiv+ausgegraut
// V8.47: die beiden Schalter des Einstellungen-Reiters. Beide wirken WIRKLICH und
// sofort sichtbar — kein Schalter ohne Wirkung. Nur im Arbeitsspeicher.
let zeigeNeuZaehler = true;  // Kopf-Pille "N neu" + Zaehler am Reiter "Anfragen"
let neuesteZuerst = false;   // Reihenfolge INNERHALB jeder Gruppe umdrehen
let activeFilter = 'alle'; // 'alle' | 'neu' | 'laufend' — Filter-Pillen wie v5
var _filterRects = [];     // zuletzt gezeichnete Pillen-Flaechen (fuer Tests messbar)
let detailIndex = 0;       // welche Anfrage im Detail steht
let detailSlide = 0;       // 0 = Liste, 1 = Detail (Uebergang 280 ms)
let scrollY = 0;           // Scrollstand der Karten-Liste (0..maxScroll)
let scrollAnzeigeUntil = 0; // Scroll-Indikator blendet ~600 ms nach Ruhe aus
let ripple = null;         // kurzer Tipp-Ripple der Vorfuehr-Sequenz { x, y, start }
let lockKarteP = 1;        // Mitteilungs-Karte auf dem Sperrbildschirm: 1 = an Ort;
                           // die Vorfuehr-Sequenz faehrt sie von 12 px unterhalb ein (320 ms)
// V8.44: LOGIN-Zwischenbild als Unter-Ansicht INNERHALB von state === 'app' —
// exakt nach dem bewaehrten Muster boardView/detailSlide. KEIN neuer Hauptzustand:
// Wischzone, CTA-Bar, Abbruch und API haengen weiter allein an state.
let appView = 'board';     // 'login' | 'board'
let loginSlide = 0;        // 0 = Login, 1 = Board (Uebergang 280 ms)
let pinFuellung = 0;       // 0..1 — die 4 PIN-Punkte fuellen sich selbst (keine Tastatur)
let loginTimer = 0;        // geplanter Selbst-Login nach dem App-Oeffnen
// V8.45: gruppiertes Listen-Layout wie v5 (Abschnitts-Koepfe "Neu — noch nicht
// bearbeitet" usw.); der Filter blendet Gruppen aus. EIN Wahrheitspunkt fuer
// Zeichnung, Tippziele, maxScroll und die Vorfuehr-Sequenz.
const BOARD_GRUPPEN = [
  { key: 'neu', titel: 'Neu — noch nicht bearbeitet', stat: ['neu'] },
  { key: 'laufend', titel: 'In Bearbeitung', stat: ['wartend', 'termin'] },
  { key: 'auftrag', titel: 'Aufträge — abgeschlossen', stat: ['auftrag'] },
  { key: 'verloren', titel: 'Verloren — kein Auftrag', stat: ['verloren'] }
];
// V8.46: Die Kartenhoehe folgt dem INHALT. Nur Karten mit Zusatzzeile (Beispielwert
// beim Auftrag, Follow-up-Hinweis beim Wartenden) brauchen die vollen 248 px; ohne
// sie endete die Karte bisher 44 px unter den Knoepfen — nichts als Leerflaeche.
// EIN Wahrheitspunkt: Zeichnung, Tippziele, Layout und Ripple fragen alle hier.
function karteZusatzzeile(q) {
  if (!q) return false;
  return (q.key === 'auftrag' && Number(q.wert) > 0) || (q.key === 'wartend' && !!q.followup);
}
// V8.58: Der Follow-up-Hinweis ist der EINZIGE Kartentext, der auch bei 27 px nicht
// in eine Zeile passt (gemessen 683,6 px gegen 466 px Platz). V8.57 hatte ihn auf
// 20 px heruntergerechnet — bei 515 px Breite lief er trotzdem 29 Einheiten ueber
// den Kartenrand hinaus. Er wird deshalb umgebrochen wie Meta und Nachricht, und
// zwar bevorzugt AM GEDANKENSTRICH, damit der Satz nicht im Halbsatz reisst
// ("Follow-up verschickt —" / "Kunde hat bisher nicht geantwortet": 270,6 / 407,1 px).
// Netz fuer fremde Schriftmasse: passt die Strich-Teilung nicht, greift der normale
// Wortumbruch — die Kartenhoehe folgt in beiden Faellen der Zeilenzahl.
// Wortlaut zeichengleich zu .h2d-card__flag in index.html (2D-Ersatzweg).
const FOLLOWUP_TEXT = 'Follow-up verschickt — Kunde hat bisher nicht geantwortet';
const FU_PX = 27;                  // gleiche Groesse wie die Meta-Zeile
const FU_X = 74, FU_PAD_R = 20;    // Textanfang hinter der Uhr / Rand rechts
var _fuCache = {};
function followupZeilen(maxW) {
  if (_fuCache[maxW]) return _fuCache[maxW];
  var alt = cx.font;               // Messen darf die laufende Zeichnung nicht stoeren
  cx.font = '400 ' + FU_PX + 'px ' + FONT;
  var teile = FOLLOWUP_TEXT.split(' — '), zeilen;
  if (teile.length === 2 && cx.measureText(teile[0] + ' —').width <= maxW
      && cx.measureText(teile[1]).width <= maxW) {
    zeilen = [teile[0] + ' —', teile[1]];
  } else {
    zeilen = zeilenUmbruch(FOLLOWUP_TEXT, maxW);
  }
  cx.font = alt;
  _fuCache[maxW] = zeilen;
  return zeilen;
}
// Wie viele Zusatzzeilen traegt die Karte? (Beispielwert immer eine, Follow-up so
// viele, wie der Umbruch ergibt.) EIN Wahrheitspunkt fuer Hoehe und Zeichnung.
function zusatzZeilenZahl(q) {
  if (!karteZusatzzeile(q)) return 0;
  return q.key === 'wartend' ? followupZeilen(BOARD_CARD_W - FU_X - FU_PAD_R).length : 1;
}
function karteHoehe(q) {
  var n = zusatzZeilenZahl(q);
  return n ? BOARD_CARD_H + (n - 1) * BOARD_ZUSATZ_ZEILE : BOARD_CARD_H_KURZ;
}
function boardLayout() {
  var arr = Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [];
  var n = Math.min(arr.length, BOARD_MAX_N), items = [], y = 0;
  for (var g = 0; g < BOARD_GRUPPEN.length; g++) {
    var gr = BOARD_GRUPPEN[g];
    if (activeFilter === 'neu' && gr.key !== 'neu') continue;
    if (activeFilter === 'laufend' && gr.key !== 'laufend') continue;
    var idx = [];
    for (var i = 0; i < n; i++) { var q = arr[i] || {};
      if (gr.stat.indexOf(q.key) >= 0) idx.push(i); }
    if (!idx.length) continue;
    if (neuesteZuerst) idx.reverse();   // V8.47-Schalter: Reihenfolge in der Gruppe
    items.push({ typ: 'kopf', grp: gr, anzahl: idx.length, y: y, h: BOARD_HDR_H }); y += BOARD_HDR_H + BOARD_HDR_GAP;
    for (var k = 0; k < idx.length; k++) {
      var kh = karteHoehe(arr[idx[k]]);
      items.push({ typ: 'karte', i: idx[k], y: y, h: kh }); y += kh + BOARD_GAP; }
    y += BOARD_GRP_GAP;
  }
  return { items: items, inhalt: items.length ? y + BOARD_PAD_B : 0 };
}
function boardMaxScroll() {
  return Math.max(0, boardLayout().inhalt - (BOARD_VIEW_B - BOARD_VIEW_T));
}
// Live-Zahlen aus den Datensaetzen — EINE Schleife, EIN Wahrheitspunkt (Kopf,
// Neuigkeiten, Filter-Zaehler und Statistik-Reiter rechnen alle hierueber).
function boardZahlen() {
  var arr = Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [];
  var z = { gesamt: arr.length, offen: 0, termine: 0, wert: 0, neu: 0,
            wartFolge: 0, laufend: 0, wartend: 0, auftraege: 0, verloren: 0 };
  for (var k = 0; k < arr.length; k++) { var q = arr[k] || {};
    if (q.key === 'neu' || q.key === 'wartend' || q.key === 'termin') z.offen++;
    if (q.key === 'termin') z.termine++;
    if (q.key === 'neu') z.neu++;
    if (q.key === 'wartend') z.wartend++;
    if (q.key === 'wartend' || q.key === 'termin') z.laufend++;
    if (q.key === 'wartend' && q.followup) z.wartFolge++;
    if (q.key === 'auftrag') { z.auftraege++; z.wert += (Number(q.wert) || 0); }
    if (q.key === 'verloren') z.verloren++; }
  return z;
}
function setzeFilter(f) {
  if (activeFilter === f) return;
  activeFilter = f; scrollY = 0; render();
}
function setzeTab(t) {
  if (boardTab === t) return;
  boardTab = t; render();
}
// behalteScroll (V8.45): beim App-Schliessen/Neu-Oeffnen bleiben Scrollstand,
// Filter und Reiter erhalten (wie ein echtes Handy) — Reset-Knopf, Vorfuehr-
// Sequenz und API raeumen weiterhin VOLL auf (ohne Argument).
function boardZuruecksetzen(behalteScroll) {
  boardView = 'liste'; detailSlide = 0;
  if (!behalteScroll) { scrollY = 0; activeFilter = 'alle'; boardTab = 'anfragen'; }
  // Reset/Neu-Oeffnen landet IMMER auf dem Board — der Login haengt nie fest.
  appView = 'board'; loginSlide = 0; pinFuellung = 0;
  if (loginTimer) { clearTimeout(loginTimer); loginTimer = 0; }
}
// Der Login ERWARTET nichts (kein Tastenfeld, keine Pruefung): die PIN fuellt sich
// selbst, danach gleitet das Board herein. Beide Knoepfe fuehren zum Board.
function loginZumBoard() {
  if (state !== 'app' || appView !== 'login') return;
  if (anim && (anim.kind === 'loginSlide' || anim.kind === 'pinFuellung')) return;
  startAnim('loginSlide', 0, 1, 280, function () { appView = 'board'; loginSlide = 0; pinFuellung = 0; });
}
function einloggen(pinDauer) {
  if (state !== 'app' || appView !== 'login' || anim) return;
  startAnim('pinFuellung', 0, 1, pinDauer || 300, function () { pinFuellung = 1; loginZumBoard(); });
}
function openDetail(i) {
  if (state !== 'app' || appView !== 'board' || boardView === 'detail' || boardTab !== 'anfragen') return;
  var arr = Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [];
  if (!arr.length) return;
  detailIndex = clamp(i | 0, 0, Math.min(arr.length, BOARD_MAX_N) - 1);
  boardView = 'detail';
  startAnim('detailSlide', 0, 1, 280, function () { detailSlide = 1; });
}
function closeDetail() {
  if (boardView !== 'detail') return;
  startAnim('detailSlide', 1, 0, 280, function () { boardView = 'liste'; detailSlide = 0; });
}
// Zeilenumbruch fuer ungekuerzte Texte (Schrift VOR dem Aufruf setzen).
function zeilenUmbruch(text, maxW) {
  var worte = String(text).split(' '), zeilen = [], z = '';
  for (var i = 0; i < worte.length; i++) {
    var probe = z ? z + ' ' + worte[i] : worte[i];
    if (z && cx.measureText(probe).width > maxW) { zeilen.push(z); z = worte[i]; }
    else z = probe;
  }
  if (z) zeilen.push(z);
  return zeilen;
}

const cv = document.createElement('canvas');
cv.width = Math.round(cw * SCALE); cv.height = Math.round(ch * SCALE);
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
screenTex.colorSpace = THREE.SRGBColorSpace;
// Filter-Aufbau zur Schaerfe (V8.45):
// - anisotropy auf das Geraete-Maximum statt fest 8: beim Drehen wird der Screen
//   perspektivisch gestaucht; erst die anisotrope Filterung haelt die Schrift dann scharf.
// - Mipmaps bleiben AN (Schutz gegen Flimmern beim Drehen), verlieren aber ihre
//   Unschaerfe-Wirkung, weil die Textur dank UEBERABTASTUNG = 1.0 in der Frontalansicht
//   auf Stufe 0 landet. Vorher zwang die 2,4-fache Ueberabtastung die GPU auf Stufe 1-2.
screenTex.anisotropy = (function () {
  try { return stage._renderer.capabilities.getMaxAnisotropy() || 8; } catch (e) { return 8; }
})();
screenTex.minFilter = THREE.LinearMipmapLinearFilter;
screenTex.magFilter = THREE.LinearFilter;
screenTex.generateMipmaps = true;
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
torchBeam.userData.noFit = true; // Effekt-Kegel zaehlt NICHT fuer den Kamera-Fit (sonst Handy winzig)
phone.add(torchBeam);
let flashOn = false;
function setFlashlight(on) {
  flashOn = on;
  islandMsg = on ? '' : 'Taschenlampe aus'; islandMsgCol = '#cfd3dc';
  expandIsland(); // Kamera-Pille sagt "Taschenlampe an/aus" an — sichtbares Feedback
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
let wallpaperImg = null, currentColor = 'black', islandUntil = 0;
function region(r) { if (allowHit) regions.push(r); }
function hitAt(px, py) {
  for (let i = regions.length - 1; i >= 0; i--) { const r = regions[i];
    if (r.shape === 'circle') { if (Math.hypot(px - r.cx, py - r.cy) <= r.r) return r; }
    else if (px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h) return r; }
  return null;
}

// ---------- shared chrome ----------
function islandExpandiert() { return performance.now() < islandUntil; }
function indicators(alpha, ink) {
  // B4-Fix: waehrend die Kamera-Pille expandiert ist, setzen die Statussymbole aus
  // (wie beim Vorbild-OS) — die breite Pille ueberdeckt sonst die Signalbalken.
  if (islandExpandiert() && state !== 'off') return;
  const col = ink || '#fff';
  cx.globalAlpha = alpha; cx.fillStyle = col;
  for (let i = 0; i < 4; i++) cx.fillRect(cw - 196 + i * 12, 46 - i * 5, 8, 8 + i * 5);
  // V8.84: kein '5G'-Schriftzug mehr - dieselbe Wahrheitsregel wie die
  // 2D-Werkprobe (Signal/Akku als Form, keine konkrete Netz-Behauptung).
  cx.strokeStyle = col; cx.lineWidth = 2.5; rr(cw - 96, 30, 54, 26, 8); cx.stroke();
  cx.fillRect(cw - 40, 37, 4, 12);
  cx.fillStyle = charging ? '#37cf6a' : col; rr(cw - 92, 34, Math.max(3, 40 * battery), 18, 5); cx.fill();
  // Keine Prozentzahl: So bleibt die kompakte Statuszeile überlappungsfrei.
  if (flashOn) { // Dauer-Feedback: Taschenlampen-Glyph in der Statusleiste, solange sie an ist
    GLYPH_COL = ACCENT; G.torch(cw - 232, 42, 13); GLYPH_COL = null; // Cyan traegt auf hell UND dunkel
  }
  // Blitz immer dunkel: die Batterie-Fuellung (col) ist in beiden Themes hell genug.
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
    // A3: waehrend der Vorfuehr-Sequenz faehrt die Karte 12 px von unten ein (320 ms).
    cardY += (1 - clamp(lockKarteP, 0, 1)) * 12;
    cx.save(); cx.globalAlpha = alpha * 0.95 * clamp(lockKarteP, 0, 1);
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
  const side = 54, size = 128, rowH = 200;
  const perRow = Math.min(4, APPS.length), top = Math.round(ch * 0.32); // optisch mittig statt oben schwimmend
  const cellW = (cw - 2 * side) / perRow; // Zellbreite an echter App-Zahl ausrichten: Labels ueberlappen nie
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
function appHomeIndicator(dunkel) {
  cx.fillStyle = dunkel ? 'rgba(7,25,31,0.62)' : 'rgba(255,255,255,0.85)';
  rr(cw / 2 - 78, ch - 40, 156, 11, 6); cx.fill();
}
// ---------- Anfragen-Board: LISTE (scrollbar, A4/A5) ----------
// regionsOk: Tippziele nur im Ruhezustand registrieren (nicht waehrend Uebergaengen
// oder unter der Parallaxe-Verschiebung — dort stimmen Zeichnung und Trefferflaeche
// nicht ueberein). p ist der App-Oeffnungsfortschritt (wie bisher).
// V8.45: dunkles v5-Theme, gemeinsamer Kopf (Betrieb + Tab-Leiste) fuer Liste und
// Statistik, Filter-Pillen, gruppierte Liste mit Abschnitts-Koepfen, fester
// Vorfuehr-Knopf. V8.47: "Einst." lebt (Gehaeusefarbe + zwei echte Schalter);
// "Support" bleibt BEWUSST ausgegraut (35 %) und OHNE Tippziel — nichts Totes laedt
// zum Tippen ein, und ein Support-Kanal, den es in der Demo nicht gibt, waere
// genau so eine tote Behauptung.
function drawBoardKopf(regionsOk) {
  var now = new Date();
  if (!islandExpandiert()) { // Uhr setzt wie die Symbole aus, wenn die Pille breit ist
    cx.fillStyle = APP_INK; cx.textAlign = 'left'; cx.font = '600 26px ' + FONT;
    cx.fillText(String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'), MARGIN, 52);
  }
  indicators(1, APP_INK);
  var z = boardZahlen();
  // Betriebs-Kachel + Name NEUTRAL ("BB / Beispielbetrieb") — nie ein echter
  // Kundenname. ALLES beginnt unterhalb von y 118: die expandierte Kamera-Pille
  // endet bei y 114 und darf nie ein Kopf-Element ueberdecken (Regel B4).
  cx.fillStyle = 'rgba(98,213,255,0.15)'; cx.fillRect(MARGIN, 118, 64, 64);
  cx.fillStyle = ACCENT; cx.font = '800 26px ' + FONT; cx.textAlign = 'center';
  cx.fillText('BB', MARGIN + 32, 159);
  cx.textAlign = 'left';
  cx.fillStyle = APP_INK; cx.font = '700 28px ' + FONT;
  cx.fillText('Beispielbetrieb', MARGIN + 80, 160);
  // Pillen rechts: BEISPIEL (Cyan, aussen) + "N neu" (Demo-Rot, wie v5 — ohne Puls).
  cx.font = '700 18px ' + FONT; var bad = String(DEMO.badge || 'Beispiel').toUpperCase();
  var bw = cx.measureText(bad).width + 28;
  cx.fillStyle = ACCENT; rr(cw - bw - MARGIN, 134, bw, 34, 17); cx.fill();
  cx.fillStyle = ON_ACCENT; cx.fillText(bad, cw - bw - MARGIN + 14, 158);
  if (z.neu > 0 && zeigeNeuZaehler) {
    cx.font = '700 19px ' + FONT; var neuTxt = z.neu + ' neu';
    var nw = cx.measureText(neuTxt).width + 30, nx = cw - bw - MARGIN - 10 - nw;
    cx.fillStyle = STAT_COLOR.neu; rr(nx, 134, nw, 34, 17); cx.fill();
    cx.fillStyle = '#fff'; cx.fillText(neuTxt, nx + 15, 158);
  }
  // Ehrlichkeits-Zeile in voller Breite dort, wo v5 den Ort zeigt — ehrlicher als
  // ein erfundener Ort.
  var hin = String(DEMO.boardHinweis || ''), hpx0 = 21;
  cx.fillStyle = APP_MUTED; cx.font = '400 ' + hpx0 + 'px ' + FONT;
  while (hpx0 > 16 && cx.measureText(hin).width > cw - 2 * MARGIN) { hpx0--; cx.font = '400 ' + hpx0 + 'px ' + FONT; }
  cx.fillText(hin, MARGIN, 206);
  // Tab-Leiste mit Symbolen UEBER den Beschriftungen (wie v5). "Anfragen" und
  // "Statistik" leben (weiche Ziele: Tippen wechselt, Ziehen dreht weiter).
  var tabs = [
    { t: String(DEMO.boardTitel || 'Anfragen'), id: 'anfragen' },
    { t: 'Statistik', id: 'statistik' },
    { t: 'Einst.', id: 'einst' },   // V8.47: lebt jetzt wirklich
    { t: 'Support', id: null }
  ];
  var tabW = (cw - 2 * MARGIN) / 4;
  cx.strokeStyle = APP_LINE; cx.lineWidth = 1;
  cx.beginPath(); cx.moveTo(MARGIN, 264.5); cx.lineTo(cw - MARGIN, 264.5); cx.stroke();
  cx.textAlign = 'center';
  for (var ti = 0; ti < 4; ti++) {
    var tab = tabs[ti], tcx = MARGIN + tabW * (ti + 0.5);
    var aktiv = !!tab.id && tab.id === boardTab, tot = !tab.id;
    cx.save(); if (tot) cx.globalAlpha = 0.35;
    var farbe = aktiv ? ACCENT : APP_MUTED;
    GLYPH_COL = farbe;
    if (ti === 0) G.bubble(tcx, 222, 10);
    else if (ti === 1) G.chart(tcx, 224, 10);
    else if (ti === 2) G.gear(tcx, 222, 10);
    else { cx.strokeStyle = farbe; cx.lineWidth = 2; cx.beginPath(); cx.arc(tcx, 222, 11, 0, 7); cx.stroke();
      cx.fillStyle = farbe; cx.font = '700 17px ' + FONT; cx.fillText('?', tcx, 228); }
    GLYPH_COL = null;
    cx.fillStyle = farbe; cx.font = (aktiv ? '700 ' : '400 ') + '23px ' + FONT;
    cx.fillText(tab.t, tcx, 254);
    if (aktiv) { var twA = cx.measureText(tab.t).width;
      cx.fillStyle = ACCENT; cx.fillRect(tcx - twA / 2 - 6, 258, twA + 12, 5); }
    if (ti === 0 && z.neu > 0 && zeigeNeuZaehler) { // Zaehler wie der v5-Tab-Badge
      var tw0 = cx.measureText(tab.t).width;
      cx.fillStyle = STAT_COLOR.neu; cx.beginPath(); cx.arc(tcx + tw0 / 2 + 24, 218, 13, 0, 7); cx.fill();
      cx.fillStyle = '#fff'; cx.font = '700 17px ' + FONT; cx.fillText(String(z.neu), tcx + tw0 / 2 + 24, 224);
    }
    cx.restore();
    if (regionsOk && tab.id) region({ shape: 'rect', x: MARGIN + tabW * ti, y: 204, w: tabW, h: 60,
      soft: true, action: setzeTab.bind(null, tab.id) });
  }
  cx.textAlign = 'left';
  return z;
}
// Eine Anfrage-Karte im dunklen v5-Theme: heller Status-Streifen links, Status-
// Pille im v5-Stil (getoenter Grund + heller Punkt/Text) und Umriss-Knoepfe mit
// Symbol (V8.45: KEINE Statusfarbe mehr als Knopf-Vollflaeche — Anrufen/Auftrag
// sind nicht mehr verwechselbar).
function drawBoardKarte(req, i, y, tippbar, cardX, cardW, cardH) {
  var hell = STAT_TEXT[req.key] || '#879594';
  // V8.46: Hoehe kommt aus dem Layout (inhaltsabhaengig). Ohne Angabe selbst
  // bestimmen — der EINE Wahrheitspunkt bleibt karteHoehe().
  if (!cardH) cardH = karteHoehe(req);
  cx.fillStyle = APP_CARD; cx.fillRect(cardX, y, cardW, cardH);
  cx.strokeStyle = APP_LINE; cx.lineWidth = 1; cx.strokeRect(cardX + 0.5, y + 0.5, cardW - 1, cardH - 1);
  cx.fillStyle = hell; cx.fillRect(cardX, y, 10, cardH);
  if (req.key === 'neu') { // v5-Signal: kleiner roter Eckblock oben rechts bei "Neu"
    cx.fillStyle = STAT_TEXT.neu; cx.fillRect(cardX + cardW - 18, y, 18, 18);
  }
  // Status-Pille oben rechts — v5-Logik: getoente Statusflaeche, heller Punkt+Text.
  var st = String(req.status || ''); cx.font = '700 27px ' + FONT;
  var sw = cx.measureText(st).width + 46;
  var pillX = cardX + cardW - 24 - sw;
  cx.fillStyle = hexRgba(hell, 0.14); rr(pillX, y + 15, sw, 42, 21); cx.fill();
  cx.fillStyle = hell; cx.beginPath(); cx.arc(pillX + 21, y + 36, 7, 0, 7); cx.fill();
  cx.fillText(st, pillX + 37, y + 45);
  // Name (Titel) — erst KLEINER setzen, erst danach kuerzen. Grund: "Beispielwerk
  // GmbH (fiktiv)" und "Musterhof Verwaltung (fiktiv)" tragen den Ehrlichkeits-
  // Zusatz am ENDE; ein Abschneiden wuerde genau ihn verschlucken.
  cx.fillStyle = APP_INK;
  var nam = String(req.name || ''), maxNameW = pillX - 18 - (cardX + 34), npx = 33;
  cx.font = '600 ' + npx + 'px ' + FONT;
  while (npx > 26 && cx.measureText(nam).width > maxNameW) { npx--; cx.font = '600 ' + npx + 'px ' + FONT; }
  if (cx.measureText(nam).width > maxNameW) {
    while (nam.length > 1 && cx.measureText(nam + '…').width > maxNameW) nam = nam.slice(0, -1);
    nam = nam + '…';
  }
  cx.fillText(nam, cardX + 34, y + 56);
  // Meta-Zeile wortgleich zur Demo (mit "(Beispiel)"). V8.57: ZWEI Zeilen statt einer
  // abgeschnittenen — bei 27 px passt keine dieser Zeilen mehr in eine Kartenbreite,
  // und "(Beispiel)" ist ein Ehrlichkeits-Merkmal und kein Beiwerk.
  cx.fillStyle = APP_MUTED; cx.font = '400 27px ' + FONT;
  var maxMetaW = cardW - 34 - 20;
  var mtz = zeilenUmbruch(String(req.meta || ''), maxMetaW);
  if (mtz.length > 2) {
    var t2 = mtz[1];
    while (t2.length > 1 && cx.measureText(t2 + ' …').width > maxMetaW) t2 = t2.slice(0, -1);
    mtz = [mtz[0], t2 + ' …'];
  }
  cx.fillText(mtz[0] || '', cardX + 34, y + 100);
  if (mtz[1]) cx.fillText(mtz[1], cardX + 34, y + 134);
  // Nachricht in Anfuehrungszeichen — A5: bis zu DREI Zeilen, danach ehrlich gekuerzt.
  // V8.57: die groessere Schrift braucht eine Zeile mehr. Mit drei Zeilen steht jede
  // der sechs Beispiel-Nachrichten wieder VOLLSTAENDIG da (nachgemessen); mit zwei
  // haette die Lesbarkeit den Inhalt gekostet.
  cx.fillStyle = APP_TEXT; cx.font = '400 31px ' + FONT;
  var maxMsgW = cardW - 34 - 20;
  var mz = zeilenUmbruch('„' + String(req.nachricht || '') + '“', maxMsgW);
  if (mz.length > 3) {
    var z3 = mz[2];
    while (z3.length > 1 && cx.measureText(z3 + ' …“').width > maxMsgW) z3 = z3.slice(0, -1);
    mz = [mz[0], mz[1], z3 + ' …“'];
  }
  cx.fillText(mz[0] || '', cardX + 34, y + 180);
  if (mz[1]) cx.fillText(mz[1], cardX + 34, y + 218);
  if (mz[2]) cx.fillText(mz[2], cardX + 34, y + 256);
  // Umriss-Knoepfe wie v5 (.lead-btn.call/.wa): Symbol + Text, getoente Flaeche.
  // Breiten mit der Schrift mitgewachsen (172/200 -> 214/252); die Reihe endet bei
  // cardX+518 und bleibt damit 42 px vom rechten Kartenrand entfernt.
  var b1x = cardX + 34, b1w = 214, b2x = cardX + 266, b2w = 252, by = y + 282, bh2 = 54;
  cx.fillStyle = 'rgba(55,207,106,0.10)'; rr(b1x, by, b1w, bh2, 10); cx.fill();
  cx.strokeStyle = 'rgba(55,207,106,0.38)'; cx.lineWidth = 1.5; rr(b1x + 0.5, by + 0.5, b1w - 1, bh2 - 1, 10); cx.stroke();
  GLYPH_COL = '#37cf6a'; G.phone(b1x + 34, by + 27, 12); GLYPH_COL = null;
  cx.fillStyle = '#37cf6a'; cx.font = '600 29px ' + FONT; cx.fillText('Anrufen', b1x + 60, by + 37);
  cx.fillStyle = 'rgba(98,213,255,0.10)'; rr(b2x, by, b2w, bh2, 10); cx.fill();
  cx.strokeStyle = 'rgba(98,213,255,0.38)'; cx.lineWidth = 1.5; rr(b2x + 0.5, by + 0.5, b2w - 1, bh2 - 1, 10); cx.stroke();
  GLYPH_COL = ACCENT; G.bubble(b2x + 34, by + 27, 12); GLYPH_COL = null;
  cx.fillStyle = ACCENT; cx.fillText('WhatsApp', b2x + 60, by + 37);
  // Zusatzzeile wie v5: Beispielwert (Auftrag) ODER Follow-up-Hinweis (Wartend);
  // Bernstein gedeckt (kein Gold/Gelb). Genau diese Zeile entscheidet ueber die
  // Kartenhoehe (karteZusatzzeile/zusatzZeilenZahl) — Bedingungen UND Zeilenzahl
  // muessen mit der Hoehen-Rechnung uebereinstimmen, sonst laeuft Text aus der Karte.
  if (req.key === 'auftrag' && Number(req.wert) > 0) {
    var wtx; try { wtx = Number(req.wert).toLocaleString('de-DE'); } catch (e) { wtx = String(req.wert); }
    cx.fillStyle = STAT_TEXT.auftrag; cx.font = '700 30px ' + FONT;
    cx.fillText('Beispielwert: ' + wtx + ' €', cardX + 34, y + 378);
  } else if (req.key === 'wartend' && req.followup) {
    GLYPH_COL = STAT_TEXT.wartend; G.clock(cardX + 48, y + 368, 13); GLYPH_COL = null;
    // V8.58: umgebrochen statt kleingerechnet (siehe followupZeilen). Die Uhr bleibt
    // auf der ERSTEN Zeile; jede weitere Zeile verlaengert auch die Karte (karteHoehe).
    var fz = followupZeilen(cardW - FU_X - FU_PAD_R);
    cx.fillStyle = STAT_TEXT.wartend; cx.font = '400 ' + FU_PX + 'px ' + FONT;
    for (var fi = 0; fi < fz.length; fi++) {
      cx.fillText(fz[fi], cardX + FU_X, y + 378 + fi * BOARD_ZUSATZ_ZEILE);
    }
  }
  // A1/A2: Kartenflaeche, Status-Pille und die beiden Knoepfe sind WEICHE Tippziele
  // (soft): Tippen bedient, Ziehen faellt an die Orbit-Steuerung durch — der
  // V8.42-Fix ("Ziehen dreht immer") bleibt vollstaendig erhalten.
  // Pflicht-Guard A4: Regionen nur, wenn die Karte VOLLSTAENDIG im Sichtfenster liegt.
  if (tippbar) {
    region({ shape: 'rect', x: cardX, y: y, w: cardW, h: cardH, soft: true,
      action: openDetail.bind(null, i) }); // zuerst: spaeter registrierte Ziele gewinnen im Overlap
    region({ shape: 'rect', x: pillX - 22, y: y + 5, w: cardW - (pillX - 22 - cardX) - 6, h: 66,
      soft: true, action: naechsterStatus.bind(null, i) });
    region({ shape: 'rect', x: b1x - 6, y: by - 8, w: b1w + 12, h: bh2 + 16, soft: true, action: anrufHinweis });
    region({ shape: 'rect', x: b2x - 6, y: by - 8, w: b2w + 12, h: bh2 + 16, soft: true, action: whatsappHinweis });
  }
}
function drawBoardListe(regionsOk, p) {
  cx.fillStyle = APP_BG; cx.fillRect(0, 0, cw, ch);
  var z = drawBoardKopf(regionsOk);
  var arr = Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [];
  // ---- Neuigkeiten-Zeile (Wording 1:1 aus v5, rechnet sich aus den Datensaetzen;
  // Cyan-Ton der Seite statt v5-Fremdblau) ----
  var gruppen = [];
  if (z.neu > 0) gruppen.push([[z.neu + ' neue Anfrage' + (z.neu > 1 ? 'n' : ''), true]]);
  if (z.wartFolge > 0) gruppen.push([[z.wartFolge + ' Kunde' + (z.wartFolge > 1 ? 'n' : ''), true],
    ['wartet seit 3 Tagen auf Antwort', false]]);
  if (z.termine > 0) gruppen.push([[z.termine + ' Termin' + (z.termine > 1 ? 'e' : ''), true], ['offen', false]]);
  var token = [];
  for (var gi = 0; gi < gruppen.length; gi++) {
    if (gi) token.push(['·', false]);
    for (var si = 0; si < gruppen[gi].length; si++) {
      var ws = gruppen[gi][si][0].split(' ');
      for (var wi = 0; wi < ws.length; wi++) token.push([ws[wi], gruppen[gi][si][1]]);
    }
  }
  if (token.length) {
    var nbX = MARGIN, nbY = 280, nbW = cw - 2 * MARGIN, nbH = 108;
    cx.fillStyle = 'rgba(98,213,255,0.08)'; cx.fillRect(nbX, nbY, nbW, nbH);
    cx.strokeStyle = 'rgba(98,213,255,0.40)'; cx.lineWidth = 1;
    cx.strokeRect(nbX + 0.5, nbY + 0.5, nbW - 1, nbH - 1);
    cx.save(); cx.strokeStyle = ACCENT; cx.fillStyle = ACCENT; cx.lineWidth = 2.6;
    cx.lineJoin = 'round'; cx.lineCap = 'round'; drawBell(nbX + 30, nbY + 28, 11); cx.restore();
    cx.fillStyle = ACCENT; cx.font = '700 19px ' + FONT;
    cx.fillText('NEUIGKEITEN', nbX + 52, nbY + 37);
    var nx0 = nbX + 24, nMaxW = nbW - 48, lx = nx0, ly = nbY + 66;
    for (var tk = 0; tk < token.length; tk++) {
      cx.font = (token[tk][1] ? '700 ' : '400 ') + '23px ' + FONT;
      var wtxt = token[tk][0], wpx = cx.measureText(wtxt).width;
      if (lx > nx0 && lx + wpx > nx0 + nMaxW) { lx = nx0; ly += 29; }
      if (ly > nbY + nbH - 12) break; // Netz: nie aus dem Kasten laufen
      cx.fillStyle = token[tk][1] ? APP_INK : APP_TEXT;
      cx.fillText(wtxt, lx, ly);
      lx += wpx + cx.measureText(' ').width;
    }
  }
  // ---- Filter-Pillen wie v5 (Alle / Neu / In Bearbeitung), Zaehler live. ----
  var pills = [['alle', 'Alle', z.gesamt], ['neu', 'Neu', z.neu], ['laufend', 'In Bearbeitung', z.laufend]];
  var pX = MARGIN, pY = 404, pH = 44;
  _filterRects.length = 0;
  for (var pi = 0; pi < pills.length; pi++) {
    var pk = pills[pi][0], ptxt = pills[pi][1], pz = String(pills[pi][2]);
    var aktivP = activeFilter === pk;
    cx.font = '600 22px ' + FONT; var ptw = cx.measureText(ptxt).width;
    cx.font = '700 18px ' + FONT; var pzw = cx.measureText(pz).width + 18;
    var pw = 18 + ptw + 10 + pzw + 18;
    if (aktivP) { cx.fillStyle = ACCENT; rr(pX, pY, pw, pH, 22); cx.fill(); }
    else { cx.strokeStyle = APP_LINE; cx.lineWidth = 1.5; rr(pX + 0.5, pY + 0.5, pw - 1, pH - 1, 22); cx.stroke(); }
    cx.fillStyle = aktivP ? ON_ACCENT : APP_MUTED; cx.font = '600 22px ' + FONT;
    cx.fillText(ptxt, pX + 18, pY + 30);
    var chX = pX + 18 + ptw + 10; // Zaehler-Chip (v5 chip-count; "Neu" rot, solange nicht aktiv)
    cx.fillStyle = aktivP ? 'rgba(4,34,46,0.16)' : 'rgba(255,255,255,0.06)';
    rr(chX, pY + 9, pzw, 26, 13); cx.fill();
    cx.fillStyle = aktivP ? ON_ACCENT : (pk === 'neu' && z.neu > 0 ? STAT_TEXT.neu : APP_MUTED);
    cx.font = '700 18px ' + FONT; cx.fillText(pz, chX + 9, pY + 28);
    if (regionsOk) region({ shape: 'rect', x: pX, y: pY, w: pw, h: pH, soft: true,
      action: setzeFilter.bind(null, pk) });
    _filterRects.push({ key: pk, x: pX, y: pY, w: pw, h: pH });
    pX += pw + 10;
  }
  // ---- Liste (Gruppen-Koepfe + Karten) im Sichtfenster 460..1300. Die GANZE
  // Fensterflaeche ist EINE weiche Scroll-Region (V8.45: jeder senkrechte Zug im
  // Listenbereich scrollt — nicht nur auf vollstaendig sichtbaren Karten);
  // Tippziele bleiben an den Elementen und gewinnen als spaeter registrierte.
  var L = boardLayout();
  var maxS = Math.max(0, L.inhalt - (BOARD_VIEW_B - BOARD_VIEW_T));
  if (scrollY > maxS) scrollY = maxS; // Netz: nie ausserhalb der Klemmung zeichnen
  if (scrollY < 0) scrollY = 0;
  if (regionsOk) region({ shape: 'rect', x: 0, y: BOARD_VIEW_T, w: cw, h: BOARD_VIEW_B - BOARD_VIEW_T,
    soft: true, action: function () {} });
  var cardX = MARGIN, cardW = BOARD_CARD_W;
  cx.save(); cx.beginPath(); cx.rect(0, BOARD_VIEW_T, cw, BOARD_VIEW_B - BOARD_VIEW_T); cx.clip();
  if (!L.items.length) {
    cx.fillStyle = APP_MUTED; cx.font = '400 25px ' + FONT; cx.textAlign = 'center';
    cx.fillText('Keine Anfragen in dieser Kategorie', cw / 2, BOARD_VIEW_T + 140);
    cx.textAlign = 'left';
  }
  var HKOPF_COL = { neu: STAT_TEXT.neu, laufend: STAT_TEXT.wartend, auftrag: STAT_TEXT.auftrag, verloren: STAT_TEXT.verloren };
  for (var li = 0; li < L.items.length; li++) {
    var it = L.items[li], iy = it.y + BOARD_VIEW_T - scrollY;
    if (iy + it.h < BOARD_VIEW_T || iy > BOARD_VIEW_B) continue; // komplett ausserhalb
    if (it.typ === 'kopf') {
      cx.fillStyle = HKOPF_COL[it.grp.key] || APP_MUTED;
      cx.beginPath(); cx.arc(cardX + 8, iy + 18, 6, 0, 7); cx.fill();
      cx.fillStyle = APP_INK; cx.font = '700 19px ' + FONT;
      cx.fillText(it.grp.titel.toUpperCase(), cardX + 26, iy + 25);
      var ktw = cx.measureText(it.grp.titel.toUpperCase()).width;
      cx.fillStyle = 'rgba(255,255,255,0.06)'; rr(cardX + 26 + ktw + 12, iy + 3, 40, 26, 13); cx.fill();
      cx.fillStyle = APP_MUTED; cx.font = '700 17px ' + FONT; cx.textAlign = 'center';
      cx.fillText(String(it.anzahl), cardX + 26 + ktw + 32, iy + 22);
      cx.textAlign = 'left';
    } else {
      drawBoardKarte(arr[it.i] || {}, it.i, iy,
        regionsOk && iy >= BOARD_VIEW_T && (iy + it.h) <= BOARD_VIEW_B, cardX, cardW, it.h);
    }
  }
  // Tipp-Ripple der Vorfuehr-Sequenz (an der Karte verankert, scrollt mit)
  if (ripple) {
    var rAlter = performance.now() - ripple.start;
    if (rAlter < 340) {
      cx.save(); cx.globalAlpha = 0.35 * (1 - rAlter / 340);
      cx.fillStyle = ACCENT; cx.beginPath(); cx.arc(ripple.x, ripple.y - scrollY, 30 + rAlter * 0.4, 0, 7); cx.fill();
      cx.restore();
    }
  }
  cx.restore();
  // Dunkler Verlauf GENAU auf der Schnittkante (1182..1216), solange weiter
  // gescrollt werden kann (A4). V8.46: vorher lag er 58 px tiefer und damit hinter
  // dem deckenden Vorfuehr-Knopf — die Karte wurde deshalb hart durch die Schrift
  // geschnitten. Jetzt blendet jede angeschnittene Kartenzeile in den Grund aus.
  if (maxS > 0 && scrollY < maxS - 0.5) {
    var vg = cx.createLinearGradient(0, BOARD_VIEW_B - BOARD_FADE, 0, BOARD_VIEW_B);
    vg.addColorStop(0, 'rgba(10,10,20,0)'); vg.addColorStop(1, 'rgba(10,10,20,1)');
    cx.fillStyle = vg; cx.fillRect(0, BOARD_VIEW_B - BOARD_FADE, cw, BOARD_FADE);
  }
  // FESTER Vorfuehr-Knopf (1232..1296) UNTER dem Sichtfenster — im
  // Auslieferungszustand sichtbar, ohne die Liste anzuschneiden (V8.46; vorher lag
  // er auf der Liste). Tippziel bleibt unter der Wischgrenze (~1315).
  cx.fillStyle = 'rgba(10,10,20,0.90)'; cx.fillRect(cardX, SIM_Y, cardW, SIM_H);
  cx.save(); cx.setLineDash([10, 8]); cx.strokeStyle = APP_MUTED; cx.lineWidth = 2;
  cx.strokeRect(cardX + 1, SIM_Y + 1, cardW - 2, SIM_H - 2); cx.restore();
  var simTxt = '▶ Vorführen: So kommt eine neue Anfrage an (Beispiel)', spx = 24;
  cx.fillStyle = APP_INK; cx.font = '600 ' + spx + 'px ' + FONT; cx.textAlign = 'center';
  while (spx > 16 && cx.measureText(simTxt).width > cardW - 40) { spx--; cx.font = '600 ' + spx + 'px ' + FONT; }
  cx.fillText(simTxt, cardX + cardW / 2, SIM_Y + SIM_H / 2 + 8);
  cx.textAlign = 'left';
  if (regionsOk) region({ shape: 'rect', x: cardX, y: SIM_Y, w: cardW, h: SIM_H, soft: true, action: vorfuehrAnfrage });
  // Schlanker Scroll-Indikator (x 636, Breite 4), blendet 600 ms nach Ruhe aus.
  if (maxS > 0) {
    var sAlpha = clamp((scrollAnzeigeUntil - performance.now()) / 200, 0, 1);
    if (sAlpha > 0) {
      var bahnH = BOARD_VIEW_B - BOARD_VIEW_T;
      var thumbH = Math.max(48, bahnH * bahnH / (bahnH + maxS));
      var thumbY = BOARD_VIEW_T + (scrollY / maxS) * (bahnH - thumbH);
      cx.save(); cx.globalAlpha = 0.45 * sAlpha;
      cx.fillStyle = APP_MUTED; rr(636, thumbY, 4, thumbH, 2); cx.fill();
      cx.restore();
    }
  }
  // Bedien-Hinweis (A6) unterhalb des Fensters (y 1338) — reine Anzeige, kein
  // Tippziel; die Wischzone beginnt erst bei ~1315 und der Text stoert sie nicht.
  cx.textAlign = 'center';
  cx.fillStyle = APP_MUTED;
  var hinweis = 'Karte antippen für Details · Status-Pille tippt den Status weiter.';
  var hpx = 20; cx.font = '400 ' + hpx + 'px ' + FONT;
  while (hpx > 15 && cx.measureText(hinweis).width > cw - 2 * MARGIN) { hpx--; cx.font = '400 ' + hpx + 'px ' + FONT; }
  cx.fillText(hinweis, cw / 2, 1338);
  cx.textAlign = 'left';
  appHomeIndicator(false);
}
// ---------- Anfragen-Board: STATISTIK-Reiter (V8.45, lebt wirklich) ----------
// Kennzahlen-Kacheln (aus der Liste hierher verschoben — in v5 stehen sie im
// Statistik-Reiter, nicht in der Anfragen-Liste) + Status-Verteilung. ALLES live
// aus DEMO.anfragen berechnet — keine erfundene Historie: der v5-6-Monats-Balken
// (Beispiel-Vergangenheit) ist bewusst weggelassen.
function drawBoardStatistik(regionsOk) {
  cx.fillStyle = APP_BG; cx.fillRect(0, 0, cw, ch);
  var z = drawBoardKopf(regionsOk);
  cx.textAlign = 'center'; cx.fillStyle = APP_MUTED; cx.font = 'italic 400 22px ' + FONT;
  cx.fillText('Beispielzahlen zur Veranschaulichung', cw / 2, 302);
  cx.textAlign = 'left';
  var wertTxt; try { wertTxt = z.wert.toLocaleString('de-DE') + ' €'; } catch (e) { wertTxt = z.wert + ' €'; }
  var tiles = [['Anfragen (gesamt)', String(z.gesamt)], ['Offen', String(z.offen)],
               ['Termine', String(z.termine)], ['Beispiel-Auftragswert', wertTxt]];
  var tw2 = (cw - 2 * MARGIN - 12) / 2, th2 = 128;
  for (var t = 0; t < 4; t++) {
    var tx = MARGIN + (t % 2) * (tw2 + 12), ty = 330 + ((t / 2) | 0) * (th2 + 12);
    cx.fillStyle = APP_CARD; cx.fillRect(tx, ty, tw2, th2);
    cx.strokeStyle = APP_LINE; cx.lineWidth = 1; cx.strokeRect(tx + 0.5, ty + 0.5, tw2 - 1, th2 - 1);
    cx.fillStyle = APP_MUTED; cx.font = '400 19px ' + FONT;
    cx.fillText(tiles[t][0], tx + 18, ty + 34);
    cx.fillStyle = APP_INK; cx.font = '800 ' + (t === 3 ? 34 : 44) + 'px ' + FONT;
    cx.fillText(tiles[t][1], tx + 18, ty + 96);
  }
  // Status-Verteilung wie v5 (Punkt + Label + Zahl), live gezaehlt.
  var vY = 630, vH = 64 + 5 * 46 + 14;
  cx.fillStyle = APP_CARD; cx.fillRect(MARGIN, vY, cw - 2 * MARGIN, vH);
  cx.strokeStyle = APP_LINE; cx.lineWidth = 1; cx.strokeRect(MARGIN + 0.5, vY + 0.5, cw - 2 * MARGIN - 1, vH - 1);
  cx.fillStyle = APP_INK; cx.font = '700 25px ' + FONT;
  cx.fillText('Status-Verteilung', MARGIN + 24, vY + 42);
  var reihen = [['neu', z.neu], ['wartend', z.wartend], ['termin', z.termine],
                ['auftrag', z.auftraege], ['verloren', z.verloren]];
  for (var rzi = 0; rzi < reihen.length; rzi++) {
    var ry = vY + 64 + rzi * 46 + 14;
    cx.fillStyle = STAT_TEXT[reihen[rzi][0]]; cx.beginPath(); cx.arc(MARGIN + 34, ry - 8, 7, 0, 7); cx.fill();
    cx.fillStyle = APP_TEXT; cx.font = '400 24px ' + FONT;
    cx.fillText(STAT_LABEL[reihen[rzi][0]], MARGIN + 58, ry);
    cx.fillStyle = APP_INK; cx.font = '700 24px ' + FONT; cx.textAlign = 'right';
    cx.fillText(String(reihen[rzi][1]), cw - MARGIN - 24, ry);
    cx.textAlign = 'left';
  }
  cx.textAlign = 'center'; cx.fillStyle = APP_MUTED; cx.font = '400 20px ' + FONT;
  cx.fillText(String(DEMO.boardHinweis || ''), cw / 2, 1338);
  cx.textAlign = 'left';
  appHomeIndicator(false);
}
// ---------- Anfragen-Board: EINSTELLUNGEN-REITER (V8.47) ----------
// Arturs Wunsch: der Reiter "Einst." soll nicht mehr nur ausgegraut dastehen.
// Drei Bloecke, alle drei tun etwas ECHTES und sofort Sichtbares:
//   1) Gehaeusefarbe   -> faerbt das 3D-Geraet um (Three.js-Material, kein Bild)
//   2) Zaehler-Schalter-> blendet Kopf-Pille "N neu" + Reiter-Zaehler aus/ein
//                         (die Wirkung steht direkt darueber im selben Bild)
//   3) Reihenfolge     -> dreht die Karten innerhalb jeder Gruppe um
// Dazu ein vierter, ehrlicher Knopf: "Beispiel-Daten zuruecksetzen" (stellt getippte
// Status wieder her und raeumt den Vorfuehr-Eintrag weg).
// Nichts wird gespeichert, nichts verschickt: alles lebt nur im Arbeitsspeicher
// dieser Vorfuehrung. Genau das steht auch als Satz auf dem Schirm.
// Tippziele [BERECHNET]: Farbkreise 436..524, Schalter 696..764 und 780..848,
// Zuruecksetzen-Knopf 978..1046 — alle weit ueber der App-Wischgrenze (0,93*ch
// ~ 1315), die Wischzone unten bleibt also unberuehrt.
const EIN_SW_X = cw - MARGIN - 24 - 72;   // linke Kante der Schalter-Pille
const EIN_SW_W = 72, EIN_SW_H = 38;
function einSchalter(x, y, an) {          // Pille + Knopf, Zustand = an
  cx.fillStyle = an ? ACCENT : 'rgba(255,255,255,0.14)';
  rr(x, y, EIN_SW_W, EIN_SW_H, EIN_SW_H / 2); cx.fill();
  if (!an) { cx.strokeStyle = APP_LINE; cx.lineWidth = 1;
    rr(x + 0.5, y + 0.5, EIN_SW_W - 1, EIN_SW_H - 1, EIN_SW_H / 2); cx.stroke(); }
  cx.fillStyle = an ? ON_ACCENT : '#c9cede';
  cx.beginPath(); cx.arc(x + (an ? EIN_SW_W - 19 : 19), y + EIN_SW_H / 2, 13, 0, 7); cx.fill();
}
function einZeile(y, titel, unter, an, aktion, regionsOk) {
  // Beide Zeilen enden VOR der Schalter-Pille — Netz gegen laengere Texte.
  var maxU = EIN_SW_X - (MARGIN + 24) - 20;
  cx.fillStyle = APP_INK; var tpx = 23; cx.font = '600 ' + tpx + 'px ' + FONT;
  while (tpx > 18 && cx.measureText(titel).width > maxU) { tpx--; cx.font = '600 ' + tpx + 'px ' + FONT; }
  cx.fillText(titel, MARGIN + 24, y + 26);
  cx.fillStyle = APP_MUTED; var upx = 19; cx.font = '400 ' + upx + 'px ' + FONT;
  while (upx > 15 && cx.measureText(unter).width > maxU) { upx--; cx.font = '400 ' + upx + 'px ' + FONT; }
  cx.fillText(unter, MARGIN + 24, y + 56);
  einSchalter(EIN_SW_X, y + 8, an);
  // Weiches Ziel ueber die GANZE Zeile (Tippen schaltet, Ziehen dreht weiter).
  if (regionsOk) region({ shape: 'rect', x: MARGIN + 12, y: y - 4, w: cw - 2 * MARGIN - 24, h: 68,
    soft: true, action: aktion });
}
// Echte Aktion hinter dem Knopf im Block "Vorführung": raeumt den Vorfuehr-Eintrag
// weg UND stellt die durchgetippten Status wieder her (demoDatenReset, V8.47), sagt
// per Kamera-Pille Bescheid und laesst den Anwender im Einstellungen-Reiter stehen.
function beispielDatenZuruecksetzen() {
  demoDatenReset();
  activeFilter = 'alle'; scrollY = 0; boardView = 'liste'; detailSlide = 0;
  islandMsg = 'Beispiel-Daten zurückgesetzt.'; islandMsgCol = '#cfd3dc';
  expandIsland();
  render();
}
function drawBoardEinstellungen(regionsOk) {
  cx.fillStyle = APP_BG; cx.fillRect(0, 0, cw, ch);
  drawBoardKopf(regionsOk);
  cx.textAlign = 'center'; cx.fillStyle = APP_MUTED; cx.font = 'italic 400 22px ' + FONT;
  cx.fillText('Beispiel-Einstellungen dieser Vorführung', cw / 2, 302);
  cx.textAlign = 'left';
  // ---- Block 1: Gehaeusefarbe ----
  var k1Y = 330, k1H = 270;
  cx.fillStyle = APP_CARD; cx.fillRect(MARGIN, k1Y, cw - 2 * MARGIN, k1H);
  cx.strokeStyle = APP_LINE; cx.lineWidth = 1;
  cx.strokeRect(MARGIN + 0.5, k1Y + 0.5, cw - 2 * MARGIN - 1, k1H - 1);
  cx.fillStyle = APP_INK; cx.font = '700 25px ' + FONT;
  cx.fillText('Gehäusefarbe', MARGIN + 24, k1Y + 42);
  cx.fillStyle = APP_MUTED; cx.font = '400 19px ' + FONT;
  cx.fillText('Ändert das Gerät in dieser 3D-Ansicht sofort.', MARGIN + 24, k1Y + 74);
  var swR = 38, swMid = k1Y + 150, sw0 = MARGIN + 24 + swR, swAbst = 109;
  for (var gi = 0; gi < GEHAEUSE.length; gi++) {
    var gf = GEHAEUSE[gi], gx = sw0 + gi * swAbst, gewaehlt = gf.key === gehaeuse;
    cx.fillStyle = gf.punkt;
    cx.beginPath(); cx.arc(gx, swMid, swR, 0, 7); cx.fill();
    cx.strokeStyle = 'rgba(255,255,255,0.22)'; cx.lineWidth = 1.5;
    cx.beginPath(); cx.arc(gx, swMid, swR - 0.75, 0, 7); cx.stroke();
    if (gewaehlt) { cx.strokeStyle = ACCENT; cx.lineWidth = 3;
      cx.beginPath(); cx.arc(gx, swMid, swR + 8, 0, 7); cx.stroke(); }
    if (regionsOk) region({ shape: 'rect', x: gx - swR - 6, y: swMid - swR - 6,
      w: 2 * (swR + 6), h: 2 * (swR + 6), soft: true, action: setzeGehaeuse.bind(null, gf.key) });
  }
  cx.textAlign = 'center'; cx.fillStyle = APP_TEXT; cx.font = '600 22px ' + FONT;
  cx.fillText('Gewählt: ' + gehaeuseNach(gehaeuse).name, cw / 2, k1Y + 236);
  cx.textAlign = 'left';
  // ---- Block 2: zwei echte Schalter ----
  var k2Y = 624, k2H = 248;
  cx.fillStyle = APP_CARD; cx.fillRect(MARGIN, k2Y, cw - 2 * MARGIN, k2H);
  cx.strokeStyle = APP_LINE; cx.lineWidth = 1;
  cx.strokeRect(MARGIN + 0.5, k2Y + 0.5, cw - 2 * MARGIN - 1, k2H - 1);
  cx.fillStyle = APP_INK; cx.font = '700 25px ' + FONT;
  cx.fillText('Anzeige', MARGIN + 24, k2Y + 42);
  einZeile(k2Y + 76, 'Zähler für neue Anfragen', 'Pille im Kopf und am Reiter',
    zeigeNeuZaehler, function () { zeigeNeuZaehler = !zeigeNeuZaehler; render(); }, regionsOk);
  einZeile(k2Y + 160, 'Neueste Anfrage zuerst', 'Reihenfolge in jeder Gruppe',
    neuesteZuerst, function () { neuesteZuerst = !neuesteZuerst; scrollY = 0; render(); }, regionsOk);
  // ---- Block 3: Vorfuehrung zuruecksetzen (echte Aktion) ----
  var k3Y = 896, k3H = 148;
  cx.fillStyle = APP_CARD; cx.fillRect(MARGIN, k3Y, cw - 2 * MARGIN, k3H);
  cx.strokeStyle = APP_LINE; cx.lineWidth = 1;
  cx.strokeRect(MARGIN + 0.5, k3Y + 0.5, cw - 2 * MARGIN - 1, k3H - 1);
  cx.fillStyle = APP_INK; cx.font = '700 25px ' + FONT;
  cx.fillText('Vorführung', MARGIN + 24, k3Y + 42);
  cx.fillStyle = APP_MUTED; cx.font = '400 19px ' + FONT;
  cx.fillText('Getippte Status und das Vorführ-Beispiel zurücksetzen.', MARGIN + 24, k3Y + 72);
  var zbX = MARGIN + 24, zbY = k3Y + 88, zbW = cw - 2 * MARGIN - 48, zbH = 48;
  cx.fillStyle = 'rgba(98,213,255,0.10)'; rr(zbX, zbY, zbW, zbH, 10); cx.fill();
  cx.strokeStyle = 'rgba(98,213,255,0.44)'; cx.lineWidth = 1.5;
  rr(zbX + 0.5, zbY + 0.5, zbW - 1, zbH - 1, 10); cx.stroke();
  cx.fillStyle = ACCENT; cx.font = '600 22px ' + FONT; cx.textAlign = 'center';
  cx.fillText('Beispiel-Daten zurücksetzen', cw / 2, zbY + 32);
  cx.textAlign = 'left';
  if (regionsOk) region({ shape: 'rect', x: zbX - 6, y: zbY - 6, w: zbW + 12, h: zbH + 12,
    soft: true, action: beispielDatenZuruecksetzen });
  // ---- Ehrlichkeits-Block (kein Tippziel) ----
  var eY = 1068;
  cx.strokeStyle = 'rgba(98,213,255,0.40)'; cx.lineWidth = 1;
  cx.strokeRect(MARGIN + 0.5, eY + 0.5, cw - 2 * MARGIN - 1, 144 - 1);
  cx.fillStyle = 'rgba(98,213,255,0.06)'; cx.fillRect(MARGIN, eY, cw - 2 * MARGIN, 144);
  cx.fillStyle = ACCENT; cx.font = '700 19px ' + FONT;
  cx.fillText('NUR EIN BEISPIEL', MARGIN + 24, eY + 38);
  cx.fillStyle = APP_TEXT; cx.font = '400 20px ' + FONT;
  var eZeilen = zeilenUmbruch('Diese Einstellungen leben nur in dieser Vorführung. '
    + 'Es wird nichts gespeichert und nichts verschickt.', cw - 2 * MARGIN - 48);
  for (var ez = 0; ez < eZeilen.length && ez < 3; ez++)
    cx.fillText(eZeilen[ez], MARGIN + 24, eY + 76 + ez * 28);
  cx.textAlign = 'center'; cx.fillStyle = APP_MUTED; cx.font = '400 20px ' + FONT;
  cx.fillText(String(DEMO.boardHinweis || ''), cw / 2, 1338);
  cx.textAlign = 'left';
  appHomeIndicator(false);
}
// ---------- Anfragen-App: LOGIN-Zwischenbild (V8.44) ----------
// Aufbau und Wording 1:1 aus Arturs kunden-app-v5-demo.html (Login-Schirm), Farben
// in der Board-Palette: EIN Akzent (Seiten-Cyan), kein v5-Fremdblau, kein Gelb/Gold,
// Firmencode NEUTRAL "Beispielbetrieb" (nie ein echter Kundenname). Der Schirm
// ERWARTET nichts: keine Tastatur, keine PIN-Pruefung, keine Fehlerzeile — die PIN
// fuellt sich selbst, beide Knoepfe fuehren zum Board (weiche Ziele: Ziehen dreht).
function drawLogin(regionsOk, p) {
  cx.fillStyle = APP_BG; cx.fillRect(0, 0, cw, ch);
  var now = new Date();
  if (!islandExpandiert()) {
    cx.fillStyle = APP_INK; cx.textAlign = 'left'; cx.font = '600 26px ' + FONT;
    cx.fillText(String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'), MARGIN, 52);
  }
  indicators(1, APP_INK);
  // BEISPIEL-Pille oben rechts wie auf dem Board — Ehrlichkeit ab dem ersten Bild.
  cx.font = '700 18px ' + FONT; var bad = String(DEMO.badge || 'Beispiel').toUpperCase();
  var bw = cx.measureText(bad).width + 28;
  cx.fillStyle = ACCENT; rr(cw - bw - MARGIN, 118, bw, 34, 17); cx.fill();
  cx.fillStyle = ON_ACCENT; cx.textAlign = 'left'; cx.fillText(bad, cw - bw - MARGIN + 14, 142);
  // App-Zeichen 112 px (v5: 64 px x 1,75) — Form/Groesse 1:1, Farbe Seiten-Akzent.
  var icoS = 112, icoY = 290;
  cx.fillStyle = ACCENT; rr(cw / 2 - icoS / 2, icoY, icoS, icoS, 28); cx.fill();
  cx.strokeStyle = ON_ACCENT; cx.lineWidth = 7; cx.lineJoin = 'round'; cx.lineCap = 'round';
  rr(cw / 2 - 26, icoY + 19, 52, 74, 10); cx.stroke();
  cx.fillStyle = ON_ACCENT; cx.beginPath(); cx.arc(cw / 2, icoY + 79, 4.5, 0, 7); cx.fill();
  // Titel + Untertitel (Wording 1:1 aus v5).
  cx.fillStyle = APP_INK; cx.textAlign = 'center'; cx.font = '800 36px ' + FONT;
  cx.fillText('Kunden-Manager', cw / 2, 470);
  cx.fillStyle = APP_MUTED; cx.font = '400 26px ' + FONT;
  cx.fillText('Melden Sie sich mit Ihrem Firmencode an', cw / 2, 514);
  cx.textAlign = 'left';
  var fx = MARGIN, fw = cw - 2 * MARGIN;
  // Feld 1: Firmencode (readonly wie v5) — Wert neutral.
  cx.fillStyle = APP_MUTED; cx.font = '600 24px ' + FONT; cx.fillText('Firmencode', fx, 580);
  cx.fillStyle = APP_CARD; cx.fillRect(fx, 596, fw, 84);
  cx.strokeStyle = APP_LINE; cx.lineWidth = 1; cx.strokeRect(fx + 0.5, 596.5, fw - 1, 83);
  cx.fillStyle = APP_INK; cx.font = '600 30px ' + FONT; cx.fillText('Beispielbetrieb', fx + 26, 649);
  // Feld 2: PIN — 4 Punkte, die sich selbst fuellen (pinFuellung 0..1).
  cx.fillStyle = APP_MUTED; cx.font = '600 24px ' + FONT; cx.fillText('PIN', fx, 724);
  cx.fillStyle = APP_CARD; cx.fillRect(fx, 740, fw, 84);
  cx.strokeStyle = APP_LINE; cx.strokeRect(fx + 0.5, 740.5, fw - 1, 83);
  var punkte = Math.round(clamp(pinFuellung, 0, 1) * 4);
  for (var d = 0; d < 4; d++) {
    var dx0 = fx + 44 + d * 56, dy0 = 782;
    if (d < punkte) { cx.fillStyle = APP_INK; cx.beginPath(); cx.arc(dx0, dy0, 11, 0, 7); cx.fill(); }
    else { cx.strokeStyle = APP_MUTED; cx.lineWidth = 2; cx.beginPath(); cx.arc(dx0, dy0, 11, 0, 7); cx.stroke(); }
  }
  // Knopf 1 "Einloggen →" (Form 1:1, Farbe Seiten-Akzent) + Knopf 2 — der ehrliche
  // Zweit-Weg "Demo ansehen — ohne PIN" (Wording 1:1).
  var b1y = 868, bh = 80;
  cx.fillStyle = ACCENT; cx.fillRect(fx, b1y, fw, bh);
  cx.fillStyle = ON_ACCENT; cx.font = '700 27px ' + FONT; cx.textAlign = 'center';
  cx.fillText('Einloggen →', cw / 2, b1y + 51);
  var b2y = 972;
  cx.fillStyle = APP_CARD; cx.fillRect(fx, b2y, fw, bh);
  cx.strokeStyle = APP_LINE; cx.strokeRect(fx + 0.5, b2y + 0.5, fw - 1, bh - 1);
  cx.fillStyle = APP_INK; cx.font = '600 27px ' + FONT;
  cx.fillText('Demo ansehen — ohne PIN', cw / 2, b2y + 51);
  cx.textAlign = 'left';
  if (regionsOk) {
    region({ shape: 'rect', x: fx, y: b1y, w: fw, h: bh, soft: true,
      action: function () { if (loginTimer) { clearTimeout(loginTimer); loginTimer = 0; } einloggen(300); } });
    region({ shape: 'rect', x: fx, y: b2y, w: fw, h: bh, soft: true,
      action: function () { if (loginTimer) { clearTimeout(loginTimer); loginTimer = 0; } loginZumBoard(); } });
  }
  // Hinweis (v5-Halbsatz ohne "Demo-PIN 1234" — es gibt hier nichts einzutippen).
  cx.fillStyle = APP_MUTED; cx.font = '400 25px ' + FONT;
  var hz = zeilenUmbruch('Die echte App ist durch Firmencode, PIN und Fehlversuch-Sperre geschützt.', fw);
  cx.textAlign = 'center';
  for (var hi = 0; hi < hz.length && hi < 2; hi++) cx.fillText(hz[hi], cw / 2, 1092 + hi * 34);
  // Vorfuehr-Kasten: Text 1:1 aus v5, Cyan-Rahmen statt Gelb (kein Gold im Board).
  var wkY = 1180, wkH = 116;
  cx.fillStyle = 'rgba(98,213,255,0.10)'; cx.fillRect(fx, wkY, fw, wkH);
  cx.strokeStyle = 'rgba(98,213,255,0.45)'; cx.lineWidth = 1; cx.strokeRect(fx + 0.5, wkY + 0.5, fw - 1, wkH - 1);
  cx.fillStyle = APP_TEXT; cx.font = '600 24px ' + FONT;
  var wz = zeilenUmbruch('Dies ist eine Vorführ-Version mit Beispieldaten — keine echten Kundendaten.', fw - 48);
  for (var wi2 = 0; wi2 < wz.length && wi2 < 3; wi2++) cx.fillText(wz[wi2], cw / 2, wkY + 44 + wi2 * 32);
  cx.textAlign = 'left';
  appHomeIndicator(false);
}

// ---------- Anfragen-Board: DETAIL ("Anfragedetails", A2) ----------
// Inhalte ZEICHENGLEICH aus app-demo.html (Name/Meta/Nachricht/Detailtext) —
// nichts erfunden. Farben ausschliesslich die Demo-Palette (kein Gold).
function drawBoardDetail(regionsOk) {
  var arr = Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [];
  var req = arr[detailIndex] || {};
  var col = STAT_TEXT[req.key] || '#879594'; // V8.45: helle Statusfamilie auf dunklem Grund
  cx.fillStyle = APP_BG; cx.fillRect(0, 0, cw, ch);
  var now = new Date();
  if (!islandExpandiert()) {
    cx.fillStyle = APP_INK; cx.textAlign = 'left'; cx.font = '600 26px ' + FONT;
    cx.fillText(String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0'), MARGIN, 52);
  }
  indicators(1, APP_INK);
  // Zurueck-Zeile — HARTES Tippziel (x 34..260, y 92..164; >= 44 px hoch).
  // V8.57: dieselbe Schrift-Anhebung wie in der Liste. Sonst waere der Detail-Text
  // (23 px = 9,4 CSS-px) nach dem Antippen KLEINER als die Karte, aus der er kommt.
  cx.fillStyle = APP_INK; cx.textAlign = 'left'; cx.font = '600 34px ' + FONT;
  cx.fillText('‹ Anfragen', MARGIN, 142);
  if (regionsOk) region({ shape: 'rect', x: 34, y: 92, w: 260, h: 72, action: closeDetail });
  // Name (Schrift schrumpft, bevor sie den Rand beruehrt) + Meta-Zeile.
  var nam = String(req.name || ''), npx = 44;
  cx.font = '700 ' + npx + 'px ' + FONT;
  while (npx > 30 && cx.measureText(nam).width > cw - 2 * MARGIN) { npx--; cx.font = '700 ' + npx + 'px ' + FONT; }
  cx.fillText(nam, MARGIN, 242);
  // Meta ZWEIZEILIG (wie in der Liste): bei 27 px passt keine dieser Zeilen mehr in
  // eine Breite, und "(Beispiel)" steht am Ende — abschneiden verboten.
  cx.fillStyle = APP_MUTED; cx.font = '400 27px ' + FONT;
  var maxMetaW = cw - 2 * MARGIN;
  var metZ = zeilenUmbruch(String(req.meta || ''), maxMetaW);
  if (metZ.length > 2) {
    var m2 = metZ[1];
    while (m2.length > 1 && cx.measureText(m2 + ' …').width > maxMetaW) m2 = m2.slice(0, -1);
    metZ = [metZ[0], m2 + ' …'];
  }
  cx.fillText(metZ[0] || '', MARGIN, 288);
  if (metZ[1]) cx.fillText(metZ[1], MARGIN, 322);
  // Status-Pille — WEICHES Tippziel wie in der Liste (Aktion: Status weitertippen).
  var st = String(req.status || ''); cx.font = '700 27px ' + FONT;
  var sw = cx.measureText(st).width + 64, pillY = 356, pillH = 52;
  cx.fillStyle = APP_CARD; rr(MARGIN, pillY, sw, pillH, 8); cx.fill();
  cx.strokeStyle = APP_LINE; cx.lineWidth = 1; rr(MARGIN + 0.5, pillY + 0.5, sw - 1, pillH - 1, 8); cx.stroke();
  cx.fillStyle = col; cx.beginPath(); cx.arc(MARGIN + 24, pillY + 26, 8, 0, 7); cx.fill();
  cx.fillStyle = APP_INK; cx.fillText(st, MARGIN + 44, pillY + 36);
  if (regionsOk) region({ shape: 'rect', x: MARGIN - 8, y: pillY - 8, w: sw + 16, h: pillH + 16,
    soft: true, action: naechsterStatus.bind(null, detailIndex) });
  // Nachricht UNGEKUERZT — weisse Karte mit Status-Streifen links (wie die Liste).
  var innenX = MARGIN + 34, innenW = cw - 2 * MARGIN - 34 - 20;
  cx.font = '400 31px ' + FONT;
  var mZeilen = zeilenUmbruch('„' + String(req.nachricht || '') + '“', innenW);
  var msgY = 442, mH = 34 + mZeilen.length * 40 + 18;
  cx.fillStyle = APP_CARD; cx.fillRect(MARGIN, msgY, cw - 2 * MARGIN, mH);
  cx.strokeStyle = APP_LINE; cx.strokeRect(MARGIN + 0.5, msgY + 0.5, cw - 2 * MARGIN - 1, mH - 1);
  cx.fillStyle = col; cx.fillRect(MARGIN, msgY, 10, mH);
  cx.fillStyle = APP_TEXT;
  for (var mi = 0; mi < mZeilen.length; mi++) cx.fillText(mZeilen[mi], innenX, msgY + 46 + mi * 40);
  // Weisse Karte "Anfragedetails" mit dem zeichengleichen Demo-Text.
  var dY = msgY + mH + 26;
  cx.font = '400 30px ' + FONT;
  var dZeilen = zeilenUmbruch(String(req.detail || ''), innenW);
  var dH = 66 + dZeilen.length * 38 + 20;
  cx.fillStyle = APP_CARD; cx.fillRect(MARGIN, dY, cw - 2 * MARGIN, dH);
  cx.strokeStyle = APP_LINE; cx.strokeRect(MARGIN + 0.5, dY + 0.5, cw - 2 * MARGIN - 1, dH - 1);
  cx.fillStyle = APP_INK; cx.font = '700 30px ' + FONT;
  cx.fillText('Anfragedetails', innenX, dY + 44);
  cx.fillStyle = APP_TEXT; cx.font = '400 30px ' + FONT;
  for (var di = 0; di < dZeilen.length; di++) cx.fillText(dZeilen[di], innenX, dY + 90 + di * 38);
  // Fusszeile wie die Liste: der Ehrlichkeits-Hinweis der Demo (V8.45: y 1338,
  // gleiche Zeile wie im Listen-Bild — unterhalb des frueheren 1104er-Fensters).
  cx.textAlign = 'center'; cx.fillStyle = APP_MUTED; cx.font = '400 26px ' + FONT;
  cx.fillText(String(DEMO.boardHinweis || ''), cw / 2, 1338);
  cx.textAlign = 'left';
  appHomeIndicator(false);
}

const APP_RENDER = {
  // Anfragen-System-Demo: DIESELBEN Datensaetze wie app-demo.html; die Oberflaeche
  // folgt seit V8.44/45 bewusst der kunden-app-v5-demo (dunkles Theme, Login,
  // Neuigkeiten, Filter, Statistik-Reiter) — siehe Hinweis am DEMO-Block oben.
  // A2: Liste <-> Detail. Waehrend des 280-ms-Uebergangs schiebt das Detail von
  // rechts herein, die Liste faehrt -0,3*cw Parallaxe nach links (wie im Vorbild-OS).
  anfragen(a, p) {
    // V8.44: LOGIN-Zwischenbild zuerst (Unter-Ansicht appView). Waehrend des 280-ms-
    // Uebergangs schiebt das Board von rechts herein, der Login faehrt -0,3*cw
    // Parallaxe nach links — exakt das bewaehrte Liste<->Detail-Muster.
    if (appView === 'login') {
      if (loginSlide <= 0) { drawLogin(p >= 1, p); return; }
      cx.save(); cx.translate(-0.3 * cw * loginSlide, 0); drawLogin(false, p); cx.restore();
      cx.save(); cx.translate((1 - loginSlide) * cw, 0); drawBoardListe(false, p); cx.restore();
      return;
    }
    // V8.45: lebender Statistik-Reiter (Detail gibt es nur im Anfragen-Reiter).
    if (boardTab === 'statistik') { drawBoardStatistik(p >= 1); return; }
    // V8.47: lebender Einstellungen-Reiter (Gehaeusefarbe + zwei echte Schalter).
    if (boardTab === 'einst') { drawBoardEinstellungen(p >= 1); return; }
    if (boardView === 'detail' && detailSlide >= 1) { drawBoardDetail(p >= 1); return; }
    if (detailSlide > 0) {
      cx.save(); cx.translate(-0.3 * cw * detailSlide, 0); drawBoardListe(false, p); cx.restore();
      cx.save(); cx.translate((1 - detailSlide) * cw, 0); drawBoardDetail(false); cx.restore();
      return;
    }
    drawBoardListe(p >= 1, p);
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

// ---------- flache Kamera-Aussparung + Frontkamera (auf dem Display gezeichnet) ----------
function drawIsland() {
  const expanded = islandExpandiert();
  // Breite dynamisch am Text, Deckel 470 px — und weil indicators()/Uhr waehrend
  // der Expansion aussetzen (B4), ueberdeckt die breite Pille nie ein Symbol.
  let w = 150, fontPx = 28;
  if (expanded) {
    let label = islandMsg || (flashOn ? 'Taschenlampe an' : (muted ? 'Lautlos'
      : (charging ? 'Wird geladen' : 'artur.ae')));
    cx.font = '600 ' + fontPx + 'px ' + FONT;
    while (fontPx > 21 && cx.measureText(label).width + 106 > 470) { fontPx--; cx.font = '600 ' + fontPx + 'px ' + FONT; }
    w = clamp(cx.measureText(label).width + 106, 320, 470);
  }
  // Hoehe 84 statt 96: Unterkante 114 bleibt klar UEBER der BEISPIEL-Pille (y 118).
  const h = expanded ? 84 : 46, x = cw / 2 - w / 2, y = 30, r = expanded ? 42 : 23;
  cx.save();
  cx.fillStyle = '#000'; rr(x, y, w, h, r); cx.fill();
  // Front-Kamera an FESTER Position — die Pille waechst um sie herum
  const lx = cw / 2 + 42, ly = 53;
  cx.fillStyle = '#0b0e15'; cx.beginPath(); cx.arc(lx, ly, 12, 0, 7); cx.fill();
  cx.fillStyle = '#16233a'; cx.beginPath(); cx.arc(lx, ly, 7, 0, 7); cx.fill();
  cx.fillStyle = 'rgba(130,160,210,0.55)'; cx.beginPath(); cx.arc(lx - 3, ly - 3, 2.4, 0, 7); cx.fill();
  if (expanded) {
    let label = 'artur.ae', col = '#cfd3dc', icon = 'dot';
    if (islandMsg) { label = islandMsg; col = islandMsgCol; icon = 'dot'; }
    else if (flashOn) { label = 'Taschenlampe an'; col = '#fff3d0'; icon = 'torch'; }
    else if (muted) { label = 'Lautlos'; col = '#f5a623'; icon = 'bell'; }
    else if (charging) { label = 'Wird geladen'; col = '#37cf6a'; icon = 'bolt'; }
    const ix = x + 46, iy = y + h / 2;
    cx.strokeStyle = col; cx.fillStyle = col; cx.lineWidth = 3.4; cx.lineJoin = 'round'; cx.lineCap = 'round';
    if (icon === 'torch') { GLYPH_COL = col; G.torch(ix, iy, 15); GLYPH_COL = null; }
    else if (icon === 'bell') { drawBell(ix, iy, 15); cx.beginPath(); cx.moveTo(ix - 13, iy - 13); cx.lineTo(ix + 13, iy + 13); cx.stroke(); }
    else if (icon === 'bolt') { cx.beginPath(); cx.moveTo(ix + 3, iy - 15); cx.lineTo(ix - 7, iy + 2); cx.lineTo(ix, iy + 2); cx.lineTo(ix - 3, iy + 15); cx.lineTo(ix + 8, iy - 3); cx.lineTo(ix + 1, iy - 3); cx.closePath(); cx.fill(); }
    else { cx.beginPath(); cx.arc(ix, iy, 8, 0, 7); cx.fill(); }
    cx.fillStyle = '#fff'; cx.font = '600 ' + fontPx + 'px ' + FONT; cx.textAlign = 'left';
    // Netz gegen Ueberlauf: Die Breite ist bei 470 gedeckelt und die Schrift
    // schrumpft nur bis 21 px. Ein Satz, der dann immer noch breiter ist,
    // wurde bisher einfach ueber den Pillenrand hinausgeschrieben — die
    // laengste Meldung lag mit 471 px genau 1 px darueber. Jetzt bricht er
    // auf zwei Zeilen um; Hoehe 84 traegt zwei Zeilen à 21 px, die
    // Unterkante bleibt bei 114 und damit ueber der BEISPIEL-Pille (B4).
    const textX = x + 82, maxTextW = w - 106;
    if (cx.measureText(label).width > maxTextW) {
      let zeilen = zeilenUmbruch(label, maxTextW);
      if (zeilen.length > 2) zeilen = [zeilen[0], zeilen.slice(1).join(' ')];
      // Notfall: bleibt die zweite Zeile zu breit (ein einzelnes langes
      // Wort), lieber kuerzen als ueberlaufen.
      if (zeilen[1] && cx.measureText(zeilen[1]).width > maxTextW) {
        let z = zeilen[1];
        while (z.length > 1 && cx.measureText(z + '…').width > maxTextW) z = z.slice(0, -1);
        zeilen[1] = z + '…';
      }
      const zh = Math.round(fontPx * 1.16);
      cx.fillText(zeilen[0], textX, iy + 10 - zh / 2);
      if (zeilen[1]) cx.fillText(zeilen[1], textX, iy + 10 + zh / 2);
    } else {
      cx.fillText(label, textX, iy + 10);
    }
  } else {
    if (muted) { cx.fillStyle = '#f5a623'; cx.beginPath(); cx.arc(x + 26, ly, 4, 0, 7); cx.fill(); }
    else if (flashOn) { cx.fillStyle = '#fff3d0'; cx.beginPath(); cx.arc(x + 26, ly, 4, 0, 7); cx.fill(); }
  }
  if (allowHit) region({ shape: 'rect', x: x, y: y, w: w, h: h, action: () => { islandMsg = ''; expandIsland(); } });
  cx.restore();
}

// ---------- compositor ----------
function render() {
  regions.length = 0;
  allowHit = !anim && !drag;
  // Logische Koordinaten bleiben das 660er-System; physisch wird in der gemessenen
  // Aufloesung gezeichnet. Bewusst aus den ECHTEN Canvas-Massen gerechnet (nicht aus
  // SCALE), damit die Rundung auf ganze Canvas-Pixel keinen halben Texel Versatz erzeugt.
  cx.setTransform(cv.width / cw, 0, 0, cv.height / ch, 0, 0);
  cx.clearRect(0, 0, cw, ch);
  cx.save(); cx.beginPath(); cx.roundRect(1, 1, cw - 2, ch - 2, cornerR); cx.clip();
  // A2/A3/A4: reine Wert-Animationen (Detail-Uebergang, Listen-Scroll, Mitteilungs-Karte)
  // setzen nur Variablen — gezeichnet wird ganz normal ueber die Zustands-Zweige unten.
  if (anim && anim.kind === 'detailSlide') {
    detailSlide = lerp(anim.p0, anim.p1, ease(anim.t));
    if (anim.scrollVon != null) scrollY = lerp(anim.scrollVon, 0, ease(anim.t));
  } else if (anim && anim.kind === 'boardScroll') {
    scrollY = lerp(anim.p0, anim.p1, ease(anim.t));
    scrollAnzeigeUntil = performance.now() + 600;
  } else if (anim && anim.kind === 'lockKarteP') {
    lockKarteP = lerp(anim.p0, anim.p1, ease(anim.t));
  } else if (anim && anim.kind === 'loginSlide') {
    loginSlide = lerp(anim.p0, anim.p1, ease(anim.t));
  } else if (anim && anim.kind === 'pinFuellung') {
    pinFuellung = lerp(anim.p0, anim.p1, anim.t); // linear: Punkt fuer Punkt, wie getippt
  }
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
  if (state !== 'off') drawIsland();
  const _hn = performance.now();
  if (_hn < volumeHudUntil) drawVolumeHud();
  if (_hn < muteHudUntil) drawMuteHud();
  if (ctaPrepAktiv) drawPrep(); // Klick-Choreografie: "Anfrage wird vorbereitet …"
  cx.restore();
  screenTex.needsUpdate = true;
  stage.requestRender();
  syncCta(); // Bottom-Bar folgt jedem Zustandswechsel (Screen an/aus, App/Home, Animation)
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
    if (performance.now() < Math.max(volumeHudUntil, muteHudUntil, islandUntil, scrollAnzeigeUntil)) requestAnimationFrame(loop);
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
// V8.47: Gehaeusefarbe aus dem Einstellungen-Reiter. Bewusst NICHT setColor()
// wiederverwendet: setColor faerbt zusaetzlich stage._scene.background ein, und die
// Buehne rendert mit alpha:true auf durchsichtigem Grund — ein Szenen-Hintergrund
// wuerde die Seite hinter dem Handy zumauern. Hier wird deshalb ausschliesslich das
// GERAET umgefaerbt. Die alte Rueckseiten-Textur wird freigegeben (kein GPU-Leck bei
// mehrfachem Umschalten).
function setzeGehaeuse(key) {
  var g = gehaeuseNach(key);
  if (g.key === gehaeuse) return;
  gehaeuse = g.key;
  matFrame.color.set(g.frame); matButton.color.set(g.frame);
  matChamfer.color.set(g.cham); matPlateau.color.set(g.plateau);
  var alt = matBack.map;
  matBack.map = makeBackTex(g.back[0], g.back[1], g.back[2]);
  matBack.needsUpdate = true;
  if (alt && typeof alt.dispose === 'function') alt.dispose();
  render();   // zeichnet den Screen neu UND fordert genau EIN 3D-Bild an
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
function expandIsland() { islandUntil = performance.now() + 3200; pokeHud(); }
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
    [8200, () => expandIsland()],
    [11400, () => { if (muted) toggleMute(); state = 'lock'; render(); }]
  ];
  function run() {
    seq.forEach(([t, fn]) => demoTimers.push(setTimeout(fn, t)));
    demoTimers.push(setTimeout(() => { if (demoOn) run(); }, 12800));
  }
  run();
}
// V8.45: Die Anfragen-App oeffnet ueber das Login-Zwischenbild ("die App ist
// geschuetzt"). Im HANDBETRIEB WARTET der Login auf den Tipp — beide Knoepfe sind
// verdrahtet (Arturs Login-Wunsch); erst nach ~6 s Untaetigkeit fuellt sich die
// PIN als stille Vorfuehrung von selbst. NUR die Vorfuehr-Sequenz (verweilMs)
// behaelt ihren schnellen Takt, damit die Kette unter 6 s bleibt.
function openApp(id, verweilMs) {
  if (id === 'flashlight') { setFlashlight(!flashOn); return; }
  const a = APP_BY_ID[id]; if (!a) return; // unbekannte id: nichts tun statt schwarzem Screen
  // A2: neu oeffnen = Login zuerst; Scroll/Filter/Reiter bleiben erhalten (V8.45,
  // wie ein echtes Handy) — VOLL aufraeumen tun Reset-Knopf/Sequenz/API.
  if (id === 'anfragen') { boardZuruecksetzen(true); appView = 'login'; }
  currentApp = a; openFrom = (state === 'app') ? openFrom : state;
  startAnim('appP', 0, 1, 340, () => {
    state = 'app';
    if (a.id === 'anfragen' && appView === 'login') {
      if (loginTimer) clearTimeout(loginTimer);
      loginTimer = setTimeout(function () { loginTimer = 0; einloggen(450); }, verweilMs || 6000);
    }
  });
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
// V8.85 (Arturs Ansage): Das DISPLAY bedient die App - dort wird gescrollt
// und gedrueckt, nie die Seite bewegt und nie gedreht. Beginnt eine Beruehrung
// auf dem Display, nimmt preventDefault dem Browser die Geste weg (sonst kam
// nach ~30px ein pointercancel und die SEITE scrollte statt der Liste).
// dataset.displayGriff sperrt zusaetzlich den Dreh-Waechter der Buehne.
let displayTouch = false, displayTouchY = 0, displayTouchStartSy = 0;
dom.addEventListener('touchstart', e => {
  const b = e.changedTouches && e.changedTouches[0];
  if (!b) return;
  const p = pick({ clientX: b.clientX, clientY: b.clientY });
  displayTouch = (p.hit === 'display' && state !== 'off');
  displayTouchY = b.clientY;
  displayTouchStartSy = p.py || 0;
  if (displayTouch) dom.dataset.displayGriff = '1'; else delete dom.dataset.displayGriff;
}, { passive: true });
// V8.87 (Arturs Befund am echten Geraet: 'die webseite haengt auch'):
// Das Display deckt ~77% der Buehne - ein pauschales preventDefault nahm der
// Seite JEDE senkrechte Geste. Stand die Liste am Anschlag, scrollte gar
// nichts mehr. Jetzt Scroll-WEITERGABE wie beim Vorbild-OS ueblich: die App
// behaelt die Geste nur, solange sie sie auch VERWERTEN kann (Liste kann in
// Zugrichtung scrollen, Sperrbildschirm-Entsperren, App-Schliessen unten).
// Sonst faellt die Geste an den Browser und die Seite scrollt normal weiter.
dom.addEventListener('touchmove', e => {
  if (!displayTouch) return;
  const b = e.changedTouches && e.changedTouches[0];
  if (!b) return;
  const dy = b.clientY - displayTouchY;   // + = Finger nach unten
  displayTouchY = b.clientY;
  let will = false;
  if (state === 'lock') {
    will = dy <= 0;                        // hochwischen = entsperren; runter = Seite
  } else if (state === 'app' && appView === 'board' && boardView === 'liste' && boardTab === 'anfragen') {
    const anschlagOben = scrollY <= 0.5, anschlagUnten = scrollY >= boardMaxScroll() - 0.5;
    will = (dy < 0 && !anschlagUnten) || (dy > 0 && !anschlagOben)
      || (Math.abs(dy) < 2 && !(anschlagOben && anschlagUnten));   // Richtungs-Unentschieden: Geste halten
  } else if (state === 'app' && displayTouchStartSy > ch * 0.93) {
    will = dy <= 0;                        // Home-Strich-Zone: hochwischen schliesst die App
  }
  if (will) e.preventDefault();
}, { passive: false });
const displayTouchEnde = () => { displayTouch = false; delete dom.dataset.displayGriff; };
dom.addEventListener('touchend', displayTouchEnde, { passive: true });
dom.addEventListener('touchcancel', displayTouchEnde, { passive: true });
window.addEventListener('pointercancel', displayTouchEnde);
window.addEventListener('pointerup', displayTouchEnde);
dom.addEventListener('pointerdown', e => {
  if (e.button && e.button !== 0) return;
  // A3: die erste echte Beruehrung beendet die Vorfuehr-Sequenz. Hat der Abbruch
  // gerade erst das Board eingeblendet, wird DIESER Zeiger reines Drehen (Orbit) —
  // er darf nicht auf Flaechen tippen, die beim Beruehren noch gar nicht da waren.
  const abgebrochen = vorfuehrAbbruch();
  ctaInteraktionStart(); // neues Greifen/Tippen: Rueckzentrierung abbrechen, Inaktivitaets-Uhr anhalten
  if (abgebrochen) { ptr = null; return; }
  const p = pick(e);
  if (p.hit !== 'display' && p.hit !== 'button') { ptr = null; return; }
  // Gestenregel exakt: TIPPEN bedient (Karten/Bedienfelder), ZIEHEN dreht. A1: WEICHE
  // Regionen (soft) beanspruchen das Ereignis NICHT — Tippen feuert bei pointerup,
  // Ziehen faellt an die Orbit-Steuerung durch. Nur HARTE Ziele (Zurueck, Knoepfe,
  // Kamera-Pille, Taschenlampe) stoppen das Ereignis wie bisher (V8.42-Fix bleibt).
  let soft = false;
  if (p.hit === 'display' && state !== 'off') {
    const tref = hitAt(p.px, p.py);
    const hart = !!(tref && !tref.soft);
    // B1-Fix (V8.42) + V8.45: App-Wischzone nur noch die untersten ~7 % (uebliches
    // Mass heutiger Smartphones; die alte 20-%-Zone lag mitten in der Liste und
    // schloss die App beim Scrollen). Ein HARTES Tippziel gewinnt gegen den Wisch.
    const wischZone = (state === 'lock' && p.py > ch * 0.28)
      || (state === 'app' && p.py > ch * 0.93 && !hart);
    if (!wischZone && !tref) {
      if (e.pointerType === 'touch') { soft = true; }   // V8.85: Finger-Zug scrollt ueberall auf dem Display
      else { ptr = null; return; }
    }
    // V8.86 (Gate-Fund, 2 Pruefer unabhaengig): || statt Ueberschreiben - die
    // V8.85-Zeile darueber war sonst toter Code und der Board-Kopf ohne Region
    // (Neuigkeiten/Statuszeile) fror bei Finger-Zuegen ein. Detail-Ansicht:
    // Wisch steht BEWUSST still (kein scrollbarer Inhalt; Zurueck-Flaeche ist
    // beschriftet) - wie eine echte App ohne Scroll-Inhalt.
    soft = soft || !!(tref && tref.soft);
  }
  ptr = { sx: p.px || 0, sy: p.py || 0, moved: false, hit: p.hit, name: p.name, soft: soft,
    // Pruefer-Fix (V8.43): Client-Koordinaten des Zeigerbeginns — die Tipp/Zieh-
    // Erkennung (moved) rechnet aus der CLIENT-Differenz, NICHT aus der UV-Ableitung.
    // Grund: bei weichen Zielen laeuft die Orbit-Steuerung parallel (kein
    // stopPropagation), die Kameradrehung verschiebt die UV-Projektion des Zeigers
    // und liess die 7-px-Schwelle ~2,5-fach zu frueh kippen (Tipp prellte ab ~2 px).
    cx: e.clientX, cy: e.clientY,
    scrollModus: false, scroll0: 0,
    // A4: Kamera-Schnappschuss vom Zeigerbeginn — beim Umschalten in den Scroll-Modus
    // wird der bis dahin angefallene Orbit-Anteil exakt zurueckgenommen.
    camPos: soft ? cam.position.clone() : null,
    camTarget: soft ? controls.target.clone() : null };
  if (!soft) { controls.autoRotate = false; e.stopPropagation(); }
}, true);
window.addEventListener('pointermove', e => {
  if (!ptr || ptr.hit !== 'display') return;
  // Pruefer-Fix (V8.43): moved aus der CLIENT-Differenz (Kamera-unabhaengig),
  // Schwelle 3 Seiten-px ~= 7 Canvas-px bei Skala 0,407 — entspricht der alten
  // V8.42-Toleranz. Bewusst VOR dem pick-Fruehabbruch: verlaesst der Zeiger das
  // Display, hat er sich sicher bewegt (kein Phantom-Tipp beim Loslassen).
  if (Math.abs(e.clientX - ptr.cx) > 3 || Math.abs(e.clientY - ptr.cy) > 3) ptr.moved = true;
  const p = pick(e); if (p.hit !== 'display') return;
  const dx = p.px - ptr.sx, dy = ptr.sy - p.py;
  // A4: Achsen-Sperre — ein klar senkrechter Zug, der auf einer weichen Karten-Region
  // begonnen hat, scrollt die Liste (|dy| >= 12 UND |dy| >= 1,6*|dx|). Alles andere
  // bleibt Orbit. Einmal Scroll-Modus = Scroll-Modus bis zum Loslassen.
  if (ptr.soft && state === 'app' && appView === 'board' && boardView === 'liste' && boardTab === 'anfragen') {
    if (!ptr.scrollModus && Math.abs(dy) >= 12 && Math.abs(dy) >= 1.6 * Math.abs(dx)) {
      ptr.scrollModus = true; ptr.scroll0 = scrollY;
      if (stage._dprGrob) stage._dprGrob(true);   // V8.87: Bewegung rendert grob, Stand scharf
      if (ptr.camPos) { cam.position.copy(ptr.camPos); controls.target.copy(ptr.camTarget); controls.update(); }
      controls.enabled = false; // sicher mitten in der Geste: onPointerUp der Controls raeumt IMMER auf
    }
    if (ptr.scrollModus) {
      // 1:1-Zug, hart geklemmt — kein Gummiband, keine Traegheit, kein Ausgleiten.
      scrollY = clamp(ptr.scroll0 + dy, 0, boardMaxScroll());
      scrollAnzeigeUntil = performance.now() + 600;
      render();
      return;
    }
  }
  if (state === 'lock' && dy > 0 && ptr.sy > ch * 0.28) { drag = { kind: 'unlock', p: clamp(dy / (ch * 0.42), 0, 1) }; render(); }
  else if (state === 'app' && dy > 0 && ptr.sy > ch * 0.93) { drag = { kind: 'closeApp', p: clamp(dy / (ch * 0.5), 0, 1) }; render(); }
});
window.addEventListener('pointercancel', () => {
  // Netz: abgebrochene Gesten (Systemgesten, Fenster-Wechsel) duerfen die
  // Orbit-Steuerung nie deaktiviert zuruecklassen.
  if (!controls.enabled) controls.enabled = true;
  if (ptr || drag) { ptr = null; drag = null; render(); }
});
window.addEventListener('pointerup', () => {
  if (!ptr) return;
  const P = ptr, D = drag; ptr = null; drag = null;
  if (!controls.enabled) controls.enabled = true; // A4: Scroll-Modus beendet -> Orbit wieder frei
  if (P.scrollModus) { scrollAnzeigeUntil = performance.now() + 600; pokeHud(); if (stage._dprGrob) stage._dprGrob(false); }
  ctaFreischalten();  // erste Screen-/Tasten-Interaktion schaltet die Bottom-Bar frei
  ctaIdleNeustart();  // Inaktivitaets-Uhr fuer die sanfte Rueckzentrierung neu aufziehen
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
    // V8.45: Schliessen MERKT den Scrollstand (boardZuruecksetzen(true)) — die
    // Liste springt nicht mehr an den Anfang, wenn die App zugewischt wird.
    if (D.p > 0.3) startAnim('appP', 1 - D.p, 0, 260, () => { state = openFrom; boardZuruecksetzen(true); });
    else startAnim('appP', 1 - D.p, 1, 200, () => { state = 'app';
      // V8.45: hat der abgebrochene Wisch eine laufende Login-Animation ersetzt
      // (startAnim verwirft deren onDone), die Kette an der Abbruchstelle
      // fortsetzen — der Login friert nie untippbar ein.
      if (appView === 'login') {
        if (loginSlide > 0) startAnim('loginSlide', loginSlide, 1, 200,
          function () { appView = 'board'; loginSlide = 0; pinFuellung = 0; });
        else if (pinFuellung > 0) startAnim('pinFuellung', pinFuellung, 1, 200,
          function () { pinFuellung = 1; loginZumBoard(); });
      }
    });
  } else render();
});

// ---------- öffentliche API für die neutrale Produktdemo ----------
window.ArturDemoHandy = {
  wake() { if (state === 'off') { state = 'lock'; render(); } },
  sleep() { state = 'off'; render(); },
  lock() { state = 'lock'; render(); },
  unlock() { if (state === 'lock') startAnim('unlockP', 0, 1, 300, () => { state = 'home'; }); else { state = 'home'; render(); } },
  home() { if (state === 'app') startAnim('appP', 1, 0, 260, () => { state = openFrom === 'app' ? 'home' : openFrom; boardZuruecksetzen(); }); else { state = 'home'; render(); } },
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
  // A7: Erlebniskette von aussen steuerbar (Tests + Artur-Demos)
  openDetail: (i) => { if (state === 'app') openDetail(i | 0); },
  closeDetail: () => closeDetail(),
  scrollBoard: (y) => { if (state !== 'app' || appView !== 'board' || boardView !== 'liste' || boardTab !== 'anfragen') return;
    scrollY = clamp(Number(y) || 0, 0, boardMaxScroll());
    scrollAnzeigeUntil = performance.now() + 600; pokeHud(); },
  showStatusBanner: () => expandIsland(), // Name bleibt stabil fuer externe Aufrufer
  get state() { return state; },
  get flashlightOn() { return flashOn; },
  get volume() { return volume; },
  get muted() { return muted; }
};

// Direkt die Anfragen-System-Demo zeigen (kein Sperrbildschirm davor) — "die Demos direkt zeigen".
function zeigeStart() {
  var app = APP_BY_ID['anfragen'];
  if (app) { state = 'app'; currentApp = app; openFrom = 'home'; }
  boardZuruecksetzen();
  render();
}

// =====================================================================
//  A3 — VORFUEHR-SEQUENZ ("zeige es"): einmalig, <= 5,9 s, NUR auf dem
//  Screen (Kamera und phone.rotation werden nie angefasst — Arturs
//  Auto-Dreh-Verbot bleibt strukturell unverletzbar).
//  Ablauf V8.44: Sperrbildschirm-Mitteilung faehrt ein -> Entsperren ->
//  LOGIN (PIN fuellt sich selbst) -> Board -> Liste scrollt -> Tipp auf
//  eine Karte -> Detail -> zurueck zur Liste. Abbruch jederzeit durch die
//  erste echte Beruehrung.
// =====================================================================
var vorfuehrLaeuft = false, vorfuehrFertig = false, seqTimers = [];
function seqT(ms, fn) { seqTimers.push(setTimeout(fn, ms)); }
// Start NUR, wenn keine reduzierte Bewegung gewuenscht ist UND die Buehne beim Init
// im Sichtfeld liegt. Die Buehne selbst kann beim Modul-Start noch display:none sein
// (0 Groesse, site.js schaltet .hero3d erst nach dem Laden frei) — dann entscheidet
// ersatzweise die sichtbare Hero-Sektion. Kein IntersectionObserver, rein synchron.
function vorfuehrMoeglich() {
  try {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
    var vh = window.innerHeight || document.documentElement.clientHeight || 0;
    if (!vh) return false;
    var r = stage.getBoundingClientRect();
    if (!r.height) { var hero = document.querySelector('.hero'); if (hero) r = hero.getBoundingClientRect(); }
    if (!r.height) return false;
    var sichtbar = Math.min(r.bottom, vh) - Math.max(r.top, 0); // sichtbare Hoehe in px
    return sichtbar > 0.6 * Math.min(r.height, vh); // Seite gescrollt geladen -> keine Sequenz
  } catch (e) { return false; }
}
function vorfuehrStart() {
  vorfuehrLaeuft = true;
  var seqStart = performance.now();   // V8.91: Bezugspunkt fuer die harte Obergrenze
  var app = APP_BY_ID['anfragen'];
  if (app) { currentApp = app; openFrom = 'home'; }
  boardZuruecksetzen();
  // Lock wird IM SELBEN Init-Schritt gesetzt — es gibt keinen Board->Lock-Blitzer.
  state = 'lock';
  lockKarteP = 0;
  startAnim('lockKarteP', 0, 1, 320, function () { lockKarteP = 1; });
  // V8.44: Der Home-Zwischenstopp entfaellt (Informationswert pro Sekunde: Lock >
  // Login > Home) — nach dem Entsperren oeffnet die App direkt und zeigt den LOGIN
  // als Zwischenbild: Kette Lock -> Entsperren -> Login (PIN fuellt sich) -> Board.
  // Home bleibt als ZUSTAND voll erhalten (openFrom, App-Symbole, Taschenlampe).
  //
  // V8.90 (F41) — WETTLAUF ENTFERNT. Vorher stand der naechste Schritt als fester
  // Zeitgeber bei 1450 ms, also nur 50 ms nach dem rechnerischen Ende der
  // Entsperr-Animation (1100 + 300). Kam ihr Rueckruf unter Rechnerlast auch nur
  // 35 ms zu spaet, lief die Pruefung "state === 'home'" ins Leere und die ganze
  // Kette brach ab — der Hero blieb auf dem leeren Startbildschirm stehen.
  // Jetzt haengt der Schritt AM RUECKRUF: er kann die Animation nicht mehr
  // ueberholen, egal wie langsam der Rechner ist. Die 50 ms Sicht-Pause auf dem
  // Startbildschirm bleiben als kurzer, abbrechbarer Zeitgeber erhalten.
  seqT(1100, function () {
    if (state !== 'lock') return;
    startAnim('unlockP', 0, 1, 300, function () {
      // Wurde die Vorfuehrung waehrend der Animation abgebrochen (Beruehrung,
      // Reset, Tab-Wechsel oder das Auffangnetz unten), hier NICHTS mehr
      // schreiben — sonst ueberschriebe dieser Rueckruf den bereits
      // hergestellten Endzustand.
      if (!vorfuehrLaeuft) return;
      state = 'home';
      seqT(50, function () { if (state === 'home') openApp('anfragen', 350); });
    });
  });
  // V8.91 (Codex-Fund) — FOLGE-SCHRITTE WARTEN, STATT STILL AUSZUFALLEN.
  // Die Schritte unten standen auf festen Uhrzeiten und prueften dort GENAU
  // EINMAL, ob ihre Voraussetzung erfuellt ist. Zwischen dem rechnerischen Ende
  // des Logins (~2870 ms) und dem Scroll-Schritt (2950 ms) lagen nur 80 ms
  // Reserve. Unter Rechnerlast fiel der Schritt damit still aus und die
  // Vorfuehrung zeigte nur noch einen Teil der Kette; das Auffangnetz ganz unten
  // verhindert nur das Leerbild, nicht den fehlenden Schritt.
  // seqBereit() fragt ab dem Wunsch-Zeitpunkt alle 100 ms nach und startet den
  // Schritt, sobald seine Voraussetzung steht. Ohne Last aendert sich nichts —
  // die erste Frage trifft sofort zu, die Uhrzeiten bleiben exakt die alten.
  // Unter Last DEHNT sich die Kette, statt Loecher zu bekommen. Die Geduld
  // begrenzt das Warten hart, danach uebernimmt das Auffangnetz.
  var ketteFertig = false;
  function ketteEnde() { ketteFertig = true; }
  function seqBereit(abMs, bereit, tun, geduldMs) {
    var frist = 0;
    seqT(abMs, function schritt() {
      if (!vorfuehrLaeuft) return;
      if (frist === 0) frist = performance.now() + (geduldMs || 4000);
      if (bereit()) { tun(); return; }
      if (performance.now() >= frist) { ketteEnde(); return; }
      seqT(100, schritt);
    });
  }
  // Schritt 1: Liste scrollen. scrollFertig ist der Uebergabepunkt an Schritt 2 —
  // ohne ihn wuerde der Tipp auf eine Karte mitten in die laufende Scroll-
  // Animation fallen (die Karten stehen dann noch nicht dort, wo sie hingehoeren).
  var scrollFertig = false;
  seqBereit(2950, function () {
    return state === 'app' && appView === 'board' && boardView === 'liste';
  }, function () {
    if (boardMaxScroll() > 0) {
      startAnim('boardScroll', 0, boardMaxScroll(), 700, function () { pokeHud(); scrollFertig = true; });
    } else { scrollFertig = true; }
  });
  // Schritt 2: eine Karte antippen und das Detail oeffnen.
  seqBereit(3850, function () {
    return scrollFertig && state === 'app' && appView === 'board' &&
           boardView === 'liste' && boardTab === 'anfragen';
  }, function () {
    // Erste VOLLSTAENDIG sichtbare Karte antippen — genau die, die auch ein echter
    // Nutzer an dieser Scroll-Position tippen koennte (A4-Guard). V8.45: die
    // Position kommt aus dem Gruppen-Layout (EIN Wahrheitspunkt).
    var L = boardLayout(), ziel = null;
    for (var li = 0; li < L.items.length; li++) { var it = L.items[li];
      if (it.typ !== 'karte') continue;
      var iy = it.y + BOARD_VIEW_T - scrollY;
      if (iy >= BOARD_VIEW_T && iy + it.h <= BOARD_VIEW_B) { ziel = it; break; } }
    if (!ziel) { ketteEnde(); return; }
    ripple = { x: cw / 2, y: ziel.y + BOARD_VIEW_T + ziel.h / 2, start: performance.now() };
    (function rippleLoop() {
      if (!ripple) return;
      render();
      if (performance.now() - ripple.start < 340) requestAnimationFrame(rippleLoop);
      else { ripple = null; render(); }
    })();
    seqT(120, function () {
      openDetail(ziel.i);
      // Schritt 3: zurueck zur Liste. V8.91: haengt am TATSAECHLICHEN Oeffnen des
      // Details statt an der festen Uhrzeit 5450. Der Abstand ist derselbe wie
      // bisher (3850 + 120 + 1480 = 5450), aber wenn sich Schritt 2 unter Last
      // verschiebt, verschiebt sich der Rueckweg mit — die Verweildauer im
      // Detail bleibt erhalten, statt auf null zusammenzuschrumpfen.
      seqT(1480, function () {
        if (boardView !== 'detail') { ketteEnde(); return; }
        // Zurueck zur Liste UND Scroll auf 0 in EINER Animation (400 ms).
        startAnim('detailSlide', 1, 0, 400, function () { boardZuruecksetzen(); ketteEnde(); });
        if (anim) anim.scrollVon = scrollY;
      });
    });
  });
  // V8.90 (F41) — AUFFANGNETZ. Zweites, unabhaengiges Netz hinter der Kette oben:
  // Steht der Schirm zum Schluss aus IRGENDEINEM Grund nicht auf der Werkprobe
  // (Sperrbildschirm, Startbildschirm, haengender Login), wird sie hier hart
  // hergestellt. Gemessen vor dem Fix mit 4-fach gedrosseltem Rechner: 13 von 13
  // Laeufen endeten auf dem leeren Startbildschirm. Der Hero zeigt danach nie
  // wieder eine inhaltsleere Flaeche.
  // V8.91: Laeuft die Kette wegen Rechnerlast zu diesem Zeitpunkt noch, wird das
  // Ende nach hinten geschoben statt die Vorfuehrung abzuschneiden — der Schirm
  // ist dann ja nicht leer, sondern mitten in der Vorfuehrung. Harte Obergrenze
  // 15 s ab Sequenzstart, damit daraus nie eine Endlosschleife wird.
  seqT(5900, function abschluss() {
    if (!ketteFertig && performance.now() - seqStart < 15000) { seqT(150, abschluss); return; }
    vorfuehrLaeuft = false; vorfuehrFertig = true; seqTimers = [];
    if (state !== 'app' || appView !== 'board') {
      anim = null; drag = null;
      zeigeStart();
    }
  });
  render();
}
// Abbruch: erste Beruehrung des Canvas, Reset-Knopf, CTA-Klick oder Tab-Wechsel.
// War der App-Zustand noch nicht erreicht -> SOFORT zur Werkprobe (Board), damit der
// Hero nie inhaltsleer auf dem Sperrbildschirm haengen bleibt. Sonst: einfrieren
// (laufende Screen-Animation laeuft aus, weitere Schritte entfallen). Kein Neustart.
// Rueckgabe true = dieser Abbruch hat gerade zum Board umgeschaltet; der ausloesende
// Zeiger darf dann NUR noch drehen (Orbit), nie auf dem eben erst eingeblendeten
// Board tippen — der Nutzer hat diese Flaeche beim Beruehren noch nicht gesehen.
function vorfuehrAbbruch() {
  if (!vorfuehrLaeuft) return false;
  vorfuehrLaeuft = false; vorfuehrFertig = true;
  seqTimers.forEach(clearTimeout); seqTimers = [];
  ripple = null; lockKarteP = 1;
  if (state !== 'app') {
    anim = null; drag = null;
    var app = APP_BY_ID['anfragen'];
    if (app) { currentApp = app; openFrom = 'home'; }
    state = 'app';
    boardZuruecksetzen();
    render();
    return true;
  }
  // V8.44: Abbruch, waehrend der LOGIN ruhig steht (Timer geplant, keine Animation):
  // sofort zum Board — der Login darf nie haengen bleiben. Laeuft gerade die PIN-/
  // Schiebe-Animation, laeuft ihre Kette von selbst zum Board aus (nichts anfassen).
  // Rueckgabe true aus demselben Grund wie oben: der ausloesende Zeiger darf nur
  // drehen, nie auf das eben erst eingeblendete Board tippen.
  if (appView === 'login' && !anim) {
    if (loginTimer) { clearTimeout(loginTimer); loginTimer = 0; }
    appView = 'board'; loginSlide = 0; pinFuellung = 0;
    render();
    return true;
  }
  return false;
}
document.addEventListener('visibilitychange', function () { if (document.hidden) vorfuehrAbbruch(); });

if (vorfuehrMoeglich()) { vorfuehrStart(); } else {
  zeigeStart();
  // V8.84 (Pruef-Workflow 03.08.): Auf dem Handy liegt die Buehne beim Start
  // IMMER unter der Falz - die einmalige Synchron-Pruefung schaltete die
  // Vorfuehrung dort dauerhaft ab. Nachholung: Wird die Buehne spaeter zu 60%
  // sichtbar und hat noch niemand die Leinwand beruehrt, laeuft die Show wie
  // am Desktop. Erste Beruehrung vorher = Nutzer will selbst - keine Show.
  if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches && 'IntersectionObserver' in window) {
    (function () {
      var beruehrt = false;
      dom.addEventListener('pointerdown', function () { beruehrt = true; }, { once: true, capture: true });
      var io = new IntersectionObserver(function (es) {
        var e = es[es.length - 1];
        if (!e || !e.isIntersecting) return;
        io.disconnect();
        if (!beruehrt && !vorfuehrLaeuft) vorfuehrStart();
      }, { threshold: 0.6 });
      io.observe(stage);
    })();
  }
}

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

// =====================================================================
//  SCHAERFE-REGELUNG (V8.45): Textur-Aufloesung = echte Darstellungsgroesse
//  Ursache -> Mechanismus -> Wirkung:
//  Ursache    Die Textur war mit 1320 x 2828 fest verdrahtet, der Screen wird aber
//             nur ~546 x 1150 Bildpunkte gross dargestellt (gemessen).
//  Mechanismus Bei 2,4-facher Verkleinerung waehlt die GPU Mipmap-Stufe ~1,3 und mischt
//             Stufe 2 (halbe Schirmaufloesung) ein -> Schrift wird weichgezeichnet.
//  Wirkung    Mit 1 Texel = 1 Bildpunkt liegt die Stufe bei 0: die Schrift kommt genau
//             so auf den Schirm, wie der Canvas sie gerastert hat.
//  Es wird NUR die Leinwandgroesse veraendert — kein Layout, keine Schriftgroesse,
//  keine Koordinate. Neu gezeichnet wird nur bei echter Aenderung (0,05-Raster),
//  das ereignisgesteuerte Rendern bleibt unangetastet.
// =====================================================================
const _texPos = new THREE.Vector3();
function screenBildpunkteHoch() {
  // Hoehe des Displays in echten Bildpunkten, gerechnet in der Frontal-/Ausgangslage
  // (Zoom ist gesperrt, der Abstand aendert sich also nie -> das ist der Groesstwert).
  display.updateWorldMatrix(true, false);
  _texPos.setFromMatrixPosition(display.matrixWorld);
  const abstand = cam.position.distanceTo(_texPos);
  const sichtHoehe = 2 * abstand * Math.tan(cam.fov * Math.PI / 360); // Welt-Hoehe im Bild
  const puffer = stage.clientHeight * stage._renderer.getPixelRatio();  // Bildpunkte hoch
  if (!(sichtHoehe > 0) || !(puffer > 0)) return 0;
  return scrH / sichtHoehe * puffer;
}
function texturSchaerfeNachziehen() {
  try {
    const noetig = screenBildpunkteHoch() * UEBERABTASTUNG;
    if (!(noetig > 0)) return;
    let s = clamp(noetig / ch, SCALE_MIN, SCALE_MAX);
    // 0,05-Raster (kein Neubau bei 1-px-Resize) und bewusst AUFgerundet: die Textur darf
    // nie kleiner als die Darstellung werden, sonst vergroessert die GPU wieder (= weich).
    s = Math.ceil(s * 20) / 20;
    if (Math.abs(s - SCALE) < 0.001) return;
    SCALE = s;
    cv.width = Math.round(cw * SCALE);
    cv.height = Math.round(ch * SCALE);
    screenTex.dispose();                      // alte GPU-Textur freigeben (Groesse aendert sich)
    render();                                 // zeichnet neu und setzt needsUpdate
  } catch (e) {}
}
setTimeout(texturSchaerfeNachziehen, 60); setTimeout(texturSchaerfeNachziehen, 320);
// Die Messung haengt an der Hoehe der BUEHNE (stage.clientHeight), deshalb wird auch die
// Buehne beobachtet — nicht die Zeichenflaeche: heroFit() schreibt der Zeichenflaeche eine
// feste Inline-Groesse, ihre Box aendert sich also nicht mehr, und ein Beobachter auf ihr
// wuerde bei einer reinen Hoehenaenderung stumm bleiben (nachgemessen).
if ('ResizeObserver' in window) new ResizeObserver(function () { texturSchaerfeNachziehen(); }).observe(stage);

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
      vorfuehrAbbruch();                // A3: Reset beendet eine laufende Vorfuehr-Sequenz
      ctaInteraktionStart();            // laufende Rueckzentrierung/Uhr sauber beenden
      stage._controls.reset();          // zurueck zur gemerkten Kamera-Ausgangslage
      cam.updateMatrixWorld(true);      // zweites Netz: Kamera-Matrizen SOFORT frisch (nicht erst im naechsten Frame)
      phone.rotation.y = 0;
      demoDatenReset();                 // V8.44: Vorfuehr-Eintraege wieder ausraeumen
      // V8.47: der Reset-Knopf raeumt AUCH die Einstellungen auf — Gehaeusefarbe und
      // beide Schalter zurueck in den Auslieferungszustand. Sonst gaebe es einen
      // Zustand, aus dem Artur nicht mehr mit einem Klick herauskommt.
      setzeGehaeuse(GEHAEUSE[0].key);
      zeigeNeuZaehler = true; neuesteZuerst = false;
      zeigeStart();                     // zurueck zur Anfragen-System-Demo (direkt aufs Board)
    } catch (e) {}
  }
};
// Reset-Knopf war bis zum fertigen Laden disabled -> jetzt freigeben (kein toter Klick waehrend Three laedt).
(function () { var rb = document.querySelector('[data-hero-reset]'); if (rb) rb.disabled = false; })();

// =====================================================================
//  BOTTOM-BAR "Für meinen Betrieb prüfen" + sanfte Auto-Rückzentrierung
//  Der Knopf ist ein ECHTES HTML-<button> (Tastatur/Screenreader/Touch),
//  exakt auf die Screen-Unterkante projiziert — KEIN Canvas-Knopf und
//  KEIN zweites Formular im Handy: der Abschluss laeuft ueber das echte
//  Kontaktformular der Seite (Uebergabe wie beim 60-Sekunden-Check).
//  Alle Variablen als var: render()/pointer-Handler laufen schon vor
//  diesem Block und duerfen nie in eine TDZ-Falle laufen.
// =====================================================================
var ctaWrap = document.querySelector('[data-handy-cta]');
var ctaBtn = document.querySelector('[data-handy-cta-btn]');
var ctaFrei = false;       // Bar erscheint nach erster Interaktion ODER nach ~5 s
var ctaGriff = false;      // Handy wird gerade gegriffen/gedreht -> Bar sanft aus
var ctaLauf = false;       // Klick-Choreografie laeuft (Doppelklick-Schutz)
var ctaPrepAktiv = false;  // Screen zeigt "Anfrage wird vorbereitet …"
var ctaIdleTimer = 0;      // Inaktivitaets-Uhr fuer die Rueckzentrierung (~4,5 s)
var ctaRecenter = null;    // laufende Rueckzentrierungs-Animation
var reduceMotionMedia = window.matchMedia('(prefers-reduced-motion: reduce)');
var _cv1 = new THREE.Vector3(), _cv2 = new THREE.Vector3(), _cp = new THREE.Vector3();

function istFrontal() {
  _cv1.copy(cam.position).sub(controls.target);
  _cv2.copy(controls.position0).sub(controls.target0);
  return _cv1.angleTo(_cv2) < 0.12 && Math.abs(phone.rotation.y) < 0.06;
}

// B3-Fix: Die Bar sitzt UNTER dem Display am Geraeterahmen (lokale y-Werte unterhalb
// der Screen-Unterkante) statt auf dem Screen. Sie ueberdeckt damit keine einzige
// tippbare Flaeche mehr: Wischzone, Home-Indicator und Karten bleiben komplett frei.
// Die Bar zeigt sich nur in Frontalstellung, deshalb ist die Naeherung praktisch exakt.
function ctaPlatzieren() {
  if (!ctaWrap || !ctaWrap.offsetParent) return;
  display.updateWorldMatrix(true, false);
  // Reset-Fix: Nach controls.reset() springt die Kamera in EINEM Schritt; ihre
  // matrixWorldInverse wird sonst erst im naechsten Renderframe aktualisiert und
  // .project(cam) rechnet mit der ALTEN Lage -> Bar landet ueber den Hero-Knoepfen
  // oder ausserhalb des Viewports. Ein updateMatrixWorld(true) vor der Projektion
  // haelt die Platzierung immer synchron (billig, ereignisgesteuertes Rendern bleibt).
  cam.updateMatrixWorld(true);
  const rect = dom.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const host = ctaWrap.offsetParent.getBoundingClientRect();
  const xs = [-scrW / 2 + scrW * 0.05, scrW / 2 - scrW * 0.05];
  const ys = [-scrH / 2 - scrH * 0.105, -scrH / 2 - scrH * 0.018]; // unterhalb der Screen-Kante
  let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9;
  for (const x of xs) for (const y of ys) {
    _cp.set(x, y, 0).applyMatrix4(display.matrixWorld).project(cam);
    const px = (_cp.x + 1) / 2 * rect.width + rect.left - host.left;
    const py = (1 - _cp.y) / 2 * rect.height + rect.top - host.top;
    if (px < minX) minX = px; if (px > maxX) maxX = px;
    if (py < minY) minY = py; if (py > maxY) maxY = py;
  }
  let h = maxY - minY;
  if (h < 44) h = 44; // Touch-Ziel >= 44 px — waechst nach UNTEN, nie in den Screen
  ctaWrap.style.left = minX.toFixed(1) + 'px';
  ctaWrap.style.top = minY.toFixed(1) + 'px';
  ctaWrap.style.width = Math.max(0, maxX - minX).toFixed(1) + 'px';
  // V8.84: minHeight statt height - auf Handybreiten bricht der Text zweizeilig
  // und braucht ~53-65px; eine harte 44px-Box liess ihn oben/unten rausquellen.
  ctaWrap.style.minHeight = h.toFixed(1) + 'px';
  ctaWrap.style.height = 'auto';
}

// EIN Wahrheitspunkt fuer die Sichtbarkeit: freigeschaltet + frontal + ruhig.
function syncCta() {
  if (!ctaWrap) return;
  const an = ctaFrei && !ctaGriff && !ctaLauf && !ctaPrepAktiv && !anim && !drag
    && (state === 'app' || state === 'home') && istFrontal();
  if (an) ctaPlatzieren();
  ctaWrap.classList.toggle('is-on', an);
}

function ctaFreischalten() { if (!ctaFrei) { ctaFrei = true; syncCta(); } }
function ctaIdleStopp() { if (ctaIdleTimer) { clearTimeout(ctaIdleTimer); ctaIdleTimer = 0; } }
function ctaRecenterStopp() { ctaRecenter = null; }
function ctaInteraktionStart() { ctaRecenterStopp(); ctaIdleStopp(); }

// Nach ~4,5 s ohne Interaktion weich zur Front zurueck — nie bei reduced-motion,
// jederzeit durch neues Greifen unterbrechbar (pointerdown -> ctaInteraktionStart).
function ctaIdleNeustart() {
  ctaIdleStopp();
  if (reduceMotionMedia.matches) return;
  if (istFrontal()) return;
  ctaIdleTimer = setTimeout(function () {
    ctaIdleTimer = 0;
    // NIE waehrend einer laufenden Screen-Animation oder Geste starten —
    // dann einfach neu aufziehen und spaeter ruhig zurueckdrehen.
    if (anim || drag || ptr) { ctaIdleNeustart(); return; }
    ctaRecenterStart(700, null);
  }, 4500);
}

var _cqA = new THREE.Quaternion(), _cqB = new THREE.Quaternion();
function ctaRecenterStart(dauer, fertig) {
  if (istFrontal()) { if (fertig) fertig(); return; }
  // Grosskreis-Bahn statt gerader Linie: Richtung per Quaternion-Slerp, Radius linear.
  // Eine gerade Bahn wuerde bei grossen Drehungen sichtbar "durch das Handy tauchen".
  const dir0 = cam.position.clone().sub(controls.target);
  const dir1 = controls.position0.clone().sub(controls.target0);
  const r0 = dir0.length(), r1 = dir1.length();
  dir0.normalize(); dir1.normalize();
  ctaRecenter = { start: performance.now(), dauer: dauer, fertig: fertig,
    t0: controls.target.clone(), dir0: dir0, r0: r0, r1: r1,
    qVoll: new THREE.Quaternion().setFromUnitVectors(dir0, dir1) };
  requestAnimationFrame(ctaRecenterTick);
}
// Ereignisgesteuert bleibt erhalten: dieser rAF-Lauf existiert NUR fuer die Dauer
// der einen Animation und endet danach vollstaendig.
function ctaRecenterTick(now) {
  const rc = ctaRecenter; if (!rc) return; // unterbrochen durch neues Greifen
  const k = clamp((now - rc.start) / rc.dauer, 0, 1), e = ease(k);
  _cqA.identity().slerp(rc.qVoll, e);
  controls.target.lerpVectors(rc.t0, controls.target0, e);
  cam.position.copy(rc.dir0).applyQuaternion(_cqA)
    .multiplyScalar(lerp(rc.r0, rc.r1, e)).add(controls.target);
  if (k >= 1) { // exakt in der gemerkten Ausgangslage enden (keine Restdrift)
    cam.position.copy(controls.position0);
    controls.target.copy(controls.target0);
  }
  controls.update();
  stage.requestRender();
  syncCta();
  if (k < 1) requestAnimationFrame(ctaRecenterTick);
  else { ctaRecenter = null; if (rc.fertig) rc.fertig(); }
}

// Status-Karte im Screen waehrend der Klick-Choreografie (statisch, ein Renderbild).
function drawPrep() {
  cx.fillStyle = 'rgba(5,7,12,0.55)'; cx.fillRect(0, 0, cw, ch);
  const w = 470, h = 96, x = cw / 2 - w / 2, y = ch / 2 - h / 2;
  cx.fillStyle = 'rgba(18,20,26,0.96)'; rr(x, y, w, h, h / 2); cx.fill();
  cx.strokeStyle = 'rgba(98,213,255,0.55)'; cx.lineWidth = 2; rr(x, y, w, h, h / 2); cx.stroke();
  cx.fillStyle = '#fff'; cx.font = '600 30px ' + FONT; cx.textAlign = 'center';
  cx.fillText('Anfrage wird vorbereitet …', cw / 2, ch / 2 + 11);
  cx.textAlign = 'left';
}

// Klick-Choreografie: (1) weich frontal ausrichten, (2) 500 ms Screen-Status,
// (3) Smooth-Scroll zum echten Formular mit Vorbefuellung (site.js-Uebergabe).
// reduced-motion: alles ohne Animationen, direkter Sprung.
function ctaKlick() {
  if (ctaLauf) return;
  vorfuehrAbbruch(); // A3: CTA-Klick beendet eine laufende Vorfuehr-Sequenz
  ctaLauf = true;
  ctaInteraktionStart();
  syncCta(); // Bar sofort sanft ausblenden
  const uebergabe = function () {
    if (typeof window.__handyZumKontakt === 'function') window.__handyZumKontakt();
    else { const z = document.querySelector('#kontakt'); if (z) z.scrollIntoView(); }
  };
  const abschluss = function () { ctaPrepAktiv = false; ctaLauf = false; render(); };
  if (reduceMotionMedia.matches) {
    try { controls.reset(); phone.rotation.y = 0; } catch (e) {}
    uebergabe(); abschluss(); return;
  }
  ctaRecenterStart(450, function () {
    ctaPrepAktiv = true; render();
    setTimeout(function () { uebergabe(); setTimeout(abschluss, 300); }, 500);
  });
}

if (ctaWrap && ctaBtn) {
  ctaWrap.hidden = false; // ab jetzt steuert allein die is-on-Klasse (opacity/visibility)
  ctaBtn.addEventListener('click', ctaKlick);
  // Bar-Hover zaehlt als Nutzer-Interaktion: Uhr anhalten, beim Verlassen neu aufziehen.
  ctaWrap.addEventListener('pointerenter', function () { ctaInteraktionStart(); });
  ctaWrap.addEventListener('pointerleave', function () { if (!ctaLauf) ctaIdleNeustart(); });
  setTimeout(ctaFreischalten, 5000); // spaetestens nach ~5 s anbieten
  controls.addEventListener('start', function () { ctaGriff = true; ctaInteraktionStart(); syncCta(); });
  controls.addEventListener('end', function () { ctaGriff = false; ctaIdleNeustart(); syncCta(); });
  controls.addEventListener('change', function () { syncCta(); });
  // Groesse der Buehne geaendert -> Bar nachfuehren UND die Textur-Aufloesung
  // nachziehen (Schaerfe-Regelung V8.45). Beides ist ereignisgesteuert, im Leerlauf
  // laeuft weiterhin nichts; texturSchaerfeNachziehen() steigt bei gleicher Groesse
  // sofort wieder aus (0,05-Raster) und zeichnet dann gar nichts.
  if ('ResizeObserver' in window) new ResizeObserver(function () { syncCta(); texturSchaerfeNachziehen(); }).observe(dom);
  window.addEventListener('resize', function () { syncCta(); texturSchaerfeNachziehen(); });
}

// Messpunkte fuer die automatische End-zu-End-Pruefung (lesend, ohne Seiteneffekte).
window.__heroHandy.messwerte = function () {
  return {
    kamera: [cam.position.x, cam.position.y, cam.position.z],
    frontal: istFrontal(),
    barAn: !!(ctaWrap && ctaWrap.classList.contains('is-on')),
    prep: !!ctaPrepAktiv,
    barFrei: !!ctaFrei,
    status: (Array.isArray(DEMO.anfragen) ? DEMO.anfragen : []).map(function (a) { return a.status; }),
    // A7: Erlebniskette messbar machen
    // V8.90: Hauptzustand mitmessen. Ohne ihn laesst sich von aussen nicht
    // unterscheiden, ob der Schirm die Werkprobe zeigt oder auf dem leeren
    // Startbildschirm stehen geblieben ist (boardView ist in beiden Faellen
    // 'liste'). Reines Lesen, kein Seiteneffekt.
    state: state,
    scrollY: scrollY,
    boardView: boardView,
    detailIndex: detailIndex,
    vorfuehrFertig: !!vorfuehrFertig,
    orbitAn: !!controls.enabled,
    // V8.44: Login-Zwischenbild + Vorfuehr-Anfrage messbar machen
    appView: appView,
    loginSlide: loginSlide,
    pinFuellung: pinFuellung,
    simZaehler: simZaehler,
    anzahlAnfragen: (Array.isArray(DEMO.anfragen) ? DEMO.anfragen.length : 0),
    // V8.45: Reiter, Filter, Fenster-Geometrie und Layout messbar machen
    boardTab: boardTab,
    filter: activeFilter,
    fenster: [BOARD_VIEW_T, BOARD_VIEW_B],
    simKnopf: [SIM_Y, SIM_H],
    listeAnzahl: (function () { var L = boardLayout(), n = 0;
      for (var i = 0; i < L.items.length; i++) if (L.items[i].typ === 'karte') n++; return n; })(),
    listeKoepfe: (function () { var L = boardLayout(), t = [];
      for (var i = 0; i < L.items.length; i++) if (L.items[i].typ === 'kopf') t.push(L.items[i].grp.titel); return t; })(),
    // V8.47: Wie viele Karten stehen beim aktuellen Scrollstand VOLLSTAENDIG im
    // Fenster (= genau die Bedingung, unter der sie auch tippbar sind)?
    volleKarten: (function () { var L = boardLayout(), n = 0;
      for (var i = 0; i < L.items.length; i++) { var it = L.items[i];
        if (it.typ !== 'karte') continue;
        var iy = it.y + BOARD_VIEW_T - scrollY;
        if (iy >= BOARD_VIEW_T && (iy + it.h) <= BOARD_VIEW_B) n++; }
      return n; })(),
    // V8.58: die Hoehe folgt dem Inhalt (Follow-up bricht um) — deshalb die WIRKLICH
    // vorkommenden Hoehen melden, nicht mehr nur die zwei Grundwerte.
    kartenHoehen: (function () { var arr = (Array.isArray(DEMO.anfragen) ? DEMO.anfragen : []), s = [];
      for (var i = 0; i < Math.min(arr.length, BOARD_MAX_N); i++) {
        var h = karteHoehe(arr[i]); if (s.indexOf(h) < 0) s.push(h); }
      return s.sort(function (a, b) { return a - b; }); })(),
    inhaltHoehe: boardLayout().inhalt,
    maxScroll: boardMaxScroll(),
    // V8.47: Einstellungen-Reiter messbar machen
    gehaeuse: gehaeuse,
    gehaeuseFarben: GEHAEUSE.map(function (g) { return g.key; }),
    rahmenFarbe: '#' + matFrame.color.getHexString(),
    zeigeNeuZaehler: !!zeigeNeuZaehler,
    neuesteZuerst: !!neuesteZuerst,
    ersteKarteIndex: (function () { var L = boardLayout();
      for (var i = 0; i < L.items.length; i++) if (L.items[i].typ === 'karte') return L.items[i].i;
      return -1; })(),
    filterPillen: _filterRects.slice(),
    ersterName: (((Array.isArray(DEMO.anfragen) ? DEMO.anfragen : [])[0]) || {}).name || ''
  };
};
// Hilfspunkt fuer Tests: Screen-Anteil (fx, fy ab oben links, 0..1) -> Seiten-Pixel.
window.__heroHandy.screenPunkt = function (fx, fy) {
  display.updateWorldMatrix(true, false);
  const rect = dom.getBoundingClientRect();
  _cp.set((fx - 0.5) * scrW, (0.5 - fy) * scrH, 0).applyMatrix4(display.matrixWorld).project(cam);
  return [(_cp.x + 1) / 2 * rect.width + rect.left, (1 - _cp.y) / 2 * rect.height + rect.top];
};
