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
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.05;
      renderer.shadowMap.enabled = true;
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
      controls.enableDamping = false;
      controls.enableZoom = false;
      controls.enablePan = false;
      controls.autoRotate = false;
      controls.addEventListener("change", () => this.requestRender());
      this._controls = controls;

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

      const box = new THREE.Box3().setFromObject(object);
      if (!box.isEmpty()) {
        this._ground.position.y = box.min.y;
        const sphere = box.getBoundingSphere(new THREE.Sphere());
        const distance =
          (sphere.radius / Math.tan((this._camera.fov * Math.PI) / 360)) * 0.96;
        const direction = new THREE.Vector3(0.46, 0.4, 1.7).normalize();
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
