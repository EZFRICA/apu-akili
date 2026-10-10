/**
 * chat.js - Discussion canvas message stream renderer
 */

import { buildVisualFigure, buildVisualPending } from "../../shared/visual.js";

export class ChatRenderer {
  // A pupil who has just said something about their own life is not "blocked": the guard
  // separates the two outcomes, and so does what they are shown.
  static GUARD_BADGES = {
    on_topic: { css: "approved", label: "approved" },
    approved: { css: "approved", label: "approved" },
    uncertain: { css: "approved", label: "not checked" },
    off_topic: { css: "blocked", label: "school use only" },
    blocked: { css: "blocked", label: "school use only" },
    welfare: { css: "welfare", label: "personal" },
    error: { css: "error", label: "unavailable" },
  };

  constructor(containerEl) {
    this.container = containerEl;
    this.currentAssistantBubble = null;
    this.pendingVisual = null;
  }

  addUserMessage(text) {
    const row = document.createElement("div");
    row.className = "message-row user";
    row.innerHTML = `
      <div class="message-bubble">${this._escape(text)}</div>
      <div class="message-meta"><span>Student</span></div>
    `;
    this.container.appendChild(row);
    this._scrollToBottom();
    this.currentAssistantBubble = null;
  }

  streamAssistantToken(token, meta = {}) {
    if (!this.currentAssistantBubble) {
      const row = document.createElement("div");
      row.className = "message-row assistant";

      // The label a pupil reads, and the class that styles it. Both come from a fixed
      // table rather than from the message: never interpolate a server field into HTML.
      const badge = ChatRenderer.GUARD_BADGES[meta.guard_status];
      const badgeHtml = badge
        ? `<span class="guard-badge ${badge.css}">${this._escape(badge.label)}</span>`
        : "";

      row.innerHTML = `
        <div class="message-bubble"></div>
        <div class="message-meta">
          <span>APU Tutor</span>
          ${badgeHtml}
          ${meta.pipeline_ms ? `<span>${meta.pipeline_ms}ms</span>` : ""}
        </div>
      `;
      this.container.appendChild(row);
      this.currentAssistantBubble = row.querySelector(".message-bubble");
    }

    this.currentAssistantBubble.textContent += token;
    this._scrollToBottom();
  }

  addNotebookCard(title, content) {
    const card = document.createElement("div");
    card.className = "notebook-entry-card";
    card.innerHTML = `
      <div class="notebook-icon">📓</div>
      <div class="notebook-info">
        <div class="notebook-title">Saved to notebook: "${this._escape(title)}"</div>
        <div class="notebook-excerpt">${this._escape(content)}</div>
      </div>
    `;
    this.container.appendChild(card);
    this._scrollToBottom();
  }

  appendBrailleCard(cardElement) {
    this.container.appendChild(cardElement);
    this._scrollToBottom();
  }

  /** A picture is being drawn: said in the tutor's words, where the picture will be. */
  showVisualPending(text) {
    this._dropPendingVisual();
    this.pendingVisual = buildVisualPending(text);
    this.container.appendChild(this.pendingVisual);
    this._scrollToBottom();
  }

  /** The picture, after the answer that walks through it. */
  addVisual(src, description) {
    this._dropPendingVisual();
    this.container.appendChild(buildVisualFigure(src, description));
    this._scrollToBottom();
  }

  endTurn() {
    this.currentAssistantBubble = null;
    // A picture that could not be drawn leaves no spinner behind: the answer says why.
    this._dropPendingVisual();
  }

  _dropPendingVisual() {
    if (!this.pendingVisual) return;
    this.container.removeChild(this.pendingVisual);
    this.pendingVisual = null;
  }

  _scrollToBottom() {
    this.container.scrollTop = this.container.scrollHeight;
  }

  _escape(str) {
    return (str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
}
