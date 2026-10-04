/**
 * camera.js - the presenter's camera, and the silhouette that stands in for it.
 *
 * Video only. The microphone belongs to bridge.js, which needs it at 16 kHz and streams
 * it; asking for both here would take the device twice.
 */

export class CameraController {
  constructor(videoElement, onStatusChange) {
    this.video = videoElement;
    this.onStatusChange = onStatusChange || (() => {});
    this.stream = null;
    this.isActive = false;
    this.isMirrored = true;
    this.simulatedAnimId = null;
  }

  async start() {
    this.onStatusChange("requesting", "Accessing camera…");

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("getUserMedia not supported");
      }

      // Request video stream exclusively (microphone is handled independently by bridge/audio)
      this.stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1920 },
          height: { ideal: 1080 },
          facingMode: "user"
        },
        audio: false
      });

      this.video.srcObject = this.stream;
      await this.video.play().catch(() => {});
      this.isActive = true;

      if (this.simulatedAnimId) {
        cancelAnimationFrame(this.simulatedAnimId);
        this.simulatedAnimId = null;
      }
      this.onStatusChange("active", "Camera Live (HD)");
      return true;
    } catch (err) {
      console.warn("Camera permission denied or unavailable:", err.message);
      this.isActive = false;
      this._startSimulatedPresenter();
      this.onStatusChange("simulated", "Presenter Stage (Simulated)");
      return false;
    }
  }

  stop() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }
    if (this.simulatedAnimId) {
      cancelAnimationFrame(this.simulatedAnimId);
      this.simulatedAnimId = null;
    }
    this.video.srcObject = null;
    this.isActive = false;
    this.onStatusChange("off", "Camera Inactive");
  }

  toggleMirror() {
    this.isMirrored = !this.isMirrored;
    this.video.style.transform = this.isMirrored ? "scaleX(-1)" : "scaleX(1)";
  }

  _startSimulatedPresenter() {
    if (this.simulatedAnimId) return;

    const canvas = document.createElement("canvas");
    canvas.width = 1280;
    canvas.height = 720;
    const ctx = canvas.getContext("2d");

    // The stand-in drifts and glows. Asked for less motion, it is drawn once and left
    // there: a still silhouette says the same thing as a breathing one.
    const still = window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let angle = 0;
    const renderSim = () => {
      if (this.isActive) return;
      angle += 0.012;

      // Transparent clearing so background gradient shines through at 80% opacity
      ctx.clearRect(0, 0, 1280, 720);

      // Subtle dynamic aura / keynote spotlight
      const auraX = 640 + Math.sin(angle * 0.6) * 35;
      const auraY = 220 + Math.cos(angle * 0.4) * 18;
      const aura = ctx.createRadialGradient(auraX, auraY, 10, auraX, auraY, 280);
      aura.addColorStop(0, "rgba(255, 255, 255, 0.28)");
      aura.addColorStop(0.5, "rgba(255, 255, 255, 0.08)");
      aura.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = aura;
      ctx.fillRect(0, 0, 1280, 720);

      // Presenter Head & Shoulders Silhouette
      ctx.save();
      ctx.fillStyle = "rgba(18, 12, 18, 0.75)";
      ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
      ctx.lineWidth = 2.5;

      // Head
      ctx.beginPath();
      ctx.arc(640, 220, 68, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Torso / Shoulders
      ctx.beginPath();
      ctx.ellipse(640, 460, 200, 150, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Soft rim highlight on head
      const rim = ctx.createLinearGradient(600, 150, 680, 220);
      rim.addColorStop(0, "rgba(255, 255, 255, 0.8)");
      rim.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = rim;
      ctx.beginPath();
      ctx.arc(640, 220, 66, -Math.PI * 0.8, -Math.PI * 0.2);
      ctx.lineWidth = 3.5;
      ctx.strokeStyle = rim;
      ctx.stroke();

      ctx.restore();

      if (!still) {
        this.simulatedAnimId = requestAnimationFrame(renderSim);
      }
    };

    const stream = canvas.captureStream(30);
    this.video.srcObject = stream;
    this.video.play().catch(() => {});
    renderSim();
  }
}
