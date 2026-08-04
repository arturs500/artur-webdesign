/*
 * <three-d-stage> — schlanke, lokale Three.js-Bühne für den Website-Hero.
 *
 * Die Bibliothek wird ausschließlich über die lokale Importmap in index.html
 * geladen. Die Bühne rendert ereignisgesteuert: bei Größenänderung,
 * Nutzerinteraktion oder einer aktualisierten Display-Textur. Außerhalb des
 * sichtbaren Bereichs, im Hintergrund-Tab und bei deaktiviertem 3D bleibt sie
 * vollständig stehen.
 */
(() => {
  "use strict";

  const stylesheet = `
    :host {
      position: relative;
      display: block;
      width: 100%;
      height: 100%;
      background: var(--stage-bg, transparent);
      overflow: hidden;
    }
    canvas {
      display: block;
      width: 100%;
      height: 100%;
      outline: none;
    }
    .err {
      position: absolute;
      inset: 0;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      color: #ffd8cf;
      font: 600 14px/1.55 system-ui, sans-serif;
      text-align: center;
    }
  `;

  class ThreeDStage extends HTMLElement {
    constructor() {
      super();

      const shadow = this.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      style.textContent = stylesheet;
      shadow.appendChild(style);

      this._err = document.createElement("div");
      this._err.className = "err";
      this._err.setAttribute("role", "status");
      shadow.appendChild(this._err);

      this._active = true;
      this._intersecting = !("IntersectionObserver" in window);
      this._renderQueued = 0;
      this._renderCount = 0;
      this._boundVisibility = () => this._syncActivity();

      this.ready = new Promise((resolve, reject) => {
        this._readyResolve = resolve;
        this._readyReject = reject;
      });
    }

    connectedCallback() {
      this._startObservers();
      if (this._booted) {
        this._syncActivity();
        return;
      }

      this._booted = true;
      this._boot().catch((error) => {
        this._err.style.display = "flex";
        this._err.textContent = "Die optionale 3D-Vorschau konnte nicht geladen werden.";
        this._readyReject(error);
      });
    }

    disconnectedCallback() {
      this._stopObservers();
      this._cancelRender();
    }

    setActive(active) {
      this._active = Boolean(active);
      this._syncActivity();
    }

    requestRender() {
      if (!this._canRender() || this._renderQueued) return;
      this._renderQueued = window.requestAnimationFrame(() => {
        this._renderQueued = 0;
        if (!this._canRender()) return;
        this._controls.update();
        this._renderer.render(this._scene, this._camera);
        this._renderCount += 1;
      });
    }

    _startObservers() {
      if (!this._intersectionObserver && "IntersectionObserver" in window) {
        this._intersectionObserver = new IntersectionObserver((entries) => {
          const entry = entries[entries.length - 1];
          this._intersecting = Boolean(entry && entry.isIntersecting);
          this._syncActivity();
        }, { threshold: 0.01 });
      }
      this._intersectionObserver?.observe(this);
      document.addEventListener("visibilitychange", this._boundVisibility);
      this._resizeObserver?.observe(this);
    }

    _stopObservers() {
      this._intersectionObserver?.unobserve(this);
      this._resizeObserver?.unobserve(this);
      document.removeEventListener("visibilitychange", this._boundVisibility);
    }

    _canRender() {
      return Boolean(
        this._renderer
        && this._controls
        && this._active
        && this._intersecting
        && this.isConnected
        && !document.hidden
      );
    }

    _syncActivity() {
      if (this._canRender()) this.requestRender();
      else this._cancelRender();
    }

    _cancelRender() {
      if (!this._renderQueued) return;
      window.cancelAnimationFrame(this._renderQueued);
      this._renderQueued = 0;
    }

    async _boot() {
      const background = this.getAttribute("background");
      if (background) this.style.setProperty("--stage-bg", background);

      const [THREE, controlsModule] = await Promise.all([
        import("three"),
        import("three/addons/controls/OrbitControls.js"),
      ]);
      this._THREE = THREE;

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "default",
      });
      // Schaerfe (V8.45): Deckel von 1,75 auf 2 angehoben. Bei devicePixelRatio 2
      // (jeder Retina-Mac) wurde vorher mit 87,5 % gerendert und vom Browser wieder
      // hochskaliert — dieser Zwischenschritt hat JEDE Kante weichgezogen. Mit 2 liegt
      // ein gerenderter Bildpunkt exakt auf einem Schirm-Bildpunkt. Die Leerlauf-Last
      // bleibt 0: gerendert wird ausschliesslich ereignisgesteuert (requestRender).
      // V8.84: Deckel 3 statt 2 — moderne Telefone haben devicePixelRatio 3; mit Deckel 2
      // bekam genau das Abnahme-Geraet nur 2/3 der Aufloesung (gemessen 724x1172
      // statt 1086x1758 bei 362x586 CSS). Mehrlast nur bei Interaktion (Leerlauf 0).
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 3));
      // V8.87 (Arturs Geraete-Befund 'es haengt'): Waehrend einer laufenden
      // Geste (Drehen, Listen-Scroll) wird mit Deckel 2 gerendert, im Stand
      // wieder mit 3. Ein Frame @DPR3 + Schatten + frischer Screen-Textur ist
      // fuer aeltere Telefone pro pointermove zu teuer - halbe Pixelzahl
      // waehrend der Bewegung ist unsichtbar, der Stand bleibt gestochen.
      let interaktionsDpr = false;
      const dprSetzen = (grob) => {
        if (grob === interaktionsDpr) return;
        interaktionsDpr = grob;
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, grob ? 2 : 3));
        if (this._fit) this._fit(); else this.requestRender();
      };
      this._dprGrob = dprSetzen;
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.05;
      renderer.shadowMap.enabled = true;
      // Weicher Kontaktschatten (Design-Vorgabe): PCF glaettet die Schattenkante,
      // Lichtaufbau bleibt unveraendert (1 Key + 1 Rim/Fill + Hemisphaere, kein Glow).
      // PCFShadowMap statt PCFSoft: r184 faellt ohnehin darauf zurueck, Optik identisch, 0 Konsolen-Warnung.
      renderer.shadowMap.type = THREE.PCFShadowMap;
      renderer.domElement.setAttribute("aria-hidden", "true");
      this._renderer = renderer;
      this.shadowRoot.insertBefore(renderer.domElement, this._err);

      const scene = new THREE.Scene();
      this._scene = scene;

      const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 500);
      camera.position.set(3, 2.2, 4);
      this._camera = camera;

      const controls = new controlsModule.OrbitControls(camera, renderer.domElement);
      // WICHTIG — Reihenfolge ist zwingend: OrbitControls.connect() setzt im Konstruktor
      // den Inline-Stil touchAction="none". Wirkung gemessen (28.07.2026, 1100px, Touch):
      // senkrechter Wisch ueber der Buehne = 0 px Scroll statt 538 px — der Finger bleibt
      // haengen. "pan-y" gibt das senkrechte Scrollen an den Browser zurueck; waagerechtes
      // Ziehen bleibt beim Drehen, Tippen bleibt beim Bedienen. Die CSS-Regel
      // .hero-phone__stage{touch-action:pan-y} reicht dafuer NICHT (sitzt auf dem Wrapper,
      // touch-action vererbt nicht, Inline-Stil schlaegt CSS). Nicht "aufraeumen".
      renderer.domElement.style.touchAction = "pan-y";
      controls.enableDamping = false;
      controls.enableZoom = false;
      controls.enablePan = false;
      controls.autoRotate = false;
      // Zwei-Finger-Gesten sind ohnehin aus (kein Zoom, kein Pan) — hier explizit,
      // damit Pinch/Zwei-Finger-Wisch am Handy die Seite bedient, nicht die Buehne.
      // V8.84: Ein-Finger-Drehen laeuft NICHT mehr ueber OrbitControls. Grund
      // (gemessen, Pruef-Workflow 03.08.): pan-y laesst den Browser erst nach
      // seiner Slop-Strecke entscheiden — bis dahin drehte Orbit schon mit. Im
      // 45-55-Grad-Band scrollte die Seite UND das Handy zuckte 1,5-18 Grad mit.
      // Jetzt entscheidet ein eigener Richtungs-Waechter VOR der ersten Drehung:
      // erst ab 10px Weg und |dx| >= 1,6*|dy| wird gedreht; alles andere gehoert
      // dem Browser-Scroll. Maus/Stift bleiben unveraendert bei OrbitControls.
      if (THREE.TOUCH) controls.touches = { ONE: null, TWO: null };
      controls.addEventListener("change", () => this.requestRender());
      this._controls = controls;

      controls.addEventListener("start", () => dprSetzen(true));
      controls.addEventListener("end", () => dprSetzen(false));
      const fingerDreh = { id: null, x: 0, y: 0, modus: null };
      const drehOffset = new THREE.Vector3();
      const drehKugel = new THREE.Spherical();
      const fingerDrehen = (dx, dy) => {
        drehOffset.copy(camera.position).sub(controls.target);
        drehKugel.setFromVector3(drehOffset);
        const winkel = (2 * Math.PI) / (renderer.domElement.clientHeight || 1);
        drehKugel.theta -= dx * winkel * (controls.rotateSpeed || 1);
        drehKugel.phi -= dy * winkel * (controls.rotateSpeed || 1);
        drehKugel.phi = Math.min(controls.maxPolarAngle - 1e-4,
          Math.max(controls.minPolarAngle + 1e-4, drehKugel.phi));
        drehKugel.makeSafe();
        drehOffset.setFromSpherical(drehKugel);
        camera.position.copy(controls.target).add(drehOffset);
        camera.lookAt(controls.target);
        this.requestRender();
        controls.dispatchEvent({ type: "change" });
      };
      renderer.domElement.addEventListener("pointerdown", (e) => {
        if (e.pointerType !== "touch") return;
        fingerDreh.id = e.pointerId; fingerDreh.x = e.clientX; fingerDreh.y = e.clientY;
        fingerDreh.modus = null;
      });
      renderer.domElement.addEventListener("pointermove", (e) => {
        if (e.pointerType !== "touch" || e.pointerId !== fingerDreh.id) return;
        const dx = e.clientX - fingerDreh.x;
        const dy = e.clientY - fingerDreh.y;
        if (fingerDreh.modus === null) {
          if (Math.hypot(dx, dy) < 10) return;
          // V8.85: Beruehrungen, die auf dem Geraete-Display begonnen haben,
          // bedienen die App (Flag setzt hero3d-handy.js) - nie drehen.
          if (renderer.domElement.dataset.displayGriff === "1") { fingerDreh.modus = "browser"; return; }
          fingerDreh.modus = Math.abs(dx) >= 1.6 * Math.abs(dy) ? "dreht" : "browser";
          fingerDreh.x = e.clientX; fingerDreh.y = e.clientY;
          if (fingerDreh.modus === "dreht") controls.dispatchEvent({ type: "start" });
          return;
        }
        if (fingerDreh.modus !== "dreht") return;
        fingerDrehen(dx, dy);
        fingerDreh.x = e.clientX; fingerDreh.y = e.clientY;
      });
      const fingerEnde = (e) => {
        if (e.pointerType !== "touch" || e.pointerId !== fingerDreh.id) return;
        if (fingerDreh.modus === "dreht") controls.dispatchEvent({ type: "end" });
        fingerDreh.id = null; fingerDreh.modus = null;
      };
      renderer.domElement.addEventListener("pointerup", fingerEnde);
      renderer.domElement.addEventListener("pointercancel", fingerEnde);

      scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d2c4, 1));
      const key = new THREE.DirectionalLight(0xffffff, 2.2);
      key.position.set(4, 7, 5);
      key.castShadow = true;
      key.shadow.mapSize.set(1024, 1024);
      key.shadow.bias = -0.0002;
      this._key = key;
      scene.add(key);

      const fill = new THREE.DirectionalLight(0xfff4e6, 0.5);
      fill.position.set(-5, 3, -4);
      scene.add(fill);

      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(200, 200),
        new THREE.ShadowMaterial({ opacity: 0.18 }),
      );
      ground.rotation.x = -Math.PI / 2;
      ground.receiveShadow = true;
      this._ground = ground;
      scene.add(ground);

      const fit = () => {
        const width = this.clientWidth;
        const height = this.clientHeight;
        if (!width || !height) return;
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        this.requestRender();
      };
      this._fit = fit;
      this._resizeObserver = new ResizeObserver(fit);
      if (this.isConnected) this._resizeObserver.observe(this);
      fit();

      this._readyResolve({ THREE });
      this._syncActivity();
    }

    setObject(object) {
      const THREE = this._THREE;
      if (!THREE) throw new Error("three-d-stage: Bühne ist noch nicht bereit");

      if (this._object) this._scene.remove(this._object);
      this._object = object;
      object.traverse((part) => {
        if (!part.isMesh) return;
        part.castShadow = true;
        part.receiveShadow = true;
      });

      // Kamera-Fit NUR ueber die sichtbare Geraete-Geometrie: Sprites, Lichter
      // und als userData.noFit markierte Effekt-Meshes (z. B. der unsichtbare
      // Taschenlampen-Kegel) blaehen die Box sonst um ein Mehrfaches auf ->
      // die Kamera rueckt zu weit weg und das Objekt wirkt winzig.
      object.updateWorldMatrix(true, true);
      const box = new THREE.Box3();
      const partBox = new THREE.Box3();
      object.traverse((part) => {
        if (!part.isMesh || part.userData.noFit || !part.geometry) return;
        if (part.geometry.boundingBox === null) part.geometry.computeBoundingBox();
        partBox.copy(part.geometry.boundingBox).applyMatrix4(part.matrixWorld);
        box.union(partBox);
      });
      if (!box.isEmpty()) {
        this._ground.position.y = box.min.y;
        const sphere = box.getBoundingSphere(new THREE.Sphere());
        const distance =
          (sphere.radius / Math.tan((this._camera.fov * Math.PI) / 360)) * 1.1;
        const direction = new THREE.Vector3(0, 0.05, 1).normalize();
        this._camera.position
          .copy(sphere.center)
          .add(direction.multiplyScalar(distance));
        this._camera.near = Math.max(distance / 100, 0.01);
        this._camera.far = distance * 100;
        this._camera.updateProjectionMatrix();
        this._controls.target.copy(sphere.center);
        this._controls.update();

        const span = sphere.radius * 3;
        this._key.shadow.camera.left = -span;
        this._key.shadow.camera.right = span;
        this._key.shadow.camera.top = span;
        this._key.shadow.camera.bottom = -span;
        this._key.shadow.camera.updateProjectionMatrix();
      }

      this._scene.add(object);
      this.requestRender();
    }
  }

  if (!customElements.get("three-d-stage")) {
    customElements.define("three-d-stage", ThreeDStage);
  }
})();
