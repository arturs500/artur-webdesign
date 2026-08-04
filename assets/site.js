(() => {
  "use strict";

  const doc = document;
  const root = doc.documentElement;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const mobileNavigation = window.matchMedia("(max-width: 1120px)");

  const all = (selector, scope = doc) => Array.from(scope.querySelectorAll(selector));

  function setupOptionalVisuals() {
    const siteScript = all("script[src]").find((script) => {
      try { return /\/site\.js$/.test(new URL(script.src, doc.baseURI).pathname); }
      catch (error) { return false; }
    });
    if (!siteScript) return;

    const assetsBase = new URL(".", new URL(siteScript.src, doc.baseURI));
    const loaded = new Set();
    const load = (file) => {
      if (loaded.has(file) || doc.querySelector(`script[data-optional-visual="${file}"]`)) return;
      loaded.add(file);
      const script = doc.createElement("script");
      script.src = new URL(file, assetsBase).href;
      script.defer = true;
      script.dataset.optionalVisual = file;
      doc.head.appendChild(script);
    };

    const desktopVisuals = window.matchMedia("(min-width: 1400px)"); // Treppen-Schwelle wie damals (V8.8)
    // V8.83 (Arturs Ansage 03.08.2026): das echte 3D-Handy laeuft auf ALLEN
    // Geraeten - "auf dem Handy genauso wie auf dem Mac". Die Buehne rendert
    // ereignisgesteuert (0 Leerlauf-Last), Canvas hat touch-action:pan-y
    // (senkrecht wischen scrollt die Seite, waagerecht ziehen dreht). 320px
    // als Boden; scheitert WebGL, kommt weiterhin die 2D-Werkprobe.
    const handyVisual = window.matchMedia("(min-width: 320px)");
    let heroHandyStarted = false;
    let heroHandyReady = false;
    // V8.59: Einmal gescheitert = dauerhaft gescheitert. Ohne dieses Gedaechtnis
    // koennte ein spaeter eintreffendes onload das 3D wieder "fertig" melden — dann
    // haette die Seite ein leeres Handy-Feld UND die 2D-Werkprobe waere ausgeblendet.
    let heroHandyFailed = false;
    let heroStage = null;

    const heroHandyEligible = () => !reduceMotion.matches && handyVisual.matches;
    const syncHeroHandy = () => {
      const active = heroHandyEligible();
      if (heroStage && typeof heroStage.setActive === "function") {
        heroStage.setActive(active);
      }
      root.classList.toggle("hero3d", active && heroHandyReady && !heroHandyFailed);
    };
    // V8.59: Scheitert das 3D (Skript nicht ladbar, kein WebGL), bleibt die
    // Hero-Spalte auf grossen Schirmen sonst LEER — frueher stand dort das alte
    // Schema-Diagramm. ".hero3d-fehlt" holt stattdessen die 2D-Werkprobe herein
    // (siehe site.css, Regel im 1024er-Fenster). Erst hier gesetzt, nicht vorab:
    // solange das Laden laeuft, soll nichts aufblitzen, was gleich wieder geht.
    const failHeroHandy = () => {
      heroHandyReady = false;
      heroHandyFailed = true;
      root.classList.remove("hero3d");
      root.classList.add("hero3d-fehlt");
      if (heroStage && typeof heroStage.setActive === "function") {
        heroStage.setActive(false);
      }
    };

    // Neutrales 3D-Handy (Three.js, lokal gehostet). Nur passende Desktopgeräte.
    const loadHeroHandy = () => {
      if (heroHandyStarted) return;
      const mount = doc.querySelector("[data-hero-stage]");
      if (!mount) return;
      heroHandyStarted = true;
      heroStage = doc.createElement("three-d-stage");
      heroStage.setAttribute("name", "artur-demo-handy");
      heroStage.setAttribute("background", "transparent");
      mount.appendChild(heroStage);

      const s1 = doc.createElement("script");
      s1.src = new URL("hero3d-stage.js?v=137", assetsBase).href;
      s1.dataset.optionalVisual = "hero3d-stage.js";
      s1.onerror = failHeroHandy;
      s1.onload = () => {
        syncHeroHandy();
        // Die Buehne meldet ueber ihr ready-Versprechen, ob WebGL wirklich anlief.
        // Ohne dieses catch bliebe eine abgelehnte Zusage unbehandelt (Fehler in der
        // Browser-Konsole) UND niemand wuesste, dass Ersatz noetig ist.
        if (heroStage && heroStage.ready && typeof heroStage.ready.catch === "function") {
          heroStage.ready.catch(failHeroHandy);
        }
        const s2 = doc.createElement("script");
        s2.type = "module";
        s2.src = new URL("hero3d-handy.js?v=137", assetsBase).href;
        s2.dataset.optionalVisual = "hero3d-handy.js";
        s2.onload = () => {
          if (heroHandyFailed) return;
          heroHandyReady = true;
          syncHeroHandy();
        };
        s2.onerror = failHeroHandy;
        doc.head.appendChild(s2);
      };
      doc.head.appendChild(s1);
      const reset = doc.querySelector("[data-hero-reset]");
      if (reset) {
        reset.addEventListener("click", () => window.__heroHandy?.reset());
      }
    };

    const maybeLoad = () => {
      // V8.69: treppe.js laedt jetzt auch auf dem Handy - darin steckt die
      // A-Leiste, die Artur dort haben wollte. Die Treppe selbst und die Figur
      // bleiben unter 1400px aus (Entscheidung liegt in treppe.js, damit es
      // nur EINE Stelle gibt, die ueber Mobil entscheidet). 10 KB gepackt.
      // V8.92 (Arturs Befund "datenschutz impressum haben weder das Maennchen
      // noch das A"): Die Bedingung fragte nur nach ".hero" - diese Klasse gibt
      // es NUR auf der Startseite. Alle Unterseiten heissen ".subhero",
      // ".auto-hero" oder ".demo-hero", also lud treppe.js dort nie, und mit ihr
      // fehlten A-Leiste UND Figur komplett. Statt die Hero-Klassen aufzuzaehlen
      // (jede neue Seite haette dieselbe Falle) entscheidet jetzt ein
      // ausdruecklicher Schalter am body: data-treppe. So steht in jeder Datei
      // selbst, ob sie die Leiste haben soll - kurze Seiten ohne Inhaltstiefe
      // (danke, 404, bestellung, bezahlen, lead-paket) bekommen ihn bewusst
      // nicht, dort waere die Leiste reine Deko.
      if (!reduceMotion.matches &&
          (doc.querySelector(".hero") || (doc.body && doc.body.hasAttribute("data-treppe")))) {
        load("treppe.js?v=137");
      }
      if (heroHandyEligible() && doc.querySelector("[data-hero-stage]")) {
        loadHeroHandy();
      }
      syncHeroHandy();
    };

    // Erst nach dem ersten Seitenbild laden (window load + Leerlauf) — die 3D-Kette
    // (~457 KB gzip, gemessen 28.07.2026) darf den kritischen Pfad nie anfassen.
    // Bei Datensparmodus gar nicht.
    const conn = navigator.connection;
    const spare = !!(conn && (conn.saveData || /(^|\b)(2g|slow-2g|3g)\b/.test(conn.effectiveType || "")));
    const idle = (cb) => (window.requestIdleCallback ? window.requestIdleCallback(cb, { timeout: 2000 }) : window.setTimeout(cb, 350));
    const lazyLoad = () => idle(() => {
      if (!spare) maybeLoad();
      else syncHeroHandy();
    });
    if (document.readyState === "complete") lazyLoad();
    else window.addEventListener("load", lazyLoad, { once: true });
    desktopVisuals.addEventListener?.("change", lazyLoad);
    handyVisual.addEventListener?.("change", lazyLoad);
    reduceMotion.addEventListener?.("change", lazyLoad);
  }

  function setCurrentYear() {
    all("[data-current-year]").forEach((node) => {
      node.textContent = String(new Date().getFullYear());
    });
  }

  function setupMenu() {
    const toggle = doc.querySelector("[data-menu-toggle]");
    const nav = doc.querySelector("[data-menu]");
    if (!toggle || !nav) return;

    // Der direkte <body>-Nachkomme, der Menue + Umschalter enthaelt (der Header).
    // Beim Oeffnen alle Geschwister davon per `inert` sperren, damit der Hintergrund
    // fuer Tastatur und Vorlese-Software nicht erreichbar ist. Kein aria-modal
    // (ohne role=dialog undefiniert); der vorhandene Tab-Trap bleibt als Fallback.
    let menuScope = nav;
    while (menuScope.parentElement && menuScope.parentElement !== doc.body) menuScope = menuScope.parentElement;
    const setBackgroundInert = (on) => {
      if (menuScope.parentElement !== doc.body) return;
      Array.from(doc.body.children).forEach((child) => {
        if (child === menuScope) return;
        if (on) child.setAttribute("inert", "");
        else child.removeAttribute("inert");
      });
    };

    const close = (restoreFocus = false) => {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Menü öffnen");
      doc.body.classList.remove("menu-open");
      setBackgroundInert(false);
      if (restoreFocus) toggle.focus();
    };

    const open = () => {
      nav.classList.add("is-open");
      toggle.setAttribute("aria-expanded", "true");
      toggle.setAttribute("aria-label", "Menü schließen");
      doc.body.classList.add("menu-open");
      setBackgroundInert(true);
      const firstLink = nav.querySelector("a");
      if (firstLink) window.requestAnimationFrame(() => firstLink.focus());
    };

    toggle.addEventListener("click", () => {
      if (nav.classList.contains("is-open")) close();
      else open();
    });

    nav.addEventListener("click", (event) => {
      const link = event.target.closest("a");
      if (!link) return;
      close();
      // Sprung selbst ausführen: der native Anker-Scroll läuft, bevor die
      // aufgehobene Scroll-Sperre (body.menu-open) stilseitig wirksam ist,
      // und bleibt sonst stehen.
      const id = decodeURIComponent((link.hash || "").slice(1));
      const target = id ? doc.getElementById(id) : null;
      if (target) {
        event.preventDefault();
        history.pushState(null, "", link.hash);
        window.requestAnimationFrame(() => {
          target.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
          const focusTarget = target.matches("h1,h2,h3") ? target : target.querySelector("h1,h2,h3") || target;
          if (!focusTarget.hasAttribute("tabindex")) focusTarget.setAttribute("tabindex", "-1");
          window.setTimeout(() => focusTarget.focus({ preventScroll: true }), reduceMotion.matches ? 0 : 450);
        });
      }
    });

    doc.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && nav.classList.contains("is-open")) close(true);
      if (event.key !== "Tab" || !nav.classList.contains("is-open")) return;

      // In Dokumentreihenfolge sammeln: auf Unterseiten steht der Toggle VOR der
      // Nav — eine fest angehängte Liste ließe den Fokus hinter das Overlay fallen.
      const scope = nav.closest("header") || doc;
      const focusable = all("a,button:not([disabled])", scope).filter((el) => el === toggle || nav.contains(el));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && doc.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && doc.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    const resetAtBreakpoint = (event) => {
      if (!event.matches) close();
    };
    mobileNavigation.addEventListener?.("change", resetAtBreakpoint);
  }

  // V8.57: Sprungziele koennen den Preisbereich mitbringen.
  // Ursache -> Mechanismus -> Wirkung: Seit V8.56 gelten die Reiter auf JEDER Breite.
  // Damit zeigt #preise IMMER den Reiter "Website" — auch dann, wenn der Weg dorthin
  // einen anderen Bereich versprochen hat (Empfehlung "Anfragen-System", Leistungs-
  // karte "Google Ads", Ratgeber-Link "inklusive Google Ads und Anfragen-System").
  // Der beworbene Preis stand dann im ausgeblendeten Panel. Diese Weiche setzt vor
  // dem Sprung den passenden Reiter. Ohne JavaScript bleibt alles offen (noscript).
  let preisBereichAktivieren = () => false;

  function setupPriceTabs() {
    all("[data-price-tabs]").forEach((tabList) => {
      const tabs = all('[role="tab"]', tabList);
      const panels = tabs
        .map((tab) => doc.getElementById(tab.getAttribute("aria-controls")))
        .filter(Boolean);

      // Seit V8.56 gelten die Reiter auf JEDER Breite. Vorher klappte das Handy
      // alle vier Preisbereiche untereinander auf — rund fuenf Bildschirme, durch
      // die sich auch scrollen musste, wer nur die Website-Preise sehen wollte.
      // Ohne JavaScript bleiben weiterhin alle Bereiche offen (noscript-Stil).
      const activate = (tab, moveFocus = false) => {
        tabs.forEach((item) => {
          const selected = item === tab;
          item.setAttribute("aria-selected", String(selected));
          item.tabIndex = selected ? 0 : -1;
        });
        panels.forEach((panel) => {
          panel.hidden = panel.id !== tab.getAttribute("aria-controls");
        });
        if (moveFocus) tab.focus();
      };

      tabs.forEach((tab, index) => {
        tab.addEventListener("click", () => activate(tab));
        tab.addEventListener("keydown", (event) => {
          let nextIndex = null;
          if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % tabs.length;
          if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + tabs.length) % tabs.length;
          if (event.key === "Home") nextIndex = 0;
          if (event.key === "End") nextIndex = tabs.length - 1;
          if (nextIndex === null) return;
          event.preventDefault();
          activate(tabs[nextIndex], true);
        });
      });

      const selected = tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0];
      if (selected) activate(selected);

      // Weiche fuer Sprungziele: "wachstum" -> Reiter mit aria-controls="panel-wachstum".
      preisBereichAktivieren = (bereich) => {
        const ziel = tabs.find((tab) => tab.getAttribute("aria-controls") === `panel-${bereich}`);
        if (!ziel) return false;
        activate(ziel);
        return true;
      };
    });
  }

  // Zwei Wege fuehren zu einem bestimmten Preisbereich:
  // 1) Links auf derselben Seite mit data-preis-bereich (der Reiter wird VOR dem
  //    Sprung gesetzt, damit die Sprungmarke schon die richtige Hoehe hat).
  // 2) Links von anderen Seiten auf /#panel-wachstum: die Panel-Kennungen sind
  //    echte Ankerziele, deshalb springt auch ein Browser ohne JavaScript richtig
  //    (ohne JS steht jedes Panel offen — noscript-Regel).
  const PREIS_BEREICHE = ["web", "pflege", "wachstum", "ki"];

  function setupPreisSprungziele() {
    if (!doc.querySelector("[data-price-tabs]")) return;

    doc.addEventListener("click", (event) => {
      const link = event.target?.closest?.("a[data-preis-bereich]");
      if (!link) return;
      preisBereichAktivieren(link.dataset.preisBereich);
    });

    const ausHash = () => {
      const treffer = /^#panel-([a-z]+)$/.exec(window.location.hash || "");
      if (!treffer || PREIS_BEREICHE.indexOf(treffer[1]) < 0) return;
      if (!preisBereichAktivieren(treffer[1])) return;
      // Ziel ist GENAU das Panel — dasselbe Ziel, das auch der Browser selbst
      // anspringt. Zwei verschiedene Ziele hiessen zwei Scroll-Bewegungen
      // hintereinander (gemessen: erst zum Abschnitt, dann noch einmal 440 px
      // weiter). Dass die Reiterleiste dabei im Blick bleibt, macht der
      // scroll-margin-top der Panels in site.css.
      doc.getElementById(`panel-${treffer[1]}`)?.scrollIntoView({
        behavior: reduceMotion.matches ? "auto" : "smooth",
        block: "start"
      });
    };
    ausHash();
    window.addEventListener("hashchange", ausHash);
  }

  // ===== V8.50: Vorlagen fuer den kurzen Weg =====
  // Zweck: eine Anfrage ohne Tipparbeit im Nachrichtenfeld. Ein Tipp setzt einen
  // fertigen Satz, der danach frei aenderbar bleibt — kein Overlay, kein Zwang.
  // KOLLISION mit den Uebernahme-Wegen (60-Sekunden-Check, Handy-Demo) und mit
  // selbst geschriebenem Text ist der heikle Punkt. Regel: eine Vorlage darf
  // fremden Text NIE heimlich loeschen.
  // Ursache -> Mechanismus -> Wirkung: steht im Feld ein Text, den keine Vorlage
  // geschrieben hat, warnt die Zeile SCHON VOR dem Tippen ("Ein Tipp ersetzt
  // Ihren Text."); beim Ersetzen wird der alte Text gemerkt und ist ueber einen
  // sichtbaren Knopf zurueckholbar. Deshalb muessen die Vorlagen bei aktiver
  // Uebernahme nicht ausgeblendet werden — der schnelle Weg bleibt genau den
  // Interessenten erhalten, die schon aus Check oder Handy-Demo kommen.
  let vorlagenAktualisieren = () => {};

  function setupVorlagen() {
    const gruppe = doc.querySelector("[data-vorlagen]");
    const feld = doc.querySelector("#nachricht");
    if (!gruppe || !feld) return;
    const knoepfe = all("[data-vorlage]", gruppe);
    if (!knoepfe.length) return;
    const hinweis = gruppe.querySelector("[data-vorlagen-hinweis]");
    const hinweisText = gruppe.querySelector("[data-vorlagen-text]");
    const zurueck = gruppe.querySelector("[data-vorlagen-zurueck]");
    const saetze = knoepfe.map((knopf) => knopf.dataset.vorlage);
    let gemerkt = "";

    const istVorlage = (wert) => saetze.indexOf(wert.trim()) > -1;
    const markieren = () => {
      const wert = feld.value.trim();
      knoepfe.forEach((knopf) => {
        knopf.setAttribute("aria-pressed", String(knopf.dataset.vorlage === wert));
      });
    };
    const hinweisZeigen = (text, mitZurueck) => {
      if (!hinweis || !hinweisText) return;
      // Nur bei echter Aenderung schreiben: die Zeile ist ein aria-live-Bereich.
      // Jedes Setzen — auch auf denselben Wert — meldet Vorlese-Software erneut,
      // sonst spraeche sie den Hinweis bei JEDEM getippten Zeichen noch einmal.
      if (hinweisText.textContent !== text) hinweisText.textContent = text;
      if (zurueck) zurueck.hidden = !mitZurueck;
      hinweis.hidden = !text;
    };
    // Zustand neu bewerten: nach eigenem Tippen, nach dem Rueckweg und immer
    // dann, wenn die Vorlagen wieder sichtbar werden (z. B. Wechsel auf "kurz"
    // nach einer Uebernahme, die das Feld ohne input-Ereignis gefuellt hat).
    const pruefen = () => {
      markieren();
      if (gemerkt) return; // Rueckweg bleibt stehen, solange er nicht genutzt wurde
      const wert = feld.value.trim();
      const fremd = wert && !istVorlage(wert);
      hinweisZeigen(fremd ? "Ein Tipp ersetzt Ihren Text." : "", false);
    };

    knoepfe.forEach((knopf) => {
      knopf.addEventListener("click", () => {
        const vorher = feld.value;
        if (vorher.trim() && !istVorlage(vorher)) gemerkt = vorher;
        feld.value = knopf.dataset.vorlage;
        markieren();
        hinweisZeigen(gemerkt ? "Ihr Text wurde ersetzt." : "", Boolean(gemerkt));
      });
    });

    zurueck?.addEventListener("click", () => {
      if (!gemerkt) return;
      feld.value = gemerkt;
      gemerkt = "";
      pruefen();
      feld.focus();
    });

    // Eigenes Tippen beendet den Rueckweg: ab hier ist der Text wieder der des Nutzers.
    feld.addEventListener("input", () => { gemerkt = ""; pruefen(); });

    vorlagenAktualisieren = pruefen;
    gruppe.dataset.vorlagenLive = "1"; // erst jetzt darf der Umschalter sie zeigen
    pruefen();
  }

  // ===== V8.49: zwei Anfrage-Wege (kurz / ausfuehrlich) in EINEM Formular =====
  // Warum EIN Formular: ein zweites <form> waere ein zweiter Endpunkt, ein zweiter
  // Pflegepfad und ein zweiter Ort, an dem die Uebergaben aus 60-Sekunden-Check und
  // Handy-Demo landen koennten. Stattdessen zwei Ansichten derselben Felder.
  // Datensparsamkeit, Ursache -> Mechanismus -> Wirkung: ausgeblendete Felder werden
  // zusaetzlich disabled; new FormData(form) uebertraegt deaktivierte Felder nicht.
  // Wirkung: im kurzen Weg verlassen nur Name, E-Mail, Nachricht (plus die
  // Uebergabefelder) den Browser — keine leeren Zeilen in der Mail.
  // WICHTIG: die diagnose_*-Felder liegen bewusst AUSSERHALB von
  // [data-kontakt-extra] und werden deshalb nie deaktiviert.
  let kontaktAufAusfuehrlich = () => {};

  function setupKontaktModus() {
    const gruppe = doc.querySelector("[data-kontakt-modus]");
    const form = doc.querySelector("[data-contact-form]");
    if (!gruppe || !form) return;
    const tabs = all('[role="tab"]', gruppe);
    const extras = all("[data-kontakt-extra]", form);
    if (tabs.length < 2 || !extras.length) return;

    const panel = doc.getElementById(tabs[0].getAttribute("aria-controls"));
    const hinweis = form.querySelector("[data-nachricht-hinweis]");
    const betreff = form.querySelector('input[name="subject"]');
    const vorlagen = form.querySelector("[data-vorlagen]");

    // Der Umschalter selbst ist die Ueberschrift des Formulars (V8.56): der frueher
    // zusaetzliche Kopf wiederholte nur die Beschriftung des aktiven Reiters.
    const texte = {
      kurz: {
        hinweis: "Ein Satz reicht",
        betreff: "Neue Anfrage über artur.ae (kurz)"
      },
      lang: {
        hinweis: "Stichworte reichen",
        betreff: "Neue Anfrage über artur.ae (ausführlich)"
      }
    };

    let aktuell = "";
    const aktivieren = (modus, fokus) => {
      const text = texte[modus] || texte.lang;
      const zeigen = modus !== "kurz";
      tabs.forEach((tab) => {
        const an = tab.dataset.modusWahl === modus;
        tab.setAttribute("aria-selected", String(an));
        tab.tabIndex = an ? 0 : -1;
        if (!an) return;
        if (panel) panel.setAttribute("aria-labelledby", tab.id);
        if (fokus) tab.focus();
      });
      extras.forEach((feld) => {
        feld.hidden = !zeigen;
        all("input,select,textarea", feld).forEach((el) => { el.disabled = !zeigen; });
      });
      if (hinweis) hinweis.textContent = text.hinweis;
      if (betreff) betreff.value = text.betreff;
      // Vorlagen gehoeren zum kurzen Weg. Sie werden nur eingeblendet, wenn
      // setupVorlagen sie wirklich verdrahtet hat — sonst staenden hier Knoepfe,
      // die nichts befuellen. Beim Einblenden neu bewerten: eine Uebernahme kann
      // das Feld ohne input-Ereignis gefuellt haben.
      if (vorlagen && vorlagen.dataset.vorlagenLive) {
        vorlagen.hidden = zeigen;
        if (!zeigen) vorlagenAktualisieren();
      }
      aktuell = modus;
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => aktivieren(tab.dataset.modusWahl, false));
      tab.addEventListener("keydown", (event) => {
        let naechster = null;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") naechster = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") naechster = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home") naechster = 0;
        if (event.key === "End") naechster = tabs.length - 1;
        if (naechster === null) return;
        event.preventDefault();
        aktivieren(tabs[naechster].dataset.modusWahl, true);
      });
    });

    // Uebergabe aus der Handy-Demo schaltet auf den ausfuehrlichen Weg: dort wird
    // "Worum geht es?" gesetzt UND ein Nachrichtentext vorbefuellt - beides soll der
    // Besucher sehen und aendern koennen. Der 60-Sekunden-Check nutzt diesen Weg seit
    // V8.52 NICHT mehr (er befuellt kein sichtbares Feld); er laesst den kurzen Weg
    // kurz und gibt sein Ergebnis ueber die diagnose_*-Felder weiter.
    kontaktAufAusfuehrlich = () => { if (aktuell !== "lang") aktivieren("lang", false); };

    gruppe.dataset.modusLive = "1"; // erst jetzt sichtbar — der Umschalter funktioniert wirklich
    aktivieren("kurz", false);
  }

  function setupDiagnostic() {
    const diagnostic = doc.querySelector("[data-diagnostic]");
    if (!diagnostic) return;

    const choices = all("[data-diagnostic-choice]", diagnostic);
    const resultTitle = diagnostic.querySelector("[data-result-title]");
    const resultText = diagnostic.querySelector("[data-result-text]");
    const resultPrice = diagnostic.querySelector("[data-result-price]");
    const resultCode = diagnostic.querySelector("[data-result-code]");
    const resultLink = diagnostic.querySelector("[data-result-link]");
    const resultPrices = diagnostic.querySelector("[data-result-prices]");
    const resultWa = diagnostic.querySelector("[data-result-wa]");
    const resultAside = diagnostic.querySelector(".diagnostic-result");
    const contactSelect = doc.querySelector("#anliegen");
    // Zeile am Formular: benennt sichtbar, dass das Check-Ergebnis mitgeht.
    const checkUebernahme = doc.querySelector("[data-check-uebernahme]");
    // Sobald der Nutzer das Anliegen selbst waehlt, nicht mehr automatisch ueberschreiben.
    let anliegenTouched = false;
    contactSelect?.addEventListener("change", () => { anliegenTouched = true; });
    // Nur beim UEBERGANG auf vollstaendig (nicht bei jeder Aenderung) einmalig scrollen.
    let wasComplete = false;
    const diagnosticFields = {
      bottleneck: doc.querySelector('[name="diagnose_engpass"]'),
      current: doc.querySelector('[name="diagnose_ausgangslage"]'),
      goal: doc.querySelector('[name="diagnose_ziel"]'),
      recommendation: doc.querySelector('[name="diagnose_empfehlung"]')
    };
    const state = {};
    const labels = {
      bottleneck: {
        visibility: "Zu wenig Sichtbarkeit",
        website: "Unklare Website",
        inquiries: "Chaotische Anfragen",
        routine: "Zu viel Handarbeit"
      },
      current: {
        none: "Keine nutzbare Website",
        exists: "Website besteht",
        scattered: "Mehrere Kontaktwege",
        unsure: "Ausgangslage noch unklar"
      },
      goal: {
        assessment: "Klare Einordnung",
        budget: "Belastbarer Preisrahmen",
        demo: "Ein Beispiel sehen",
        conversation: "Kurz mit Artur besprechen"
      }
    };

    // preisBereich = das Panel im Preis-Abschnitt, in dem der genannte Preis WIRKLICH
    // steht (V8.57). Ohne diese Zuordnung landete der Sprung "Alle Festpreise ansehen"
    // immer auf "Website" — bei der Empfehlung "Anfragen-System" (490 € + 49 €/Monat,
    // panel-wachstum) und "KI-Pilot" (ab 1.990 €, panel-ki) war der beworbene Preis
    // damit ausgeblendet.
    const recommendations = {
      visibility: {
        title: "Erst die Grundlage für Sichtbarkeit prüfen.",
        text: "Google Ads bringen Besucher auf die Zielseite. Ob daraus passende Anfragen werden, hängt auch von Angebot und Kontaktweg ab. Der Website-Check prüft diese Basis zuerst.",
        price: "Wenn passend: Website-Check ab 49 €",
        code: "01 / PRÜFEN",
        select: "Website-Check",
        preisBereich: "web"   // Website-Check 49 / 79 / 129 € steht in panel-web
      },
      visibilityFoundation: {
        title: "Zuerst klären, worauf Sichtbarkeit einzahlen soll.",
        text: "Bevor Werbung startet, muss klar sein, welches Angebot sichtbar werden soll und wohin Interessenten geführt werden. Ohne belegte, tragfähige Zielseite bleibt offen, ob eine vorhandene Seite reicht, eine einzelne Zielseite oder eine kompakte Website gebraucht wird.",
        price: "Wenn passend: Ads-Setup 349 € oder Kompakt-Website 990 €",
        code: "01 / GRUNDLAGE",
        select: "Noch unsicher",
        // Diese Empfehlung nennt bewusst ZWEI Wege (Ads-Setup 349 € · Kompakt-Website
        // 990 €), die in zwei Bereichen stehen. Ein Reiter kann nur einer sein: die
        // Empfehlung sagt, dass zuerst die Zielseite geklaert wird — deshalb "web".
        // Der Ads-Preis ist einen beschrifteten Reiter entfernt.
        preisBereich: "web",
        summary: "Sichtbarkeitsbasis klären",
        demoHref: "#loesungsweg",
        demoLabel: "Sichtbarkeits-Bausteine ansehen"
      },
      website: {
        title: "Bestehende Seite prüfen, bevor Sie neu bauen.",
        text: "Wenn Struktur und Technik noch tragfähig sind, reicht oft eine gezielte Reparatur. Nur wenn das Fundament nicht mehr passt, ist eine neue Website sinnvoll.",
        price: "Wenn passend: Prüfung ab 49 € · Reparatur 290–990 €",
        code: "02 / KLÄREN",
        select: "Website-Check",
        preisBereich: "web"   // Prüfung 49 € · Reparatur 290–990 € stehen in panel-web
      },
      inquiries: {
        title: "Anfragen zuerst an einer Stelle zusammenführen.",
        text: "Ein Anfragen-System lohnt sich, wenn bereits Kontakte entstehen, aber zwischen Telefon, WhatsApp und Notizen verloren gehen. Der genaue Ablauf wird vorab begrenzt.",
        price: "Wenn passend: 490 € Einrichtung + 49 €/Monat",
        code: "03 / ORDNEN",
        select: "Anfragen-System",
        preisBereich: "wachstum"   // 490 € + 49 €/Monat stehen in panel-wachstum
      },
      routine: {
        title: "Einen wiederkehrenden Ablauf als Pilot testen.",
        text: "Nicht alles auf einmal automatisieren. Ein klarer, häufig wiederholter Ablauf wird als kleiner Pilot gebaut und gegen den heutigen Prozess geprüft.",
        price: "Wenn passend: KI-Pilot ab 1.990 €",
        code: "04 / TESTEN",
        select: "KI-Pilot",
        preisBereich: "ki"   // ab 1.990 € steht in panel-ki
      },
      newsite: {
        title: "Eine klare Website als belastbare Basis bauen.",
        text: "Wenn keine nutzbare Seite vorhanden ist, wird zuerst die Basis aus Angebot, Ziel und Kontaktweg sauber aufgebaut. Danach können Sichtbarkeit und digitale Abläufe sinnvoll folgen.",
        price: "Wenn passend: Kompakt-Website 990 € · 5–8 Seiten 1.990 €",
        code: "02 / BAUEN",
        select: "Neue Website",
        preisBereich: "web"   // Kompakt-Website 990 € · Betriebs-Website 1.990 €
      },
      // defensive Absicherung / Fallback, aktuell nie erreicht (bottleneck bei completed===3 stets gueltig)
      unsure: {
        title: "Mit einer kleinen Bestandsaufnahme anfangen.",
        text: "Sie müssen die technische Lösung noch nicht kennen. Beschreiben Sie kurz Ihre Lage; Sie bekommen eine klare Einordnung statt eines unnötig großen Pakets.",
        price: "Erst einordnen, dann den passenden Festpreis wählen",
        code: "01 / EINORDNEN",
        select: "Noch unsicher",
        preisBereich: "web"   // Auffangfall: der Preis-Abschnitt startet ohnehin hier
      }
    };

    const goalText = {
      assessment: "Ihr gewählter nächster Schritt: erst einordnen und erst danach entscheiden.",
      budget: "Sie möchten zuerst den Preisrahmen sehen; deshalb führt der nächste Schritt direkt zu allen Festpreisen.",
      demo: "Sie möchten zuerst ein Beispiel sehen; die fachliche Empfehlung bleibt dabei unverändert.",
      conversation: "Sie möchten den Fall direkt besprechen; die drei Antworten werden dafür in die Anfrage übernommen."
    };

    const chooseRecommendation = () => {
      if (state.bottleneck === "visibility" && state.current !== "exists") {
        return recommendations.visibilityFoundation;
      }
      if (state.current === "none" && state.bottleneck === "website") {
        return recommendations.newsite;
      }
      return recommendations[state.bottleneck] || recommendations.unsure;
    };

    const getContextText = () => {
      if (state.current === "none") {
        if (state.bottleneck === "visibility") {
          return "Die fehlende Website verändert die Reihenfolge: Erst braucht die Sichtbarkeit ein klares Ziel, bevor Werbung sinnvoll ist.";
        }
        if (state.bottleneck === "website") {
          return "Weil keine nutzbare Website vorhanden ist, gehört eine belastbare digitale Basis bei diesem Engpass zum ersten Schritt.";
        }
        return "Die fehlende Website ist ein zweiter Befund. Für Ihren genannten Hauptengpass muss sie nicht automatisch zuerst gebaut werden.";
      }
      if (state.current === "exists") {
        return "Die vorhandene Website wird als Ausgangslage einbezogen und nicht automatisch ersetzt.";
      }
      if (state.current === "scattered") {
        if (state.bottleneck === "inquiries") {
          return "Die parallelen Kontaktwege bestätigen, dass zuerst Ordnung in den Anfrageweg gehört.";
        }
        return "Die parallelen Kontaktwege bleiben ein zweiter Befund; den ersten Schritt bestimmt Ihr genannter Hauptengpass.";
      }
      return "Die Ausgangslage ist noch unklar. Deshalb ist die Empfehlung eine Arbeitsrichtung, die Artur vor einem Auftrag persönlich prüft.";
    };

    const setDiagnosticField = (name, value = "") => {
      if (diagnosticFields[name]) diagnosticFields[name].value = value;
    };

    const render = () => {
      const completed = [state.bottleneck, state.current, state.goal].filter(Boolean).length;
      if (completed < 3) {
        const missing = 3 - completed;
        if (resultTitle) resultTitle.textContent = missing === 1 ? "Noch eine Antwort bis zur Einordnung." : `Noch ${missing} Antworten bis zur Einordnung.`;
        if (resultText) resultText.textContent = "Erst wenn klar ist, wo es klemmt, was schon da ist und was Ihnen zuerst hilft, wird eine Richtung vorgeschlagen.";
        if (resultPrice) resultPrice.textContent = `${completed} von 3 Fragen beantwortet`;
        if (resultCode) resultCode.textContent = `Diagnose: ${completed} von 3 Fragen beantwortet`;
        if (resultLink) {
          resultLink.setAttribute("aria-disabled", "true");
          resultLink.removeAttribute("href");
          resultLink.textContent = "Diagnose vervollständigen";
          delete resultLink.dataset.recommendation;
          delete resultLink.dataset.preisBereich;
        }
        if (resultPrices) resultPrices.hidden = true;
        if (resultWa) resultWa.hidden = true;
        setDiagnosticField("bottleneck");
        setDiagnosticField("current");
        setDiagnosticField("goal");
        setDiagnosticField("recommendation");
        wasComplete = false;
        return;
      }

      const recommendation = chooseRecommendation();
      if (resultTitle) resultTitle.textContent = recommendation.title;
      if (resultText) {
        resultText.textContent = [recommendation.text, getContextText(), goalText[state.goal]]
          .filter(Boolean)
          .join(" ");
      }
      if (resultPrice) resultPrice.textContent = recommendation.price;
      if (resultCode) resultCode.textContent = recommendation.code;
      if (resultLink) {
        resultLink.removeAttribute("aria-disabled");
        resultLink.dataset.recommendation = recommendation.select;
        if (state.goal === "demo") {
          if (recommendation.demoHref) {
            resultLink.href = recommendation.demoHref;
            resultLink.textContent = recommendation.demoLabel;
          } else if (recommendation.select === "Anfragen-System") {
            resultLink.href = "app-demo.html";
            resultLink.textContent = "Kunden-App testen";
          } else if (recommendation.select === "KI-Pilot") {
            resultLink.href = "automatisierung-demo.html";
            resultLink.textContent = "Ablauf simulieren";
          } else if (recommendation.select === "Neue Website") {
            resultLink.href = "#preise";
            resultLink.textContent = "Website-Umfang ansehen";
          } else {
            resultLink.href = "#website-check";
            resultLink.textContent = "Prüfbeispiel ansehen";
          }
        } else if (state.goal === "budget") {
          resultLink.href = "#preise";
          resultLink.textContent = "Alle Festpreise ansehen";
        } else if (state.goal === "assessment") {
          resultLink.href = "#kontakt";
          resultLink.textContent = "Einordnung anfragen";
        } else {
          resultLink.href = "#kontakt";
          resultLink.textContent = "Problem schildern";
        }
        // V8.57: Nur wenn der Weg wirklich in den Preis-Abschnitt fuehrt, wird der
        // Bereich mitgegeben — sonst wuerde ein Klick auf "Kunden-App testen" oder
        // "Ablauf simulieren" unnoetig am Reiter drehen.
        if (resultLink.getAttribute("href") === "#preise") {
          resultLink.dataset.preisBereich = recommendation.preisBereich || "web";
        } else {
          delete resultLink.dataset.preisBereich;
        }
      }
      if (resultPrices) {
        resultPrices.hidden = false;
        resultPrices.dataset.preisBereich = recommendation.preisBereich || "web";
      }
      if (resultWa) {
        const waText = [
          "Hallo Artur, hier ist mein Ergebnis aus dem 60-Sekunden-Check:",
          "Engpass: " + labels.bottleneck[state.bottleneck],
          "Ausgangslage: " + labels.current[state.current],
          "Ziel: " + labels.goal[state.goal],
          "Arbeitsrichtung: " + (recommendation.summary || recommendation.select),
          "Können Sie das kurz einordnen?"
        ].join("\n");
        resultWa.href = "https://wa.me/4917622659649?text=" + encodeURIComponent(waText);
        resultWa.hidden = false;
      }
      if (!anliegenTouched && contactSelect && contactSelect.querySelector(`option[value="${recommendation.select}"]`)) {
        contactSelect.value = recommendation.select;
      }
      setDiagnosticField("bottleneck", labels.bottleneck[state.bottleneck]);
      setDiagnosticField("current", labels.current[state.current]);
      setDiagnosticField("goal", labels.goal[state.goal]);
      setDiagnosticField(
        "recommendation",
        `${recommendation.summary || recommendation.select} · ${recommendation.price}`
      );
      if (checkUebernahme) checkUebernahme.hidden = false;
      // V8.52: Der Check schaltet das Formular NICHT mehr auf den ausfuehrlichen Weg.
      // Ursache -> Wirkung: der Hero bewirbt "Kurz anfragen - drei Felder - 60 Sekunden";
      // ein erzwungener Umschalter nahm genau diesem Weg die Vorlagen-Bausteine, die
      // Telefon-Zeile und das kurze Versprechen. Das Ergebnis geht trotzdem mit -
      // ueber die vier "diagnose_*"-Felder oben, in denen auch die angezeigte
      // Empfehlung im Klartext steht. Die Uebernahme-Zeile darunter benennt das.
      // Am Handy beim UEBERGANG auf vollstaendig das Ergebnis einmalig in den Blick holen.
      if (!wasComplete && mobileNavigation.matches && resultAside) {
        resultAside.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
      }
      wasComplete = true;
    };

    const selectChoice = (choice, focusIt) => {
      const group = choice.dataset.group;
      all(`[data-group="${group}"]`, diagnostic).forEach((peer) => {
        const on = peer === choice;
        peer.setAttribute("aria-checked", String(on));
        peer.tabIndex = on ? 0 : -1;
      });
      state[group] = choice.dataset.value;
      if (focusIt) choice.focus();
      render();
    };

    choices.forEach((choice) => {
      choice.addEventListener("click", () => selectChoice(choice, false));
      choice.addEventListener("keydown", (event) => {
        const peers = all(`[data-group="${choice.dataset.group}"]`, diagnostic);
        const index = peers.indexOf(choice);
        let next = -1;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % peers.length;
        else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + peers.length) % peers.length;
        if (next >= 0) {
          event.preventDefault();
          selectChoice(peers[next], true);
        }
      });
    });

    resultLink?.addEventListener("click", () => {
      if (resultLink.getAttribute("aria-disabled") === "true") return;
      const recommendation = resultLink.dataset.recommendation;
      if (contactSelect && recommendation) {
        // V8.52: kein Zwangs-Umschalter mehr. Die Wahl wird gesetzt und ist im
        // ausfuehrlichen Weg sofort sichtbar. Im kurzen Weg bleibt sie deaktiviert und
        // wird NICHT uebertragen - so steht es auch in der Datenschutzerklaerung.
        // Das Check-Ergebnis selbst geht ueber "diagnose_empfehlung" mit.
        contactSelect.value = recommendation;
        anliegenTouched = true;
      }
    });

    render();
  }

  // Uebergabe aus der 3D-Handy-Demo: DIESELBE Mechanik wie der 60-Sekunden-Check
  // (Felder direkt setzen + zum Formular scrollen). hero3d-handy.js ruft window.__handyZumKontakt().
  function setupHandyUebergabe() {
    const target = doc.querySelector("#kontakt");
    if (!target) return;
    const select = doc.querySelector("#anliegen");
    const message = doc.querySelector("#nachricht");
    const note = doc.querySelector("[data-handy-uebernahme]");
    const HANDY_NACHRICHT = "Ich habe die interaktive Kunden-App-Demo getestet und möchte prüfen, ob sie zu meinem Betrieb passt.";
    window.__handyZumKontakt = () => {
      // Zuerst auf den ausfuehrlichen Weg schalten: "Worum geht es?" wird gleich
      // gesetzt und muss sichtbar (und aktiv) sein, sonst ginge es nicht mit.
      kontaktAufAusfuehrlich();
      if (select && select.querySelector('option[value="Anfragen-System"]')) {
        select.value = "Anfragen-System";
        // "change" melden — sonst haelt der 60-Sekunden-Check diese Wahl fuer
        // unberuehrt und ueberschreibt sie still, sobald der Besucher den Check
        // danach zu Ende klickt (gemessen: "Anfragen-System" -> "Noch unsicher").
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
      // Nie eigenen Text des Nutzers ueberschreiben — nur ein leeres Feld vorbefuellen.
      if (message && !message.value.trim()) message.value = HANDY_NACHRICHT;
      if (note) note.hidden = false; // sichtbare Zeile NUR, wenn per Handy gekommen
      // reduced-motion: direkter Sprung statt Smooth-Scroll.
      target.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
    };
  }

  // Mobile 2D-Werkprobe (V8.48). Fortschreitende Verbesserung: das Markup steht
  // vollstaendig und lesbar in index.html (alle drei Bildschirme untereinander).
  // Erst hier wird daraus die Bildschirm-Kette Board -> Detail -> zurueck und
  // Board -> Sperren -> Login -> Board. Faellt dieses Skript aus, bleibt die
  // lesbare Fassung stehen — nichts verschwindet.
  function setupHandy2d() {
    const block = doc.querySelector("[data-handy2d]");
    if (!block) return;
    const screens = all("[data-h2d-screen]", block);
    if (screens.length < 2) return;

    const zeige = (name, fokus) => {
      screens.forEach((s) => { s.hidden = s.dataset.h2dScreen !== name; });
      if (fokus) {
        const ziel = block.querySelector(`[data-h2d-screen="${name}"] button`);
        if (ziel) ziel.focus();
      }
    };

    // Echte Geraetezeit in der Statusleiste (V8.65). Sie ist die einzige Angabe
    // dort, die nicht erfunden ist — und der Besucher sieht 300px darueber seine
    // eigene Uhr. Eine feste "09:41" waere genau der Moment, in dem das Geraet
    // zum Bild wird. Nur bei Minutenwechsel schreiben, plus Nachziehen beim
    // Zurueckkehren zum Tab (Hintergrund-Timer werden gedrosselt).
    const uhr = block.querySelector("[data-h2d-clock]");
    if (uhr) {
      let letzteMinute = -1;
      const uhrSchreiben = () => {
        const j = new Date();
        if (j.getMinutes() === letzteMinute) return;
        letzteMinute = j.getMinutes();
        uhr.textContent = String(j.getHours()).padStart(2, "0") + ":" +
          String(j.getMinutes()).padStart(2, "0");
      };
      uhrSchreiben();
      window.setInterval(uhrSchreiben, 15000);
      doc.addEventListener("visibilitychange", () => { if (!doc.hidden) uhrSchreiben(); });
    }

    // Alle Bildschirme bekommen die Hoehe des Boards (des groessten). Ursache:
    // ohne das schrumpft der Rahmen beim Wechsel auf Detail/Login um ~115 px und
    // die halbe Seite rutscht unter dem Finger weg. Gemessen statt geraten, damit
    // Schriftgroesse, Zoom und Fensterbreite die Zahl selbst bestimmen.
    const board = block.querySelector('[data-h2d-screen="board"]');
    // V8.73: Misst das Maximum ueber ALLE Bildschirme, nicht nur das Board.
    // Vorher: Ist ein anderer Bildschirm hoeher als das Board, ueberschreitet
    // er die gesetzte Mindesthoehe und der Rahmen springt beim Wechsel - genau
    // der Fehler, den diese Funktion verhindern soll.
    const hoeheAngleichen = () => {
      if (!screens.length) return;
      // Der hoechste Zustand ist der Anfragen-Bereich. Ist gerade ein anderer
      // Reiter offen, wird fuer die Messung kurz auf ihn zurueckgeschaltet.
      const tabBloecke = all("[data-h2d-tabinhalt]", block);
      const tabMerker = tabBloecke.map((c) => c.hidden);
      tabBloecke.forEach((c) => { c.hidden = c.dataset.h2dTabinhalt !== "anfragen"; });
      const merker = screens.map((s) => s.hidden);
      screens.forEach((s) => { s.hidden = false; s.style.minHeight = ""; });
      const h = Math.round(Math.max(...screens.map((s) => s.getBoundingClientRect().height)));
      screens.forEach((s, i) => { s.hidden = merker[i]; });
      tabBloecke.forEach((c, i) => { c.hidden = tabMerker[i]; });
      if (h > 0) screens.forEach((s) => { s.style.minHeight = h + "px"; });
    };
    let messTimer = 0;
    const spaeterMessen = () => {
      window.clearTimeout(messTimer);
      messTimer = window.setTimeout(hoeheAngleichen, 180);
    };
    window.addEventListener("resize", spaeterMessen, { passive: true });
    window.addEventListener("orientationchange", spaeterMessen, { passive: true });

    // V8.71: Zahlen zaehlen statt eintragen. Vorher standen "3 / 2 / 1" fest im
    // Markup - sie logen, sobald sich eine Karte aenderte. Am Desktop
    // (boardZahlen in hero3d-handy.js) und in app-demo.html (countStatus) wird
    // gezaehlt; die Werkprobe zog als einzige nicht mit. Feld-Bedeutung
    // bewusst gleich: laufend = wartend + termin.
    const LAUFEND = ["wartend", "termin"];
    const zaehle = () => {
      const k = all(".h2d-card", block);
      const n = (s) => k.filter((c) => c.dataset.h2dStat === s).length;
      return {
        alle: k.length, neu: n("neu"), wartend: n("wartend"), termin: n("termin"),
        auftrag: n("auftrag"), verloren: n("verloren"),
        laufend: k.filter((c) => LAUFEND.includes(c.dataset.h2dStat)).length
      };
    };
    // Neuigkeiten-Zeile: dieselbe Rechnung wie in app-demo.html (updateNews),
    // damit beide Flaechen denselben Satz zeigen.
    const newsBox = block.querySelector("[data-h2d-news]");
    const newsText = block.querySelector("[data-h2d-news-text]");
    const newsSchreiben = (z) => {
      if (!newsBox || !newsText) return;
      const wartendMitFollowup = all(".h2d-card", block).filter(
        (c) => c.dataset.h2dStat === "wartend" && c.querySelector(".h2d-card__flag")
      ).length;
      const teile = [];
      if (z.neu > 0) teile.push([z.neu + " neue Anfrage" + (z.neu > 1 ? "n" : ""), ""]);
      if (wartendMitFollowup > 0) teile.push([wartendMitFollowup + " Kunde" + (wartendMitFollowup > 1 ? "n" : ""), " wartet seit 3 Tagen auf Antwort"]);
      if (z.termin > 0) teile.push([z.termin + " Termin" + (z.termin > 1 ? "e" : ""), " offen"]);
      newsBox.hidden = teile.length === 0;
      newsText.textContent = "";
      teile.forEach(([stark, rest], i) => {
        if (i) newsText.appendChild(doc.createTextNode(" · "));
        const b = doc.createElement("strong");
        b.textContent = stark;
        newsText.appendChild(b);
        if (rest) newsText.appendChild(doc.createTextNode(rest));
      });
    };

    // V8.73 Statistik: dieselbe Zaehlung wie die Pillen. Kacheln und
    // Verteilung koennen den Filtern damit nicht widersprechen.
    const VERTEILUNG = [
      ["neu", "Neu", "var(--h2d-neu)"], ["wartend", "Wartend", "var(--h2d-wartend)"],
      ["termin", "Termin", "var(--h2d-termin)"], ["auftrag", "Auftrag", "var(--h2d-auftrag)"],
      ["verloren", "Verloren", "var(--h2d-verloren)"]
    ];
    const statistikSchreiben = (z) => {
      const wert = all(".h2d-card", block)
        .filter((c) => c.dataset.h2dStat === "auftrag")
        .reduce((s, c) => {
          const m = (c.querySelector(".h2d-card__flag--wert")?.textContent || "").match(/([\d.]+)\s*€/);
          return s + (m ? parseInt(m[1].replace(/\./g, ""), 10) : 0);
        }, 0);
      const werte = { gesamt: z.alle, offen: z.neu + z.wartend + z.termin, termine: z.termin,
                      wert: wert.toLocaleString("de-DE") + " €" };
      all("[data-h2d-kachel]", block).forEach((el) => {
        el.textContent = werte[el.dataset.h2dKachel] ?? "";
      });
      const liste = block.querySelector("[data-h2d-verteilung]");
      if (liste) {
        liste.textContent = "";
        VERTEILUNG.forEach(([key, label, farbe]) => {
          const li = doc.createElement("li");
          li.innerHTML = '<i style="color:' + farbe + '"></i>' + label + "<b>" + (z[key] || 0) + "</b>";
          liste.appendChild(li);
        });
      }
    };

    const zahlenSchreiben = () => {
      const z = zaehle();
      all("[data-h2d-count]", block).forEach((el) => {
        el.textContent = z[el.dataset.h2dCount] ?? "";
      });
      const summe = block.querySelector("[data-h2d-summe]");
      if (summe) summe.textContent = z.alle + (z.alle === 1 ? " Beispiel" : " Beispiele");
      newsSchreiben(z);
      statistikSchreiben(z);
      hoeheAngleichen();   // Zahlen koennen eine Zeile umbrechen lassen
    };

    // Filter wie im 3D-Board: blendet ganze Gruppen aus. Die feste Mindesthoehe
    // im CSS haelt den Block dabei gleich hoch -> kein Springen beim Scrollen.
    const pillen = all("[data-h2d-filter]", block);
    const posten = all("[data-h2d-grp]", block);
    pillen.forEach((pille) => {
      pille.addEventListener("click", () => {
        const f = pille.dataset.h2dFilter;
        pillen.forEach((p) => {
          const on = p === pille;
          p.classList.toggle("is-on", on);
          p.setAttribute("aria-pressed", String(on));
        });
        posten.forEach((p) => { p.hidden = f !== "alle" && p.dataset.h2dGrp !== f; });
      });
    });

    // Karte antippen -> Detail. Inhalte kommen aus der Karte selbst, damit es
    // nur EINEN Wahrheitspunkt fuer die Beispieldaten gibt.
    const dName = block.querySelector("[data-h2d-d-name]");
    const dStat = block.querySelector("[data-h2d-d-stat]");
    const dMeta = block.querySelector("[data-h2d-d-meta]");
    const dMsg = block.querySelector("[data-h2d-d-msg]");
    const dDetail = block.querySelector("[data-h2d-d-detail]");
    const dHint = block.querySelector("[data-h2d-hintout]");
    // Als benannte Funktion, damit auch eine spaeter erzeugte Karte
    // (Vorfuehr-Knopf) denselben Weg nimmt - kein zweiter Pfad.
    const detailOeffnen = (karte) => {
      const hole = (sel) => (karte.querySelector(sel)?.textContent || "").trim();
      if (dName) dName.textContent = hole(".h2d-card__name");
      if (dMeta) dMeta.textContent = hole(".h2d-card__meta");
      if (dMsg) {
        dMsg.textContent = hole(".h2d-card__msg");
        dMsg.dataset.stat = karte.dataset.h2dStat || "neu"; // Status-Streifen wie im 3D-Detail
      }
      if (dDetail) dDetail.textContent = karte.dataset.h2dDetail || "";
      if (dStat) {
        dStat.textContent = karte.dataset.h2dStatlabel || "";
        dStat.className = "h2d-stat h2d-stat--" + (karte.dataset.h2dStat || "neu");
      }
      if (dHint) dHint.textContent = "";
      offeneKarte = karte;
      if (weiterKnopf) { weiterKnopf.hidden = false; weiterBeschriften(); }
      zeige("detail", true);
    };
    all(".h2d-card", block).forEach((karte) => {
      karte.addEventListener("click", () => detailOeffnen(karte));
    });

    // V8.72: Status weitertippen. Sitzt im DETAIL, nicht auf der Karte - die
    // Karte ist selbst ein <button>, ein Knopf darin waere ungueltiges HTML.
    // Reihenfolge 1:1 aus STAT_NEXT (hero3d-handy.js).
    const STAT_NEXT = { neu: "wartend", wartend: "termin", termin: "auftrag", auftrag: "verloren", verloren: "neu" };
    const STAT_LABEL = { neu: "Neu", wartend: "Wartend", termin: "Termin", auftrag: "Auftrag", verloren: "Verloren" };
    const GRUPPE_ZU = { neu: "neu", wartend: "laufend", termin: "laufend", auftrag: "auftrag", verloren: "verloren" };
    let offeneKarte = null;
    const weiterKnopf = block.querySelector("[data-h2d-next]");
    const weiterBeschriften = () => {
      if (!weiterKnopf || !offeneKarte) return;
      const naechster = STAT_NEXT[offeneKarte.dataset.h2dStat] || "neu";
      weiterKnopf.textContent = "Status weiter → " + STAT_LABEL[naechster];
    };
    weiterKnopf?.addEventListener("click", () => {
      if (!offeneKarte) return;
      const neuStat = STAT_NEXT[offeneKarte.dataset.h2dStat] || "neu";
      offeneKarte.dataset.h2dStat = neuStat;
      offeneKarte.dataset.h2dStatlabel = STAT_LABEL[neuStat];
      offeneKarte.dataset.h2dGrp = GRUPPE_ZU[neuStat];
      const chip = offeneKarte.querySelector(".h2d-stat");
      if (chip) { chip.textContent = STAT_LABEL[neuStat]; chip.className = "h2d-stat h2d-stat--" + neuStat; }
      if (dStat) { dStat.textContent = STAT_LABEL[neuStat]; dStat.className = "h2d-stat h2d-stat--" + neuStat; }
      if (dMsg) dMsg.dataset.stat = neuStat;
      if (dHint) dHint.textContent = "Demo-Status geändert: " + STAT_LABEL[neuStat] + ". Es wird nichts gespeichert.";
      weiterBeschriften();
      zahlenSchreiben();   // Pillen, Zusammenfassung und Neuigkeiten zusammen
    });

    // V8.72: Vorfuehr-Knopf. Legt EINE zusaetzliche Beispiel-Anfrage oben in
    // "Neu" an - dieselbe wie SIM_BEISPIEL im 3D-Board, damit beide Flaechen
    // dasselbe zeigen. Genau einmal; danach sagt der Knopf, dass Schluss ist.
    const simKnopf = block.querySelector("[data-h2d-sim]");
    const liste = block.querySelector("[data-h2d-list]");
    if (simKnopf && liste) {
      simKnopf.hidden = false;   // erst jetzt sichtbar: ohne JS kein toter Knopf
      simKnopf.addEventListener("click", () => {
        if (simKnopf.disabled) return;
        const karte = doc.createElement("button");
        karte.className = "h2d-card";
        karte.type = "button";
        karte.dataset.h2dGrp = "neu";
        karte.dataset.h2dStat = "neu";
        karte.dataset.h2dStatlabel = "Neu";
        karte.dataset.h2dDetail = "Diese Anfrage kam über den Vorführ-Knopf herein — ein frei erfundenes Beispiel dafür, wie eine neue Anfrage oben einsortiert wird.";
        karte.innerHTML =
          '<span class="h2d-card__top"><span class="h2d-card__name">Fr. Krause (Beispiel)</span>' +
          '<span class="h2d-stat h2d-stat--neu">Neu</span></span>' +
          '<span class="h2d-card__meta">Privat · über Google Ads · gerade eben (Beispiel)</span>' +
          '<span class="h2d-card__msg">Guten Abend, ich habe alte Heizkörper, ca. 60 kg. Holen Sie so etwas ab?</span>';
        karte.addEventListener("click", () => detailOeffnen(karte));
        const ersteNeu = liste.querySelector('[data-h2d-grp="neu"].h2d-card');
        if (ersteNeu) liste.insertBefore(karte, ersteNeu);
        else liste.prepend(karte);
        // Filter auf "Alle" zuruecksetzen, sonst legt der Knopf eine Karte an,
        // die hinter einem aktiven Filter niemand sieht (wie im 3D, :479).
        pillen.forEach((p) => {
          const on = p.dataset.h2dFilter === "alle";
          p.classList.toggle("is-on", on);
          p.setAttribute("aria-pressed", String(on));
        });
        posten.forEach((p) => { p.hidden = false; });
        simKnopf.disabled = true;
        simKnopf.textContent = "Genug Beispiele für diese Demo.";
        zahlenSchreiben();
      });
    }

    // V8.73: Reiter. Erst hier sichtbar - ohne JavaScript stehen alle drei
    // Bereiche untereinander und niemand sieht eine tote Reiterleiste.
    const tabs = all("[data-h2d-tab]", block);
    const tabInhalte = all("[data-h2d-tabinhalt]", block);
    const tabLeiste = block.querySelector("[data-h2d-tabs]");
    if (tabs.length && tabInhalte.length) {
      if (tabLeiste) tabLeiste.hidden = false;
      const tabWechsel = (name) => {
        tabs.forEach((t) => {
          const on = t.dataset.h2dTab === name;
          t.classList.toggle("is-on", on);
          t.setAttribute("aria-selected", String(on));
        });
        tabInhalte.forEach((c) => { c.hidden = c.dataset.h2dTabinhalt !== name; });
        // BEWUSST kein Neumessen: Die Mindesthoehe stammt vom Anfragen-Bereich,
        // dem hoechsten. Wuerde hier neu gemessen, schrumpfte der Rahmen beim
        // Wechsel auf Ueberblick von 1023 auf 537px - genau das Springen, das
        // die Angleichung verhindern soll (gemessen).
      };
      tabs.forEach((t, i) => {
        t.addEventListener("click", () => tabWechsel(t.dataset.h2dTab));
        t.addEventListener("keydown", (e) => {
          const richtung = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
          if (!richtung) return;
          e.preventDefault();
          const ziel = tabs[(i + richtung + tabs.length) % tabs.length];
          ziel.focus();
          tabWechsel(ziel.dataset.h2dTab);
        });
      });
      tabWechsel("anfragen");
    }

    // Die zwei Anzeige-Schalter wirken sofort und sichtbar - sonst waeren sie
    // eine Behauptung statt einer Vorfuehrung.
    block.querySelector('[data-h2d-opt="zaehler"]')?.addEventListener("change", (e) => {
      all("[data-h2d-count]", block).forEach((el) => { el.hidden = !e.target.checked; });
      const news = block.querySelector("[data-h2d-news]");
      if (news && !e.target.checked) news.hidden = true;
      else zahlenSchreiben();
      hoeheAngleichen();
    });
    block.querySelector('[data-h2d-opt="neueste"]')?.addEventListener("change", (e) => {
      const liste2 = block.querySelector("[data-h2d-list]");
      if (!liste2) return;
      // Reihenfolge INNERHALB jeder Gruppe drehen, Gruppenkoepfe bleiben stehen.
      let gruppe = [];
      const spuelen = () => { gruppe.reverse().forEach((k) => liste2.appendChild(k)); gruppe = []; };
      [...liste2.children].forEach((kind) => {
        if (kind.classList.contains("h2d-group")) { spuelen(); liste2.appendChild(kind); }
        else gruppe.push(kind);
      });
      spuelen();
      if (dHint) dHint.textContent = "";
      hoeheAngleichen();
    });
    block.querySelector("[data-h2d-reset]")?.addEventListener("click", () => {
      window.location.reload();   // ehrlichster Weg: Ausgangszustand herstellen
    });

    block.querySelector("[data-h2d-back]")?.addEventListener("click", () => zeige("board", true));
    block.querySelector("[data-h2d-lock]")?.addEventListener("click", () => zeige("login", true));
    all("[data-h2d-login]", block).forEach((k) => k.addEventListener("click", () => zeige("board", true)));
    all("[data-h2d-hint]", block).forEach((knopf) => {
      knopf.addEventListener("click", () => { if (dHint) dHint.textContent = knopf.dataset.h2dHint || ""; });
    });
    // Derselbe Uebergabeweg wie die Bottom-Bar des 3D-Handys — kein zweiter Pfad.
    block.querySelector("[data-h2d-kontakt]")?.addEventListener("click", () => {
      if (typeof window.__handyZumKontakt === "function") window.__handyZumKontakt();
      else doc.querySelector("#kontakt")?.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
    });

    block.dataset.h2dLive = "1";
    zeige("board", false);
    zahlenSchreiben();
    hoeheAngleichen();
    // Schriften laden nach -> Hoehe kann sich noch aendern. Einmal nachmessen.
    doc.fonts?.ready?.then(hoeheAngleichen).catch(() => {});
  }

  // ===== V8.60: Preis-Rechner (#preise) =====
  // EINE Quelle fuer jede Zahl. Im Markup steht kein Preis; jede Beschriftung,
  // jede Zeile im Ergebnis und jeder Satz in der Uebernahme-Nachricht wird aus
  // diesem Objekt gebaut. Ursache -> Mechanismus -> Wirkung: eine Preisaenderung
  // hier schlaegt ueberall gleichzeitig durch, und ein Preis, der hier nicht
  // steht, kann nirgends entstehen.
  // Spannen (Reparatur) haben bewusst KEIN "einmal" — sie duerfen in keine Summe
  // einfliessen. Wer sie waehlt, sieht die Spanne als eigene Zeile plus Hinweis.
  const PREIS_KANON = {
    kompakt:   { titel: "Kompakt-Website",       einmal: 990 },
    betrieb:   { titel: "Betriebs-Website",      einmal: 1990 },
    reparatur: { titel: "Website-Reparatur",     von: 290, bis: 990, note: "Preis nach Aufwand" },
    system:    { titel: "Anfragen-System",       einmal: 490, monat: 49, note: "sechs Monate Mindestlaufzeit, danach monatlich kündbar" },
    adsSetup:  { titel: "Google-Ads-Setup",      einmal: 349 },
    adsKlein:  { titel: "Google-Ads-Betreuung",  monat: 179, note: "Werbebudget bis 750 €, direkt an Google" },
    adsGross:  { titel: "Google-Ads-Betreuung",  monat: 229, note: "Werbebudget über 750 €, direkt an Google" },
    hosting:   { titel: "Nur Hosting",           monat: 39 },
    pflege:    { titel: "Pflege & Hosting",      monat: 79 },
    komfort:   { titel: "Komfort",               monat: 119 },
    kombi:     { titel: "Ads + Anfragen-System", einmal: 749, monat: 199, note: "fünf Monate Mindestlaufzeit, danach monatlich kündbar" }
  };
  const ANZAHLUNG_AB = 400;      // Projektwert, ab dem eine Anzahlung faellig wird
  const ANZAHLUNG_ANTEIL = 0.5;  // 50 % bei Auftrag

  function setupPreisRechner() {
    const block = doc.querySelector("[data-rechner]");
    if (!block) return;
    const wahlen = all("[data-rechner-wahl]", block);
    if (!wahlen.length) return;

    const postenVon = (btn) => (btn.dataset.posten || "").split(",").map((s) => s.trim()).filter(Boolean);
    // Fail-closed: zeigt auch nur EINE Wahl auf einen Posten, den der Kanon nicht
    // kennt oder der keinen Preis traegt, bleibt der ganze Rechner unsichtbar.
    // Lieber kein Rechner als eine Zeile ohne belegten Preis.
    const brauchbar = (schluessel) => {
      const p = PREIS_KANON[schluessel];
      return Boolean(p && p.titel && (p.einmal || p.monat || (p.von && p.bis)));
    };
    const alleGueltig = wahlen.every((btn) => postenVon(btn).every(brauchbar));
    if (!alleGueltig || !brauchbar("kombi")) return;

    const euro = (n) => n.toLocaleString("de-DE", {
      minimumFractionDigits: Number.isInteger(n) ? 0 : 2,
      maximumFractionDigits: 2
    }) + " €";
    const spanneText = (p) => euro(p.von).replace(" €", "") + "–" + euro(p.bis);
    // Preistext eines oder mehrerer Posten: "349 € + 179 €/Monat", "290–990 €".
    const preisText = (schluessel) => {
      const teile = [];
      const spanne = schluessel.find((k) => PREIS_KANON[k].von);
      const einmal = schluessel.reduce((s, k) => s + (PREIS_KANON[k].einmal || 0), 0);
      const monat = schluessel.reduce((s, k) => s + (PREIS_KANON[k].monat || 0), 0);
      if (spanne) teile.push(spanneText(PREIS_KANON[spanne]));
      if (einmal) teile.push(euro(einmal));
      if (monat) teile.push(euro(monat) + "/Monat");
      return teile.join(" + ");
    };

    // Beschriftungen der Wahl-Knoepfe aus dem Kanon setzen (im HTML steht dort nichts).
    wahlen.forEach((btn) => {
      const feld = btn.querySelector("[data-rechner-preis]");
      if (!feld) return;
      const schluessel = postenVon(btn);
      if (!schluessel.length) { feld.hidden = true; return; }
      feld.textContent = preisText(schluessel);
      feld.hidden = false;
    });

    const liste = block.querySelector("[data-rechner-liste]");
    const leer = block.querySelector("[data-rechner-leer]");
    const summe = block.querySelector("[data-rechner-summe]");
    const feldEinmal = block.querySelector("[data-rechner-einmal]");
    const feldMonat = block.querySelector("[data-rechner-monat]");
    const zeileAnzahlung = block.querySelector("[data-rechner-anzahlung-zeile]");
    const feldAnzahlung = block.querySelector("[data-rechner-anzahlung]");
    const hinweis = block.querySelector("[data-rechner-hinweis]");
    const kombiBox = block.querySelector("[data-rechner-kombi]");
    const kombiText = block.querySelector("[data-rechner-kombi-text]");
    const knopfAnfrage = block.querySelector("[data-rechner-anfrage]");
    const knopfReset = block.querySelector("[data-rechner-reset]");

    const stand = {};          // gruppe -> gewaehlter Knopf
    let letzteNachricht = "";  // was der Rechner zuletzt ins Nachrichtenfeld schrieb

    // Aus dem Zustand die Rechnung bauen — eine Stelle, die alles ableitet.
    const rechnen = () => {
      const schluessel = [];
      Object.keys(stand).forEach((gruppe) => {
        postenVon(stand[gruppe]).forEach((k) => { if (schluessel.indexOf(k) < 0) schluessel.push(k); });
      });
      const einmal = schluessel.reduce((s, k) => s + (PREIS_KANON[k].einmal || 0), 0);
      const monat = schluessel.reduce((s, k) => s + (PREIS_KANON[k].monat || 0), 0);
      const spannen = schluessel.filter((k) => PREIS_KANON[k].von);
      const adsDrin = schluessel.indexOf("adsSetup") > -1;
      const systemDrin = schluessel.indexOf("system") > -1;
      let kombi = null;
      if (adsDrin && systemDrin) {
        // Einzelpreis der beiden Bausteine gegen den Kombipreis stellen.
        const teil = ["adsSetup", "adsKlein", "adsGross", "system"].filter((k) => schluessel.indexOf(k) > -1);
        const einzelEinmal = teil.reduce((s, k) => s + (PREIS_KANON[k].einmal || 0), 0);
        const einzelMonat = teil.reduce((s, k) => s + (PREIS_KANON[k].monat || 0), 0);
        const sparEinmal = einzelEinmal - PREIS_KANON.kombi.einmal;
        const sparMonat = einzelMonat - PREIS_KANON.kombi.monat;
        // Ehrlich bleiben: "guenstigere Alternative" nur, wenn sie WIRKLICH in
        // beiden Groessen guenstiger ist. Sonst wird nichts behauptet.
        if (sparEinmal > 0 && sparMonat > 0) {
          kombi = { einzelEinmal, einzelMonat, sparEinmal, sparMonat };
        }
      }
      return { schluessel, einmal, monat, spannen, kombi };
    };

    const zeichnen = () => {
      const r = rechnen();
      const etwasGewaehlt = r.schluessel.length > 0;

      if (liste) {
        liste.textContent = "";
        r.schluessel.forEach((k) => {
          const p = PREIS_KANON[k];
          const li = doc.createElement("li");
          const name = doc.createElement("b");
          name.textContent = p.titel;
          if (p.note) {
            const klein = doc.createElement("small");
            klein.textContent = p.note;
            name.appendChild(klein);
          }
          const wert = doc.createElement("span");
          wert.textContent = preisText([k]);
          li.appendChild(name);
          li.appendChild(wert);
          liste.appendChild(li);
        });
        liste.hidden = !etwasGewaehlt;
      }
      if (leer) leer.hidden = etwasGewaehlt;

      if (summe) {
        summe.hidden = !etwasGewaehlt;
        // "keine" heisst: es faellt nichts an. Bei einer gewaehlten Spanne
        // (Website-Reparatur 290–990 €) waere genau das falsch — dort steht der
        // Preis nur noch nicht fest. Deshalb zwei getrennte Beschriftungen; die
        // laengere darf umbrechen (data-lang, siehe site.css).
        if (feldEinmal) {
          const offen = !r.einmal && r.spannen.length > 0;
          feldEinmal.textContent = r.einmal ? euro(r.einmal) : (offen ? "steht nach Sichtung fest" : "keine");
          feldEinmal.toggleAttribute("data-lang", offen);
        }
        if (feldMonat) feldMonat.textContent = r.monat ? euro(r.monat) + "/Monat" : "keine";
        const anzahlungFaellig = r.einmal >= ANZAHLUNG_AB;
        if (zeileAnzahlung) zeileAnzahlung.hidden = !anzahlungFaellig;
        if (feldAnzahlung && anzahlungFaellig) feldAnzahlung.textContent = euro(r.einmal * ANZAHLUNG_ANTEIL);
      }

      if (hinweis) {
        const saetze = [];
        if (r.spannen.length) {
          r.spannen.forEach((k) => {
            const p = PREIS_KANON[k];
            saetze.push(`Die ${p.titel} steht als Spanne (${spanneText(p)}) und ist bewusst in keiner Summe enthalten – der Preis steht erst nach Sichtung des Aufwands fest.`);
          });
        }
        if (r.spannen.length && r.einmal < ANZAHLUNG_AB) {
          saetze.push(`Dadurch kann der Projektwert über ${euro(ANZAHLUNG_AB)} steigen; dann werden 50 % bei Auftrag fällig.`);
        }
        hinweis.textContent = saetze.join(" ");
        hinweis.hidden = saetze.length === 0;
      }

      if (kombiBox && kombiText) {
        if (r.kombi) {
          kombiText.textContent =
            `Einzeln gewählt kosten Google-Ads-Setup, Ads-Betreuung und Anfragen-System ${euro(r.kombi.einzelEinmal)} + ${euro(r.kombi.einzelMonat)}/Monat. ` +
            `Als „${PREIS_KANON.kombi.titel}“ sind es ${euro(PREIS_KANON.kombi.einmal)} + ${euro(PREIS_KANON.kombi.monat)}/Monat – ` +
            `${euro(r.kombi.sparEinmal)} einmalig und ${euro(r.kombi.sparMonat)}/Monat weniger.`;
          kombiBox.hidden = false;
        } else {
          kombiBox.hidden = true;
        }
      }

      if (knopfAnfrage) knopfAnfrage.setAttribute("aria-disabled", String(!etwasGewaehlt));
      if (knopfReset) knopfReset.hidden = Object.keys(stand).length === 0;
      return r;
    };

    const waehlen = (btn, fokus) => {
      const gruppe = btn.dataset.gruppe;
      all(`[data-gruppe="${gruppe}"]`, block).forEach((peer) => {
        const an = peer === btn;
        peer.setAttribute("aria-checked", String(an));
        peer.tabIndex = an ? 0 : -1;
      });
      stand[gruppe] = btn;
      if (fokus) btn.focus();
      zeichnen();
    };

    wahlen.forEach((btn) => {
      btn.addEventListener("click", () => waehlen(btn, false));
      btn.addEventListener("keydown", (event) => {
        const peers = all(`[data-gruppe="${btn.dataset.gruppe}"]`, block);
        const index = peers.indexOf(btn);
        let next = -1;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % peers.length;
        else if (event.key === "ArrowLeft" || event.key === "ArrowUp") next = (index - 1 + peers.length) % peers.length;
        if (next < 0) return;
        event.preventDefault();
        waehlen(peers[next], true);
      });
    });

    knopfReset?.addEventListener("click", () => {
      Object.keys(stand).forEach((gruppe) => { delete stand[gruppe]; });
      // Zurueck in den Ausgangszustand: nichts angehakt, und in JEDER Gruppe ist
      // wieder genau der erste Knopf per Tabulator erreichbar (Radiogruppen-Regel).
      wahlen.forEach((btn) => {
        btn.setAttribute("aria-checked", "false");
        btn.tabIndex = all(`[data-gruppe="${btn.dataset.gruppe}"]`, block)[0] === btn ? 0 : -1;
      });
      zeichnen();
      wahlen[0]?.focus();
    });

    // Welche Option im Formular passt? Der groesste Brocken gewinnt; die
    // Nachricht traegt ohnehin die vollstaendige Zusammenstellung.
    const anliegenFuer = (schluessel) => {
      if (schluessel.indexOf("kompakt") > -1 || schluessel.indexOf("betrieb") > -1) return "Neue Website";
      if (schluessel.indexOf("reparatur") > -1) return "Website-Reparatur";
      if (schluessel.indexOf("system") > -1) return "Anfragen-System";
      if (schluessel.indexOf("adsSetup") > -1) return "Google Ads";
      return "Noch unsicher";
    };

    const nachrichtBauen = (r) => {
      const zeilen = ["Meine Zusammenstellung aus dem Preis-Rechner auf artur.ae:"];
      r.schluessel.forEach((k) => { zeilen.push("- " + PREIS_KANON[k].titel + ": " + preisText([k])); });
      // Gleiche Wahrheit wie in der Ergebnis-Spalte: bei einer gewaehlten Spanne
      // ist der einmalige Betrag offen, nicht "keine".
      const spannenText = r.spannen.map((k) => spanneText(PREIS_KANON[k])).join(" / ");
      zeilen.push("Einmalig: " + (
        r.einmal ? euro(r.einmal)
                 : (r.spannen.length ? "steht nach Sichtung fest — nur die Spanne " + spannenText : "keine")
      ));
      zeilen.push("Monatlich: " + (r.monat ? euro(r.monat) + "/Monat" : "keine"));
      if (r.einmal >= ANZAHLUNG_AB) zeilen.push("50 % bei Auftrag: " + euro(r.einmal * ANZAHLUNG_ANTEIL));
      r.spannen.forEach((k) => {
        zeilen.push("Hinweis: " + PREIS_KANON[k].titel + " ist eine Spanne (" + spanneText(PREIS_KANON[k]) + ") und nicht eingerechnet.");
      });
      if (r.kombi) {
        zeilen.push("Alternative: " + PREIS_KANON.kombi.titel + " für " + euro(PREIS_KANON.kombi.einmal) + " + " + euro(PREIS_KANON.kombi.monat) + "/Monat.");
      }
      zeilen.push("Das ist meine Orientierung – bitte sagen Sie mir, ob das so passt.");
      return zeilen.join("\n");
    };

    knopfAnfrage?.addEventListener("click", () => {
      if (knopfAnfrage.getAttribute("aria-disabled") === "true") return;
      const r = zeichnen();
      if (!r.schluessel.length) return;
      const ziel = doc.querySelector("#kontakt");
      const auswahl = doc.querySelector("#anliegen");
      const feld = doc.querySelector("#nachricht");
      const zeile = doc.querySelector("[data-rechner-uebernahme]");
      // Gleiche Mechanik wie Handy-CTA und 60-Sekunden-Check: erst auf den
      // ausfuehrlichen Weg schalten, denn "Worum geht es?" wird gleich gesetzt
      // und muss sichtbar UND aktiv sein, sonst ginge die Wahl nicht mit.
      kontaktAufAusfuehrlich();
      const anliegen = anliegenFuer(r.schluessel);
      if (auswahl && auswahl.querySelector(`option[value="${anliegen}"]`)) {
        auswahl.value = anliegen;
        // "change" melden: sonst haelt der 60-Sekunden-Check die Wahl fuer
        // unberuehrt und wuerde sie spaeter still ueberschreiben.
        auswahl.dispatchEvent(new Event("change", { bubbles: true }));
      }
      const text = nachrichtBauen(r);
      if (feld) {
        const vorhanden = feld.value.trim();
        // Nichts vom Nutzer loeschen, aber auch nie zwei widersprechende
        // Zusammenstellungen stehen lassen. Reihenfolge der Faelle:
        // 1. Der zuletzt eingesetzte Block steht noch irgendwo im Feld
        //    (auch mit eigenem Text davor) -> genau dieser Block wird ersetzt.
        // 2. Feld leer -> Block einsetzen.
        // 3. Nur fremder Text -> Block darunter haengen.
        if (letzteNachricht && feld.value.indexOf(letzteNachricht) > -1) {
          // Ersatz als Funktion: so bleibt der neue Text buchstabengetreu stehen
          // (eine Zeichenkette wuerde $-Muster wie "$&" als Befehl deuten).
          feld.value = feld.value.replace(letzteNachricht, () => text);
        } else if (!vorhanden) {
          feld.value = text;
        } else {
          feld.value = feld.value.replace(/\s+$/, "") + "\n\n" + text;
        }
        letzteNachricht = text;
      }
      if (zeile) zeile.hidden = false;
      ziel?.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" });
    });

    zeichnen();
    // Erst jetzt sichtbar — jede Zahl steht und stammt aus dem Kanon.
    // V8.62: sichtbar wird die HUELLE (<details>), nicht mehr der Rechner selbst.
    // Am Handy bleibt sie zugeklappt (spart rund 1.150 px Scrollweg); ab 981 px
    // steht der Rechner ohnehin zweispaltig und wird gleich aufgeklappt gezeigt.
    // Wer dem Link "Selbst zusammenstellen" folgt, klappt ihn auf — das erledigt
    // setupAnkerAufklappen() fuer jedes <details>, das Ziel eines #-Links ist.
    const huelle = block.closest("[data-rechner-huelle]");
    if (huelle) {
      huelle.hidden = false;
      if (window.matchMedia("(min-width: 981px)").matches) huelle.open = true;
    } else {
      block.hidden = false;
    }
    // Der Weg-Link steht nur, wenn es den Rechner wirklich gibt (kein toter Anker).
    const weg = doc.querySelector("[data-rechner-weg]");
    if (weg) weg.hidden = false;
  }

  // V8.62: Muster-Vergleich ist am Handy zugeklappt (Scrollweg), ab 721 px offen —
  // genau die Breite, ab der er zweispaltig neben den Text passt. Ohne JavaScript
  // bleibt er zugeklappt und ist per Tippen erreichbar; nichts geht verloren.
  function setupMusterKlappe() {
    const muster = doc.querySelector("[data-muster]");
    if (!muster) return;
    if (window.matchMedia("(min-width: 721px)").matches) muster.open = true;
  }

  function setupContactForm() {
    const form = doc.querySelector("[data-contact-form]");
    if (!form) return;
    const submit = form.querySelector('[type="submit"]');
    const status = form.querySelector("[data-form-status]");
    // V8.53: Das Spiegeln der Auswahl "Worum geht es?" in ein verstecktes Feld ist
    // ersatzlos entfallen. Grund: die Datenschutzerklaerung sichert zu, dass diese
    // Auswahl im kurzen Weg NICHT uebertragen wird - das Spiegelfeld hat sie
    // uebertragen. Im kurzen Weg ist "#anliegen" ausgeblendet UND deaktiviert,
    // FormData laesst deaktivierte Felder aus; damit stimmt Zusage und Verhalten
    // wieder ueberein. Das Check-Ergebnis geht unveraendert ueber die vier
    // "diagnose_*"-Felder mit, inklusive der angezeigten Empfehlung im Klartext.

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;

      if (submit) {
        submit.disabled = true;
        submit.dataset.label = submit.textContent;
        submit.textContent = "Wird übertragen …";
      }
      if (status) status.textContent = "Die Anfrage wird an Formspree übertragen.";

      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: { Accept: "application/json" }
        });
        if (!response.ok) throw new Error("Formularübertragung fehlgeschlagen");
        window.location.assign("danke.html");
      } catch (error) {
        if (status) status.textContent = "Das hat nicht geklappt. Bitte schreiben Sie an info@artur.ae oder rufen Sie an.";
        if (submit) {
          submit.disabled = false;
          submit.textContent = submit.dataset.label || "Anfrage senden";
        }
      }
    });
  }

  function setupMotion() {
    const progress = doc.querySelector("[data-scroll-progress]");
    const revealItems = all("[data-reveal]");
    const reportSheet = doc.querySelector(".report-sheet");
    const sequenceItems = all(".service");
    const einstiegsAnimationen = [];
    let scrubRaf = 0;
    let scrubAnfordern = null;
    let progressScrollStopp = null;
    let inViewStopp = null;
    let bewegungGestoppt = false;
    // Lebend-Pruefung: feuert der erste Animations-Frame, ist die Umgebung
    // gesund und Scroll/inView uebernehmen die Choreografie selbst. Nur wenn
    // KEIN Frame laeuft (versteckter Tab/WebView), loest das Sicherheitsnetz
    // alle Zustaende hart auf — sonst wuerde es die Choreografie zerstoeren.
    let rafLebt = false;
    window.requestAnimationFrame(() => { rafLebt = true; });

    const revealEverything = (hart = false) => {
      if (rafLebt && !hart) return;
      revealItems.forEach((item) => item.classList.remove("motion-pending"));
      if (reportSheet) reportSheet.classList.add("is-checked");
      sequenceItems.forEach((item) => item.classList.add("is-passed"));
      einstiegsAnimationen.forEach((steuerung) => {
        try { steuerung.complete(); } catch (fehler) { /* schon fertig */ }
      });
      all(".mask > *", doc.querySelector(".hero") || undefined).forEach((zeile) => { zeile.style.transform = "none"; });
      all("[data-hero-motion]").forEach((el) => { el.style.opacity = ""; el.style.transform = ""; });
    };

    const bewegungStoppen = () => {
      if (bewegungGestoppt) return;
      bewegungGestoppt = true;
      revealEverything(true);
      if (scrubRaf) {
        window.cancelAnimationFrame(scrubRaf);
        scrubRaf = 0;
      }
      if (scrubAnfordern) {
        window.removeEventListener("scroll", scrubAnfordern);
        window.removeEventListener("resize", scrubAnfordern);
      }
      if (typeof inViewStopp === "function") inViewStopp();
      if (typeof progressScrollStopp === "function") progressScrollStopp();
      if (progress) {
        const max = Math.max(1, doc.documentElement.scrollHeight - window.innerHeight);
        progress.style.transform = `scaleX(${Math.min(1, Math.max(0, window.scrollY / max))})`;
      }
      all(".button").forEach((btn) => { btn.style.transform = ""; });
    };

    reduceMotion.addEventListener?.("change", (event) => { if (event.matches) bewegungStoppen(); });

    if (reduceMotion.matches || !window.Motion) {
      rafLebt = false;
      revealEverything();
      if (reportSheet) reportSheet.classList.add("is-checked");
      sequenceItems.forEach((item) => item.classList.add("is-passed"));
      if (progress) {
        const update = () => {
          const max = Math.max(1, doc.documentElement.scrollHeight - window.innerHeight);
          progress.style.transform = `scaleX(${Math.min(1, Math.max(0, window.scrollY / max))})`;
        };
        let progressRaf = 0;
        const updateAnfordern = () => { if (!progressRaf) progressRaf = window.requestAnimationFrame(() => { progressRaf = 0; update(); }); };
        update();
        window.addEventListener("scroll", updateAnfordern, { passive: true });
        window.addEventListener("resize", updateAnfordern, { passive: true });
      }
      return;
    }

    const { animate, inView } = window.Motion;
    // Fortschrittsbalken: eigener Scroll-Handler statt Motions scroll()-Bindung.
    // Ursache-Fix 26.07.2026: scroll(animation) hat den Balken in manchen
    // Umgebungen nie angetrieben (live gemessen: transform blieb scaleX(0)),
    // dasselbe Muster wie beim ziel-gebundenen scroll({target}) unten. Die
    // Rechnung ist trivial — also deterministisch selbst, wie im reduce-Zweig.
    if (progress) {
      const progressUpdate = () => {
        const max = Math.max(1, doc.documentElement.scrollHeight - window.innerHeight);
        progress.style.transform = `scaleX(${Math.min(1, Math.max(0, window.scrollY / max))})`;
      };
      let progressRaf = 0;
      const progressAnfordern = () => { if (!progressRaf) progressRaf = window.requestAnimationFrame(() => { progressRaf = 0; progressUpdate(); }); };
      progressUpdate();
      window.addEventListener("scroll", progressAnfordern, { passive: true });
      window.addEventListener("resize", progressAnfordern, { passive: true });
      progressScrollStopp = () => {
        window.removeEventListener("scroll", progressAnfordern);
        window.removeEventListener("resize", progressAnfordern);
        if (progressRaf) { window.cancelAnimationFrame(progressRaf); progressRaf = 0; }
      };
    }

    // Hero-Ueberschrift: Zeilen steigen aus Masken auf
    const heroTitle = doc.querySelector(".hero h1");
    if (heroTitle && animate) {
      [...heroTitle.children].forEach((line, index) => {
        const mask = doc.createElement("span");
        mask.className = "mask";
        line.replaceWith(mask);
        mask.appendChild(line);
        // Die Kernaussage bleibt schon im ersten Bild lesbar. Die Bewegung
        // verschiebt die Zeile nur leicht, statt sie zunächst zu verstecken.
        einstiegsAnimationen.push(animate(line, { transform: ["translateY(10%)", "translateY(0%)"] }, { duration: .7, delay: .04 + index * .12, ease: [0.22, 1, 0.36, 1] }));
      });
    }

    // V8.59: Der Filter auf ".signal-console" ist entfallen — das Diagramm gibt es
    // nicht mehr, uebrig bleibt die Ueberschrift, die ihre eigene Masken-Animation hat.
    const aboveFold = all("[data-hero-motion]").filter((el) => el.tagName !== "H1");
    aboveFold.forEach((item, index) => {
      einstiegsAnimationen.push(animate(item, { transform: ["translateY(10px)", "translateY(0px)"] }, { duration: .5, delay: .12 + index * .07, ease: [0.22, 1, 0.36, 1] }));
    });

    // Loesungsweg-Scrub mit eigenem Scroll-Listener:
    // Motions ziel-gebundenes scroll({target}) feuert in manchen Umgebungen
    // nie (empirisch 20.07.2026) — die Rechnung ist trivial, also selbst machen.
    // V8.59: Die Hero-Parallaxe entfiel mit dem Schema-Diagramm — sie hatte nur
    // dieses eine Element verschoben.
    const seqList = doc.querySelector(".services-grid");
    const scrubUpdate = () => {
      scrubRaf = 0;
      if (bewegungGestoppt) return;
      if (reportSheet && !reportSheet.classList.contains("is-checked")) {
        const rr = reportSheet.getBoundingClientRect();
        if (rr.top < window.innerHeight * 0.6 && rr.bottom > 0) {
          all(".report-status", reportSheet).forEach((s, i) => { s.style.transitionDelay = `${180 + i * 300}ms`; });
          reportSheet.classList.add("is-checked");
        }
      }
      if (seqList && sequenceItems.length) {
        const r = seqList.getBoundingClientRect();
        const start = window.innerHeight * 0.8;
        const spanne = Math.max(1, r.height + (start - window.innerHeight * 0.45));
        const p = Math.min(1, Math.max(0, (start - r.top) / spanne));
        sequenceItems.forEach((item, i) => {
          item.classList.toggle("is-passed", p >= (i + 0.35) / sequenceItems.length);
        });
      }
    };
    scrubAnfordern = () => { if (!bewegungGestoppt && !scrubRaf) scrubRaf = window.requestAnimationFrame(scrubUpdate); };
    window.addEventListener("scroll", scrubAnfordern, { passive: true });
    window.addEventListener("resize", scrubAnfordern, { passive: true });
    scrubUpdate();

    // Abschnitts-Einblendungen mit Kaskade innerhalb einer Gruppe
    revealItems.forEach((item) => item.classList.add("motion-pending"));
    if (inView) {
      inViewStopp = inView(revealItems, (item) => {
        if (!item.classList.contains("motion-pending")) return;
        const geschwister = item.parentElement ? [...item.parentElement.children].filter((c) => c.hasAttribute("data-reveal")) : [item];
        const gi = Math.max(0, geschwister.indexOf(item));
        item.classList.remove("motion-pending");
        einstiegsAnimationen.push(animate(item, { opacity: [0, 1], transform: ["translateY(28px)", "translateY(0px)"] }, { duration: .58, delay: gi * .09, ease: [0.22, 1, 0.36, 1] }));
      }, { margin: "0px 0px -10% 0px", amount: .12 });
    }

    // Magnet-Knoepfe (nur echte Zeiger, nicht am Handy)
    if (window.matchMedia("(hover:hover) and (pointer:fine)").matches) {
      all(".button").forEach((btn) => {
        let raf = 0;
        btn.addEventListener("mousemove", (event) => {
          if (bewegungGestoppt || reduceMotion.matches) return;
          const r = btn.getBoundingClientRect();
          const dx = ((event.clientX - r.left) / r.width - 0.5) * 8;
          const dy = ((event.clientY - r.top) / r.height - 0.5) * 6;
          cancelAnimationFrame(raf);
          raf = requestAnimationFrame(() => { btn.style.transform = `translate(${dx}px, ${dy - 2}px)`; });
        });
        btn.addEventListener("mouseleave", () => {
          cancelAnimationFrame(raf);
          btn.style.transform = "";
        });
      });
    }

    window.setTimeout(revealEverything, 2600);
  }

  // Kleine Prozentzahl (dezent, aria-hidden): zeigt beim Scrollen den
  // Seitenfortschritt, blendet nach kurzer Ruhe aus. Nach V8.11-Vorlage;
  // seit V8.67 haengt sie am Ende des blauen Fortschrittsbalkens unter der
  // Kopfzeile und wandert waagerecht mit (vorher: rechts oben festgeklebt,
  // ab 1400px am A der Leiste angedockt).
  function setupScrollProzent() {
    if (!doc.querySelector(".scroll-progress")) return;
    // Bei reduzierter Bewegung keine ein-/ausblendende Pille (haertetes Blinken vermeiden).
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const label = doc.createElement("div");
    label.className = "scroll-prozent";
    label.setAttribute("aria-hidden", "true");
    // V8.67: Die Zahl haengt am Ende des blauen Balkens und wandert mit.
    // Bezug ist die gemessene Balkenbreite, nicht 100vw — mit klassischer
    // Scrollleiste (Windows) sind das nicht dieselben Zahlen.
    const balken = doc.querySelector(".scroll-progress");
    const RAND = 10;
    const prozentSetzen = () => {
      const max = Math.max(1, doc.documentElement.scrollHeight - window.innerHeight);
      const p = Math.min(1, Math.max(0, window.scrollY / max));
      label.textContent = Math.round(p * 100) + " %";
      const B = balken ? balken.clientWidth : window.innerWidth;
      const w = label.offsetWidth || 56;
      // Geklemmt: bei 0 % laeuft sie sonst links raus, bei 100 % rechts.
      let lo = RAND, hi = B - w - RAND;
      // V8.89: Auf dem Handy sitzt die Pille IM Kopfband (CSS top -24px) -
      // waagerecht darf sie dort weder Logo noch Menue-Knopf beruehren.
      if (window.matchMedia("(max-width: 720px)").matches) {
        const brand = doc.querySelector(".brand");
        const knopf = doc.querySelector(".menu-toggle");
        if (brand) lo = Math.max(lo, brand.getBoundingClientRect().right + 8);
        if (knopf && getComputedStyle(knopf).display !== "none") {
          hi = Math.min(hi, knopf.getBoundingClientRect().left - w - 8);
        }
      }
      const x = Math.round(Math.max(lo, Math.min(p * B - w / 2, hi)));
      label.style.transform = "translate3d(" + x + "px,0,0)";
    };
    prozentSetzen();
    doc.body.appendChild(label);
    let raf = 0;
    let ausblenden = 0;
    window.addEventListener("scroll", () => {
      if (raf) return;
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        prozentSetzen();
        label.classList.add("sichtbar");
        window.clearTimeout(ausblenden);
        ausblenden = window.setTimeout(() => label.classList.remove("sichtbar"), 1100);
      });
    }, { passive: true });
  }

  function setupMarquee() {
    const stop = doc.querySelector("[data-marquee-stop]");
    const band = stop ? stop.closest(".marquee") : null;
    if (!stop || !band) return;
    stop.addEventListener("click", () => {
      const pausiert = band.classList.toggle("marquee--paused");
      stop.setAttribute("aria-pressed", String(pausiert));
      stop.setAttribute("aria-label", pausiert ? "Laufband abspielen" : "Laufband anhalten");
      stop.textContent = pausiert ? "▶" : "❚❚";
    });
  }

  // Ein Sprungziel darf nicht zugeklappt bleiben: zeigt ein Anker auf ein
  // geschlossenes <details> (oder auf etwas darin), wird es vorher geoeffnet.
  // Ohne JavaScript bleibt es zu — dann klappt der Besucher selbst auf, die
  // Kopfzeile traegt die Aussage auch geschlossen.
  function setupAnkerAufklappen() {
    const oeffnen = (hash) => {
      const id = decodeURIComponent((hash || "").replace(/^#/, ""));
      if (!id) return;
      let knoten = doc.getElementById(id);
      while (knoten) {
        if (knoten.tagName === "DETAILS") knoten.open = true;
        knoten = knoten.parentElement;
      }
    };
    doc.addEventListener("click", (event) => {
      const link = event.target.closest('a[href^="#"]');
      if (link) oeffnen(link.hash);
    }, true);
    window.addEventListener("hashchange", () => oeffnen(window.location.hash));
    oeffnen(window.location.hash);
  }

  setCurrentYear();
  setupMenu();
  setupAnkerAufklappen();
  setupOptionalVisuals();
  setupMarquee();
  setupPriceTabs();
  setupPreisSprungziele(); // NACH setupPriceTabs: erst dort entsteht die Weiche
  setupVorlagen();     // vor dem Umschalter: der schaltet die Vorlagen sichtbar
  setupKontaktModus(); // vor der Diagnose: sie darf den ausfuehrlichen Weg oeffnen
  setupDiagnostic();
  setupPreisRechner(); // nach setupKontaktModus: der Rechner nutzt den ausfuehrlichen Weg
  setupMusterKlappe();
  setupHandyUebergabe();
  setupHandy2d();
  setupContactForm();
  setupMotion();
  setupScrollProzent();
  root.classList.add("site-ready");
})();
