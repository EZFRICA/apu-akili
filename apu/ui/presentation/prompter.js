/**
 * prompter.js - Continuous Stream Teleprompter for Keynote Presentation
 * Displays ONLY the active voice transcript (19px font) without accumulating previous turns.
 * Braille is displayed on-demand when the Braille button is clicked, adhering to accessibility standards.
 */

// Client-side Grade 1 Braille translator for instant tactile representation
const BRAILLE_G1_MAP = {
  a: "⠁", b: "⠃", c: "⠉", d: "⠙", e: "⠑", f: "⠋", g: "⠛", h: "⠓", i: "⠊", j: "⠚",
  k: "⠅", l: "⠇", m: "⠍", n: "⠝", o: "⠕", p: "⠏", q: "⠟", r: "⠗", s: "⠎", t: "⠞",
  u: "⠥", v: "⠧", w: "⠺", x: "⠭", y: "⠽", z: "⠵",
  " ": "⠀",
  ",": "⠂", ";": "⠆", ":": "⠒", ".": "⠲", "!": "⠖", "?": "⠦", "'": "⠄", "-": "⠤",
  "1": "⠼⠁", "2": "⠼⠃", "3": "⠼⠉", "4": "⠼⠙", "5": "⠼⠑",
  "6": "⠼⠋", "7": "⠼⠛", "8": "⠼⠓", "9": "⠼⠊", "0": "⠼⠚",
  "é": "⠿", "è": "⠮", "ê": "⠣", "à": "⠷", "â": "⠡", "ù": "⠾", "ç": "⠯", "î": "⠩", "ô": "⠹"
};

function textToBrailleG1(text) {
  if (!text) return "⠁⠏⠥ · ⠁⠅⠊⠇⠊";
  return text
    .toLowerCase()
    .split("")
    .map((ch) => BRAILLE_G1_MAP[ch] || ch)
    .join("");
}

export class PrompterController {
  constructor(containerEl) {
    this.container = containerEl;
    this.badgeEl = containerEl.querySelector(".prompter-speaker-badge");
    this.textWindow = containerEl.querySelector(".prompter-text-window");
    this.textEl = containerEl.querySelector(".prompter-text");
    this.cardSlot = containerEl.querySelector(".prompter-card-slot");
    this.announcerEl = containerEl.querySelector("#prompter-announcer");
    this.currentSpeaker = "idle";

    // Only the words being spoken right now are on screen. The flag, rather than a
    // comparison on the speaker, is what decides when a reply starts a fresh line:
    // the caller sets the speaker before streaming, so comparing it never cleared
    // anything and each answer was appended to the one before it.
    this.activeText = "";
    this.streamingReply = false;
    // Whether anything new was streamed since the last end of turn. A turn that only
    // acknowledges an action leaves the previous answer on screen, and reading that
    // answer out a second time is a screen reader repeating itself for no reason.
    this.unreadReply = false;

    // Cached braille data for active turn
    this.cachedBraille = null;
    this.brailleVisible = false;
  }

  setSpeaker(speaker) {
    this.currentSpeaker = speaker;
    if (this.badgeEl) {
      this.badgeEl.className = `prompter-speaker-badge ${speaker}`;
      if (speaker === "user") {
        this.badgeEl.innerHTML = `<span class="badge-pulse"></span>🎙️ Pupil speaking`;
      } else if (speaker === "assistant") {
        this.badgeEl.innerHTML = `<span class="badge-pulse"></span>✨ APU Akili answering`;
      } else if (speaker === "answered") {
        // The turn is over but the answer is still on screen: saying "waiting for voice"
        // over a full paragraph is the kind of small lie that makes an interface feel off.
        this.badgeEl.innerHTML = `<span>✨ Answer ready</span>`;
      } else {
        this.badgeEl.innerHTML = `<span>Waiting for voice…</span>`;
      }
    }
  }

  /**
   * Set user speech text. ONLY the active utterance is displayed.
   */
  setUserTranscript(text, isTemporaryStatus = false) {
    this.setSpeaker("user");
    this.streamingReply = false;
    this.activeText = text || "";
    
    if (this.textEl) {
      this.textEl.classList.remove("empty");
      this.textEl.textContent = this.activeText;
      this._scrollToBottom();
    }

    if (this.brailleVisible) {
      this._renderBrailleCard();
    }
  }

  /**
   * Stream assistant response token. ONLY the current assistant reply is displayed.
   */
  streamAssistantToken(token) {
    if (!this.streamingReply) {
      this.streamingReply = true;
      this.unreadReply = true;
      this.setSpeaker("assistant");
      this.activeText = "";
      if (this.textEl) {
        this.textEl.textContent = "";
        this.textEl.classList.remove("empty");
      }
    }

    this.activeText += token;
    if (this.textEl) {
      this.textEl.textContent = this.activeText;
      this._scrollToBottom();
    }

    if (this.brailleVisible) {
      this._renderBrailleCard();
    }
  }

  /**
   * Store received backend Braille data (liblouis grade 1 & grade 2)
   */
  setBrailleData(braillePayload) {
    this.cachedBraille = braillePayload;
    if (this.brailleVisible) {
      this._renderBrailleCard();
    }
  }

  /**
   * Toggle Braille card on/off when the user clicks the Braille button.
   * Conforms to web accessibility standards (ARIA, high-contrast, scalable text).
   */
  toggleBraille(forceState) {
    this.brailleVisible = forceState !== undefined ? forceState : !this.brailleVisible;
    this.container?.classList.toggle("braille-open", this.brailleVisible);

    if (!this.brailleVisible) {
      if (this.cardSlot) this.cardSlot.innerHTML = "";
      return false;
    }

    this._renderBrailleCard();
    return true;
  }

  /**
   * What is about to be embossed, laid out the way the paper will hold it.
   *
   * This card used to be a row of cells running off the side of a box, which is a screen's
   * idea of braille and not braille. Braille is printed: forty cells to a line, twenty-five
   * lines to a page, words wrapped at spaces. The server lays it out with the same embosser
   * code that writes the .BRF file, and this shows that layout, page by page, so what is on
   * screen is what a pupil would hold.
   */
  _renderBrailleCard() {
    if (!this.cardSlot) return;
    this.cardSlot.innerHTML = "";

    // Nothing yet means nothing shown. It used to fall back to cells spelling the product
    // name, which a pupil reading with their fingers would take for the answer: the same
    // rule the lab follows when liblouis gives it nothing.
    const emboss = this.cachedBraille?.emboss || null;
    const g1 = this.cachedBraille?.braille_g1 || this.cachedBraille?.braille_cells
               || (this.activeText ? textToBrailleG1(this.activeText) : "");
    const g2 = this.cachedBraille?.braille_g2 || g1;

    const card = document.createElement("section");
    card.className = "braille-keynote-card";
    card.setAttribute("role", "region");
    card.setAttribute("aria-label", "Braille output");
    card.setAttribute("aria-live", "polite");

    // These are plain strings. Escaping happens once, where they enter the markup below,
    // because a value escaped at the point it is built is escaped somewhere nobody looks
    // and the next person adds a line that skips it.
    const pageCount = emboss ? emboss.pages_unicode.length : 1;
    let sheet = "uncontracted cells, not laid out for paper";
    let sheetLabel = "Braille cells";
    if (emboss) {
      sheet = `${emboss.cells_per_line} cells x ${emboss.lines_per_page} lines`;
      sheetLabel = `Braille page, ${pageCount} page${pageCount > 1 ? "s" : ""}`;
    } else if (!g1) {
      sheet = "nothing to emboss yet";
      sheetLabel = "Nothing to emboss yet";
    }

    card.innerHTML = `
      <div class="braille-card-header">
        <div class="braille-title-group">
          <span class="braille-tag" aria-hidden="true">Braille output</span>
          <span class="braille-sub" id="braille-sheet-desc">${this._escape(sheet)}</span>
        </div>
        <div class="braille-grade-toggles" role="group" aria-label="Braille grade">
          <button class="braille-grade-btn active" data-grade="1" aria-pressed="true" aria-label="Show uncontracted grade 1 braille">Grade 1</button>
          <button class="braille-grade-btn" data-grade="2" aria-pressed="false" aria-label="Show contracted grade 2 braille">Grade 2</button>
          <button class="braille-close-btn" aria-label="Close the braille output" title="Close">X</button>
        </div>
      </div>

      <div class="braille-sheet" tabindex="0" role="group" aria-label="${this._escape(sheetLabel)}">
        <div class="braille-page" id="braille-page"></div>
      </div>

      <div class="braille-card-footer">
        <div class="braille-page-nav">
          <button class="braille-page-btn" data-step="-1" aria-label="Previous page">&lt;</button>
          <span class="braille-page-label" id="braille-page-label" aria-live="polite"></span>
          <button class="braille-page-btn" data-step="1" aria-label="Next page">&gt;</button>
        </div>
        <div class="braille-actions">
          <button class="btn-download-brf" aria-label="Download the embosser file"
                  title="The file a braille embosser prints from">.BRF</button>
        </div>
      </div>
    `;

    const pageEl = card.querySelector("#braille-page");
    const labelEl = card.querySelector("#braille-page-label");
    const g1Btn = card.querySelector('[data-grade="1"]');
    const g2Btn = card.querySelector('[data-grade="2"]');

    let grade = "1";
    let page = 0;

    // Grade 2 is what the server laid out, because that is what is embossed. Grade 1 has
    // no layout of its own, so it is shown as cells rather than as a page that would lie
    // about where the lines break.
    const render = () => {
      const laidOut = emboss && grade === "2";
      const lines = laidOut ? emboss.pages_unicode[page] : [g1];
      pageEl.className = `braille-page ${laidOut ? "as-printed" : "as-cells"}`;
      pageEl.textContent = lines.join("\n");
      // textContent, so a page number is never markup whatever the server sent.
      if (laidOut) {
        labelEl.textContent = `Page ${page + 1} of ${emboss.pages_unicode.length}`;
      } else if (g1) {
        labelEl.textContent = "Uncontracted cells";
      } else {
        labelEl.textContent = "Ask about your lesson first";
      }
      for (const button of card.querySelectorAll(".braille-page-btn")) {
        button.disabled = !laidOut || emboss.pages_unicode.length < 2;
      }
    };

    const setGrade = (next) => {
      grade = next;
      page = 0;
      g1Btn.classList.toggle("active", next === "1");
      g1Btn.setAttribute("aria-pressed", String(next === "1"));
      g2Btn.classList.toggle("active", next === "2");
      g2Btn.setAttribute("aria-pressed", String(next === "2"));
      render();
    };

    g1Btn.addEventListener("click", () => setGrade("1"));
    g2Btn.addEventListener("click", () => setGrade("2"));
    card.querySelector(".braille-close-btn").addEventListener("click", () => {
      this.toggleBraille(false);
    });

    for (const button of card.querySelectorAll(".braille-page-btn")) {
      button.addEventListener("click", () => {
        const step = Number(button.getAttribute("data-step"));
        const last = emboss ? emboss.pages_unicode.length - 1 : 0;
        page = Math.min(last, Math.max(0, page + step));
        render();
      });
    }

    card.querySelector(".btn-download-brf").addEventListener("click", () => {
      // The server's own BRF, written by the embosser that laid out the page above, not a
      // string this page assembled: the file and the preview cannot disagree.
      this._downloadBRF(emboss ? emboss.brf : g2, "apu_akili_lesson.brf");
    });

    this.cardSlot.appendChild(card);
    // Grade 2 when there is a page to show, since that is what comes out of the embosser.
    setGrade(emboss ? "2" : "1");
    this._scrollToBottom();
  }

  _downloadBRF(brailleContent, filename = "lesson.brf") {
    const blob = new Blob([brailleContent], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  _escape(str) {
    return String(str ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /**
   * Something the device did, said rather than printed.
   *
   * "Here is the braille transcription of our last explanation" is a sentence about the
   * cells, not a lesson. On the prompter it replaced the explanation the pupil had just
   * asked to have embossed, which is the text those cells hold.
   *
   * So it is spoken, and read once to a screen reader, and that is all. Nothing is drawn:
   * a sighted reader already sees the page of cells appear, which says the same thing
   * better, and a badge here is overwritten by the end of the turn a second later anyway.
   */
  announceAction(message) {
    if (!message) return;
    this._announce(message);
  }

  endTurn() {
    // The answer stays readable after the voice stops; the next one replaces it.
    this.streamingReply = false;
    this.setSpeaker(this.activeText ? "answered" : "idle");
    if (this.unreadReply) {
      this._announce(this.activeText);
      this.unreadReply = false;
    }
  }

  /** Say it once, whole. Streaming into a live region reads a sentence word by word. */
  _announce(text) {
    if (!this.announcerEl || !text) return;
    window.clearTimeout(this._announceTimer);
    this.announcerEl.textContent = "";
    // The empty write first, so the same answer twice is still announced twice.
    this._announceTimer = window.setTimeout(() => {
      this.announcerEl.textContent = text;
    }, 60);
  }

  /**
   * Something went wrong, said on the prompter and to the screen reader.
   *
   * A failure used to live in the status pill alone: eleven characters of grey text in a
   * corner, which a pupil who cannot see the screen was never told about at all.
   */
  showNotice(message) {
    this.streamingReply = false;
    this.setSpeaker("idle");
    this.activeText = "";
    if (this.textEl) {
      this.textEl.textContent = message;
      this.textEl.classList.add("empty");
    }
    this._announce(message);
  }

  reset() {
    this.setSpeaker("idle");
    this.streamingReply = false;
    this.unreadReply = false;
    this.activeText = "";
    this.cachedBraille = null;
    this.brailleVisible = false;
    if (this.textEl) {
      this.textEl.textContent = "Speak or press a tactile button on Pocket Akili below…";
      this.textEl.classList.add("empty");
    }
    if (this.cardSlot) this.cardSlot.innerHTML = "";
  }

  _scrollToBottom() {
    if (this.textWindow) {
      this.textWindow.scrollTop = this.textWindow.scrollHeight;
    }
  }
}
