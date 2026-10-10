/** A picture the tutor drew, run rather than read: the shared builders and the stage. */
import assert from "node:assert/strict";
import { installDom, buildPrompter } from "./dom_stub.mjs";

const { El, root } = installDom();
const { visualSource, buildVisualFigure, buildVisualPending } =
  await import("../../apu/ui/shared/visual.js");
const { PrompterController } = await import("../../apu/ui/presentation/prompter.js");

const cases = [];
const test = (name, fn) => cases.push([name, fn]);
const fresh = () => {
  root.children = [];
  const dom = buildPrompter(El, root);
  return { p: new PrompterController(dom.container), dom };
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const SRC = "data:image/jpeg;base64,AAAA";
const find = (el, tag) => el.querySelectorAll(tag);

test("only a picture becomes a data URL", () => {
  assert.equal(visualSource({ image: "AAAA", mime: "image/jpeg" }), SRC);
  assert.equal(visualSource({ image: "AAAA", mime: "text/html" }), null,
               "a message cannot smuggle a page in where a picture goes");
  assert.equal(visualSource({ mime: "image/png" }), null);
  assert.equal(visualSource(null), null);
});

test("the description is the picture's alt, and stays text", () => {
  const figure = buildVisualFigure(SRC, "<b>3/4</b> of a pizza");
  const [image] = find(figure, "img");
  const [caption] = find(figure, "figcaption");
  assert.equal(image.getAttribute("alt"), "<b>3/4</b> of a pizza");
  assert.equal(caption.textContent, "<b>3/4</b> of a pizza");
  assert.equal(find(figure, "b").length, 0, "no markup was parsed out of the description");
  assert.equal(caption.getAttribute("aria-hidden"), "true",
               "read once, from the alt, not a second time from the caption");
});

test("a picture with no description still has an alt", () => {
  const [image] = find(buildVisualFigure(SRC, ""), "img");
  assert.ok(image.getAttribute("alt"), "an image with an empty alt is skipped by a screen reader");
});

test("the waiting card is a status, in the tutor's words", () => {
  const card = buildVisualPending("Je te dessine ça.");
  assert.equal(card.getAttribute("role"), "status");
  assert.equal(card.textContent, "Je te dessine ça.");
});

test("the stage shows and announces the wait, then the answer replaces it", async () => {
  const { p, dom } = fresh();
  p.showVisualPending("I am drawing it for you.");
  assert.equal(find(dom.slot, ".pending").length, 1);
  await sleep(80);
  assert.equal(dom.announcer.textContent, "I am drawing it for you.");

  p.streamAssistantToken("Look at the pizza.");
  assert.equal(dom.slot.children.length, 0, "the wait is over once the answer starts");

  p.showVisual(SRC, "A pizza in four.");
  const [image] = find(dom.slot, "img");
  assert.equal(image.getAttribute("src"), SRC);
});

test("the braille page covers the picture and gives it back when closed", () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("Look at the pizza.");
  p.showVisual(SRC, "A pizza in four.");
  p.toggleBraille(true);
  assert.equal(find(dom.slot, "img").length, 0, "the cells are what was asked for");
  p.showVisual(SRC, "A pizza in four.");
  assert.equal(find(dom.slot, "img").length, 0, "a picture arriving does not push them away");
  p.toggleBraille(false);
  assert.equal(find(dom.slot, "img").length, 1);
});

test("the prompter makes room for the picture, as it does for the braille page", () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("Look at the pizza.");
  p.showVisual(SRC, "A pizza in four.");
  assert.ok(dom.container.classList.contains("visual-open"),
            "at full height the prompter pushed the picture behind the device");
  p.toggleBraille(true);
  assert.ok(!dom.container.classList.contains("visual-open"), "the braille page has the room");
  p.toggleBraille(false);
  assert.ok(dom.container.classList.contains("visual-open"));
  p.streamAssistantToken("x");
  p.endTurn();
  p.streamAssistantToken("Next answer.");
  assert.ok(!dom.container.classList.contains("visual-open"), "no picture, no room kept for one");
});

test("the next answer takes the previous picture away", () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("Look at the pizza.");
  p.showVisual(SRC, "A pizza in four.");
  p.endTurn();
  p.streamAssistantToken("Now, the perimeter.");
  assert.equal(find(dom.slot, "img").length, 0, "a picture is about the answer it came with");
});

let failed = 0;
for (const [name, fn] of cases) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL ${name}\n     ${error.message}`);
  }
}
console.log(`${cases.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
