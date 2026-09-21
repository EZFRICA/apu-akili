/**
 * app.js - Main Application Orchestrator for APU Live Lab
 */

import { AudioController } from "./audio.js";
import { BrailleManager } from "./braille.js";
import { ChatRenderer } from "./chat.js";
import { PrompterRenderer } from "./prompter.js";
import { LiveSocket } from "./ws.js";

class App {
  constructor() {
    this.currentMode = "discussion"; // "discussion" | "prompter"
    this.activeModel = "eleven_english_sts_v2";
    this.activeStudent = "eleve-aya";
    this.activeClass = "lycee-cocody:3eA";

    this.dom = {
      modelTabs: document.querySelectorAll(".model-tab"),
      studentSelect: document.getElementById("student-select"),
      statusPill: document.getElementById("status-pill"),
      statusText: document.getElementById("status-text"),
      modeBtns: document.querySelectorAll(".mode-btn"),
      chatContainer: document.getElementById("chat-container"),
      prompterContainer: document.getElementById("prompter-container"),
      micBtn: document.getElementById("mic-btn"),
      textInput: document.getElementById("text-fallback-input"),
      textSubmit: document.getElementById("text-fallback-submit"),
      hudLatency: document.getElementById("hud-latency"),
      hudAudioDur: document.getElementById("hud-audio-dur"),
      logsDrawer: document.getElementById("logs-content"),
    };

    // Sub-components
    this.socket = new LiveSocket();
    this.audio = new AudioController((pcmChunk) => {
      this.socket.sendBinary(pcmChunk);
    });
    this.braille = new BrailleManager();
    this.chat = new ChatRenderer(this.dom.chatContainer);
    this.prompter = new PrompterRenderer(this.dom.prompterContainer);

    this._bindEvents();
    this._connectSocket();
  }

  _bindEvents() {
    // 1. Model Switching
    this.dom.modelTabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const targetModel = tab.getAttribute("data-model");
        if (targetModel === this.activeModel) return;

        this.dom.modelTabs.forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        this.activeModel = targetModel;

        this._appendLog(`Model selected: ${targetModel}`);
        this._connectSocket();
      });
    });

    // 2. Student Selection
    this.dom.studentSelect.addEventListener("change", (e) => {
      const parts = e.target.value.split("|");
      this.activeStudent = parts[0];
      this.activeClass = parts[1] || "lycee-cocody:3eA";
      this._appendLog(`Student selected: ${this.activeStudent} (${this.activeClass})`);
      this._connectSocket();
    });

    // 3. Mode Toggling
    this.dom.modeBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.getAttribute("data-mode");
        this.setMode(mode);
      });
    });

    // 4. Microphone Button
    this.dom.micBtn.addEventListener("click", async () => {
      if (this.audio.isRecording) {
        this.stopListening();
      } else {
        await this.startListening();
      }
    });

    // 5. Fallback Text Input (if present)
    if (this.dom.textSubmit && this.dom.textInput) {
      const submitText = () => {
        const text = this.dom.textInput.value.trim();
        if (!text) return;
        this.dom.textInput.value = "";

        this.chat.addUserMessage(text);
        this.prompter.setUserTranscript(text, true);

        this.socket.sendJson({ type: "text_prompt", text });
        this._setStatus("thinking", "Thinking…");
      };

      this.dom.textSubmit.addEventListener("click", submitText);
      this.dom.textInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") submitText();
      });
    }

    // 6. WebSocket event handlers
    this.socket.on("connected", () => {
      this._setStatus("connected", "Connected");
    });

    this.socket.on("disconnected", () => {
      this._setStatus("disconnected", "Disconnected");
    });

    this.socket.on("error", (err) => {
      this._setStatus("error", "Error");
    });

    this.socket.on("log", (msg) => {
      this._appendLog(msg);
    });

    this.socket.on("user_transcript", (data) => {
      const text = data.text;
      if (data.replace) {
        this.prompter.setUserTranscript(text, true);
      } else {
        this.prompter.setUserTranscript(text, false);
      }
    });

    this.socket.on("assistant_token", (data) => {
      this._setStatus("talking", "APU speaking…");
      this.chat.streamAssistantToken(data.token, data);
      this.prompter.streamAssistantToken(data.token);
    });

    this.socket.on("audio_response", (data) => {
      if (data.audio) {
        this.audio.enqueueAudio(data.audio, data.mime || "audio/wav");
      }
      if (data.total_latency_ms && this.dom.hudLatency) {
        this.dom.hudLatency.textContent = `${data.total_latency_ms}ms`;
      }
      if (data.duration && this.dom.hudAudioDur) {
        this.dom.hudAudioDur.textContent = `${data.duration}s`;
      }
    });

    this.socket.on("notebook_saved", (data) => {
      this.chat.addNotebookCard(data.title, data.content);
    });

    this.socket.on("braille_format", (data) => {
      const card = this.braille.createCard(data.original_text, data.braille_g1, data.braille_g2);
      this.chat.appendBrailleCard(card);
      // Also provide a clone for prompter card slot
      const prompterCard = this.braille.createCard(data.original_text, data.braille_g1, data.braille_g2);
      this.prompter.appendBrailleCard(prompterCard);
    });

    this.socket.on("turn_complete", () => {
      this.chat.endTurn();
      this.prompter.endTurn();
      this._setStatus("connected", "Ready");
    });
  }

  setMode(mode) {
    this.currentMode = mode;
    this.dom.modeBtns.forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-mode") === mode);
    });

    if (mode === "discussion") {
      this.dom.chatContainer.classList.remove("hidden");
      this.dom.prompterContainer.classList.add("hidden");
    } else {
      this.dom.chatContainer.classList.add("hidden");
      this.dom.prompterContainer.classList.remove("hidden");
    }
  }

  async startListening() {
    try {
      this.dom.micBtn.classList.add("active");
      this._setStatus("listening", "Listening…");
      this.prompter.setSpeaker("user");
      await this.audio.startRecording();
    } catch (err) {
      console.error("Microphone access error:", err);
      this._setStatus("error", "Mic blocked");
      this.dom.micBtn.classList.remove("active");
    }
  }

  stopListening() {
    this.dom.micBtn.classList.remove("active");
    this.audio.stopRecording();
    this.socket.sendEndOfTurn();
    this._setStatus("thinking", "Processing…");
  }

  _connectSocket() {
    this.socket.connect(this.activeModel, this.activeStudent, this.activeClass);
  }

  _setStatus(state, text) {
    this.dom.statusPill.className = `status-pill ${state}`;
    this.dom.statusText.textContent = text;
  }

  _appendLog(message) {
    if (!this.dom.logsDrawer) return;
    const time = new Date().toLocaleTimeString();
    const line = document.createElement("div");
    line.textContent = `[${time}] ${message}`;
    this.dom.logsDrawer.appendChild(line);
    this.dom.logsDrawer.scrollTop = this.dom.logsDrawer.scrollHeight;
  }
}

// Auto-boot on load
window.addEventListener("DOMContentLoaded", () => {
  window.app = new App();
});
