/**
 * bridge.js - what a key on Pocket Akili means, and nothing else.
 *
 * The socket, the microphone and the loudspeaker live in apu/ui/shared, because the lab's
 * own page needs exactly the same three and used to carry its own copy of them. What is
 * left here is the part only this stage has: which key sends which words, and which key
 * stops glowing when which answer comes back.
 */

import { AudioPlayback, MicrophoneStream } from "../shared/audio.js";
import {
  LiveSocket, SOCKET_CLOSED, SOCKET_FAILED, SOCKET_LOG, SOCKET_OPENED,
} from "../shared/socket.js";

export const HARDWARE_ACTIONS = {
  btn_ptt: {
    id: "btn_ptt",
    label: "Voice Push-to-Talk",
    desc: "Starts/stops live 16kHz PCM microphone stream",
    sound: "heavy",
  },
  btn_notebook: {
    id: "btn_notebook",
    label: "Save Note to SQLite",
    prompt: "Save that in my notebook",
    desc: "Persists the preceding explanation directly into student notebook",
    sound: "notebook",
  },
  btn_summary: {
    id: "btn_summary",
    label: "Spoken Revision Summary",
    prompt: "Summarize my notebook",
    desc: "Synthesizes an auditory recap of all points in notebook",
    sound: "mechanical",
  },
  btn_braille: {
    id: "btn_braille",
    label: "Grade 1 & 2 Braille",
    prompt: "Give me that in braille",
    desc: "Translates active answer to Braille cells via liblouis",
    sound: "braille",
  },
  port_usbc: {
    id: "port_usbc",
    label: "USB Type-C 20W PD",
    desc: "Fast charge and low-latency USB host connection",
    sound: "mechanical",
  },
  port_jack: {
    id: "port_jack",
    label: "3.5mm TRRS Headphone",
    desc: "Direct stereo DAC output for private classroom listening",
    sound: "mechanical",
  },
  port_braille: {
    id: "port_braille",
    label: "Magnetic Braille Dock",
    desc: "14-pin magnetic dock for refreshable braille displays",
    sound: "mechanical",
  },
  volume_wheel: {
    id: "volume_wheel",
    label: "Knurled Volume Wheel",
    desc: "Rotary analog potentiometer with 24 tactile detents",
    sound: "mechanical",
  },
};

export class KeynoteBridge {
  constructor(options = {}) {
    this.onEvent = options.onEvent || (() => {});
    this.activeIntent = null;

    this.socket = new LiveSocket({
      model: options.model || "gemini-3.5-transcribe-live",
      student: options.student || "eleve-aya",
      classId: options.classId || "lycee-cocody:3eA",
      onEvent: (type, payload) => this._onSocketEvent(type, payload),
    });
    this.microphone = new MicrophoneStream({
      onChunk: (chunk) => this.socket.sendBinary(chunk),
    });
    this.playback = new AudioPlayback();
  }

  get isConnected() {
    return this.socket.isConnected;
  }

  get isRecordingMic() {
    return this.microphone.isRecording;
  }

  get model() {
    return this.socket.model;
  }

  connect() {
    return this.socket.connect();
  }

  setModel(modelId) {
    this.socket.setModel(modelId);
  }

  setStudent(studentId, classId = "lycee-cocody:3eA") {
    this.socket.setStudent(studentId, classId);
  }

  sendEndOfTurn() {
    this.socket.sendEndOfTurn();
  }

  stopMic() {
    this.microphone.stop();
  }

  /**
   * A tactile key, pressed. Each one toggles: a second press stops what the first started.
   */
  async triggerHardwareAction(partId) {
    const action = HARDWARE_ACTIONS[partId];
    if (!action) return false;

    if (partId === "btn_ptt") return this._toggleMicrophone();
    if (action.prompt) return this._toggleIntent(partId, action);

    // A port or the wheel: a specification, not an action.
    this.onEvent("inspected", action);
    return true;
  }

  async _toggleMicrophone() {
    if (this.microphone.isRecording) {
      this.microphone.stop();
      this.sendEndOfTurn();
      this.onEvent("ptt_stop", {});
      return false;
    }

    if (!(await this.microphone.start())) {
      this.onEvent("error", {
        source: "mic_permission",
        message: "The microphone is not available. You can use the buttons instead.",
      });
      return false;
    }

    this.onEvent("ptt_start", {});
    if (!this.isConnected) {
      const connected = await this.socket.connect();
      if (!connected) {
        // The microphone closes with the failure. Leaving it open records a pupil into a
        // socket that is not there, with the browser's recording light on.
        this.microphone.stop();
        this.onEvent("ptt_stop", {});
        this.onEvent("error", {
          message: "The live lab is not answering, so the microphone was closed.",
        });
        return false;
      }
    }
    return true;
  }

  async _toggleIntent(partId, action) {
    if (this.activeIntent === partId) {
      this.activeIntent = null;
      this.onEvent("action_stop", { partId, action });
      return false;
    }

    this.activeIntent = partId;
    this.onEvent("action_start", { partId, action });

    if (!this.isConnected && !(await this.socket.connect())) {
      this.activeIntent = null;
      this.onEvent("error", { message: "The live lab is not answering." });
      this.onEvent("action_stop", { partId, action });
      return false;
    }

    this.socket.sendJson({ type: "text_prompt", text: action.prompt });
    return true;
  }

  /** The key that was waiting on this answer stops glowing, once. */
  _releaseIntent() {
    if (!this.activeIntent) return;
    const ended = this.activeIntent;
    this.activeIntent = null;
    this.onEvent("action_stop", { partId: ended });
  }

  _onSocketEvent(type, payload) {
    switch (type) {
      case SOCKET_OPENED:
        this.onEvent("online", payload);
        return;
      case SOCKET_CLOSED:
        this.microphone.stop();
        this.activeIntent = null;
        this.onEvent("closed", payload);
        return;
      case SOCKET_FAILED:
        // This socket failing to open, which is not the server's own "error" message
        // below, meaning the tutor could not answer.
        this.onEvent("offline", payload);
        return;
      case SOCKET_LOG:
        return;

      case "audio_response":
        this.playback.enqueue(payload.audio, payload.mime || "audio/wav");
        break;
      case "braille_format":
        if (this.activeIntent === "btn_braille") this._releaseIntent();
        break;
      case "notebook_saved":
        if (this.activeIntent === "btn_notebook") this._releaseIntent();
        break;
      case "turn_complete":
      case "error":
        // The tutor's own failure ends the turn as surely as an answer does. Without this
        // the key that asked the question went on glowing until the next one.
        this._releaseIntent();
        break;
      default:
        break;
    }

    this.onEvent(type, payload);
  }
}
