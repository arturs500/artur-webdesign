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
    const handyVisual = window.matchMedia("(min-width: 1024px) and (hover: hover)");
    let heroHandyStarted = false;
    let heroHandyReady = false;
    let heroStage = null;

    const heroHandyEligible = () => !reduceMotion.matches && handyVisual.matches;
    const syncHeroHandy = () => {
      const active = heroHandyEligible();
      if (heroStage && typeof heroStage.setActive === "function") {
        heroStage.setActive(active);
      }
      root.classList.toggle("hero3d", active && heroHandyReady);
    };
    const failHeroHandy = () => {
      heroHandyReady = false;
      root.classList.remove("hero3d");
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
      s1.src = new URL("hero3d-stage.js?v=75", assetsBase).href;
      s1.dataset.optionalVisual = "hero3d-stage.js";
      s1.onerror = failHeroHandy;
      s1.onload = () => {
        syncHeroHandy();
        const s2 = doc.createElement("script");
        s2.type = "module";
        s2.src = new URL("hero3d-handy.js?v=75", assetsBase).href;
        s2.dataset.optionalVisual = "hero3d-handy.js";
        s2.onload = () => {
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
      if (!reduceMotion.matches && desktopVisuals.matches && doc.querySelector(".hero")) {
        load("treppe.js?v=75");
      }
      if (heroHandyEligible() && doc.querySelector("[data-hero-stage]")) {
        loadHeroHandy();
      }
      syncHeroHandy();
    };

    // Erst nach dem ersten Seitenbild laden (window load + Leerlauf) — die 3D-Kette
    // (~443 KB gzip) darf den kritischen Pfad nie anfassen. Bei Datensparmodus gar nicht.
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

  function setupPriceTabs() {
    all("[data-price-tabs]").forEach((tabList) => {
      const tabs = all('[role="tab"]', tabList);
      const compactPrices = window.matchMedia("(max-width: 720px)");
      const panels = tabs
        .map((tab) => doc.getElementById(tab.getAttribute("aria-controls")))
        .filter(Boolean);

      const activate = (tab, moveFocus = false) => {
        tabs.forEach((item) => {
          const selected = item === tab;
          item.setAttribute("aria-selected", String(selected));
          item.tabIndex = selected ? 0 : -1;
        });
        panels.forEach((panel) => {
          panel.hidden = compactPrices.matches ? false : panel.id !== tab.getAttribute("aria-controls");
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

      const syncLayout = () => {
        const selected = tabs.find((tab) => tab.getAttribute("aria-selected") === "true") || tabs[0];
        if (selected) activate(selected);
      };
      compactPrices.addEventListener?.("change", syncLayout);
      syncLayout();
    });
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

    const recommendations = {
      visibility: {
        title: "Erst die Grundlage für Sichtbarkeit prüfen.",
        text: "Google Ads bringen Besucher auf die Zielseite. Ob daraus passende Anfragen werden, hängt auch von Angebot und Kontaktweg ab. Der Website-Check prüft diese Basis zuerst.",
        price: "Wenn passend: Website-Check ab 49 €",
        code: "01 / PRÜFEN",
        select: "Website-Check"
      },
      visibilityFoundation: {
        title: "Zuerst klären, worauf Sichtbarkeit einzahlen soll.",
        text: "Bevor Werbung startet, muss klar sein, welches Angebot sichtbar werden soll und wohin Interessenten geführt werden. Ohne belegte, tragfähige Zielseite bleibt offen, ob eine vorhandene Seite reicht, eine einzelne Zielseite oder eine kompakte Website gebraucht wird.",
        price: "Wenn passend: Ads-Setup 349 € oder Kompakt-Website 990 €",
        code: "01 / GRUNDLAGE",
        select: "Noch unsicher",
        summary: "Sichtbarkeitsbasis klären",
        demoHref: "#loesungsweg",
        demoLabel: "Sichtbarkeits-Bausteine ansehen"
      },
      website: {
        title: "Bestehende Seite prüfen, bevor Sie neu bauen.",
        text: "Wenn Struktur und Technik noch tragfähig sind, reicht oft eine gezielte Reparatur. Nur wenn das Fundament nicht mehr passt, ist eine neue Website sinnvoll.",
        price: "Wenn passend: Prüfung ab 49 € · Reparatur 290–990 €",
        code: "02 / KLÄREN",
        select: "Website-Check"
      },
      inquiries: {
        title: "Anfragen zuerst an einer Stelle zusammenführen.",
        text: "Ein Anfragen-System lohnt sich, wenn bereits Kontakte entstehen, aber zwischen Telefon, WhatsApp und Notizen verloren gehen. Der genaue Ablauf wird vorab begrenzt.",
        price: "Wenn passend: 490 € Einrichtung + 49 €/Monat",
        code: "03 / ORDNEN",
        select: "Anfragen-System"
      },
      routine: {
        title: "Einen wiederkehrenden Ablauf als Pilot testen.",
        text: "Nicht alles auf einmal automatisieren. Ein klarer, häufig wiederholter Ablauf wird als kleiner Pilot gebaut und gegen den heutigen Prozess geprüft.",
        price: "Wenn passend: KI-Pilot ab 1.990 €",
        code: "04 / TESTEN",
        select: "KI-Pilot"
      },
      newsite: {
        title: "Eine klare Website als belastbare Basis bauen.",
        text: "Wenn keine nutzbare Seite vorhanden ist, wird zuerst die Basis aus Angebot, Ziel und Kontaktweg sauber aufgebaut. Danach können Sichtbarkeit und digitale Abläufe sinnvoll folgen.",
        price: "Wenn passend: Kompakt-Website 990 € · 5–8 Seiten 1.990 €",
        code: "02 / BAUEN",
        select: "Neue Website"
      },
      // defensive Absicherung / Fallback, aktuell nie erreicht (bottleneck bei completed===3 stets gueltig)
      unsure: {
        title: "Mit einer kleinen Bestandsaufnahme anfangen.",
        text: "Sie müssen die technische Lösung noch nicht kennen. Beschreiben Sie kurz Ihre Lage; Sie bekommen eine klare Einordnung statt eines unnötig großen Pakets.",
        price: "Erst einordnen, dann den passenden Festpreis wählen",
        code: "01 / EINORDNEN",
        select: "Noch unsicher"
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
      }
      if (resultPrices) resultPrices.hidden = false;
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
        contactSelect.value = recommendation;
        anliegenTouched = true;
      }
    });

    render();
  }

  function setupContactForm() {
    const form = doc.querySelector("[data-contact-form]");
    if (!form) return;
    const submit = form.querySelector('[type="submit"]');
    const status = form.querySelector("[data-form-status]");

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
    const konsole = doc.querySelector(".signal-console");
    let scrubRaf = 0;
    let scrubAnfordern = null;
    let pulseAnimation = null;
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
      [pulseAnimation].forEach((steuerung) => {
        if (!steuerung) return;
        try { steuerung.pause(); } catch (fehler) { /* bereits beendet */ }
      });
      if (progress) {
        const max = Math.max(1, doc.documentElement.scrollHeight - window.innerHeight);
        progress.style.transform = `scaleX(${Math.min(1, Math.max(0, window.scrollY / max))})`;
      }
      if (konsole) konsole.style.transform = "";
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

    const aboveFold = all("[data-hero-motion]").filter((el) => el.tagName !== "H1" && !el.classList.contains("signal-console"));
    const konsoleEinstieg = doc.querySelector(".signal-console");
    if (konsoleEinstieg) {
      einstiegsAnimationen.push(animate(konsoleEinstieg, { transform: ["translateY(12px)", "translateY(0px)"] }, { duration: .65, delay: .2, ease: "easeOut" }));
    }
    aboveFold.forEach((item, index) => {
      einstiegsAnimationen.push(animate(item, { transform: ["translateY(10px)", "translateY(0px)"] }, { duration: .5, delay: .12 + index * .07, ease: [0.22, 1, 0.36, 1] }));
    });

    // Parallaxe + Loesungsweg-Scrub mit eigenem Scroll-Listener:
    // Motions ziel-gebundenes scroll({target}) feuert in manchen Umgebungen
    // nie (empirisch 20.07.2026) — die Rechnung ist trivial, also selbst machen.
    const heroSection = doc.querySelector(".hero");
    const seqList = doc.querySelector(".services-grid");
    const scrubUpdate = () => {
      scrubRaf = 0;
      if (bewegungGestoppt) return;
      if (konsole && heroSection) {
        const hr = heroSection.getBoundingClientRect();
        const hp = Math.min(1, Math.max(0, -hr.top / Math.max(1, hr.height)));
        konsole.style.transform = `translate3d(0, ${(hp * -34).toFixed(1)}px, 0)`;
      }
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

    all(".console-map .signal-line").forEach((line, index) => {
      einstiegsAnimationen.push(animate(line, { opacity: [0, 1] }, { duration: .9, delay: .55 + index * .16, ease: "easeInOut" }));
    });

    const pulse = doc.querySelector(".console-cursor");
    if (pulse) {
      pulseAnimation = animate(pulse, { transform: ["scale(1)", "scale(1.08)", "scale(1)"], opacity: [1, .72, 1] }, { duration: 2.4, repeat: Infinity, ease: "easeInOut" });
      doc.addEventListener("visibilitychange", () => {
        if (doc.hidden) pulseAnimation.pause();
        else if (!bewegungGestoppt && !reduceMotion.matches) pulseAnimation.play();
      });
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

  // Kleine Prozentzahl am Fortschrittsbalken (rechts oben, dezent, aria-hidden):
  // zeigt beim Scrollen den Seitenfortschritt, blendet nach kurzer Ruhe aus.
  // Wiederbelebt nach V8.11-Vorlage (damals wanderte das Label mit dem Balken);
  // heute fest rechts oben, damit es dem 3D-Hero und dem Menü nie im Weg steht.
  function setupScrollProzent() {
    if (!doc.querySelector(".scroll-progress")) return;
    // Bei reduzierter Bewegung keine ein-/ausblendende Pille (haertetes Blinken vermeiden).
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const label = doc.createElement("div");
    label.className = "scroll-prozent";
    label.setAttribute("aria-hidden", "true");
    const prozentSetzen = () => {
      const max = Math.max(1, doc.documentElement.scrollHeight - window.innerHeight);
      const p = Math.min(1, Math.max(0, window.scrollY / max));
      label.textContent = Math.round(p * 100) + " %";
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

  setCurrentYear();
  setupMenu();
  setupOptionalVisuals();
  setupMarquee();
  setupPriceTabs();
  setupDiagnostic();
  setupContactForm();
  setupMotion();
  setupScrollProzent();
  root.classList.add("site-ready");
})();
