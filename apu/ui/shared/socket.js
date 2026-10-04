/**
 * The websocket to the live lab, for every front end that talks to it.
 *
 * One connection attempt at a time, one live socket, and a close that only counts if it is
 * the socket still in use. Each of those was a bug in one of the two copies this file
 * replaces.
 *
 * Events a caller can listen for: the four below, and every `type` the server sends, handed
 * on unchanged. The four are namespaced because the server sends a message of type "error"
 * of its own, meaning the tutor could not answer, which is not the same thing at all as
 * this socket failing to open and must not arrive on the same channel.
 */

export const SOCKET_OPENED = "socket:opened";
export const SOCKET_CLOSED = "socket:closed";
export const SOCKET_FAILED = "socket:failed";
export const SOCKET_LOG = "socket:log";

const CONNECT_TIMEOUT_MS = 4000;

export class LiveSocket {
  constructor({ model, student, classId, onEvent } = {}) {
    this.model = model || null;
    this.student = student || null;
    this.classId = classId || null;
    this.onEvent = onEvent || null;

    this.socket = null;
    this.connecting = null;
    this.listeners = new Map();
  }

  on(event, callback) {
    if (!this.listeners.has(event)) this.listeners.set(event, []);
    this.listeners.get(event).push(callback);
  }

  _emit(event, payload) {
    for (const handler of this.listeners.get(event) || []) {
      try {
        handler(payload);
      } catch (err) {
        console.error(`Error in listener for ${event}:`, err);
      }
    }
    if (this.onEvent) {
      try {
        this.onEvent(event, payload);
      } catch (err) {
        console.error(`Error in onEvent for ${event}:`, err);
      }
    }
  }

  get isConnected() {
    // A boolean. It used to return the socket itself, or null, and every caller that
    // compared it to false was comparing against something that was never false.
    return Boolean(this.socket) && this.socket.readyState === WebSocket.OPEN;
  }

  get url() {
    // Derived from the page, not hardcoded: the lab serves every front end it feeds, so
    // the socket goes back to wherever the page came from, over wss if the page was.
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "localhost:8765";
    const query = `student_id=${encodeURIComponent(this.student)}` +
                  `&class_id=${encodeURIComponent(this.classId)}`;
    return `${protocol}//${host}/ws/${encodeURIComponent(this.model)}?${query}`;
  }

  /** Resolves true once the lab has accepted the connection, false if it has not. */
  async connect() {
    if (this.isConnected) return true;
    // One attempt at a time. Pressing the microphone and then a key before the first
    // socket had opened used to open a second one, and the lab answered the turn twice.
    if (this.connecting) return this.connecting;

    this.connecting = new Promise((resolve) => {
      let socket;
      try {
        socket = new WebSocket(this.url);
      } catch (err) {
        this._emit(SOCKET_FAILED, { reason: String(err) });
        resolve(false);
        return;
      }

      socket.binaryType = "arraybuffer";
      this._emit(SOCKET_LOG, `Connecting: ${this.model} (${this.student})`);

      const timeout = window.setTimeout(() => {
        this._emit(SOCKET_FAILED,
                   { reason: `The live lab did not answer within ${CONNECT_TIMEOUT_MS / 1000} s.` });
        try { socket.close(); } catch (_) { /* already gone */ }
        resolve(false);
      }, CONNECT_TIMEOUT_MS);

      socket.onopen = () => {
        window.clearTimeout(timeout);
        this.socket = socket;
        this._emit(SOCKET_OPENED, { model: this.model, student: this.student });
        resolve(true);
      };

      socket.onerror = () => {
        window.clearTimeout(timeout);
        this._emit(SOCKET_FAILED, { reason: "The connection to the live lab failed." });
        resolve(false);
      };

      socket.onclose = (event) => {
        // Only if this is still the live socket. setModel() closes the old one and opens
        // the next immediately, and the late close of the old one used to drop the new.
        if (this.socket && this.socket !== socket) return;
        this.socket = null;
        this._emit(SOCKET_CLOSED, { code: event?.code, reason: event?.reason });
      };

      socket.onmessage = (event) => this._handleMessage(event);
    });

    try {
      return await this.connecting;
    } finally {
      this.connecting = null;
    }
  }

  _handleMessage(event) {
    // Binary frames carry nothing a front end reads; audio arrives as base64 in JSON.
    if (typeof event.data !== "string") return;

    let message;
    try {
      message = JSON.parse(event.data);
    } catch (_) {
      // A proxy error page, or a half-written frame. Dropping it is the whole handling.
      return;
    }
    if (message && message.type) this._emit(message.type, message);
  }

  close() {
    if (!this.socket) return;
    const socket = this.socket;
    this.socket = null;
    try {
      socket.close(1000, "Switching session");
    } catch (_) { /* already gone */ }
  }

  /**
   * Which model, which pupil, which class. If the socket is open it is reopened, because
   * the lab fixes all three when it accepts the connection.
   */
  configure({ model, student, classId } = {}) {
    const before = `${this.model}|${this.student}|${this.classId}`;
    if (model !== undefined) this.model = model;
    if (student !== undefined) this.student = student;
    if (classId !== undefined && classId !== null) this.classId = classId;

    const changed = before !== `${this.model}|${this.student}|${this.classId}`;
    if (changed && this.socket) {
      this.close();
      this.connect();
    }
    return changed;
  }

  setModel(modelId) {
    return this.configure({ model: modelId });
  }

  setStudent(studentId, classId) {
    return this.configure({ student: studentId, classId });
  }

  sendBinary(arrayBuffer) {
    if (!this.isConnected) return false;
    this.socket.send(arrayBuffer);
    return true;
  }

  sendJson(payload) {
    if (!this.isConnected) return false;
    this.socket.send(JSON.stringify(payload));
    return true;
  }

  sendEndOfTurn() {
    return this.sendBinary(new TextEncoder().encode("END_OF_TURN"));
  }
}
