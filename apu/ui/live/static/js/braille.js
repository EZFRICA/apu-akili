/**
 * braille.js - Braille card rendering, Grade 1 / Grade 2 toggle, and BRF export
 */

export class BrailleManager {
  /**
   * Create a tactile Braille card element
   */
  createCard(originalText, brailleG1, brailleG2) {
    const card = document.createElement("div");
    card.className = "braille-card";

    card.innerHTML = `
      <div class="braille-card-header">
        <div class="braille-card-title">
          <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
          Braille Format
        </div>
        <div class="braille-grade-toggles">
          <button class="grade-btn active" data-grade="1">Grade 1</button>
          <button class="grade-btn" data-grade="2">Grade 2</button>
        </div>
      </div>
      <div class="braille-card-body">
        <div class="braille-dots-text">${this._escape(brailleG1)}</div>
      </div>
      <div class="braille-card-footer">
        <button class="btn-download-brf">
          <svg viewBox="0 0 24 24"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM17 13l-5 5-5-5h3V9h4v4h3z"/></svg>
          Download .BRF
        </button>
      </div>
    `;

    const g1Btn = card.querySelector('[data-grade="1"]');
    const g2Btn = card.querySelector('[data-grade="2"]');
    const dotsEl = card.querySelector(".braille-dots-text");
    const downloadBtn = card.querySelector(".btn-download-brf");

    g1Btn.addEventListener("click", () => {
      g1Btn.classList.add("active");
      g2Btn.classList.remove("active");
      dotsEl.textContent = brailleG1;
    });

    g2Btn.addEventListener("click", () => {
      g2Btn.classList.add("active");
      g1Btn.classList.remove("active");
      dotsEl.textContent = brailleG2;
    });

    downloadBtn.addEventListener("click", () => {
      const activeGrade = g1Btn.classList.contains("active") ? "1" : "2";
      const content = activeGrade === "1" ? brailleG1 : brailleG2;
      this.downloadBRF(content, "braille_explanation.brf");
    });

    return card;
  }

  downloadBRF(brailleContent, filename = "document.brf") {
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
    return (str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }
}
