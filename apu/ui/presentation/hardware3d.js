/**
 * hardware3d.js - 3D Tactile Equipment Studio at the base of the Keynote Prompter
 * Features:
 * - Three.js WebGL realistic rendering of Pocket Akili
 * - Mouse proximity detection: cursor morphs into a hand when approaching the device
 * - Highly visible click feedback: 3D mechanical button depression + screen-space shockwave ripple
 * - Audio haptic clicks
 * - Direct triggering of real actions (Speech turn, Notebook, Summary, Braille)
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

function createButtonIconTexture(type, bg = "#1e3a8a", fg = "#ffffff", ringColor = "#3b82f6") {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");

  // Rich base fill
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, 256, 256);

  // Circular tactile recessed surface with high-contrast accent ring
  ctx.beginPath();
  ctx.arc(128, 128, 120, 0, Math.PI * 2);
  ctx.fillStyle = bg;
  ctx.fill();
  ctx.lineWidth = 10;
  ctx.strokeStyle = ringColor;
  ctx.stroke();

  // Subtle inner highlight ring for realistic tactile depth
  ctx.beginPath();
  ctx.arc(128, 128, 112, 0, Math.PI * 2);
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
  ctx.stroke();

  ctx.fillStyle = fg;
  ctx.strokeStyle = fg;
  ctx.lineWidth = 14;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  ctx.save();
  ctx.translate(128, 128);
  ctx.rotate(-Math.PI / 2);
  ctx.translate(-128, -128);

  if (type === "mic") {
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(102, 50, 52, 88, 26);
    } else {
      ctx.rect(102, 50, 52, 88);
    }
    ctx.fill();

    ctx.beginPath();
    ctx.arc(128, 118, 44, 0, Math.PI);
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(128, 162);
    ctx.lineTo(128, 196);
    ctx.moveTo(96, 196);
    ctx.lineTo(160, 196);
    ctx.stroke();
  } else if (type === "star") {
    ctx.save();
    ctx.translate(128, 128);
    ctx.beginPath();
    const spikes = 5;
    const outerRadius = 72;
    const innerRadius = 36;
    let rot = (Math.PI / 2) * 3;
    const step = Math.PI / spikes;

    ctx.moveTo(0, -outerRadius);
    for (let i = 0; i < spikes; i++) {
      ctx.lineTo(Math.cos(rot) * outerRadius, Math.sin(rot) * outerRadius);
      rot += step;
      ctx.lineTo(Math.cos(rot) * innerRadius, Math.sin(rot) * innerRadius);
      rot += step;
    }
    ctx.lineTo(0, -outerRadius);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  } else if (type === "summary") {
    ctx.beginPath();
    ctx.moveTo(86, 76);
    ctx.lineTo(184, 76);
    ctx.moveTo(86, 116);
    ctx.lineTo(184, 116);
    ctx.moveTo(86, 156);
    ctx.lineTo(156, 156);
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(66, 76, 8, 0, Math.PI * 2);
    ctx.arc(66, 116, 8, 0, Math.PI * 2);
    ctx.arc(66, 156, 8, 0, Math.PI * 2);
    ctx.fill();
  } else if (type === "braille") {
    const dotRadius = 14;
    const xCell1 = [68, 108];
    const xCell2 = [148, 188];
    const yRows = [76, 128, 180];

    for (let c of xCell1) {
      for (let r of yRows) {
        ctx.beginPath();
        ctx.arc(c, r, dotRadius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    for (let c of xCell2) {
      for (let r of yRows) {
        ctx.beginPath();
        ctx.arc(c, r, dotRadius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  } else if (type === "speaker") {
    ctx.lineWidth = 8;
    for (let r = 24; r <= 104; r += 26) {
      ctx.beginPath();
      ctx.arc(128, 128, r, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(128, 128, 12, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.restore();
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

class TactileAudio {
  constructor() {
    this.ctx = null;
  }
  _init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) this.ctx = new AudioCtx();
    }
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }
  play(type = "mechanical") {
    try {
      this._init();
      if (!this.ctx) return;
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      const t = this.ctx.currentTime;

      if (type === "heavy") {
        osc.frequency.setValueAtTime(160, t);
        osc.frequency.exponentialRampToValueAtTime(50, t + 0.08);
        gain.gain.setValueAtTime(0.28, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.08);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + 0.08);
      } else if (type === "notebook") {
        osc.type = "sine";
        osc.frequency.setValueAtTime(523.25, t);
        osc.frequency.setValueAtTime(783.99, t + 0.06);
        gain.gain.setValueAtTime(0.2, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.22);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + 0.22);
      } else if (type === "braille") {
        osc.frequency.setValueAtTime(800, t);
        osc.frequency.setValueAtTime(1200, t + 0.03);
        gain.gain.setValueAtTime(0.18, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.08);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + 0.08);
      } else {
        osc.frequency.setValueAtTime(440, t);
        osc.frequency.exponentialRampToValueAtTime(100, t + 0.04);
        gain.gain.setValueAtTime(0.18, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.04);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(t);
        osc.stop(t + 0.04);
      }
    } catch (_) {}
  }
}

export const HARDWARE_PARTS_INFO = {
  btn_ptt: {
    id: "btn_ptt",
    name: "PTT / Microphone Button (Push-to-Talk)",
    badge: "Voice Input · 16kHz PCM",
    codeRef: "apu/ui/live/pipeline.py ➔ process_turn()",
    desc: "Oversized central button with high-relief concentric rings and embossed microphone icon. Pressing it streams 16kHz PCM audio over WebSocket (/ws/eleven_english_sts_v2 or /ws/gemini-3.5-transcribe-live) for real-time speech-to-text, topical guardrail verification, and Socratic tutoring.",
    sound: "heavy",
    targetPos: new THREE.Vector3(0, -0.15, 0.2),
  },
  btn_notebook: {
    id: "btn_notebook",
    name: "Notebook Button (Save to Notebook)",
    badge: "Memory Persistence · SQLite",
    codeRef: "apu/ui/live/intents.py ➔ handle_save_notebook()",
    desc: "Amber star button embossed with a star icon and Braille letter 'N' (⠝). Pressing this button immediately persists the preceding tutor explanation or lesson takeaway directly into the student's SQLite revision notebook (data/notebook.sqlite3).",
    sound: "notebook",
    targetPos: new THREE.Vector3(0.42, -0.15, 0.2),
  },
  btn_summary: {
    id: "btn_summary",
    name: "Summary Button (Notebook Recap)",
    badge: "Spoken Revision · Notes",
    codeRef: "apu/ui/live/intents.py ➔ handle_summary_notebook()",
    desc: "Emerald grooved button embossed with document list icon. Triggers a synthesized vocal summary of all lesson points recorded in the student's notebook for the active subject, enabling quick auditory review without a screen.",
    sound: "mechanical",
    targetPos: new THREE.Vector3(-0.42, -0.15, 0.2),
  },
  btn_braille: {
    id: "btn_braille",
    name: "Braille Button (Grade 1 & 2 Format)",
    badge: "Accessibility · liblouis",
    codeRef: "apu/ui/live/intents.py ➔ compute_braille()",
    desc: "Tactile button embossed with raised Braille dots. Converts the tutor's latest response into Grade 1 (uncontracted) and Grade 2 (contracted) Braille via liblouis, dispatching it to the connected refreshable Braille display.",
    sound: "braille",
    targetPos: new THREE.Vector3(0, -0.55, 0.2),
  },
  port_usbc: {
    id: "port_usbc",
    name: "USB Type-C Port (Power & Data)",
    badge: "Power & Fast Charge 20W PD",
    codeRef: "Hardware ➔ Battery & USB-PD Charging",
    desc: "Reversible USB Type-C charging port with a tactile beveled guide funnel for easy non-visual cable insertion. Delivers 18 hours of voice tutoring autonomy with 55-minute fast charging.",
    sound: "mechanical",
    targetPos: new THREE.Vector3(0, -1.18, 0),
  },
  port_jack: {
    id: "port_jack",
    name: "3.5mm Headphone Jack (Audio Out)",
    badge: "Stereo Voice DAC",
    codeRef: "apu/modality/voice.py ➔ Audio DAC",
    desc: "Standard 3.5mm TRRS gold-plated audio socket with chamfered lead-in rim for standard headphones or bone-conduction headsets, allowing private tutoring in noisy school environments.",
    sound: "mechanical",
    targetPos: new THREE.Vector3(-0.44, -1.18, 0),
  },
  port_braille: {
    id: "port_braille",
    name: "Braille Display Connector (14-pin Magnetic Dock)",
    badge: "Assistive Peripheral Dock",
    codeRef: "apu/modality/braille/ ➔ HID Braille Protocol",
    desc: "Magnetic alignment multi-pin dock port on the bottom edge. Snaps directly onto portable refreshable Braille displays (Orbit Reader 20, HumanWare Brailliant, Focus 14) to stream tactile braille under the student's fingertips.",
    sound: "mechanical",
    targetPos: new THREE.Vector3(0.44, -1.18, 0),
  },
  volume_wheel: {
    id: "volume_wheel",
    name: "Tactile Knurled Volume Wheel",
    badge: "Analog Control · Rotary",
    codeRef: "Hardware ➔ Audio Gain Potentiometer",
    desc: "Textured aluminum thumbwheel with 24 tactile detents located naturally under the right thumb. Allows instant tactile volume adjustments without navigating screen menus.",
    sound: "mechanical",
    targetPos: new THREE.Vector3(0.72, 0.15, 0),
  },
  speaker_grille: {
    id: "speaker_grille",
    name: "Front Acoustic Speaker Grille",
    badge: "Voice Projection · 40mm Neodymium",
    codeRef: "apu/ui/live/pipeline.py ➔ synthesize_and_send()",
    desc: "Circular micro-mesh acoustic grille tuned specifically for speech frequencies (300 Hz - 7 kHz), providing crisp vocal clarity for pedagogical dialogue.",
    sound: "mechanical",
    targetPos: new THREE.Vector3(0, 0.52, 0.2),
  }
};

const SHOTS = {
  stage: { pos: new THREE.Vector3(0, 0.2, 4.2), look: new THREE.Vector3(0, -0.05, 0) },
  controls: { pos: new THREE.Vector3(0, 0.05, 3.2), look: new THREE.Vector3(0, -0.15, 0.1) },
  ports: { pos: new THREE.Vector3(0, -1.0, 2.7), look: new THREE.Vector3(0, -0.9, 0) },
  inhand: { pos: new THREE.Vector3(-0.4, 0.4, 3.7), look: new THREE.Vector3(0, 0, 0) }
};

export class KeynoteHardware3D {
  constructor(containerEl, onActionTriggered, onPartSelected) {
    this.container = containerEl;
    this.onActionTriggered = onActionTriggered || (() => {});
    this.onPartSelected = onPartSelected || (() => {});

    this.scene = new THREE.Scene();
    const w = this.container.clientWidth || 800;
    const h = this.container.clientHeight || 450;
    this.camera = new THREE.PerspectiveCamera(34, w / h, 0.1, 100);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    this.controls = null;
    this.audio = new TactileAudio();

    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
    this.deviceGroup = new THREE.Group();
    this.interactiveMeshes = [];
    this.activePartId = "btn_ptt";
    this.buttonStates = {
      btn_ptt: false,
      btn_notebook: false,
      btn_summary: false,
      btn_braille: false,
    };

    this.targetCamPos = new THREE.Vector3().copy(SHOTS.stage.pos);
    this.targetLookAt = new THREE.Vector3().copy(SHOTS.stage.look);

    this.isNearDevice = false;

    // CSS cannot reach inside a WebGL canvas, so the stylesheet's reduced-motion rules
    // stop the page animating and left the device floating and the keys pulsing. This is
    // the same preference, read where the animation actually lives.
    this.reducedMotion = window.matchMedia
      ? window.matchMedia("(prefers-reduced-motion: reduce)")
      : { matches: false };

    this._init();
  }

  _init() {
    const w = this.container.clientWidth || 800;
    const h = this.container.clientHeight || 450;
    this.renderer.setSize(w, h);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;

    this.container.appendChild(this.renderer.domElement);

    this.camera.position.copy(SHOTS.stage.pos);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 1.6;
    this.controls.maxDistance = 8.0;
    this.controls.target.copy(SHOTS.stage.look);

    this._setupLighting();
    this._setupEnvironment();
    this._buildModel();
    this._setupProximityAndClickEvents();

    // The capsule changes size without the window changing size: collapsing the side
    // panels does it. A canvas that kept its old size still rendered, so the pointer and
    // the picture disagreed about where a key was and presses landed next to it.
    if (window.ResizeObserver) {
      this.resizeObserver = new ResizeObserver(() => this._onResize());
      this.resizeObserver.observe(this.container);
    } else {
      window.addEventListener("resize", () => this._onResize());
    }
    setTimeout(() => this._onResize(), 100);

    this._animate();
  }

  _setupLighting() {
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.6));

    const key = new THREE.DirectionalLight(0xffffff, 1.8);
    key.position.set(2.5, 4, 3.5);
    key.castShadow = true;
    key.shadow.mapSize.width = 1024;
    key.shadow.mapSize.height = 1024;
    key.shadow.bias = -0.0005;
    this.scene.add(key);

    const rimCool = new THREE.DirectionalLight(0x94a3b8, 1.1);
    rimCool.position.set(-3, 1, -2);
    this.scene.add(rimCool);

    const rimWarm = new THREE.DirectionalLight(0x64748b, 0.8);
    rimWarm.position.set(3, 0.5, -2.5);
    this.scene.add(rimWarm);

    const bounce = new THREE.DirectionalLight(0xd97706, 0.4);
    bounce.position.set(0, -3, 2);
    this.scene.add(bounce);
  }

  _setupEnvironment() {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 512;
      canvas.height = 256;
      const ctx = canvas.getContext("2d");

      const sky = ctx.createLinearGradient(0, 0, 0, 256);
      sky.addColorStop(0, "#cbd5e1");
      sky.addColorStop(0.4, "#334155");
      sky.addColorStop(0.6, "#0f172a");
      sky.addColorStop(1, "#020617");
      ctx.fillStyle = sky;
      ctx.fillRect(0, 0, 512, 256);

      const panel = ctx.createRadialGradient(140, 96, 10, 140, 96, 150);
      panel.addColorStop(0, "rgba(255,255,255,0.9)");
      panel.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = panel;
      ctx.fillRect(0, 0, 512, 256);

      const cool = ctx.createRadialGradient(400, 120, 8, 400, 120, 130);
      cool.addColorStop(0, "rgba(56,189,248,0.6)");
      cool.addColorStop(1, "rgba(56,189,248,0)");
      ctx.fillStyle = cool;
      ctx.fillRect(0, 0, 512, 256);

      const equirect = new THREE.CanvasTexture(canvas);
      equirect.mapping = THREE.EquirectangularReflectionMapping;
      equirect.colorSpace = THREE.SRGBColorSpace;

      const pmrem = new THREE.PMREMGenerator(this.renderer);
      this.scene.environment = pmrem.fromEquirectangular(equirect).texture;
      pmrem.dispose();
    } catch (e) {
      console.warn("PMREM environment notice:", e);
    }
  }

  _buildModel() {
    this.scene.add(this.deviceGroup);
    this.deviceGroup.position.set(0, -0.15, 0);
    this.deviceGroup.rotation.x = 0.1;
    this.deviceGroup.scale.set(0.82, 0.82, 0.82);

    this.matChassis = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.32,
      metalness: 0.65,
      envMapIntensity: 1.4
    });

    this.matGrip = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      roughness: 0.88,
      metalness: 0.05,
      envMapIntensity: 0.4
    });

    this.matBezel = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      roughness: 0.28,
      metalness: 0.85,
      envMapIntensity: 1.6
    });

    this.matButtonRim = new THREE.MeshStandardMaterial({
      color: 0x334155,
      roughness: 0.22,
      metalness: 0.9,
      envMapIntensity: 2.0
    });

    this.matMetal = new THREE.MeshStandardMaterial({
      color: 0x94a3b8,
      roughness: 0.18,
      metalness: 0.92,
      envMapIntensity: 1.9
    });

    this.matGold = new THREE.MeshStandardMaterial({
      color: 0xd97706,
      roughness: 0.25,
      metalness: 0.8
    });

    // 1. Chassis
    const shape = new THREE.Shape();
    const w = 0.68;
    const h = 1.12;
    const r = 0.16;

    shape.absarc(-w + r, -h + r, r, Math.PI, 1.5 * Math.PI, true);
    shape.absarc(w - r, -h + r, r, 1.5 * Math.PI, 2 * Math.PI, true);
    shape.absarc(w - r, h - r, r, 0, 0.5 * Math.PI, true);
    shape.absarc(-w + r, h - r, r, 0.5 * Math.PI, Math.PI, true);

    const casingGeo = new THREE.ExtrudeGeometry(shape, {
      depth: 0.32,
      bevelEnabled: true,
      bevelSegments: 8,
      steps: 1,
      bevelSize: 0.04,
      bevelThickness: 0.04
    });
    casingGeo.center();
    const casingMesh = new THREE.Mesh(casingGeo, this.matChassis);
    casingMesh.castShadow = true;
    casingMesh.receiveShadow = true;
    this.deviceGroup.add(casingMesh);

    // 2. Tactile Side Grips
    const createSideGrip = (x) => {
      const g = new THREE.Group();
      g.position.set(x, 0, 0);
      const base = new THREE.Mesh(new THREE.BoxGeometry(0.05, 1.5, 0.26), this.matGrip);
      g.add(base);
      for (let i = -5; i <= 5; i++) {
        const rib = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.03, 0.28), this.matBezel);
        rib.position.y = i * 0.13;
        g.add(rib);
      }
      return g;
    };
    this.deviceGroup.add(createSideGrip(-0.7));
    this.deviceGroup.add(createSideGrip(0.7));

    // 3. Front Face Recessed Bezel Plate
    const frontPlate = new THREE.Mesh(new THREE.BoxGeometry(1.22, 2.08, 0.02), this.matBezel);
    frontPlate.position.set(0, 0, 0.18);
    this.deviceGroup.add(frontPlate);

    // 4. Acoustic Speaker Grille
    const speakerG = new THREE.Group();
    speakerG.position.set(0, 0.52, 0.19);
    const speakerTex = createButtonIconTexture("speaker", "#090d16", "#38bdf8", "#0284c7");
    const speakerMat = new THREE.MeshStandardMaterial({ map: speakerTex, roughness: 0.5, metalness: 0.3 });
    const speakerMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.025, 32), speakerMat);
    speakerMesh.rotateX(Math.PI / 2);
    speakerMesh.userData = { partId: "speaker_grille" };
    speakerG.userData = { partId: "speaker_grille" };
    speakerG.add(speakerMesh);
    this.interactiveMeshes.push(speakerMesh);
    this.deviceGroup.add(speakerG);

    // 5. PTT / MICROPHONE BUTTON (Center) - Deep royal cobalt at stop, ruby crimson when active
    const pttG = new THREE.Group();
    pttG.position.set(0, -0.15, 0.19);

    const pttRim = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.33, 0.03, 32), this.matButtonRim);
    pttRim.rotateX(Math.PI / 2);
    pttRim.userData = { partId: "btn_ptt" };
    pttG.add(pttRim);

    this.texMicBlue = createButtonIconTexture("mic", "#172554", "#ffffff", "#3b82f6");
    this.texMicRed = createButtonIconTexture("mic", "#7f1d1d", "#ffffff", "#ef4444");

    const matPttWithIcon = new THREE.MeshStandardMaterial({
      map: this.texMicBlue,
      roughness: 0.35,
      metalness: 0.12,
      emissive: 0x172554,
      emissiveIntensity: 0.35,
    });

    this.meshPttBtn = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.06, 32), matPttWithIcon);
    this.meshPttBtn.rotateX(Math.PI / 2);
    this.meshPttBtn.position.z = 0.025;
    this.meshPttBtn.userData = { partId: "btn_ptt" };
    pttG.add(this.meshPttBtn);

    const pttRing = new THREE.Mesh(new THREE.TorusGeometry(0.285, 0.015, 8, 28), this.matMetal);
    pttRing.position.z = 0.055;
    pttRing.userData = { partId: "btn_ptt" };
    pttG.add(pttRing);

    pttG.userData = { partId: "btn_ptt" };
    this.interactiveMeshes.push(this.meshPttBtn, pttRim, pttRing);
    this._addHitTarget(pttG, "btn_ptt", 0.37);
    this.deviceGroup.add(pttG);

    // 6. NOTEBOOK BUTTON (Right) - Deep golden amber bronze
    const noteG = new THREE.Group();
    noteG.position.set(0.42, -0.15, 0.19);
    const noteRim = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.025, 24), this.matButtonRim);
    noteRim.rotateX(Math.PI / 2);
    noteRim.userData = { partId: "btn_notebook" };
    noteG.add(noteRim);

    const starTex = createButtonIconTexture("star", "#78350f", "#ffffff", "#f59e0b");
    const matStar = new THREE.MeshStandardMaterial({
      map: starTex,
      roughness: 0.35,
      metalness: 0.12,
      emissive: 0x451a03,
      emissiveIntensity: 0.3
    });
    this.meshNoteBtn = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 0.055, 24), matStar);
    this.meshNoteBtn.rotateX(Math.PI / 2);
    this.meshNoteBtn.position.z = 0.025;
    this.meshNoteBtn.userData = { partId: "btn_notebook" };
    noteG.add(this.meshNoteBtn);
    noteG.userData = { partId: "btn_notebook" };
    this.interactiveMeshes.push(this.meshNoteBtn, noteRim);
    this._addHitTarget(noteG, "btn_notebook", 0.3);
    this.deviceGroup.add(noteG);

    // 7. SUMMARY BUTTON (Left) - Deep forest emerald
    const sumG = new THREE.Group();
    sumG.position.set(-0.42, -0.15, 0.19);
    const sumRim = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.025, 24), this.matButtonRim);
    sumRim.rotateX(Math.PI / 2);
    sumRim.userData = { partId: "btn_summary" };
    sumG.add(sumRim);

    const sumTex = createButtonIconTexture("summary", "#064e3b", "#ffffff", "#10b981");
    const matSum = new THREE.MeshStandardMaterial({
      map: sumTex,
      roughness: 0.35,
      metalness: 0.12,
      emissive: 0x022c22,
      emissiveIntensity: 0.3
    });
    this.meshSumBtn = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 0.055, 24), matSum);
    this.meshSumBtn.rotateX(Math.PI / 2);
    this.meshSumBtn.position.z = 0.025;
    this.meshSumBtn.userData = { partId: "btn_summary" };
    sumG.add(this.meshSumBtn);
    sumG.userData = { partId: "btn_summary" };
    this.interactiveMeshes.push(this.meshSumBtn, sumRim);
    this._addHitTarget(sumG, "btn_summary", 0.3);
    this.deviceGroup.add(sumG);

    // 8. BRAILLE BUTTON (Below PTT) - Deep royal violet purple
    const brailleG = new THREE.Group();
    brailleG.position.set(0, -0.74, 0.19);
    const brailleRim = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.22, 0.025), this.matButtonRim);
    brailleRim.userData = { partId: "btn_braille" };
    brailleG.add(brailleRim);

    const brailleTex = createButtonIconTexture("braille", "#3b0764", "#ffffff", "#a855f7");
    const matBraille = new THREE.MeshStandardMaterial({
      map: brailleTex,
      roughness: 0.35,
      metalness: 0.12,
      emissive: 0x2e1065,
      emissiveIntensity: 0.3
    });
    this.meshBrailleBtn = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.17, 0.055), matBraille);
    this.meshBrailleBtn.position.z = 0.025;
    this.meshBrailleBtn.userData = { partId: "btn_braille" };
    brailleG.add(this.meshBrailleBtn);
    brailleG.userData = { partId: "btn_braille" };
    this.interactiveMeshes.push(this.meshBrailleBtn, brailleRim);
    this._addHitTarget(brailleG, "btn_braille", 0.34);
    this.deviceGroup.add(brailleG);

    // 9. BOTTOM EDGE PORTS
    const bottomG = new THREE.Group();
    bottomG.position.set(0, -1.14, 0);

    const jackOuter = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, 0.1, 24), this.matBezel);
    jackOuter.position.x = -0.44;
    jackOuter.userData = { partId: "port_jack" };
    bottomG.add(jackOuter);
    const jackHit = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 0.3), new THREE.MeshBasicMaterial({ visible: false }));
    jackHit.position.x = -0.44;
    jackHit.userData = { partId: "port_jack" };
    bottomG.add(jackHit);
    this.interactiveMeshes.push(jackOuter, jackHit);

    const usbcBezel = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.1, 0.18), this.matBezel);
    usbcBezel.userData = { partId: "port_usbc" };
    bottomG.add(usbcBezel);
    const usbcHit = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.3, 0.3), new THREE.MeshBasicMaterial({ visible: false }));
    usbcHit.userData = { partId: "port_usbc" };
    bottomG.add(usbcHit);
    this.interactiveMeshes.push(usbcBezel, usbcHit);

    const brailleDock = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.1, 0.2), this.matGold);
    brailleDock.position.x = 0.44;
    brailleDock.userData = { partId: "port_braille" };
    bottomG.add(brailleDock);
    const brailleHit = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.3, 0.3), new THREE.MeshBasicMaterial({ visible: false }));
    brailleHit.position.x = 0.44;
    brailleHit.userData = { partId: "port_braille" };
    bottomG.add(brailleHit);
    this.interactiveMeshes.push(brailleDock, brailleHit);

    this.deviceGroup.add(bottomG);

    // 10. Volume Thumbwheel
    const wheelG = new THREE.Group();
    wheelG.position.set(0.69, 0.15, 0);
    const wheelMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.26, 24), this.matMetal);
    wheelMesh.rotateZ(Math.PI / 2);
    wheelMesh.userData = { partId: "volume_wheel" };
    wheelG.add(wheelMesh);
    wheelG.userData = { partId: "volume_wheel" };
    this.interactiveMeshes.push(wheelMesh);
    this.deviceGroup.add(wheelG);

    // 11. Top Edge Mics & Loop
    const mic1 = new THREE.Mesh(new THREE.CylinderGeometry(0.024, 0.024, 0.08, 12), this.matMetal);
    mic1.position.set(-0.35, 1.15, 0);
    this.deviceGroup.add(mic1);
    const mic2 = new THREE.Mesh(new THREE.CylinderGeometry(0.024, 0.024, 0.08, 12), this.matMetal);
    mic2.position.set(0.35, 1.15, 0);
    this.deviceGroup.add(mic2);

    // Pedestal Glow Ring underneath device
    const glowRing = new THREE.Mesh(
      new THREE.RingGeometry(0.7, 1.4, 32),
      new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0.25,
        side: THREE.DoubleSide
      })
    );
    glowRing.rotation.x = -Math.PI / 2;
    glowRing.position.set(0, -1.3, 0);
    this.scene.add(glowRing);
  }


  /**
   * An invisible disc in front of a button, wider than the button itself.
   *
   * The visible keys are 28 to 49 pixels across on screen and the device breathes, so
   * aiming at the moulded shape alone is a game of patience. The target a pointer has to
   * find is this disc; what the eye aims at stays the key.
   */
  _addHitTarget(group, partId, radius) {
    const target = new THREE.Mesh(
      new THREE.CylinderGeometry(radius, radius, 0.12, 20),
      new THREE.MeshBasicMaterial({ visible: false })
    );
    target.rotateX(Math.PI / 2);
    target.position.z = 0.08;
    target.userData = { partId };
    group.add(target);
    this.interactiveMeshes.push(target);
    return target;
  }

  _setupProximityAndClickEvents() {
    const el = this.renderer.domElement;

    // Track proximity and hover over buttons
    window.addEventListener("pointermove", (e) => {
      const rect = el.getBoundingClientRect();
      const isInsideOrNear = (
        e.clientX >= rect.left - 50 &&
        e.clientX <= rect.right + 50 &&
        e.clientY >= rect.top - 50 &&
        e.clientY <= rect.bottom + 50
      );

      if (isInsideOrNear !== this.isNearDevice) {
        this.isNearDevice = isInsideOrNear;
        if (this.isNearDevice) {
          document.body.classList.add("tactile-hand-cursor");
          el.classList.add("cursor-hand");
        } else {
          document.body.classList.remove("tactile-hand-cursor");
          el.classList.remove("cursor-hand");
        }
      }

      // Check hover over interactive button meshes
      if (isInsideOrNear) {
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        this.raycaster.setFromCamera(this.mouse, this.camera);
        const hits = this.raycaster.intersectObjects(this.interactiveMeshes, true);
        if (hits.length > 0) {
          el.style.cursor = "pointer";
        } else if (this.isNearDevice) {
          el.style.cursor = "grab";
        }
      }
    });

    // Handle clicks and pointerdown on 3D elements
    const handleActionClick = (event) => {
      const rect = el.getBoundingClientRect();
      this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

      this.raycaster.setFromCamera(this.mouse, this.camera);
      const intersects = this.raycaster.intersectObjects(this.interactiveMeshes, true);

      const partId = this._partUnderRay(intersects);
      if (partId) {
        event.stopPropagation();
        this.triggerPress(partId, event.clientX, event.clientY);
      }
    };

    el.addEventListener("pointerdown", handleActionClick);
  }

  /**
   * Which key a ray that crossed several of them was aimed at.
   *
   * The aiming discs are deliberately wider than the keys, so near a key they overlap. It
   * used to be the first crossing that won, which is the nearest surface and not the
   * nearest key: pressing braille, under a microphone disc that reached past it, pressed
   * the microphone. The key whose centre the ray passes closest to is the one meant.
   */
  _partUnderRay(intersects) {
    let best = null;
    let bestDistance = Infinity;

    for (const hit of intersects) {
      let obj = hit.object;
      while (obj && !obj.userData?.partId && obj.parent) {
        obj = obj.parent;
      }
      const partId = obj?.userData?.partId;
      if (!partId || !HARDWARE_PARTS_INFO[partId]) continue;

      const centre = new THREE.Vector3();
      obj.getWorldPosition(centre);
      const distance = centre.distanceTo(hit.point);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = partId;
      }
    }
    return best;
  }

  setButtonInUse(partId, inUse) {
    this.buttonStates[partId] = Boolean(inUse);

    if (partId === "btn_ptt" && this.meshPttBtn) {
      this.meshPttBtn.position.z = inUse ? 0.005 : 0.025;
      this.meshPttBtn.material.map = inUse ? this.texMicRed : this.texMicBlue;
      this.meshPttBtn.material.emissive = new THREE.Color(inUse ? 0xdc2626 : 0x172554);
      this.meshPttBtn.material.emissiveIntensity = inUse ? 1.5 : 0.35;
      this.meshPttBtn.material.needsUpdate = true;
    } else if (partId === "btn_notebook" && this.meshNoteBtn) {
      this.meshNoteBtn.position.z = inUse ? 0.005 : 0.025;
      this.meshNoteBtn.material.emissive = new THREE.Color(inUse ? 0xd97706 : 0x451a03);
      this.meshNoteBtn.material.emissiveIntensity = inUse ? 1.5 : 0.3;
    } else if (partId === "btn_summary" && this.meshSumBtn) {
      this.meshSumBtn.position.z = inUse ? 0.005 : 0.025;
      this.meshSumBtn.material.emissive = new THREE.Color(inUse ? 0x059669 : 0x022c22);
      this.meshSumBtn.material.emissiveIntensity = inUse ? 1.5 : 0.3;
    } else if (partId === "btn_braille" && this.meshBrailleBtn) {
      this.meshBrailleBtn.position.z = inUse ? 0.005 : 0.025;
      this.meshBrailleBtn.material.emissive = new THREE.Color(inUse ? 0x7c3aed : 0x2e1065);
      this.meshBrailleBtn.material.emissiveIntensity = inUse ? 1.5 : 0.3;
    }
  }

  triggerPress(partId, screenX, screenY) {
    const info = HARDWARE_PARTS_INFO[partId];
    if (!info) return;

    this.activePartId = partId;
    this.audio.play(info.sound || "mechanical");

    this._spawnShockwave(partId, screenX, screenY);
    this.onPartSelected(partId, info);
    this.onActionTriggered(partId, info);
  }

  _spawnShockwave(partId, screenX, screenY) {
    let x = screenX;
    let y = screenY;

    if (x === undefined || y === undefined) {
      const info = HARDWARE_PARTS_INFO[partId];
      if (info && info.targetPos) {
        const worldPos = info.targetPos.clone();
        this.deviceGroup.localToWorld(worldPos);
        const projected = worldPos.project(this.camera);
        const rect = this.renderer.domElement.getBoundingClientRect();
        x = rect.left + ((projected.x + 1) / 2) * rect.width;
        y = rect.top + ((-projected.y + 1) / 2) * rect.height;
      }
    }

    if (x === undefined || y === undefined) return;

    const ripple = document.createElement("div");
    ripple.className = "tactile-shockwave-halo";
    ripple.style.left = `${x}px`;
    ripple.style.top = `${y}px`;

    let color = "#ffffff";
    if (partId === "btn_ptt") color = "#ef4444";
    else if (partId === "btn_notebook") color = "#f59e0b";
    else if (partId === "btn_summary") color = "#10b981";
    else if (partId === "btn_braille") color = "#a855f7";

    ripple.style.setProperty("--ripple-color", color);
    document.body.appendChild(ripple);

    setTimeout(() => {
      ripple.remove();
    }, 700);
  }

  setShot(name) {
    const shot = SHOTS[name];
    if (!shot) return;
    this.targetCamPos.copy(shot.pos);
    this.targetLookAt.copy(shot.look);
  }

  _onResize() {
    if (!this.container) return;
    const w = this.container.clientWidth;
    const h = this.container.clientHeight;
    if (w > 0 && h > 0) {
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w, h);
    }
  }

  _animate() {
    requestAnimationFrame(() => this._animate());

    this.camera.position.lerp(this.targetCamPos, 0.05);
    this.controls.target.lerp(this.targetLookAt, 0.05);
    this.controls.update();

    const t = performance.now() * 0.0015;
    const still = this.reducedMotion.matches;
    // The float is a presentation flourish, and it moves every key by six pixels. It
    // settles as soon as a pointer comes near, so nobody has to aim at a moving target.
    const drift = (this.isNearDevice || still) ? 0 : Math.sin(t) * 0.015;
    this.deviceGroup.position.y += (-0.15 + drift - this.deviceGroup.position.y) * 0.08;

    // A key in use glows. It pulses unless the viewer asked for less motion, in which
    // case it stays bright: the state is the information, the throb is decoration.
    const glow = still ? 1.4 : 1.0 + 0.45 * Math.sin(t * 8);
    const inUse = [
      [this.buttonStates.btn_ptt, this.meshPttBtn],
      [this.buttonStates.btn_notebook, this.meshNoteBtn],
      [this.buttonStates.btn_summary, this.meshSumBtn],
      [this.buttonStates.btn_braille, this.meshBrailleBtn],
    ];
    for (const [isOn, mesh] of inUse) {
      if (isOn && mesh) mesh.material.emissiveIntensity = glow;
    }

    this.renderer.render(this.scene, this.camera);
  }
}
