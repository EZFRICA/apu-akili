/**
 * viewer.js - Compact 3D Hardware Studio for APU Akili Tactile Voice Companion
 * Form Factor: Handheld Pocket Dictaphone / Tape-Recorder format
 * Direct Mapping: All buttons are explicitly linked to apu.ui.live backend functions.
 * Icons: Rendered directly on the 3D buttons using high-res dynamic canvas textures.
 * Language: English
 */

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// ==============================================================================
// 1. Dynamic Canvas Texture Generators for 3D Button Icons
// ==============================================================================
function createButtonIconTexture(type, bg = "#dc2626", fg = "#ffffff") {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");

  // Background circle
  ctx.fillStyle = bg;
  ctx.beginPath();
  ctx.arc(128, 128, 124, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = fg;
  ctx.strokeStyle = fg;
  ctx.lineWidth = 14;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  // Rotate canvas by -90 deg so that 2D drawing aligns upright on the Three.js mesh
  ctx.save();
  ctx.translate(128, 128);
  ctx.rotate(-Math.PI / 2);
  ctx.translate(-128, -128);

  if (type === "mic") {
    // Microphone body / capsule
    ctx.beginPath();
    if (ctx.roundRect) {
      ctx.roundRect(102, 50, 52, 88, 26);
    } else {
      ctx.rect(102, 50, 52, 88);
    }
    ctx.fill();

    // Mic cradle
    ctx.beginPath();
    ctx.arc(128, 118, 44, 0, Math.PI);
    ctx.stroke();

    // Stem and base
    ctx.beginPath();
    ctx.moveTo(128, 162);
    ctx.lineTo(128, 196);
    ctx.moveTo(96, 196);
    ctx.lineTo(160, 196);
    ctx.stroke();
  } else if (type === "star") {
    // Star / Bookmark icon
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
    // Document / Notes list icon
    ctx.beginPath();
    ctx.moveTo(86, 76);
    ctx.lineTo(184, 76);
    ctx.moveTo(86, 116);
    ctx.lineTo(184, 116);
    ctx.moveTo(86, 156);
    ctx.lineTo(156, 156);
    ctx.stroke();

    // Small dot bullets
    ctx.beginPath();
    ctx.arc(66, 76, 8, 0, Math.PI * 2);
    ctx.arc(66, 116, 8, 0, Math.PI * 2);
    ctx.arc(66, 156, 8, 0, Math.PI * 2);
    ctx.fill();
  } else if (type === "braille") {
    // Two authentic 6-dot Braille cells side-by-side (Grade 1 & Grade 2 format)
    const dotRadius = 14;
    const xCell1 = [68, 108];
    const xCell2 = [148, 188];
    const yRows = [76, 128, 180];

    // Left Cell (dots 1, 2 = letter 'B')
    for (let c of xCell1) {
      for (let r of yRows) {
        ctx.beginPath();
        ctx.arc(c, r, dotRadius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    // Right Cell
    for (let c of xCell2) {
      for (let r of yRows) {
        ctx.beginPath();
        ctx.arc(c, r, dotRadius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  } else if (type === "speaker") {
    // Speaker concentric acoustic ring pattern
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
  texture.anisotropy = 8;
  return texture;
}

// ==============================================================================
// 2. Web Audio Haptic & Click Synthesizer
// ==============================================================================
class TactileAudioEngine {
  constructor() {
    this.ctx = null;
    this.muted = false;
  }

  _init() {
    if (!this.ctx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AudioContext();
    }
    if (this.ctx.state === "suspended") {
      this.ctx.resume();
    }
  }

  playClick(type = "mechanical") {
    if (this.muted) return;
    this._init();
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    const t = this.ctx.currentTime;

    if (type === "heavy") {
      // PTT Mic button press
      osc.frequency.setValueAtTime(160, t);
      osc.frequency.exponentialRampToValueAtTime(50, t + 0.07);
      gain.gain.setValueAtTime(0.25, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.07);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(t);
      osc.stop(t + 0.07);
    } else if (type === "notebook") {
      // Pleasant chime for saving note
      osc.type = "sine";
      osc.frequency.setValueAtTime(523.25, t); // C5
      osc.frequency.setValueAtTime(783.99, t + 0.06); // G5
      gain.gain.setValueAtTime(0.18, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.22);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(t);
      osc.stop(t + 0.22);
    } else if (type === "braille") {
      // Quick double tick
      osc.frequency.setValueAtTime(800, t);
      osc.frequency.setValueAtTime(1200, t + 0.03);
      gain.gain.setValueAtTime(0.15, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.08);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(t);
      osc.stop(t + 0.08);
    } else {
      // Standard tactile microswitch click
      osc.frequency.setValueAtTime(440, t);
      osc.frequency.exponentialRampToValueAtTime(100, t + 0.04);
      gain.gain.setValueAtTime(0.15, t);
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.04);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(t);
      osc.stop(t + 0.04);
    }
  }
}

const audio = new TactileAudioEngine();

// ==============================================================================
// 3. Hardware Controls Database (Mapped to apu.ui.live)
// ==============================================================================
const HARDWARE_PARTS = {
  btn_ptt: {
    id: "btn_ptt",
    name: "PTT / Microphone Button (Push-to-Talk)",
    badge: "Voice Input · 16kHz PCM",
    codeRef: "apu/ui/live/pipeline.py ➔ process_turn()",
    desc: "Oversized central button with high-relief concentric rings and embossed microphone icon. Pressing it streams 16kHz PCM audio over WebSocket (/ws/eleven_english_sts_v2 or /ws/gemini-3.5-transcribe-live) for real-time speech-to-text, topical guardrail verification, and Socratic tutoring.",
    actionTitle: "Test Push-to-Talk Speech Action",
    sound: "heavy",
    targetPos: new THREE.Vector3(0, -0.15, 0.2),
    camOffset: new THREE.Vector3(0, 0.1, 3.1)
  },
  btn_notebook: {
    id: "btn_notebook",
    name: "Notebook Button (Save to Notebook)",
    badge: "Memory Persistence · SQLite",
    codeRef: "apu/ui/live/intents.py ➔ handle_save_notebook()",
    desc: "Amber star button embossed with a star icon and Braille letter 'N' (⠝). Pressing this button immediately persists the preceding tutor explanation or lesson takeaway directly into the student's SQLite revision notebook (data/notebook.sqlite3).",
    actionTitle: "Test Save to Notebook Action",
    sound: "notebook",
    targetPos: new THREE.Vector3(0.42, -0.15, 0.2),
    camOffset: new THREE.Vector3(0.12, 0.1, 3.1)
  },
  btn_summary: {
    id: "btn_summary",
    name: "Summary Button (Notebook Recap)",
    badge: "Spoken Revision · Notes",
    codeRef: "apu/ui/live/intents.py ➔ handle_summary_notebook()",
    desc: "Emerald grooved button embossed with document list icon. Triggers a synthesized vocal summary of all lesson points recorded in the student's notebook for the active subject, enabling quick auditory review without a screen.",
    actionTitle: "Test Spoken Summary Action",
    sound: "mechanical",
    targetPos: new THREE.Vector3(-0.42, -0.15, 0.2),
    camOffset: new THREE.Vector3(-0.12, 0.1, 3.1)
  },
  btn_braille: {
    id: "btn_braille",
    name: "Braille Button (Grade 1 & 2 Format)",
    badge: "Accessibility · liblouis",
    codeRef: "apu/ui/live/intents.py ➔ compute_braille()",
    desc: "Tactile button embossed with raised Braille dots. Converts the tutor's latest response into Grade 1 (uncontracted) and Grade 2 (contracted) Braille via liblouis, dispatching it to the connected refreshable Braille display.",
    actionTitle: "Test Braille Translation Action",
    sound: "braille",
    targetPos: new THREE.Vector3(0, -0.55, 0.2),
    camOffset: new THREE.Vector3(0, -0.15, 3.1)
  },
  port_usbc: {
    id: "port_usbc",
    name: "USB Type-C Port (Power & Data)",
    badge: "Power & Fast Charge 20W PD",
    codeRef: "Hardware ➔ Battery & USB-PD Charging",
    desc: "Reversible USB Type-C charging port with a tactile beveled guide funnel for easy non-visual cable insertion. Delivers 18 hours of voice tutoring autonomy with 55-minute fast charging.",
    actionTitle: "Inspect USB Type-C Port",
    sound: "mechanical",
    targetPos: new THREE.Vector3(0, -1.18, 0),
    camOffset: new THREE.Vector3(0, -1.2, 2.5)
  },
  port_jack: {
    id: "port_jack",
    name: "3.5mm Headphone Jack (Audio Out)",
    badge: "Stereo Voice DAC",
    codeRef: "apu/modality/voice.py ➔ Audio DAC",
    desc: "Standard 3.5mm TRRS gold-plated audio socket with chamfered lead-in rim for standard headphones or bone-conduction headsets, allowing private tutoring in noisy school environments.",
    actionTitle: "Inspect 3.5mm Audio Jack",
    sound: "mechanical",
    targetPos: new THREE.Vector3(-0.44, -1.18, 0),
    camOffset: new THREE.Vector3(-0.25, -1.2, 2.5)
  },
  port_braille: {
    id: "port_braille",
    name: "Braille Display Connector (14-pin Magnetic Dock)",
    badge: "Assistive Peripheral Dock",
    codeRef: "apu/modality/braille/ ➔ HID Braille Protocol",
    desc: "Magnetic alignment multi-pin dock port on the bottom edge. Snaps directly onto portable refreshable Braille displays (Orbit Reader 20, HumanWare Brailliant, Focus 14) to stream tactile braille under the student's fingertips.",
    actionTitle: "Inspect Braille Connector",
    sound: "mechanical",
    targetPos: new THREE.Vector3(0.44, -1.18, 0),
    camOffset: new THREE.Vector3(0.25, -1.2, 2.5)
  },
  volume_wheel: {
    id: "volume_wheel",
    name: "Tactile Knurled Volume Wheel",
    badge: "Analog Control · Rotary",
    codeRef: "Hardware ➔ Audio Gain Potentiometer",
    desc: "Textured aluminum thumbwheel with 24 tactile detents located naturally under the right thumb. Allows instant tactile volume adjustments without navigating screen menus.",
    actionTitle: "Test Volume Thumbwheel",
    sound: "mechanical",
    targetPos: new THREE.Vector3(0.72, 0.15, 0),
    camOffset: new THREE.Vector3(0.9, 0.15, 2.7)
  },
  speaker_grille: {
    id: "speaker_grille",
    name: "Front Acoustic Speaker Grille",
    badge: "Voice Projection · 40mm Neodymium",
    codeRef: "apu/ui/live/pipeline.py ➔ synthesize_and_send()",
    desc: "Circular micro-mesh acoustic grille tuned specifically for speech frequencies (300 Hz - 7 kHz), providing crisp vocal clarity for pedagogical dialogue.",
    actionTitle: "Inspect Speaker Grille",
    sound: "mechanical",
    targetPos: new THREE.Vector3(0, 0.52, 0.2),
    camOffset: new THREE.Vector3(0, 0.35, 3.1)
  }
};

// ==============================================================================
// 4. Three.js Compact 3D Studio
// ==============================================================================
class HardwareStudio {
  constructor() {
    this.container = document.getElementById("canvas-container");
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(35, window.innerWidth / window.innerHeight, 0.1, 100);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    this.controls = null;
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();

    this.deviceGroup = new THREE.Group();
    this.interactiveMeshes = [];
    this.activePartId = "btn_ptt";

    // Shift device slightly right to center it between the left sidebar and right inspector card
    this.deviceGroup.position.set(0.08, 0.05, 0);

    // Camera target overview (generous distance so the entire device is in view)
    this.targetCamPos = new THREE.Vector3(0.08, 0.35, 3.5);
    this.targetLookAt = new THREE.Vector3(0.08, 0, 0);

    this._init();
  }

  _init() {
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.15;
    this.container.appendChild(this.renderer.domElement);

    // Initial camera position
    this.camera.position.set(0.4, 0.5, 3.6);

    // OrbitControls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.minDistance = 2.0;
    this.controls.maxDistance = 7.0;
    this.controls.target.set(0.08, 0, 0);

    this._setupLighting();
    this._buildCompactModel();

    window.addEventListener("resize", () => this._onResize());
    this.renderer.domElement.addEventListener("pointerdown", (e) => this._onPointerDown(e));

    this._bindUi();
    this._selectPart("btn_ptt", false);

    this._animate();
  }

  _setupLighting() {
    const amb = new THREE.AmbientLight(0xffffff, 0.9);
    this.scene.add(amb);

    const key = new THREE.DirectionalLight(0xffffff, 2.0);
    key.position.set(3, 5, 4);
    key.castShadow = true;
    key.shadow.mapSize.width = 2048;
    key.shadow.mapSize.height = 2048;
    this.scene.add(key);

    const rim = new THREE.DirectionalLight(0x38bdf8, 1.8);
    rim.position.set(-3, -2, -3);
    this.scene.add(rim);

    const fill = new THREE.DirectionalLight(0xf59e0b, 0.6);
    fill.position.set(0, -4, 2);
    this.scene.add(fill);
  }

  _buildCompactModel() {
    this.scene.add(this.deviceGroup);

    // Scale to pocket handheld companion dimensions (120mm x 72mm x 18mm equivalent)
    this.deviceGroup.scale.set(0.68, 0.68, 0.68);

    // Materials
    this.matChassis = new THREE.MeshStandardMaterial({
      color: 0x161b22,
      roughness: 0.42,
      metalness: 0.28
    });

    this.matGrip = new THREE.MeshStandardMaterial({
      color: 0x0d1117,
      roughness: 0.85,
      metalness: 0.05
    });

    this.matBezel = new THREE.MeshStandardMaterial({
      color: 0x21262d,
      roughness: 0.4,
      metalness: 0.4
    });

    this.matMetal = new THREE.MeshStandardMaterial({
      color: 0x94a3b8,
      roughness: 0.22,
      metalness: 0.85
    });

    this.matGold = new THREE.MeshStandardMaterial({
      color: 0xd97706,
      roughness: 0.28,
      metalness: 0.75
    });

    // 1. Sleek Compact Chassis (Width: 1.35, Height: 2.2, Depth: 0.32)
    const shape = new THREE.Shape();
    const w = 0.67;
    const h = 1.1;
    const r = 0.15;

    shape.absarc(-w + r, -h + r, r, Math.PI, 1.5 * Math.PI, true);
    shape.absarc(w - r, -h + r, r, 1.5 * Math.PI, 2 * Math.PI, true);
    shape.absarc(w - r, h - r, r, 0, 0.5 * Math.PI, true);
    shape.absarc(-w + r, h - r, r, 0.5 * Math.PI, Math.PI, true);

    const extrudeSettings = {
      depth: 0.32,
      bevelEnabled: true,
      bevelSegments: 8,
      steps: 1,
      bevelSize: 0.04,
      bevelThickness: 0.04
    };

    const casingGeo = new THREE.ExtrudeGeometry(shape, extrudeSettings);
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
    this.deviceGroup.add(createSideGrip(-0.69));
    this.deviceGroup.add(createSideGrip(0.69));

    // 3. Front Face Recessed Bezel Plate
    const frontPlate = new THREE.Mesh(new THREE.BoxGeometry(1.2, 2.05, 0.02), this.matBezel);
    frontPlate.position.set(0, 0, 0.18);
    this.deviceGroup.add(frontPlate);

    // 4. Acoustic Speaker Grille with Speaker Icon
    const speakerG = new THREE.Group();
    speakerG.position.set(0, 0.52, 0.19);

    const speakerTex = createButtonIconTexture("speaker", "#111827", "#38bdf8");
    const speakerMat = new THREE.MeshStandardMaterial({
      map: speakerTex,
      roughness: 0.5,
      metalness: 0.4
    });

    const speakerMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.025, 32), speakerMat);
    speakerMesh.rotateX(Math.PI / 2);
    speakerG.add(speakerMesh);

    speakerG.userData = { partId: "speaker_grille" };
    this.interactiveMeshes.push(speakerMesh);
    this.deviceGroup.add(speakerG);

    // 5. PTT / MICROPHONE BUTTON (Center) with Mic Icon Texture
    const pttG = new THREE.Group();
    pttG.position.set(0, -0.15, 0.19);

    const pttRim = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 0.03, 32), this.matBezel);
    pttRim.rotateX(Math.PI / 2);
    pttG.add(pttRim);

    const micTex = createButtonIconTexture("mic", "#dc2626", "#ffffff");
    const matPttWithIcon = new THREE.MeshStandardMaterial({
      map: micTex,
      roughness: 0.35,
      metalness: 0.2,
      emissive: 0x450a0a,
      emissiveIntensity: 0.3
    });

    this.meshPttBtn = new THREE.Mesh(new THREE.CylinderGeometry(0.27, 0.27, 0.06, 32), matPttWithIcon);
    this.meshPttBtn.rotateX(Math.PI / 2);
    this.meshPttBtn.position.z = 0.025;
    pttG.add(this.meshPttBtn);

    // High tactile concentric ring for touch orientation
    const pttRing = new THREE.Mesh(new THREE.TorusGeometry(0.275, 0.015, 8, 28), this.matMetal);
    pttRing.position.z = 0.055;
    pttG.add(pttRing);

    pttG.userData = { partId: "btn_ptt" };
    this.interactiveMeshes.push(this.meshPttBtn, pttRim, pttRing);
    this.deviceGroup.add(pttG);

    // 6. NOTEBOOK BUTTON (Right) with Star Icon Texture
    const noteG = new THREE.Group();
    noteG.position.set(0.42, -0.15, 0.19);

    const noteRim = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.025, 24), this.matBezel);
    noteRim.rotateX(Math.PI / 2);
    noteG.add(noteRim);

    const starTex = createButtonIconTexture("star", "#f59e0b", "#ffffff");
    const matStarWithIcon = new THREE.MeshStandardMaterial({
      map: starTex,
      roughness: 0.3,
      metalness: 0.35,
      emissive: 0x78350f,
      emissiveIntensity: 0.3
    });

    this.meshNoteBtn = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 0.055, 24), matStarWithIcon);
    this.meshNoteBtn.rotateX(Math.PI / 2);
    this.meshNoteBtn.position.z = 0.025;
    noteG.add(this.meshNoteBtn);

    noteG.userData = { partId: "btn_notebook" };
    this.interactiveMeshes.push(this.meshNoteBtn, noteRim);
    this.deviceGroup.add(noteG);

    // 7. SUMMARY BUTTON (Left) with Notes List Icon Texture
    const sumG = new THREE.Group();
    sumG.position.set(-0.42, -0.15, 0.19);

    const sumRim = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.025, 24), this.matBezel);
    sumRim.rotateX(Math.PI / 2);
    sumG.add(sumRim);

    const sumTex = createButtonIconTexture("summary", "#10b981", "#ffffff");
    const matSumWithIcon = new THREE.MeshStandardMaterial({
      map: sumTex,
      roughness: 0.35,
      metalness: 0.3,
      emissive: 0x064e3b,
      emissiveIntensity: 0.3
    });

    this.meshSumBtn = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 0.055, 24), matSumWithIcon);
    this.meshSumBtn.rotateX(Math.PI / 2);
    this.meshSumBtn.position.z = 0.025;
    sumG.add(this.meshSumBtn);

    sumG.userData = { partId: "btn_summary" };
    this.interactiveMeshes.push(this.meshSumBtn, sumRim);
    this.deviceGroup.add(sumG);

    // 8. BRAILLE BUTTON (Below PTT) with 6-dot Braille Icon Texture
    const brailleG = new THREE.Group();
    brailleG.position.set(0, -0.55, 0.19);

    const brailleRim = new THREE.Mesh(new THREE.BoxGeometry(0.54, 0.22, 0.025), this.matBezel);
    brailleG.add(brailleRim);

    const brailleTex = createButtonIconTexture("braille", "#7c3aed", "#ffffff");
    const matBrailleWithIcon = new THREE.MeshStandardMaterial({
      map: brailleTex,
      roughness: 0.35,
      metalness: 0.3,
      emissive: 0x4c1d95,
      emissiveIntensity: 0.3
    });

    this.meshBrailleBtn = new THREE.Mesh(new THREE.BoxGeometry(0.48, 0.17, 0.055), matBrailleWithIcon);
    this.meshBrailleBtn.position.z = 0.025;
    brailleG.add(this.meshBrailleBtn);

    brailleG.userData = { partId: "btn_braille" };
    this.interactiveMeshes.push(this.meshBrailleBtn, brailleRim);
    this.deviceGroup.add(brailleG);

    // 9. BOTTOM EDGE PORTS (3.5mm Jack, USB Type-C, Braille Dock)
    const bottomG = new THREE.Group();
    bottomG.position.set(0, -1.14, 0);

    // A) 3.5mm Headphone Jack (Left)
    const jackOuter = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, 0.1, 24), this.matBezel);
    jackOuter.position.x = -0.44;
    bottomG.add(jackOuter);

    const jackHole = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.12, 24), this.matGold);
    jackHole.position.x = -0.44;
    bottomG.add(jackHole);

    const jackHit = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 0.3), new THREE.MeshBasicMaterial({ visible: false }));
    jackHit.position.x = -0.44;
    jackHit.userData = { partId: "port_jack" };
    bottomG.add(jackHit);
    this.interactiveMeshes.push(jackOuter, jackHole, jackHit);

    // B) USB Type-C Port (Center) with metallic tongue pin
    const usbcBezel = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.1, 0.18), this.matBezel);
    bottomG.add(usbcBezel);

    const usbcInner = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.05, 0.2), this.matMetal);
    bottomG.add(usbcInner);

    // USB-C center pin
    const usbcPin = new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.015, 0.22), this.matGold);
    bottomG.add(usbcPin);

    const usbcHit = new THREE.Mesh(new THREE.BoxGeometry(0.36, 0.3, 0.3), new THREE.MeshBasicMaterial({ visible: false }));
    usbcHit.userData = { partId: "port_usbc" };
    bottomG.add(usbcHit);
    this.interactiveMeshes.push(usbcBezel, usbcInner, usbcHit);

    // C) Braille Display Connector (Right) with 14 contact pins
    const brailleDockBezel = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.1, 0.2), this.matGold);
    brailleDockBezel.position.x = 0.44;
    bottomG.add(brailleDockBezel);

    const brailleHit = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.3, 0.3), new THREE.MeshBasicMaterial({ visible: false }));
    brailleHit.position.x = 0.44;
    brailleHit.userData = { partId: "port_braille" };
    bottomG.add(brailleHit);
    this.interactiveMeshes.push(brailleDockBezel, brailleHit);

    this.deviceGroup.add(bottomG);

    // 10. Volume Thumbwheel (Right side)
    const wheelG = new THREE.Group();
    wheelG.position.set(0.69, 0.15, 0);

    const wheelMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.26, 24), this.matMetal);
    wheelMesh.rotateZ(Math.PI / 2);
    wheelG.add(wheelMesh);

    wheelG.userData = { partId: "volume_wheel" };
    this.interactiveMeshes.push(wheelMesh);
    this.deviceGroup.add(wheelG);

    // 11. Top Edge Mics & Lanyard Loop
    const mic1 = new THREE.Mesh(new THREE.CylinderGeometry(0.024, 0.024, 0.08, 12), this.matMetal);
    mic1.position.set(-0.35, 1.15, 0);
    this.deviceGroup.add(mic1);

    const mic2 = new THREE.Mesh(new THREE.CylinderGeometry(0.024, 0.024, 0.08, 12), this.matMetal);
    mic2.position.set(0.35, 1.15, 0);
    this.deviceGroup.add(mic2);

    const eyelet = new THREE.Mesh(new THREE.TorusGeometry(0.11, 0.03, 8, 20), this.matMetal);
    eyelet.position.set(-0.62, 1.08, 0);
    eyelet.rotateY(Math.PI / 4);
    this.deviceGroup.add(eyelet);
  }

  _onPointerDown(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.interactiveMeshes, true);

    if (intersects.length > 0) {
      let obj = intersects[0].object;
      while (obj && !obj.userData?.partId && obj.parent) {
        obj = obj.parent;
      }
      const partId = obj?.userData?.partId;
      if (partId && HARDWARE_PARTS[partId]) {
        this._selectPart(partId);
      }
    }
  }

  _selectPart(partId, animateCam = true) {
    const info = HARDWARE_PARTS[partId];
    if (!info) return;

    this.activePartId = partId;
    audio.playClick(info.sound || "mechanical");

    // Button depression micro-animation
    if (partId === "btn_ptt" && this.meshPttBtn) {
      this.meshPttBtn.position.z = 0.0;
      setTimeout(() => { if (this.meshPttBtn) this.meshPttBtn.position.z = 0.025; }, 120);
    } else if (partId === "btn_notebook" && this.meshNoteBtn) {
      this.meshNoteBtn.position.z = 0.0;
      setTimeout(() => { if (this.meshNoteBtn) this.meshNoteBtn.position.z = 0.025; }, 120);
    } else if (partId === "btn_summary" && this.meshSumBtn) {
      this.meshSumBtn.position.z = 0.0;
      setTimeout(() => { if (this.meshSumBtn) this.meshSumBtn.position.z = 0.025; }, 120);
    } else if (partId === "btn_braille" && this.meshBrailleBtn) {
      this.meshBrailleBtn.position.z = 0.0;
      setTimeout(() => { if (this.meshBrailleBtn) this.meshBrailleBtn.position.z = 0.025; }, 120);
    }

    // Update UI Inspector Card (English)
    const title = document.getElementById("inspector-title");
    const badge = document.getElementById("inspector-badge");
    const code = document.getElementById("inspector-code");
    const desc = document.getElementById("inspector-desc");
    const btnAction = document.getElementById("trigger-btn");

    if (title && badge && code && desc && btnAction) {
      title.textContent = info.name;
      badge.textContent = info.badge;
      code.textContent = info.codeRef;
      desc.textContent = info.desc;
      btnAction.querySelector("span").textContent = info.actionTitle || "Test Action";
    }

    // Update active highlight in the left navigation sidebar
    document.querySelectorAll(".part-nav-item").forEach((el) => {
      el.classList.toggle("active", el.getAttribute("data-part") === partId);
    });

    // Gentle camera adjustment (never too close, keeps full device in view)
    if (animateCam && info.targetPos && info.camOffset) {
      const worldTarget = info.targetPos.clone();
      this.deviceGroup.localToWorld(worldTarget);
      this.targetLookAt.copy(worldTarget);
      this.targetCamPos.copy(worldTarget).add(info.camOffset);
    }
  }

  _bindUi() {
    document.querySelectorAll(".part-nav-item").forEach((btn) => {
      btn.addEventListener("click", () => {
        const partId = btn.getAttribute("data-part");
        this._selectPart(partId, true);
      });
    });

    // Reset View Button (Overview)
    const btnReset = document.getElementById("btn-reset");
    if (btnReset) {
      btnReset.addEventListener("click", () => {
        this.targetCamPos.set(0.08, 0.35, 3.5);
        this.targetLookAt.set(0.08, 0, 0);
        audio.playClick("mechanical");
      });
    }

    // Front View Button
    const btnFront = document.getElementById("btn-front");
    if (btnFront) {
      btnFront.addEventListener("click", () => {
        this.targetCamPos.set(0.08, 0, 3.3);
        this.targetLookAt.set(0.08, 0, 0);
        audio.playClick("mechanical");
      });
    }

    // Ports View Button (Bottom edge)
    const btnPorts = document.getElementById("btn-ports");
    if (btnPorts) {
      btnPorts.addEventListener("click", () => {
        this.targetCamPos.set(0.08, -1.2, 2.4);
        this.targetLookAt.set(0.08, -0.8, 0);
        audio.playClick("mechanical");
      });
    }

    // Action Trigger Button
    const triggerBtn = document.getElementById("trigger-btn");
    if (triggerBtn) {
      triggerBtn.addEventListener("click", () => {
        const info = HARDWARE_PARTS[this.activePartId];
        audio.playClick(info ? info.sound : "mechanical");
        triggerBtn.classList.add("pulse");
        setTimeout(() => triggerBtn.classList.remove("pulse"), 200);
      });
    }

    // Sound toggle
    const soundToggle = document.getElementById("sound-toggle");
    if (soundToggle) {
      soundToggle.addEventListener("click", () => {
        audio.muted = !audio.muted;
        soundToggle.style.opacity = audio.muted ? "0.4" : "1";
        if (!audio.muted) audio.playClick("mechanical");
      });
    }
  }

  _onResize() {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  }

  _animate() {
    requestAnimationFrame(() => this._animate());

    this.camera.position.lerp(this.targetCamPos, 0.07);
    this.controls.target.lerp(this.targetLookAt, 0.07);
    this.controls.update();

    this.renderer.render(this.scene, this.camera);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  window.studio = new HardwareStudio();
});
