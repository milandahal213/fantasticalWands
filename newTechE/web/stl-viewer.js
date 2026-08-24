// stl-viewer.js - lightweight drag-to-rotate STL previews for the Build page.
// Loads three.js from a CDN (same pattern as the pyscript.net include in index.html).
// Each <div class="stl-viewer" data-parts='[{"url":"...","color":"#ddd"}]'></div>
// gets its own scene; multiple parts in one viewer render as a combined assembly.

import * as THREE from "three";
import { STLLoader } from "https://unpkg.com/three@0.160.0/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "https://unpkg.com/three@0.160.0/examples/jsm/controls/OrbitControls.js";

function createViewer(container) {
  const parts = JSON.parse(container.dataset.parts || "[]");
  if (!parts.length) return;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 10000);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(1, 2, 3);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.35);
  fill.position.set(-2, -1, -1);
  scene.add(fill);

  const group = new THREE.Group();
  scene.add(group);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 2.2;
  controls.enablePan = false;
  controls.minDistance = 1;
  controls.maxDistance = 100000;
  renderer.domElement.addEventListener("pointerdown", () => (controls.autoRotate = false));

  const loader = new STLLoader();
  let loaded = 0;
  parts.forEach((part) => {
    loader.load(part.url, (geometry) => {
      geometry.computeVertexNormals();
      const material = new THREE.MeshStandardMaterial({
        color: part.color || "#c9cfe6",
        roughness: 0.55,
        metalness: 0.05,
        transparent: !!part.opacity,
        opacity: part.opacity ?? 1,
      });
      const mesh = new THREE.Mesh(geometry, material);
      group.add(mesh);
      loaded += 1;
      if (loaded === parts.length) fitCameraToGroup();
    });
  });

  function fitCameraToGroup() {
    const box = new THREE.Box3().setFromObject(group);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    group.position.sub(center);

    const radius = Math.max(size.x, size.y, size.z, 1) * 0.5;
    const dist = radius / Math.sin((camera.fov * Math.PI) / 360) * 1.35;
    camera.position.set(dist * 0.6, dist * 0.45, dist * 0.8);
    camera.near = dist / 100;
    camera.far = dist * 100;
    camera.updateProjectionMatrix();
    controls.target.set(0, 0, 0);
    controls.update();
  }

  function resize() {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (!w || !h) return;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  resize();
  new ResizeObserver(resize).observe(container);

  // Only spend GPU/CPU on viewers actually scrolled into view.
  let rafId = null;
  function animate() {
    rafId = requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  new IntersectionObserver((entries) => {
    const visible = entries[0].isIntersecting;
    if (visible && rafId === null) animate();
    if (!visible && rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }).observe(container);
}

function initAll() {
  document.querySelectorAll(".stl-viewer").forEach(createViewer);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAll);
} else {
  initAll();
}
