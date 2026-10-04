/** The resampler every front end's microphone goes through. */
import assert from "node:assert/strict";
import { installDom } from "./dom_stub.mjs";

installDom();
const { downsampleTo16k } = await import("../../apu/ui/shared/audio.js");

const cases = [];
const test = (name, fn) => cases.push([name, fn]);
const out = (floats, rate) => new Int16Array(downsampleTo16k(floats, rate));

test("48 kHz becomes 16 kHz, a third of the samples", () => {
  const result = out(new Float32Array(4800).fill(0.5), 48000);
  assert.equal(result.length, 1600);
  assert.ok(Math.abs(result[0] - 0.5 * 0x7fff) < 2, "half scale stays half scale");
});

test("already 16 kHz audio is converted sample for sample", () => {
  const result = out(new Float32Array(320).fill(-1), 16000);
  assert.equal(result.length, 320);
  assert.equal(result[0], -0x8000);
});

test("what cannot be heard at 16 kHz is removed, not folded into the speech", () => {
  // 24 kHz at a 48 kHz rate: the fastest signal there is, far above what 16 kHz can
  // carry. Taking one sample in three keeps it at full scale as a false low tone; the
  // weighted window is what makes it disappear, which is what a filter is for.
  const input = new Float32Array(4800);
  for (let i = 0; i < input.length; i++) input[i] = i % 2 === 0 ? 1 : -1;
  const result = out(input, 48000);

  // Measured away from the two ends, where the window runs off the edge of the chunk and
  // is lopsided. That is two samples in sixteen hundred, at every chunk boundary.
  const peak = Math.max(...Array.from(result.slice(2, -2), Math.abs));
  assert.ok(peak < 0.15 * 0x7fff,
            `aliased tone survived at ${(peak / 0x7fff).toFixed(2)} of full scale`);
  const edges = Math.max(Math.abs(result[0]), Math.abs(result[result.length - 1]));
  assert.ok(edges < 0.4 * 0x7fff, "even the lopsided window at a chunk edge attenuates it");
});

test("a real tone the band can carry comes through at its own strength", () => {
  // 440 Hz at 48 kHz: well inside what 16 kHz carries, so the filter must leave it alone.
  const input = new Float32Array(4800);
  for (let i = 0; i < input.length; i++) input[i] = Math.sin((2 * Math.PI * 440 * i) / 48000);
  const peak = Math.max(...Array.from(out(input, 48000).slice(4, -4), Math.abs));
  assert.ok(peak > 0.9 * 0x7fff, `a 440 Hz tone lost ${(1 - peak / 0x7fff).toFixed(2)} of itself`);
});

test("44.1 kHz, which is what a lot of hardware actually reports, also converts", () => {
  assert.equal(out(new Float32Array(4410).fill(0.25), 44100).length, 1600);
});

test("a buffer shorter than one output sample does not produce a sample out of nothing", () => {
  assert.equal(out(new Float32Array(2).fill(1), 48000).length, 0);
});

test("silence stays silence", () => {
  assert.ok(out(new Float32Array(4800), 44100).every((s) => s === 0));
});

test("a signal beyond full scale is clamped rather than wrapped", () => {
  const result = out(new Float32Array(4800).fill(4), 48000);
  assert.equal(result[800], 0x7fff, "wrapping would turn a loud pupil into a crackle");
});

let failed = 0;
for (const [name, fn] of cases) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (err) {
    failed++;
    console.log(`FAIL ${name}\n     ${err.message.split("\n")[0]}`);
  }
}
console.log(`\n${cases.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
