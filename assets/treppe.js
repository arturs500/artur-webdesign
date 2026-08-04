/* Treppen-Läufer (dekorativ, interaktiv):
   - Zickzack-Treppe FEST an der Seite verankert (scrollt mit dem Inhalt).
   - Figur verfolgt das Fenster: läuft Stufe für Stufe hinab/hinauf, Tempo
     folgt dem Scroll-Tempo (gedeckelt, damit jede Stufe sichtbar bleibt).
   - Greifen + Werfen: Figur ist mit Maus oder Tastatur bedienbar, fliegt mit
     Schwung durchs Bild, fällt ganz nach unten und muss die Treppe wieder hochlaufen.
   Schutzgitter: reduced-motion = aus, ohne JS nicht vorhanden, nur ab 1400px
   Breite (CSS), Treppe fängt keine Klicks (nur der kleine Griff-Punkt). */
(function () {
  "use strict";
  // Doppel-Lade-Schutz: index.html laedt deterministisch (Inline-Loader),
  // site.js lazy — wer zuerst kommt, gewinnt; ein zweiter Lauf tut nichts.
  if (window.__treppeGeladen) return;
  window.__treppeGeladen = true;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  var desktopMQ = window.matchMedia("(min-width:1400px)");
  // V8.69: Unter 1400px laeuft nur noch die A-Leiste (Arturs Wunsch: das A auch
  // auf dem Handy). Treppe, Figur und Wurf-Overlay bleiben dort aus - 120px
  // Canvas ueber 390px Bildschirm waeren 27 % der Lesebreite, und der
  // unsichtbare Greif-Bereich wuerde Tipps auf Links schlucken.
  var nurLeiste = function () { return !desktopMQ.matches; };
  var laeuft = false;
  if (reduce.matches) return;

  // Treppe (Welt = Seiten-Koordinaten, y 0 = Seitenanfang)
  var STEP_W = 13;
  var STEP_H = 22;          // 1 Stufe je 22 Seiten-px -> Treppe klebt an der Seite
  var FLIGHT = 6;
  var RAIL_W = 120;
  var X_MIN = 20, X_MAX = 98;
  // V8.69: Schmal-Geometrie unter 1400px. 120px Spur ueber 390px Bildschirm
  // waeren 27 % der Lesebreite gewesen - mit STEP_W 8 sind es 7 %.
  // Zwangsbedingung: STEP_W * (FLIGHT-1) <= X_MAX - X_MIN, sonst laeuft die
  // Figur aus der Spur (8*3 = 24 = 32-8).
  var GEO_WEIT = { STEP_W: 13, FLIGHT: 6, RAIL_W: 120, X_MIN: 20, X_MAX: 98 };
  // V8.81: Spur auf den 14px-Randstreifen VOR dem Textbeginn (x=14) verengt.
  // Die Figur ist ~13px breit (Arme +-6 um die Achse, Kopf r4.6) - Achse 3..7
  // haelt alles im Canvas; was die Treppe darueber hinaus zeichnet, schneidet
  // das 14px-Canvas ab. Vorher (RAIL_W 46) lag die Figur auf Buchstaben.
  var GEO_SCHMAL = { STEP_W: 5, FLIGHT: 3, RAIL_W: 14, X_MIN: 3, X_MAX: 7 };
  var FIG_S = 1;   // V8.89: Figur-Massstab (schmale Spur: 0.62, sonst 1)
  var TEMPO_MAX = 0.024;    // ~24 Stufen/s bei 60fps

  var rail, canvas, ctx, overlay, octx, griff, leiste, anfasser;
  var dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  var railH = 0, vpW = 0, vpH = 0, docH = 0, maxStufe = 100, leisteTop = 78;
  var current = 0, lastCurrent = 0, idleSeit = 0, lastTs = 0;
  var letzteRichtung = 1;

  // FESTE Farben (Arturs Ansage) — eine Palette je Hintergrund-Art
  var FARBEN = {
    dunkel: { linie: "rgba(241,235,222,.45)", figur: "rgba(251,253,254,.92)", augeHell: true },
    papier: { linie: "rgba(7,25,31,.38)", figur: "rgba(7,25,31,.9)", augeHell: false }
  };
  // FESTE Abschnitts-Positionen (Seiten-Koordinaten), beim Messen aufgebaut
  var abschnitte = [];
  var farbe = { linie: "rgba(241,235,222,.45)", figur: "rgba(251,253,254,.92)", augeHell: true };
  // Modus: laufen (Treppe) | greifen (gepackt) | welt (Physik: fliegt/laeuft auf Elementen)
  var modus = "laufen";
  var zieh = { x: 0, y: 0, spur: [] };
  // Welt-Physik: die Figur behandelt Seiten-Elemente als Plattformen (Seiten-Koordinaten).
  var welt = { wx: 0, wy: 0, vx: 0, vy: 0, amBoden: false, stand: null, phase: 0, dir: -1, rot: 0,
               springt: false, springT: 0, springVon: { x: 0, y: 0 }, springZiel: { x: 0, y: 0 },
               springStufe: 0, springDauer: 360, springBogen: 38 };
  var weltPlattformen = [];
  var STAIR_JUMP_X = 150; // ab diesem x springt die Figur seitlich auf die Treppe (statt bis unten zu fallen)
  var STAIR_ZONE_X = X_MAX + STEP_W + 8; // Treppen-Zone (links): solide Landeflaeche; wird in messen() neu gesetzt

  function posAufTreppe(s) {
    var lauf = Math.floor(s / FLIGHT);
    var innen = s - lauf * FLIGHT;
    var nachRechts = lauf % 2 === 0;
    var x0 = nachRechts ? X_MIN : X_MAX;
    return { x: x0 + (nachRechts ? 1 : -1) * STEP_W * innen, y: s * STEP_H, dir: nachRechts ? 1 : -1 };
  }

  function messen() {
    dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));  // bei Monitorwechsel neu
    // Geometrie zuerst - RAIL_W geht in die Canvas-Breite ein, STAIR_ZONE_X
    // haengt an X_MAX. Beim Drehen des Geraets greift das automatisch.
    var g = nurLeiste() ? GEO_SCHMAL : GEO_WEIT;
    FIG_S = nurLeiste() ? 0.62 : 1;   // V8.89: volle Figur wirkte in 14px gequetscht (Arturs Befund)
    STEP_W = g.STEP_W; FLIGHT = g.FLIGHT; RAIL_W = g.RAIL_W;
    X_MIN = g.X_MIN; X_MAX = g.X_MAX;
    STAIR_ZONE_X = X_MAX + STEP_W + 8;
    vpW = window.innerWidth; vpH = window.innerHeight;
    docH = document.documentElement.scrollHeight;
    rail.style.height = "";            // Hoehe kommt aus CSS (fixed top:0 bottom:0 = Fensterhoehe)
    railH = vpH;                       // Canvas bleibt FENSTERGROSS -> unter dem GPU-Textur-Limit (16384)
    canvas.width = Math.round(RAIL_W * dpr); canvas.height = Math.round(railH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    overlay.width = Math.round(vpW * dpr); overlay.height = Math.round(vpH * dpr);
    octx.setTransform(dpr, 0, 0, dpr, 0, 0);
    maxStufe = Math.max(10, Math.floor((docH - 24) / STEP_H));  // bis fast an den Seitenboden
    if (leiste) leisteTop = leiste.getBoundingClientRect().top || leisteTop; // Header-Hoehe fuer Welt-Y der A-Leiste
    abschnitteAufbauen();
    heroMessen();
    if (modus === "welt") weltPlattformenBauen();  // Plattformen bei Layout-Aenderung frisch halten
  }

  var letzteFarbeWarPapier = false;
  // Eigene Ideen: kleiner Freuden-Hüpfer nach langem Nachlaufen, Blinzeln beim Stehen
  var warWeitWeg = false, hopfBis = 0, blinzelt = false;
  // Ideen-Panel: Landungs-Stauchung, Innehalten nach hartem Aufprall, Skript-Blick bei Ruhe,
  // seltenes Sitzen, Mini-Hüpfer bei kleinen Absätzen.
  var stauchBis = 0, pauseBis = 0, letzteMausT = 0, sitzBis = 0, sitzErlaubtAb = 0, stepHopBis = 0;
  // Mauszeiger-Verfolgung: im Stehen dreht sich die Figur zur Maus,
  // im Laufen folgen nur die Augen
  var mausX = -1, mausY = -1, blickDir = 1, blickDy = 0;

  // Ist der (ggf. vererbte) Hintergrund einer Sektion hell? Liest die echte
  // berechnete Farbe; bei durchsichtigem Hintergrund geht es zu den Eltern hoch.
  // So passt sich die Treppe auf JEDER Seite an, nicht nur bei .paper/.signal-section.
  function hintergrundHell(el) {
    var node = el;
    while (node && node.nodeType === 1) {
      var bg = getComputedStyle(node).backgroundColor || "";
      var m = bg.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)/);
      if (m) {
        var a = m[4] === undefined ? 1 : parseFloat(m[4]);
        if (a > 0.1) {
          var lum = (0.299 * +m[1] + 0.587 * +m[2] + 0.114 * +m[3]) / 255;
          return lum > 0.5;
        }
      }
      node = node.parentElement;
    }
    return false;
  }

  // Abschnitts-Tabelle aufbauen: [von, bis, istPapier] in Seiten-Koordinaten.
  // Damit ist der Farbwechsel EXAKT an den Abschnittsgrenzen — keine Live-Messung.
  var kanten = []; // alle Abschnittsgrenzen (y), zum Teilen der Stufen-Linien
  function abschnitteAufbauen() {
    abschnitte = [];
    var sy = window.scrollY || 0;
    document.querySelectorAll("section, footer").forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.height < 40) return;
      abschnitte.push({
        von: r.top + sy,
        bis: r.bottom + sy,
        papier: el.classList.contains("paper") || el.classList.contains("signal-section") || hintergrundHell(el)
      });
    });
    abschnitte.sort(function (a, b) { return a.von - b.von; });
    kanten = [];
    abschnitte.forEach(function (a) { kanten.push(a.von, a.bis); });
    kanten.sort(function (a, b) { return a - b; });
  }

  function istPapierBei(worldY) {
    for (var i = 0; i < abschnitte.length; i++) {
      if (worldY >= abschnitte[i].von && worldY < abschnitte[i].bis) return abschnitte[i].papier;
    }
    return false; // außerhalb: dunkler Seiten-Hintergrund
  }

  // Mehrheits-Regel (Arturs 51 %): 5 Punkte von Kopf bis Fuß gegen die
  // Abschnitts-Tabelle — die überwiegende Hintergrund-Art entscheidet.
  function figurFarbe(worldY) {
    var papierTreffer = 0;
    for (var i = 0; i < 5; i++) {
      if (istPapierBei(worldY - 38 + i * 9.5)) papierTreffer++;
    }
    var papier = papierTreffer > 2.5;
    letzteFarbeWarPapier = papier;
    farbe = papier ? FARBEN.papier : FARBEN.dunkel;
  }

  // Treppe pro Bild im sichtbaren Fenster zeichnen, in BILDSCHIRM-Koordinaten (y = p.y - sy).
  // Das Canvas bleibt fenstergross; die Treppe scrollt trotzdem mit, weil jede Stufe an ihrer
  // Seiten-Position minus Scroll gezeichnet wird. Segmentweise gefaerbt (Wechsel exakt an Grenze).
  function zeichneTreppe(sy) {
    var vonStufe, bisStufe;
    if (nurLeiste()) {
      // Nur die Stufen unter den Fuessen: 5 statt ~42. Das Auge liest sie als
      // Boden, nicht als Kratzer quer durch den Text.
      vonStufe = Math.max(0, Math.floor(current) - 2);
      bisStufe = Math.min(maxStufe, Math.ceil(current) + 2);
    } else {
      vonStufe = Math.max(0, Math.floor(sy / STEP_H) - 2);
      bisStufe = Math.min(maxStufe, Math.ceil((sy + vpH) / STEP_H) + 2);
    }
    ctx.lineWidth = 1;
    ctx.lineCap = "square";
    var paesse = [
      { farbe: FARBEN.dunkel.linie, papier: false },
      { farbe: FARBEN.papier.linie, papier: true }
    ];
    for (var pi = 0; pi < 2; pi++) {
      ctx.strokeStyle = paesse[pi].farbe;
      ctx.beginPath();
      for (var s = vonStufe; s <= bisStufe; s++) {
        var p = posAufTreppe(s);
        var y = p.y - sy;
        if (y < -30 || y > vpH + 30) continue;
        if (istPapierBei(p.y) === paesse[pi].papier) {
          ctx.moveTo(p.x, y);
          ctx.lineTo(p.x + STEP_W * p.dir, y);
        }
        if (s < maxStufe) {
          var xR = p.x + STEP_W * p.dir;
          var von = p.y, bis = p.y + STEP_H, seg = von;
          for (var ki = 0; ki <= kanten.length; ki++) {
            var ende = ki < kanten.length ? kanten[ki] : bis;
            if (ende <= seg) continue;
            if (ende > bis) ende = bis;
            if (istPapierBei((seg + ende) / 2) === paesse[pi].papier) {
              ctx.moveTo(xR, seg - sy);
              ctx.lineTo(xR, ende - sy);
            }
            seg = ende;
            if (seg >= bis) break;
          }
        }
      }
      ctx.stroke();
    }
  }

  function zeichneFigur(c, x, y, phase, dir, steht, pose, rot, stauch) {
    c.save();
    c.translate(x, y);
    if (rot) c.rotate(rot);
    if (stauch) c.scale(1 + stauch * 0.16, 1 - stauch * 0.20);  // Idee 1: Landungs-Stauchung
    if (FIG_S !== 1) c.scale(FIG_S, FIG_S);  // V8.89: Mini-Figur passt MIT Kopf und Armen in die 14px-Spur
    c.strokeStyle = farbe.figur; c.fillStyle = farbe.figur;
    c.lineWidth = stauch ? 2 / (1 - stauch * 0.20) : 2; c.lineCap = "round"; c.lineJoin = "round";
    var bob = steht || pose ? 0 : Math.sin(phase * Math.PI * 2) * 1.3;
    var hueftY = -16 + bob, schulterY = -26 + bob;
    var beinA = Math.sin(phase * Math.PI * 2), beinB = -beinA;
    var spann = steht ? 2.5 : 6.5;
    c.beginPath();
    if (pose === "haengt") {
      c.moveTo(0, hueftY); c.lineTo(-3, -2 + Math.sin(phase * 6) * 1.5);
      c.moveTo(0, hueftY); c.lineTo(3, -1 - Math.sin(phase * 6) * 1.5);
      c.moveTo(0, hueftY); c.lineTo(0, schulterY);
      c.moveTo(0, schulterY + 2); c.lineTo(-4, schulterY - 7);
      c.moveTo(0, schulterY + 2); c.lineTo(4, schulterY - 7);
    } else if (pose === "fliegt") {
      c.moveTo(0, hueftY); c.lineTo(-6, -3);
      c.moveTo(0, hueftY); c.lineTo(6, -5);
      c.moveTo(0, hueftY); c.lineTo(0, schulterY);
      c.moveTo(0, schulterY + 2); c.lineTo(-7, schulterY - 4);
      c.moveTo(0, schulterY + 2); c.lineTo(7, schulterY - 2);
    } else if (pose === "sitzt") {
      // Idee 6: sitzt auf einer Kante, Beine baumeln locker
      var baum = Math.sin(phase * Math.PI * 2) * 1.6;  // Zyklus schliesst glatt (kein Ruckeln beim Sitzen)
      c.moveTo(-2, hueftY); c.lineTo(-4, hueftY + 10 + baum);
      c.moveTo(2, hueftY); c.lineTo(4, hueftY + 10 - baum);
      c.moveTo(0, hueftY); c.lineTo(0, schulterY);
      c.moveTo(0, schulterY + 2); c.lineTo(-4, schulterY + 6);
      c.moveTo(0, schulterY + 2); c.lineTo(4, schulterY + 6);
    } else {
      c.moveTo(0, hueftY);
      c.lineTo((steht ? -spann : beinA * spann * dir), -(steht ? 0 : Math.max(0, beinA) * 4));
      c.moveTo(0, hueftY);
      c.lineTo((steht ? spann : beinB * spann * dir), -(steht ? 0 : Math.max(0, beinB) * 4));
      c.moveTo(0, hueftY); c.lineTo(0, schulterY);
      var arm = steht ? 0.15 : Math.sin(phase * Math.PI * 2 + Math.PI) * 0.9;
      c.moveTo(0, schulterY + 2); c.lineTo(Math.sin(arm) * 6 * dir + (steht ? -3 : 0), schulterY + 9);
      c.moveTo(0, schulterY + 2); c.lineTo(-Math.sin(arm) * 6 * dir + (steht ? 3 : 0), schulterY + 9);
    }
    c.stroke();
    // Kopf: im Stehen zur Maus gedreht (Körper-dir zeigt dann zur Maus),
    // im Laufen bleibt der Kopf in Laufrichtung — nur das Auge folgt der Maus.
    // Hoch/runter schauen: der ganze Kopf neigt sich mit (Arturs Ansage).
    var frei = !pose || pose === "sitzt"; // sitzend darf der Kopf frei schauen
    var kopfX = dir * 1.5, kopfY = schulterY - 6 + (frei ? blickDy * 2 : 0);
    if (!frei) { kopfX = 0; }
    c.beginPath(); c.arc(kopfX, kopfY, 4.6, 0, Math.PI * 2); c.fill();
    if (!blinzelt) {
      c.fillStyle = farbe.augeHell ? "#07191f" : "#f1ebde";
      var blick = frei ? blickDir : dir;
      c.beginPath(); c.arc(kopfX + blick * 2.1, kopfY - 0.6 + blickDy * 2.2, 1.05, 0, Math.PI * 2); c.fill();
    }
    c.restore();
  }

  function griffSetzen(viewX, viewY, sichtbar) {
    if (!sichtbar) { griff.style.display = "none"; return; }
    griff.style.display = "block";
    griff.style.transform = "translate(" + (viewX - 22) + "px," + (viewY - 40) + "px)";
  }

  // Plattformen aus echten Seiten-Elementen bauen (Seiten-Koordinaten). Die Oberkante
  // jedes Elements ist eine Lauffläche; ganz unten kommt der Seitenboden dazu.
  function weltPlattformenBauen() {
    weltPlattformen = [];
    var sy = window.scrollY || 0;
    // Kuratierte, WIEDERKEHRENDE Objekte als Plattformen (keine einzelnen Textzeilen -> ruhiger, sinnvoller):
    // Ueberschriften, Buttons, Karten/Artikel, Bilder, Chips, Demo-Widgets.
    var sel = "h1,h2,h3,.button,a.button,.service,article,figure,img,blockquote,.pill,.chip,.stat,.price-card,.success-card,.report-sheet,.legal-section h2,.footer-links";
    var els = document.querySelectorAll(sel);
    for (var i = 0; i < els.length && weltPlattformen.length < 180; i++) {
      // Feste/klebende Kopf-/Sticky-Elemente ueberspringen: ihre Seiten-Position driftet beim
      // Scrollen (r.top bleibt gleich, sy nicht) -> sonst Phantom-Plattform im Flug.
      if (els[i].closest(".site-header,.mobile-dock,.demo-topbar,.auto-topbar,.process-sticky,.faq-intro,.legal-nav")) continue;
      var r = els[i].getBoundingClientRect();
      if (r.width < 36 || r.height < 20) continue;   // keine duennen Textzeilen als Plattform
      // Verschachteltes Kind mit fast gleicher Oberkante wie ein Vorfahr-Treffer ueberspringen
      // (sonst doppelte Plattform an derselben Kante -> theoretisches Jitter-Risiko).
      var vor = els[i].parentElement && els[i].parentElement.closest(sel);
      if (vor && Math.abs(vor.getBoundingClientRect().top - r.top) < 8) continue;
      weltPlattformen.push({ x: r.left, r: r.right, top: r.top + sy });
    }
    weltPlattformen.push({ x: -20, r: Math.max(vpW, docH) + 20, top: docH - 3, boden: true }); // Seitenboden
    weltPlattformen.sort(function (a, b) { return a.top - b.top; });
  }

  function wurfStarten(vx, vy) {
    weltPlattformenBauen();
    welt.vx = vx; welt.vy = vy; welt.amBoden = false; welt.stand = null; welt.rot = 0;
    welt.springt = false; welt.springT = 0;  // laufenden Sprung abbrechen (Regriff-Bug)
    stauchBis = pauseBis = stepHopBis = 0;    // Idee-Timer nicht als Altlast in den neuen Wurf ziehen
    modus = "welt";
  }

  // V8.69 Akku: Die Schleife forderte bisher BEDINGUNGSLOS jedes Bild neu an -
  // 60 Bilder je Sekunde, solange die Seite offen ist, auch wenn niemand
  // scrollt. Am Schreibtisch faellt das nicht auf, auf dem Handy schon.
  // Im Schmalmodus haelt sie deshalb nach 1,5s Ruhe an und wird vom naechsten
  // Scrollen geweckt.
  var LEERLAUF_STOPP_MS = 1500;
  function schleife(ts) {
    window.__treppeBilder = (window.__treppeBilder || 0) + 1; // Messpunkt fuer die QA
    if (reduce.matches || document.hidden) { laeuft = false; return; }
    if (nurLeiste() && modus === "laufen" && idleSeit > LEERLAUF_STOPP_MS) {
      laeuft = false;                       // ruht, bis wieder gescrollt wird
      return;
    }
    requestAnimationFrame(schleife);
    tick(ts);
  }
  function starten() {
    if (laeuft || reduce.matches || document.hidden) return;
    laeuft = true;
    lastTs = 0;
    // WICHTIG: Ruhezaehler zuruecksetzen. Ohne das prueft schleife() sofort
    // wieder "idleSeit > Grenze" und haelt im selben Bild an - die Figur
    // wuerde nach dem ersten Leerlauf-Stopp nie wieder gezeichnet und das A
    // bliebe stehen. (Von Artur auf dem echten Geraet gefunden.)
    idleSeit = 0;
    requestAnimationFrame(schleife);
  }

  var heroUnterkante = 0;
  function heroMessen() {
    var h = document.querySelector(".hero");
    heroUnterkante = h ? h.getBoundingClientRect().bottom + (window.scrollY || 0) : 0;
  }

  function tick(ts) {
    var sy0 = window.scrollY || 0;
    if (!rail.offsetWidth) { griff.style.display = "none"; leisteAktualisieren(sy0); return; }
    // Schmalmodus (Handy): Leiste immer, Figur nur unterhalb des Hero-Bereichs.
    // Sonst stuende sie beim Seitenaufbau mitten auf der Werkprobe - genau der
    // Schauseite. Nebenwirkung: der erste Bildschirm hat null Canvas-Arbeit.
    if (nurLeiste()) griff.style.display = "none";
    var dt = lastTs ? Math.min(64, ts - lastTs) : 16;
    lastTs = ts;
    var sy = sy0;

    ctx.clearRect(0, 0, RAIL_W, vpH);  // fenstergrosses Canvas ganz loeschen
    // Das fenstergrosse Overlay ist nur fuer Greifen/Werfen da - mobil beides
    // aus, also auch nicht loeschen (bei 390x844 und dpr 2 sind das 1,3 Mpx je Bild).
    if (!nurLeiste()) octx.clearRect(0, 0, vpW, vpH);
    leisteAktualisieren(sy);
    if (modus === "laufen") {
      // Ziel: die Stufe nahe der Fenstermitte — die Figur verfolgt das Fenster
      var ziel = Math.max(0, Math.min(maxStufe, (sy + vpH * 0.46) / STEP_H));
      var diff = ziel - current;
      // V8.69, Schmalmodus: Auf dem Handy wird schnell und weit gescrollt. Mit
      // dem Desktop-Tempo (max. 24 Stufen/s) braeuchte die Figur nach einem
      // Sprung ueber eine halbe Seite rund 15 Sekunden - sie waere praktisch
      // nie zu sehen. Ab 25 Stufen Rueckstand setzt sie deshalb einmal nach
      // (bleibt knapp hinter dem Ziel, laeuft den Rest sichtbar).
      if (nurLeiste() && Math.abs(diff) > 25) {
        current = ziel - (diff > 0 ? 6 : -6);
        diff = ziel - current;
        warWeitWeg = true;
      }
      var tempo = 0.004 + Math.min(TEMPO_MAX - 0.004, Math.abs(diff) * 0.0016);
      var maxSchritt = dt * tempo;
      var bewegt = Math.abs(diff) > 0.015;
      if (Math.abs(diff) > 4) warWeitWeg = true;
      if (bewegt) { current += Math.max(-maxSchritt, Math.min(maxSchritt, diff)); idleSeit = 0; }
      else {
        idleSeit += dt;
        if (warWeitWeg) { warWeitWeg = false; hopfBis = ts + 300; } // angekommen: Hüpfer
      }
      var steht = idleSeit > 260;
      blinzelt = steht && (ts % 3800) < 150;
      var delta = current - lastCurrent; lastCurrent = current;
      if (Math.abs(delta) > 0.0001) {
        var pv = posAufTreppe(current + (delta > 0 ? 0.35 : -0.35));
        var ph = posAufTreppe(current);
        if (Math.abs(pv.x - ph.x) > 0.3) letzteRichtung = pv.x > ph.x ? 1 : -1;
      }
      var p = posAufTreppe(current);
      var viewY = p.y - sy;
      figurFarbe(p.y);
      if (!(nurLeiste() && current * STEP_H < heroUnterkante)) zeichneTreppe(sy);
      var hopf = ts < hopfBis ? -7 * Math.sin((1 - (hopfBis - ts) / 300) * Math.PI) : 0;
      if (mausX >= 0) {
        blickDir = mausX >= p.x ? 1 : -1;
        blickDy = Math.max(-1, Math.min(1, (mausY - (viewY - 32)) / 160));
      } else { blickDir = 1; blickDy = 0; }
      // Idee 5: Skript-Blick, wenn die Maus lange ruht und die Figur steht
      if (steht && ts - letzteMausT > 4000) { blickDir = Math.sin(ts / 1500) >= 0 ? 1 : -1; blickDy = Math.sin(ts / 2300) * 0.5; }
      // Idee 6: sehr seltenes Sitzen (langer Cooldown), nur im Stehen
      if (steht && ts > sitzErlaubtAb && Math.random() < 0.0016) { sitzBis = ts + 3600; sitzErlaubtAb = ts + 90000; }
      var sitzt = steht && ts < sitzBis;
      var koerperDir = steht ? blickDir : letzteRichtung;
      var stauch = ts < stauchBis ? (stauchBis - ts) / 140 : 0;
      // Schmalmodus: solange die Figur im Hero-Bereich steht, wird sie nicht
      // gemalt - dort liegt die Werkprobe, die Schauseite. Die Bewegung oben
      // laeuft trotzdem weiter; wer sie hier aussperrt, laesst die Figur fuer
      // immer auf Stufe 0 stehen (beim Bau passiert und gemessen).
      var imHero = nurLeiste() && current * STEP_H < heroUnterkante;
      if (imHero) ctx.clearRect(0, 0, RAIL_W, vpH);
      if (!imHero && viewY > -50 && viewY < vpH + 50) {
        var phaseAus = sitzt ? (ts / 800) % 1 : ((current % 1) + 1) % 1;
        zeichneFigur(ctx, p.x, viewY + hopf, phaseAus, koerperDir, steht, sitzt ? "sitzt" : null, 0, stauch);
        griffSetzen(p.x, viewY, true);
      } else {
        griffSetzen(0, 0, false);
      }
      if (window.__treppeDebug) window.__treppe = { modus: modus, current: current, ziel: ziel, steht: steht, maxStufe: maxStufe, papier: letzteFarbeWarPapier, blick: blickDir, abschnitte: abschnitte.length };
    } else if (modus === "greifen") {
      figurFarbe(zieh.y + sy);
      zeichneTreppe(sy);
      zeichneFigur(octx, zieh.x, zieh.y, (ts / 400) % 1, 1, false, "haengt", 0);
      griffSetzen(zieh.x, zieh.y, true);
      if (window.__treppeDebug) window.__treppe = { modus: modus, x: zieh.x, y: zieh.y };
    } else if (modus === "welt") {
      var sek = Math.min(0.05, dt / 1000);
      var G = 2400, LAUF = 165, STEP_UP = 30, SNAP = 46;
      if (welt.springt) {
        // Bogen-Sprung von einem Objekt SEITLICH auf die Treppe (in AKTUELLER Hoehe).
        // Dauer + Bogenhoehe skalieren mit der Sprungweite (langer Satz = hoeher/laenger).
        welt.springT = Math.min(1, welt.springT + dt / welt.springDauer);
        var jt = welt.springT;
        var ease = jt < 0.5 ? 2 * jt * jt : 1 - Math.pow(-2 * jt + 2, 2) / 2; // sanfter Ein-/Ausstieg
        welt.wx = welt.springVon.x + (welt.springZiel.x - welt.springVon.x) * ease;
        welt.wy = welt.springVon.y + (welt.springZiel.y - welt.springVon.y) * ease - Math.sin(jt * Math.PI) * welt.springBogen;
        if (jt < 0.14) welt.wy += (1 - Math.cos(jt / 0.14 * Math.PI * 2)) * 2;  // Idee 2: Anlauf-Hocke, ruckelfrei ein-/ausblendend
        welt.dir = -1;
        if (jt >= 1) {
          modus = "laufen";
          current = welt.springStufe; lastCurrent = welt.springStufe; idleSeit = 0;
          letzteRichtung = -1; hopfBis = ts + 260; stauchBis = ts + 120; welt.springt = false; // Idee 1: Stauchung beim Aufsetzen
        }
      } else if (!welt.amBoden) {
        // fliegen/fallen mit Schwerkraft
        welt.vy += G * sek;
        var prevWy = welt.wy;
        welt.wx += welt.vx * sek;
        welt.wy += welt.vy * sek;
        welt.rot += welt.vx * sek * 0.012;
        if (welt.wx < 10) { welt.wx = 10; welt.vx = Math.abs(welt.vx) * 0.5; }        // linke Wand
        if (welt.wx > vpW - 10) { welt.wx = vpW - 10; welt.vx = -Math.abs(welt.vx) * 0.5; } // rechte Wand
        if (welt.vy > 0 && welt.wx <= STAIR_ZONE_X) {
          // Treppe ist SOLIDE: faellt die Figur in die Treppen-Zone, landet sie auf der Stufe ihrer
          // Hoehe (nicht durchfallen). Der Sprung-Zweig setzt sie danach sauber auf die Stufe.
          if (welt.vy > 700) stauchBis = ts + 140; if (welt.vy > 1100) pauseBis = ts + 210; // Ideen 1+4
          welt.wy = Math.round(welt.wy / STEP_H) * STEP_H;
          welt.vy = 0; welt.vx = 0; welt.amBoden = true; welt.stand = null; welt.rot = 0;
        } else if (welt.vy > 0) { // fallend: hoechste Plattform-Oberkante, die die Fuesse durchquert haben
          var beste = null;
          for (var wi = 0; wi < weltPlattformen.length; wi++) {
            var pl = weltPlattformen[wi];
            if (welt.wx >= pl.x - 3 && welt.wx <= pl.r + 3 && pl.top >= prevWy - 2 && pl.top <= welt.wy + 2) {
              if (!beste || pl.top < beste.top) beste = pl;
            }
          }
          if (beste) { if (welt.vy > 700) stauchBis = ts + 140; if (welt.vy > 1100) pauseBis = ts + 210; welt.wy = beste.top; welt.vy = 0; welt.vx = 0; welt.amBoden = true; welt.stand = beste; welt.rot = 0; }
        }
        if (!welt.amBoden && welt.wy > docH + 150) {  // Sicherheitsnetz: Figur nie unter der Seite verlieren
          welt.wy = docH - 3; welt.vy = 0; welt.vx = 0; welt.amBoden = true; welt.stand = null; welt.rot = 0;
        }
      } else if (ts < pauseBis) {
        // Idee 4: nach hartem Aufprall kurz innehalten (nicht sofort weiterlaufen)
        welt.dir = -1;
      } else {
        // Auf einem Objekt nach LINKS laufen. An der OBJEKT-KANTE (oder nah an der Treppe) SPRINGT
        // die Figur seitlich auf die Treppe -- in AKTUELLER Hoehe, statt unten hochzuklettern.
        welt.dir = -1;
        var schritt = LAUF * sek;
        welt.wx -= schritt;
        welt.phase = (welt.phase + schritt / 26) % 1;
        var stuetze = null;
        for (var wj = 0; wj < weltPlattformen.length; wj++) {
          var q = weltPlattformen[wj];
          if (welt.wx >= q.x - 3 && welt.wx <= q.r + 3 && q.top >= welt.wy - STEP_UP && q.top <= welt.wy + SNAP) {
            if (!stuetze || Math.abs(q.top - welt.wy) < Math.abs(stuetze.top - welt.wy)) stuetze = q;
          }
        }
        if (stuetze && welt.wx > STAIR_JUMP_X) {
          if (welt.wy - stuetze.top > 8 && ts > stepHopBis) stepHopBis = ts + 130;  // Idee 3: Mini-Hüpfer bei Absatz hoch
          welt.wy = stuetze.top; welt.stand = stuetze;
        } else {
          // Objekt-Kante links erreicht ODER nah an der Treppe -> Sprung auf die Stufe der aktuellen Hoehe
          welt.springStufe = Math.max(0, Math.min(maxStufe, Math.round(welt.wy / STEP_H)));
          var pz = posAufTreppe(welt.springStufe);
          welt.springVon = { x: welt.wx, y: welt.wy };
          welt.springZiel = { x: pz.x, y: pz.y };
          var dx = Math.abs(welt.springVon.x - welt.springZiel.x);
          welt.springBogen = Math.max(30, Math.min(90, dx * 0.16 + 22));    // weiter -> hoeherer Bogen
          welt.springDauer = Math.max(320, Math.min(720, dx * 1.15 + 240)); // weiter -> etwas laenger
          welt.springt = true; welt.springT = 0;
        }
      }
      figurFarbe(welt.wy);
      zeichneTreppe(sy);
      if (modus === "welt") {
        var wViewY = welt.wy - sy;
        var wStauch = ts < stauchBis ? (stauchBis - ts) / 140 : 0;                          // Idee 1
        var wHop = ts < stepHopBis ? -Math.sin((stepHopBis - ts) / 130 * Math.PI) * 5 : 0;  // Idee 3
        var pausiert = welt.amBoden && ts < pauseBis;                                        // Idee 4
        griffSetzen(welt.wx, wViewY, wViewY > -60 && wViewY < vpH + 60);
        if (welt.springt) zeichneFigur(octx, welt.wx, wViewY, 0, -1, false, "fliegt", 0, 0);
        else if (welt.amBoden) zeichneFigur(octx, welt.wx, wViewY + wHop, welt.phase, welt.dir, pausiert, null, 0, wStauch);
        else zeichneFigur(octx, welt.wx, wViewY, 0, welt.vx >= 0 ? 1 : -1, false, "fliegt", welt.rot, 0);
      }
      if (window.__treppeDebug) window.__treppe = { modus: modus, wx: Math.round(welt.wx), wy: Math.round(welt.wy), amBoden: welt.amBoden, springt: welt.springt, plattformen: weltPlattformen.length };
    }
  }

  // Rechte A-Leiste: der Buchstabe A ZEIGT den Scroll-Stand an, die Farbe
  // wechselt am Abschnitt (hell/dunkel) wie bei der Treppe.
  // V8.94 (Arturs Entscheid "es soll nur mitlaufen ohne scroll funktion"):
  // Das A ist kein Griff mehr. Ziehen, Halte-Riegel, Zitter-Hysterese und die
  // Wisch-Sperre sind ersatzlos entfernt - die Geschichte steht im git log.
  // Diese Rechnung hier ist die Rueckfallebene fuer Browser ohne
  // scroll()-Zeitleiste; sonst zeichnet die scroll-gesteuerte Animation aus
  // site.css die Lage (V8.92), und zwar neben dem Hauptfaden.
  function leisteAktualisieren(sy) {
    if (!leiste || !leiste.offsetWidth) return;
    var spurH = leiste.clientHeight - 28;
    var maxScroll = Math.max(1, docH - vpH);
    var anteil = Math.min(1, Math.max(0, sy / maxScroll));
    var top = 14 + anteil * (spurH - 40);
    anfasser.style.top = top + "px";
    var weltY = sy + leisteTop + top + 20; // A-Mitte in Seiten-Koordinaten
    anfasser.classList.toggle("auf-papier", istPapierBei(weltY));
  }

  function greifenStart(e) {
    var sy = window.scrollY || 0;
    if (modus === "welt") { zieh.x = welt.wx; zieh.y = welt.wy - sy; }
    else { var p = posAufTreppe(current); zieh.x = p.x; zieh.y = p.y - sy; }
    modus = "greifen";
    zieh.spur = [{ x: e.clientX, y: e.clientY, t: performance.now() }];
    e.preventDefault();
    window.addEventListener("pointermove", greifenBewegen);
    window.addEventListener("pointerup", greifenEnde, { once: true });
    window.addEventListener("pointercancel", greifenEnde, { once: true });
  }
  function greifenBewegen(e) {
    zieh.x = e.clientX; zieh.y = e.clientY;
    zieh.spur.push({ x: e.clientX, y: e.clientY, t: performance.now() });
    if (zieh.spur.length > 6) zieh.spur.shift();
  }
  function greifenEnde() {
    window.removeEventListener("pointermove", greifenBewegen);
    window.removeEventListener("pointerup", greifenEnde);
    window.removeEventListener("pointercancel", greifenEnde);
    var jetzt = performance.now();
    var alt = zieh.spur[0], neu = zieh.spur[zieh.spur.length - 1];
    var dtMs = Math.max(16, neu.t - alt.t);
    var vx = (neu.x - alt.x) / dtMs * 1000;
    var vy = (neu.y - alt.y) / dtMs * 1000;
    var mag = Math.hypot(vx, vy);
    if (mag > 2600) { vx *= 2600 / mag; vy *= 2600 / mag; }
    welt.wx = zieh.x;
    welt.wy = Math.min(zieh.y + (window.scrollY || 0), docH - 5);  // nie unter den Seitenboden werfen
    wurfStarten(vx, vy - 120);
  }

  function griffTastatur(e) {
    var erlaubt = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", " ", "Enter"];
    if (erlaubt.indexOf(e.key) === -1) return;
    e.preventDefault();

    var p = modus === "welt" ? { x: welt.wx, y: welt.wy } : posAufTreppe(current);
    welt.wx = p.x;
    welt.wy = p.y;

    var vx = 0, vy = -760;
    if (e.key === "ArrowLeft") { vx = -720; vy = -420; }
    if (e.key === "ArrowRight") { vx = 720; vy = -420; }
    if (e.key === "ArrowUp") { vx = 0; vy = -940; }
    if (e.key === "ArrowDown") { vx = 0; vy = 520; }
    if (e.key === " " || e.key === "Enter") { vx = 520; vy = -760; }
    wurfStarten(vx, vy);
  }

  function init() {
    rail = document.createElement("div");
    rail.className = "treppe-rail";
    rail.setAttribute("aria-hidden", "true");
    canvas = document.createElement("canvas");
    rail.appendChild(canvas);
    overlay = document.createElement("canvas");
    overlay.className = "treppe-overlay";
    overlay.setAttribute("aria-hidden", "true");
    griff = document.createElement("button");
    griff.type = "button";
    griff.className = "treppe-griff";
    griff.setAttribute("aria-label", "Treppenfigur bewegen – Pfeiltasten oder Leertaste drücken");
    griff.setAttribute("title", "Mit Pfeiltasten oder Leertaste bewegen");
    leiste = document.createElement("div");
    leiste.className = "a-leiste";
    leiste.setAttribute("aria-hidden", "true");
    anfasser = document.createElement("div");
    anfasser.className = "a-anfasser";
    anfasser.textContent = "A";
    leiste.appendChild(anfasser);
    document.body.appendChild(rail);
    document.body.appendChild(overlay);
    document.body.appendChild(griff);
    document.body.appendChild(leiste);
    // V8.94 (Arturs Entscheid): Am A haengt KEIN Zeiger-Listener mehr. Es ist
    // reiner Anzeiger - Beruehrungen und Klicks gehen hindurch (site.css:
    // pointer-events:none). Die Geschichte des Griffs steht im git log.
    ctx = canvas.getContext("2d");
    octx = overlay.getContext("2d");
    messen();
    window.addEventListener("resize", messen, { passive: true });
    document.addEventListener("visibilitychange", starten);
    window.addEventListener("scroll", starten, { passive: true }); // weckt nach Leerlauf-Stopp
    if (desktopMQ.addEventListener) desktopMQ.addEventListener("change", starten);
    if (!nurLeiste()) window.addEventListener("mousemove", function (e) { mausX = e.clientX; mausY = e.clientY; letzteMausT = performance.now(); }, { passive: true });
    setInterval(function () { // Seitenhöhe kann sich ändern (Preis-Tabs etc.)
      // Im Hintergrund-Tab nichts messen: messen() ruft abschnitteAufbauen(),
      // das ueber alle Abschnitte laeuft und Layout erzwingt.
      if (document.hidden) return;
      var h = document.documentElement.scrollHeight;
      if (Math.abs(h - docH) > 40) messen();
    }, nurLeiste() ? 4000 : 2000);
    griff.addEventListener("pointerdown", greifenStart);
    griff.addEventListener("keydown", griffTastatur);
    reduce.addEventListener && reduce.addEventListener("change", function (e) {
      var aus = e.matches ? "none" : "";
      rail.style.display = aus; overlay.style.display = aus; griff.style.display = aus; leiste.style.display = aus;
      if (!e.matches) starten();
    });
    if (window.__treppeDebug) {
      window.__treppeWurf = function (vx, vy) {
        var p = posAufTreppe(current);
        welt.wx = p.x; welt.wy = p.y; wurfStarten(vx, vy);
      };
      window.__treppeTick = function (dt) { tick((lastTs || 16) + (dt || 16)); };
    }
    starten();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
