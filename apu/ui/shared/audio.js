/**
 * The microphone and the loudspeaker, for every front end that talks to the live lab.
 *
 * This file used to exist twice, once in the lab's own page and once in the keynote stage,
 * written separately against the same server. Two of the defects fixed in one copy were
 * still running in the other months later: the decimation that folded half the spectrum
 * back into the speech, and the microphone wired to the speakers of the room it records.
 * Plumbing that knows the protocol and nothing about the decor belongs in one place.
 */

const TARGET_RATE = 16000;

/**
 * Float samples at any rate, to 16 kHz signed 16-bit PCM.
 *
 * The low-pass is the point. 16 kHz cannot carry what 48 kHz holds, and whatever is left
 * above 8 kHz comes back as a false low tone in the middle of the speech. Taking one
 * sample in three keeps that tone at full strength; the mean of each window divides it by
 * three; these triangular weights, spread over twice the window, take it down by more than
 * twenty, for six multiplications per output sample.
 */
export function downsampleTo16k(buffer, sampleRate) {
  if (sampleRate === TARGET_RATE) {
    const pcm16 = new Int16Array(buffer.length);
    for (let i = 0; i < buffer.length; i++) {
      const sample = Math.max(-1, Math.min(1, buffer[i]));
      pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return pcm16.buffer;
  }

  const ratio = sampleRate / TARGET_RATE;
  const newLength = Math.floor(buffer.length / ratio);
  const result = new Int16Array(newLength);

  for (let i = 0; i < newLength; i++) {
    const centre = i * ratio;
    const first = Math.max(0, Math.ceil(centre - ratio));
    const last = Math.min(buffer.length - 1, Math.floor(centre + ratio));
    let sum = 0;
    let weightSum = 0;
    for (let j = first; j <= last; j++) {
      const weight = 1 - Math.abs(j - centre) / ratio;
      if (weight <= 0) continue;
      sum += buffer[j] * weight;
      weightSum += weight;
    }
    const mean = weightSum > 0 ? sum / weightSum : 0;
    const clamped = Math.max(-1, Math.min(1, mean));
    result[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
  }
  return result.buffer;
}

/** The microphone, as 16 kHz PCM chunks handed to a callback. */
export class MicrophoneStream {
  constructor({ onChunk } = {}) {
    this.onChunk = onChunk || (() => {});
    this.audioContext = null;
    this.mediaStream = null;
    this.processor = null;
    this.sink = null;
    this.isRecording = false;
  }

  /** True if the microphone is open. Never throws: a refused microphone is an answer. */
  async start() {
    if (this.isRecording) return true;

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("This browser does not expose a microphone.");
      }

      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: { ideal: TARGET_RATE },
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx();
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }

      const source = this.audioContext.createMediaStreamSource(this.mediaStream);
      const inputRate = this.audioContext.sampleRate;
      this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);

      this.processor.onaudioprocess = (event) => {
        if (!this.isRecording) return;
        const chunk = downsampleTo16k(event.inputBuffer.getChannelData(0), inputRate);
        if (chunk && chunk.byteLength > 0) this.onChunk(chunk);
      };

      source.connect(this.processor);
      // Silent sink: the node only runs if something downstream pulls it, and sending a
      // live microphone to the speakers of the room it is recording is a feedback loop.
      this.sink = this.audioContext.createGain();
      this.sink.gain.value = 0;
      this.processor.connect(this.sink);
      this.sink.connect(this.audioContext.destination);

      this.isRecording = true;
      return true;
    } catch (err) {
      console.warn("Microphone unavailable:", err);
      this.stop();
      this.isRecording = false;
      return false;
    }
  }

  stop() {
    this.isRecording = false;

    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }
    if (this.sink) {
      this.sink.disconnect();
      this.sink = null;
    }
    if (this.audioContext) {
      this.audioContext.close().catch(() => {});
      this.audioContext = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
  }
}

/** The tutor's voice, played in the order it arrives. */
export class AudioPlayback {
  constructor() {
    this.context = null;
    this.queue = [];
    this.isPlaying = false;
  }

  enqueue(base64Data, mimeType = "audio/wav") {
    if (!base64Data) return;
    this.queue.push({ base64Data, mimeType });
    if (!this.isPlaying) this._playNext();
  }

  async _playNext() {
    if (this.queue.length === 0) {
      this.isPlaying = false;
      return;
    }

    this.isPlaying = true;
    const item = this.queue.shift();

    try {
      const binary = atob(item.base64Data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

      if (!this.context || this.context.state === "closed") {
        this.context = new (window.AudioContext || window.webkitAudioContext)();
      }

      const buffer = await this.context.decodeAudioData(bytes.buffer.slice(0));
      const source = this.context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.context.destination);
      source.onended = () => this._playNext();
      source.start();
    } catch (err) {
      // One clip that will not decode must not stop the ones behind it.
      console.warn("Audio decoding error:", err);
      this._playNext();
    }
  }

  stop() {
    this.queue = [];
    if (this.context) {
      this.context.close().catch(() => {});
      this.context = null;
    }
    this.isPlaying = false;
  }
}
