/**
 * prompter.js - Teleprompter layout for real-time speech and subtitles
 */

export class PrompterRenderer {
  constructor(containerEl) {
    this.container = containerEl;
    this.badgeEl = containerEl.querySelector(".prompter-speaker-badge");
    this.textEl = containerEl.querySelector(".prompter-text");
    this.cardSlot = containerEl.querySelector(".prompter-card-slot");
    this.currentSpeaker = "idle";
  }

  setSpeaker(speaker) {
    this.currentSpeaker = speaker;
    this.badgeEl.className = `prompter-speaker-badge ${speaker}`;
    if (speaker === "user") {
      this.badgeEl.textContent = "🎙️ Student speaking…";
    } else if (speaker === "assistant") {
      this.badgeEl.textContent = "✨ APU answering…";
    } else {
      this.badgeEl.textContent = "Waiting for voice…";
    }
  }

  setUserTranscript(text, replace = true) {
    this.setSpeaker("user");
    if (this.cardSlot) this.cardSlot.innerHTML = "";
    this.textEl.classList.remove("empty");
    if (replace) {
      this.textEl.textContent = text;
    } else {
      this.textEl.textContent += text;
    }
  }

  streamAssistantToken(token) {
    if (this.currentSpeaker !== "assistant") {
      this.setSpeaker("assistant");
      this.textEl.textContent = "";
      this.textEl.classList.remove("empty");
      if (this.cardSlot) this.cardSlot.innerHTML = "";
    }
    this.textEl.textContent += token;
  }

  appendBrailleCard(cardElement) {
    if (this.cardSlot) {
      this.cardSlot.innerHTML = "";
      this.cardSlot.appendChild(cardElement);
    }
  }

  endTurn() {
    this.setSpeaker("idle");
  }

  reset() {
    this.setSpeaker("idle");
    this.textEl.textContent = "Speak or click the microphone to begin…";
    this.textEl.classList.add("empty");
    if (this.cardSlot) this.cardSlot.innerHTML = "";
  }
}
