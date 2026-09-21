/**
 * audio.js - Audio Recording (16kHz PCM) and Audio Playback Queue
 */

export class AudioController {
  constructor(onChunkCallback) {
    this.onChunk = onChunkCallback;
    this.audioContext = null;
    this.mediaStream = null;
    this.processor = null;
    this.isRecording = false;

    // Playback queue
    this.playContext = null;
    this.audioQueue = [];
    this.isPlaying = false;
  }

  async startRecording() {
    if (this.isRecording) return;

    this.mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: { ideal: 16000 },
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const source = this.audioContext.createMediaStreamSource(this.mediaStream);
    const inputSampleRate = this.audioContext.sampleRate;

    // Use ScriptProcessor for maximum browser compatibility (downsampling to 16kHz)
    const bufferSize = 4096;
    this.processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

    this.processor.onaudioprocess = (e) => {
      if (!this.isRecording) return;
      const inputData = e.inputBuffer.getChannelData(0);
      const downsampled16k = this._downsampleTo16k(inputData, inputSampleRate);
      if (downsampled16k && downsampled16k.byteLength > 0 && this.onChunk) {
        this.onChunk(downsampled16k);
      }
    };

    source.connect(this.processor);
    this.processor.connect(this.audioContext.destination);
    this.isRecording = true;
  }

  stopRecording() {
    if (!this.isRecording) return;
    this.isRecording = false;

    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => track.stop());
      this.mediaStream = null;
    }
  }

  /**
   * Convert Float32Array to 16kHz 16-bit signed PCM ArrayBuffer
   */
  _downsampleTo16k(buffer, sampleRate) {
    if (sampleRate === 16000) {
      const pcm16 = new Int16Array(buffer.length);
      for (let i = 0; i < buffer.length; i++) {
        const s = Math.max(-1, Math.min(1, buffer[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      return pcm16.buffer;
    }

    const ratio = sampleRate / 16000;
    const newLength = Math.round(buffer.length / ratio);
    const result = new Int16Array(newLength);

    for (let i = 0; i < newLength; i++) {
      const origIndex = Math.min(Math.round(i * ratio), buffer.length - 1);
      const s = Math.max(-1, Math.min(1, buffer[origIndex]));
      result[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return result.buffer;
  }

  /**
   * Play base64 encoded audio (WAV, MP3, etc.) through queue
   */
  enqueueAudio(base64Data, mimeType = "audio/wav") {
    this.audioQueue.push({ base64Data, mimeType });
    if (!this.isPlaying) {
      this._playNext();
    }
  }

  async _playNext() {
    if (this.audioQueue.length === 0) {
      this.isPlaying = false;
      return;
    }

    this.isPlaying = true;
    const item = this.audioQueue.shift();

    try {
      const binaryString = atob(item.base64Data);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      if (!this.playContext || this.playContext.state === "closed") {
        this.playContext = new (window.AudioContext || window.webkitAudioContext)();
      }

      const audioBuffer = await this.playContext.decodeAudioData(bytes.buffer.slice(0));
      const source = this.playContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(this.playContext.destination);

      source.onended = () => {
        this._playNext();
      };
      source.start();
    } catch (err) {
      console.warn("Erreur lecture audio queue:", err);
      this._playNext();
    }
  }

  stopPlayback() {
    this.audioQueue = [];
    if (this.playContext) {
      this.playContext.close();
      this.playContext = null;
    }
    this.isPlaying = false;
  }
}
