/**
 * presentation.js - the glue: one event from the live lab, one change on the stage.
 */

import { CameraController } from "./camera.js";
import { PrompterController } from "./prompter.js";
import { KeynoteHardware3D, HARDWARE_PARTS_INFO } from "./hardware3d.js";
import { KeynoteBridge } from "./bridge.js";

class KeynoteApp {
  constructor() {
    this.dom = {
      videoFeed: document.getElementById("camera-feed"),
      cameraStatus: document.getElementById("camera-status-text"),
      prompterContainer: document.getElementById("prompter-stage-container"),
      equipment3dContainer: document.getElementById("equipment-3d-stage"),
      modelTabs: document.querySelectorAll(".model-pill-btn"),
      studentSelect: document.getElementById("student-select"),
      statusPill: document.getElementById("status-pill"),
      statusText: document.getElementById("status-text"),
      toggleMicBtn: document.getElementById("toggle-mic-btn"),
      toggleCameraBtn: document.getElementById("toggle-camera-btn"),
      toggleMirrorBtn: document.getElementById("toggle-mirror-btn"),
      toggleFullscreenBtn: document.getElementById("toggle-fullscreen-btn"),
      toggleDrawerBtn: document.getElementById("toggle-drawer-btn"),
      partsDrawer: document.getElementById("hardware-parts-drawer"),
      inspectorCard: document.getElementById("hardware-inspector-card"),
      inspectorBadge: document.getElementById("inspector-badge"),
      inspectorTitle: document.getElementById("inspector-title"),
      inspectorCode: document.getElementById("inspector-code"),
      inspectorDesc: document.getElementById("inspector-desc"),
      partsList: document.getElementById("parts-list"),
      viewShotBtns: document.querySelectorAll(".view-shot-btn"),
    };

    this.activeModel = "gemini-3.5-transcribe-live";
    this.activeStudent = "eleve-aya";
    this.activeClass = "lycee-cocody:3eA";

    this._init();
  }

  async _init() {
    // 1. Teleprompter Controller
    this.prompter = new PrompterController(this.dom.prompterContainer);

    // 2. 3D Tactile Hardware Studio (initialize immediately)
    this.hardware3d = new KeynoteHardware3D(
      this.dom.equipment3dContainer,
      (partId, info) => this._onHardwareActionTriggered(partId, info),
      (partId, info) => this._onPartSelected(partId, info)
    );

    // 3. Live Tutor WebSocket Bridge
    this.bridge = new KeynoteBridge({
      model: this.activeModel,
      student: this.activeStudent,
      classId: this.activeClass,
      onEvent: (type, payload) => this._onBridgeEvent(type, payload),
    });

    // 4. Camera Controller (starts non-blocking with keynote presenter fallback)
    this.camera = new CameraController(this.dom.videoFeed, (state, label) => {
      if (this.dom.cameraStatus) this.dom.cameraStatus.textContent = label;
    });
    this.camera.start()
      .then(() => this._setPressed(this.dom.toggleCameraBtn, this.camera.isActive))
      .catch((e) => console.warn("Camera init:", e));
    this._setPressed(this.dom.toggleMirrorBtn, this.camera.isMirrored);
    this._setPressed(this.dom.toggleDrawerBtn, true);

    this._bindEvents();
    this._renderPartsList();

    // Set initial inspector view to PTT button description: Voice Input · 16kHz PCM
    this._onPartSelected("btn_ptt", HARDWARE_PARTS_INFO["btn_ptt"]);

    // Connect bridge to live lab
    this.bridge.connect();
  }

  _setPressed(el, on) {
    el?.setAttribute("aria-pressed", on ? "true" : "false");
  }

  _setStatus(state, text) {
    if (this.dom.statusPill) {
      this.dom.statusPill.className = `status-pill ${state}`;
    }
    if (this.dom.statusText) {
      this.dom.statusText.textContent = text;
    }
  }

  /**
   * Back to resting state after a turn.
   *
   * The pill used to fall back to a flat "Ready" once anything finished, which threw away
   * the one thing it is there to say: whether the live lab is still on the other end.
   */
  _setIdleStatus() {
    if (this.bridge?.isConnected) {
      this._setStatus("connected", "Live Connected");
    } else {
      this._setStatus("offline", "Offline (check :8765)");
    }
  }

  _bindEvents() {
    // Model Selection
    this.dom.modelTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const model = tab.getAttribute("data-model");
        if (model === this.activeModel) return;
        this.dom.modelTabs.forEach((t) => {
          t.classList.remove("active");
          t.setAttribute("aria-pressed", "false");
        });
        tab.classList.add("active");
        tab.setAttribute("aria-pressed", "true");
        this.activeModel = model;
        this.bridge.setModel(model);
      });
    });

    // Student Selection
    this.dom.studentSelect?.addEventListener("change", (e) => {
      const parts = e.target.value.split("|");
      this.activeStudent = parts[0];
      this.activeClass = parts[1] || "lycee-cocody:3eA";
      this.bridge.setStudent(this.activeStudent, this.activeClass);
    });

    // Direct Microphone Activation from Header
    this.dom.toggleMicBtn?.addEventListener("click", () => {
      this._onHardwareActionTriggered("btn_ptt", HARDWARE_PARTS_INFO["btn_ptt"]);
    });

    // No microphone hidden under the teleprompter. A click anywhere on that band used to
    // open it: an unlabelled target eight hundred pixels wide, that a keyboard could not
    // reach, over text that moves. When an answer arrived the band slid fifty pixels up
    // under the pointer, so a click aimed at the badge opened the microphone instead.
    // The header button, the M key and the key on the device are how it opens.

    // Camera Controls
    this.dom.toggleCameraBtn?.addEventListener("click", async () => {
      if (this.camera.isActive) {
        this.camera.stop();
      } else {
        await this.camera.start();
      }
      this._setPressed(this.dom.toggleCameraBtn, this.camera.isActive);
    });

    this.dom.toggleMirrorBtn?.addEventListener("click", () => {
      this.camera.toggleMirror();
      this._setPressed(this.dom.toggleMirrorBtn, this.camera.isMirrored);
    });

    // Fullscreen Toggle
    this.dom.toggleFullscreenBtn?.addEventListener("click", () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
    });

    // Drawer Toggles
    this.dom.toggleDrawerBtn?.addEventListener("click", () => {
      const collapsed = this.dom.partsDrawer?.classList.toggle("collapsed");
      this.dom.inspectorCard?.classList.toggle("collapsed", collapsed);
      // Out of sight is not out of the accessibility tree: a panel slid off the stage is
      // still read, and still focusable, unless it is hidden in the tree as well.
      [this.dom.partsDrawer, this.dom.inspectorCard].forEach((panel) => {
        if (panel) panel.hidden = Boolean(collapsed);
      });
      this._setPressed(this.dom.toggleDrawerBtn, !collapsed);
    });

    // The device on stage is a canvas: no focus, no keys, nothing a screen reader can
    // press. The component list is its keyboard equivalent, and these two shortcuts are
    // for the two things a presenter does mid-sentence without looking.
    window.addEventListener("keydown", (event) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const tag = document.activeElement?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;

      if (event.key === "Escape" && this.prompter.brailleVisible) {
        event.preventDefault();
        this._onHardwareActionTriggered("btn_braille", HARDWARE_PARTS_INFO["btn_braille"]);
      } else if (event.key === "m" || event.key === "M") {
        event.preventDefault();
        this.hardware3d.triggerPress("btn_ptt");
      }
    });

    // Camera Shot Views
    this.dom.viewShotBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const shot = btn.getAttribute("data-shot");
        this.dom.viewShotBtns.forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
        this.hardware3d.setShot(shot);
      });
    });
  }

  _renderPartsList() {
    if (!this.dom.partsList) return;
    this.dom.partsList.innerHTML = "";

    const parts = [
      { id: "btn_ptt", icon: "🎙️", name: "Mic / PTT", sub: "16kHz PCM Speech" },
      { id: "btn_notebook", icon: "⭐", name: "Notebook", sub: "Save Note (SQLite)" },
      { id: "btn_summary", icon: "📄", name: "Summary", sub: "Auditory Recap" },
      { id: "btn_braille", icon: "⠿", name: "Braille", sub: "Grade 1 & 2 Output" },
      { id: "port_usbc", icon: "⚡", name: "USB-C", sub: "20W Fast Charge" },
      { id: "port_jack", icon: "🎧", name: "3.5mm Jack", sub: "Stereo DAC Audio" },
      { id: "port_braille", icon: "🧲", name: "Braille Dock", sub: "14-pin Magnetic Dock" },
      { id: "volume_wheel", icon: "🎛️", name: "Volume Wheel", sub: "Rotary Detents" },
    ];

    parts.forEach((part) => {
      const btn = document.createElement("button");
      btn.className = `part-btn-item ${part.id === "btn_ptt" ? "active" : ""}`;
      btn.setAttribute("data-part", part.id);
      // Said out loud, because the browser computed no name at all for these: eight
      // buttons announced as "button", and they are the only way to this device for
      // anyone not holding a mouse. The emoji is decoration and says so.
      btn.setAttribute("aria-label", `${part.name}. ${part.sub}`);
      btn.innerHTML = `
        <span class="part-icon" aria-hidden="true">${part.icon}</span>
        <div class="part-info">
          <span class="part-name">${part.name}</span>
          <span class="part-desc-short">${part.sub}</span>
        </div>
      `;

      btn.addEventListener("click", () => {
        document.querySelectorAll(".part-btn-item").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        this.hardware3d.triggerPress(part.id);
      });

      this.dom.partsList.appendChild(btn);
    });
  }

  _updateDrawerInUse(partId, inUse) {
    if (!partId) {
      document.querySelectorAll(".part-btn-item").forEach((b) => b.classList.remove("in-use"));
      return;
    }
    document.querySelectorAll(".part-btn-item").forEach((b) => {
      if (b.getAttribute("data-part") === partId) {
        b.classList.toggle("in-use", Boolean(inUse));
      }
    });
  }

  _onPartSelected(partId, info) {
    if (!info) return;

    // Update highlight in parts drawer
    document.querySelectorAll(".part-btn-item").forEach((b) => {
      b.classList.toggle("active", b.getAttribute("data-part") === partId);
    });

    // Update Inspector Card (strictly description & specs, no Talk button)
    if (this.dom.inspectorBadge) this.dom.inspectorBadge.textContent = info.badge || "Tactile Component";
    if (this.dom.inspectorTitle) this.dom.inspectorTitle.textContent = info.name || partId;
    if (this.dom.inspectorCode) this.dom.inspectorCode.textContent = info.codeRef || "";
    if (this.dom.inspectorDesc) this.dom.inspectorDesc.textContent = info.desc || "";
  }

  async _onHardwareActionTriggered(partId, info) {
    if (partId === "btn_braille") {
      const isVisible = this.prompter.toggleBraille();
      this.hardware3d.setButtonInUse("btn_braille", isVisible);
      this._updateDrawerInUse("btn_braille", isVisible);
      if (isVisible) {
        // Ask the lab for real liblouis cells if it is there; the card already shows the
        // client-side grade 1 fallback, so it is never empty while that answer travels.
        if (this.bridge.isConnected) {
          this.bridge.triggerHardwareAction("btn_braille");
        } else {
          this._setStatus("connected", "Braille shown");
        }
      } else {
        this._setIdleStatus();
      }
      return;
    }

    await this.bridge.triggerHardwareAction(partId);
  }

  _onBridgeEvent(type, payload) {
    switch (type) {
      case "online":
        this._setStatus("connected", "Live Connected");
        break;

      case "offline":
      case "closed":
        this._setStatus("offline", payload?.reason ? "Offline (Check :8765)" : "Disconnected");
        break;

      case "ptt_start":
        this._setPressed(this.dom.toggleMicBtn, true);
        // State: "en cours d'utilisation"
        this.hardware3d.setButtonInUse("btn_ptt", true);
        this.dom.toggleMicBtn?.classList.add("active");
        this._updateDrawerInUse("btn_ptt", true);
        this._setStatus("listening", "Listening…");
        this.prompter.setSpeaker("user");
        this.prompter.setUserTranscript("🎙️ Your turn, go ahead…", true);
        break;

      case "ptt_stop":
        this._setPressed(this.dom.toggleMicBtn, false);
        // State: "en stop"
        this.hardware3d.setButtonInUse("btn_ptt", false);
        this.dom.toggleMicBtn?.classList.remove("active");
        this._updateDrawerInUse("btn_ptt", false);
        this._setStatus("thinking", "Working on what you said…");
        this.prompter.setSpeaker("idle");
        break;

      case "action_start":
        // Action buttons "en cours d'utilisation"
        this.hardware3d.setButtonInUse(payload.partId, true);
        this._updateDrawerInUse(payload.partId, true);
        this._setStatus("thinking", "Working…");
        if (payload.partId === "btn_notebook") {
          this.prompter.setUserTranscript("⭐ Saving to your notebook…", true);
        } else if (payload.partId === "btn_summary") {
          this.prompter.setUserTranscript("📄 Reading your notebook back…", true);
        }
        break;

      case "action_stop":
        // Action buttons "en stop"
        if (payload.partId !== "btn_braille" || !this.prompter.brailleVisible) {
          this.hardware3d.setButtonInUse(payload.partId, false);
          this._updateDrawerInUse(payload.partId, false);
        }
        this._setIdleStatus();
        break;

      case "user_transcript":
        // ONLY the active speaker voice text is displayed
        if (payload.text) {
          this.prompter.setUserTranscript(payload.text, false);
        }
        break;

      case "assistant_token":
        if (payload.announcement) {
          // Said out loud, and never written over the explanation on the prompter: the
          // cells below hold that explanation, not this sentence about them.
          this.prompter.announceAction(payload.token);
          break;
        }
        // ONLY the active assistant response is streamed and displayed
        this._setStatus("talking", "APU Akili is answering…");
        this.prompter.setSpeaker("assistant");
        if (payload.token) {
          this.prompter.streamAssistantToken(payload.token);
        }
        break;

      case "braille_format":
        // Cache braille data without forced auto-popup (shown only on Braille button click)
        this.prompter.setBrailleData(payload);
        break;

      case "turn_complete":
        this.hardware3d.setButtonInUse("btn_ptt", false);
        this.hardware3d.setButtonInUse("btn_notebook", false);
        this.hardware3d.setButtonInUse("btn_summary", false);
        if (!this.prompter.brailleVisible) {
          this.hardware3d.setButtonInUse("btn_braille", false);
          this._updateDrawerInUse("btn_braille", false);
        }
        this.dom.toggleMicBtn?.classList.remove("active");
        this._setPressed(this.dom.toggleMicBtn, false);
        this._updateDrawerInUse("btn_ptt", false);
        this._updateDrawerInUse("btn_notebook", false);
        this._updateDrawerInUse("btn_summary", false);
        this._setIdleStatus();
        this.prompter.endTurn();
        break;

      case "error":
        if (payload?.source === "mic_permission" || !this.bridge.isRecordingMic) {
          this.hardware3d.setButtonInUse("btn_ptt", false);
          this.dom.toggleMicBtn?.classList.remove("active");
          this._setPressed(this.dom.toggleMicBtn, false);
          this._updateDrawerInUse("btn_ptt", false);
        }
        this.hardware3d.setButtonInUse("btn_notebook", false);
        this.hardware3d.setButtonInUse("btn_summary", false);
        this._updateDrawerInUse("btn_notebook", false);
        this._updateDrawerInUse("btn_summary", false);
        this._setStatus("error", payload.message || "Something went wrong");
        // On the prompter as well, so it is not eleven characters in a corner that a
        // pupil who cannot see the screen is never told about.
        this.prompter.showNotice(payload.message || "Something went wrong. Try again.");
        break;

      default:
        break;
    }
  }
}

// Bootstrap once DOM is ready
window.addEventListener("DOMContentLoaded", () => {
  window.keynoteApp = new KeynoteApp();
});
