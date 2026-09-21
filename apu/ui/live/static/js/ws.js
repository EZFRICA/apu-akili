/**
 * ws.js - WebSocket Connection and Event Dispatcher for APU Live Lab
 */

export class LiveSocket {
  constructor() {
    this.ws = null;
    this.listeners = new Map();
    this.currentModel = null;
    this.currentStudent = null;
    this.currentClass = null;
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  _emit(event, data) {
    const handlers = this.listeners.get(event) || [];
    for (const fn of handlers) {
      try {
        fn(data);
      } catch (err) {
        console.error(`Error in event listener for ${event}:`, err);
      }
    }
  }

  connect(modelId, studentId, classId) {
    this.disconnect();

    this.currentModel = modelId;
    this.currentStudent = studentId;
    this.currentClass = classId;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/${encodeURIComponent(modelId)}?student_id=${encodeURIComponent(studentId)}&class_id=${encodeURIComponent(classId)}`;

    this._emit("log", `Connecting WebSocket: ${modelId} (${studentId})`);

    try {
      this.ws = new WebSocket(url);
      this.ws.binaryType = "arraybuffer";

      this.ws.onopen = () => {
        this._emit("connected", { model: modelId, student: studentId });
        this._emit("log", `Connected to ${modelId}`);
      };

      this.ws.onclose = (event) => {
        this._emit("disconnected", { code: event.code, reason: event.reason });
        this._emit("log", `WebSocket closed (${event.code})`);
      };

      this.ws.onerror = (err) => {
        this._emit("error", err);
        this._emit("log", `WebSocket error: ${err}`);
      };

      this.ws.onmessage = (event) => {
        if (typeof event.data === "string") {
          try {
            const data = JSON.parse(event.data);
            if (data.type) {
              this._emit(data.type, data);
            }
          } catch (e) {
            console.warn("Non-JSON text message:", event.data);
          }
        }
      };
    } catch (exc) {
      this._emit("error", exc);
      this._emit("log", `Failed to open WS: ${exc}`);
    }
  }

  disconnect() {
    if (this.ws) {
      try {
        this.ws.close(1000, "Switching session");
      } catch (e) {}
      this.ws = null;
    }
  }

  sendBinary(arrayBuffer) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(arrayBuffer);
    }
  }

  sendJson(payload) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  sendEndOfTurn() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      const encoder = new TextEncoder();
      this.ws.send(encoder.encode("END_OF_TURN"));
    }
  }
}
