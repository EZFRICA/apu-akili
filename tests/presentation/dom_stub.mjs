/**
 * The smallest browser this interface will run in.
 *
 * prompter.js and bridge.js hold the rules that made the stage unusable when they broke:
 * one turn on screen, cells that are text and not markup, one socket, one announcement.
 * Reading them as strings proves they were typed. Running them proves they work, so this
 * stub exists to let node run them.
 */

class El {
  constructor(tag = "div", className = "") {
    this.tagName = tag.toUpperCase();
    this.className = className;
    this.children = [];
    this.attributes = {};
    this._text = "";
    this._html = "";
    this.listeners = {};
    this.style = {};
    this.hidden = false;
    this.scrollTop = 0;
    this.scrollHeight = 0;
  }
  get classList() {
    const self = this;
    const list = () => self.className.split(/\s+/).filter(Boolean);
    return {
      add: (...c) => { self.className = [...new Set([...list(), ...c])].join(" "); },
      remove: (...c) => { self.className = list().filter((x) => !c.includes(x)).join(" "); },
      contains: (c) => list().includes(c),
      toggle: (c, on) => {
        const want = on === undefined ? !list().includes(c) : Boolean(on);
        want ? self.classList.add(c) : self.classList.remove(c);
        return want;
      },
    };
  }
  set textContent(v) {
    this._text = String(v);
    this._html = "";
    this._htmlIsRaw = false;
    this.children = [];
  }
  get textContent() {
    if (this.children.length) return this.children.map((c) => c.textContent).join("");
    return this._text;
  }
  set innerHTML(v) {
    this._html = String(v);
    this._text = "";
    this._htmlIsRaw = true;
    // A browser parses the string; so does this, because escaping is exactly the thing
    // these tests are about and a stub that stores the string unparsed cannot show it.
    this.children = parseHtml(this._html, this.constructor);
  }
  get innerHTML() {
    if (this._htmlIsRaw) return this._html;
    return this.children.map((c) => c.outerHTML).join("");
  }
  get outerHTML() {
    const attrs = Object.entries(this.attributes)
      .map(([k, v]) => ` ${k}="${v}"`).join("");
    const cls = this.className ? ` class="${this.className}"` : "";
    return `<${this.tagName.toLowerCase()}${cls}${attrs}>${this.innerHTML}</${this.tagName.toLowerCase()}>`;
  }
  setAttribute(k, v) { this.attributes[k] = String(v); }
  getAttribute(k) { return this.attributes[k] ?? null; }
  appendChild(child) { this._htmlIsRaw = false; this.children.push(child); return child; }
  removeChild(child) { this.children = this.children.filter((c) => c !== child); }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  click() { (this.listeners.click || []).forEach((fn) => fn({ preventDefault() {} })); }
  /** Selectors here are only what the real code asks for: ".cls", "#id", "[attr=\"v\"]". */
  querySelector(sel) { return this._find(sel)[0] || null; }
  querySelectorAll(sel) { return this._find(sel); }
  _find(sel) {
    const out = [];
    const matches = (el) => {
      if (sel.startsWith(".")) return el.classList.contains(sel.slice(1));
      if (sel.startsWith("#")) return el.getAttribute("id") === sel.slice(1);
      const attr = sel.match(/^\[([a-z-]+)="?([^"\]]+)"?\]$/);
      if (attr) return el.getAttribute(attr[1]) === attr[2];
      return el.tagName === sel.toUpperCase();
    };
    const walk = (el) => { for (const c of el.children) { if (matches(c)) out.push(c); walk(c); } };
    walk(this);
    return out;
  }
}

const ENTITIES = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'" };
const decode = (t) => t.replace(/&(amp|lt|gt|quot|#39);/g, (m) => ENTITIES[m]);

/** Tags, attributes and text. Enough for the markup this interface actually writes. */
function parseHtml(html, ElClass) {
  const tokens = html.split(/(<\/?[a-zA-Z][^>]*>)/).filter((t) => t !== "");
  const out = [];
  const stack = [];
  const push = (node) => (stack.length ? stack[stack.length - 1].children : out).push(node);

  for (const token of tokens) {
    if (token.startsWith("</")) {
      stack.pop();
    } else if (token.startsWith("<")) {
      const tag = token.match(/^<([a-zA-Z][a-zA-Z0-9]*)/)[1];
      const node = new ElClass(tag);
      node._htmlIsRaw = false;
      for (const m of token.matchAll(/([a-zA-Z-]+)(?:="([^"]*)")?/g)) {
        if (m[1].toLowerCase() === tag.toLowerCase() && m.index <= tag.length) continue;
        if (m[1] === "class") node.className = decode(m[2] ?? "");
        else node.setAttribute(m[1], decode(m[2] ?? ""));
      }
      push(node);
      if (!token.endsWith("/>")) stack.push(node);
    } else if (token.trim() !== "") {
      const text = new ElClass("#text");
      text._text = decode(token);
      text._htmlIsRaw = false;
      push(text);
    }
  }
  return out;
}

export function installDom() {
  const root = new El("body");
  const document = {
    body: root,
    createElement: (tag) => new El(tag),
    querySelector: (s) => root.querySelector(s),
    querySelectorAll: (s) => root.querySelectorAll(s),
    activeElement: null,
  };
  globalThis.document = document;
  globalThis.window = {
    setTimeout: (...a) => setTimeout(...a),
    clearTimeout: (...a) => clearTimeout(...a),
    matchMedia: () => ({ matches: false }),
    location: { hostname: "localhost", host: "localhost:8765", protocol: "http:" },
    addEventListener() {},
  };
  // node defines navigator itself, read-only.
  Object.defineProperty(globalThis, "navigator", {
    value: { clipboard: { writeText: async () => {} } },
    configurable: true,
    writable: true,
  });
  globalThis.Blob = class { constructor(parts) { this.parts = parts; } };
  globalThis.URL = { createObjectURL: () => "blob:x", revokeObjectURL() {} };
  return { El, root, document };
}

/** The prompter's own container, built the way index.html builds it. */
export function buildPrompter(El, root) {
  const container = new El("div", "prompter-container");
  const badge = new El("div", "prompter-speaker-badge idle");
  const textWindow = new El("div", "prompter-text-window");
  const text = new El("div", "prompter-text empty");
  const slot = new El("div", "prompter-card-slot");
  const announcer = new El("p", "sr-only");
  announcer.setAttribute("id", "prompter-announcer");
  textWindow.appendChild(text);
  [badge, textWindow, slot, announcer].forEach((el) => container.appendChild(el));
  root.appendChild(container);
  return { container, badge, text, slot, announcer };
}

/** A websocket that opens when told to, and records what was sent through it. */
export class FakeSocket {
  static OPEN = 1;
  static instances = [];
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    this.sent = [];
    FakeSocket.instances.push(this);
  }
  open() { this.readyState = 1; this.onopen?.(); }
  deliver(obj) { this.onmessage?.({ data: JSON.stringify(obj) }); }
  send(data) { this.sent.push(data); }
  close() { this.readyState = 3; this.onclose?.(); }
}

export function installSocket() {
  FakeSocket.instances = [];
  globalThis.WebSocket = FakeSocket;
  return FakeSocket;
}
