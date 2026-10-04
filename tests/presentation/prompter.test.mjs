/** The teleprompter, run rather than read. */
import assert from "node:assert/strict";
import { installDom, buildPrompter } from "./dom_stub.mjs";

const { El, root } = installDom();
const { PrompterController } = await import("../../apu/ui/presentation/prompter.js");

const cases = [];
const test = (name, fn) => cases.push([name, fn]);
const fresh = () => {
  root.children = [];
  const dom = buildPrompter(El, root);
  return { p: new PrompterController(dom.container), dom };
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("a second answer replaces the first instead of being added to it", () => {
  const { p, dom } = fresh();
  "Twelve.".split("").forEach((c) => p.streamAssistantToken(c));
  p.endTurn();
  assert.equal(dom.text.textContent, "Twelve.");
  "Nine.".split("").forEach((c) => p.streamAssistantToken(c));
  assert.equal(dom.text.textContent, "Nine.", "the previous turn is gone from the screen");
});

test("the speaker being set before the stream does not stop the line being cleared", () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("A");
  p.endTurn();
  p.setSpeaker("assistant");          // what presentation.js does on every token
  p.streamAssistantToken("B");
  assert.equal(dom.text.textContent, "B");
});

test("the pupil's words give way to the answer", () => {
  const { p, dom } = fresh();
  p.setUserTranscript("What is a perimeter?");
  assert.equal(dom.text.textContent, "What is a perimeter?");
  p.streamAssistantToken("It is ");
  p.streamAssistantToken("the way round.");
  assert.equal(dom.text.textContent, "It is the way round.");
});

test("the badge says which of the three states the stage is in", () => {
  const { p, dom } = fresh();
  p.setUserTranscript("Hello");
  assert.match(dom.badge.innerHTML, /Pupil speaking/);
  p.streamAssistantToken("Hi");
  assert.match(dom.badge.innerHTML, /answering/);
  p.endTurn();
  assert.match(dom.badge.innerHTML, /Answer ready/, "not 'waiting' over a full paragraph");
});

test("an empty turn ends back at waiting, not at an answer that is not there", () => {
  const { p, dom } = fresh();
  p.endTurn();
  assert.match(dom.badge.innerHTML, /Waiting for voice/);
});

test("the whole sentence reaches the live region once, when it is whole", async () => {
  const { p, dom } = fresh();
  for (const token of ["A ", "perimeter ", "is ", "the ", "way ", "round."]) {
    p.streamAssistantToken(token);
  }
  assert.equal(dom.announcer.textContent, "", "nothing is announced token by token");
  p.endTurn();
  await sleep(120);
  assert.equal(dom.announcer.textContent, "A perimeter is the way round.");
});

test("the same answer twice is announced twice", async () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("Yes.");
  p.endTurn();
  await sleep(120);
  assert.equal(dom.announcer.textContent, "Yes.");
  p.streamAssistantToken("Yes.");
  p.endTurn();
  assert.equal(dom.announcer.textContent, "", "cleared first, or the reader says nothing");
  await sleep(120);
  assert.equal(dom.announcer.textContent, "Yes.");
});

test("two turns ending within the announcement delay leave the later one on the region", async () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("First.");
  p.endTurn();
  p.streamAssistantToken("Second.");
  p.endTurn();
  await sleep(150);
  assert.equal(dom.announcer.textContent, "Second.");
});

test("an answer overtaken by a failure is not read out after it", async () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("Twelve centimetres.");
  p.endTurn();
  await sleep(30);                    // the announcement is scheduled, not yet made
  p.showNotice("Something went wrong. Try again.");
  // Just after the first announcement was due. Its timer has to have been cancelled, or a
  // reader says the answer out loud and only then hears that it failed.
  await sleep(45);
  assert.equal(dom.announcer.textContent, "",
               "the superseded answer was announced on top of the failure");
  await sleep(120);
  assert.equal(dom.announcer.textContent, "Something went wrong. Try again.");
});

test("a failure is on the prompter and in the pupil's ear, not only in a corner", async () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("half an ans");
  p.showNotice("Something went wrong. Try again.");
  assert.equal(dom.text.textContent, "Something went wrong. Try again.");
  assert.equal(p.activeText, "", "the half-written answer is not left to be read as one");
  await sleep(120);
  assert.equal(dom.announcer.textContent, "Something went wrong. Try again.");
});

// A braille job as the lab sends it: cells, and the same text laid out by the embosser.
const EMBOSS = {
  braille_g1: "⠠⠞⠓⠑⠀⠏⠑⠗⠊⠍⠑⠞⠑⠗",
  braille_g2: "⠠⠮⠀⠏⠻⠊⠍⠑⠞⠻",
  emboss: {
    pages: [["line one", "line two"], ["page two line"]],
    pages_unicode: [["⠠⠮⠀⠕⠝⠑", "⠠⠮⠀⠞⠺⠕"], ["⠠⠏⠁⠛⠑⠀⠞⠺⠕"]],
    cells_per_line: 40,
    lines_per_page: 25,
    brf: ",! ONE\n,! TWO\f,PAGE TWO",
  },
};

test("what is shown is the page the embosser laid out, not a row of cells", () => {
  const { p, dom } = fresh();
  p.setBrailleData(EMBOSS);
  p.toggleBraille(true);
  const page = dom.slot.querySelector("#braille-page");
  assert.equal(page.textContent, "⠠⠮⠀⠕⠝⠑\n⠠⠮⠀⠞⠺⠕", "the embosser's own line breaks");
  assert.ok(page.classList.contains("as-printed"));
  assert.match(dom.slot.querySelector("#braille-page-label").textContent, /Page 1 of 2/);
});

test("the sheet says how much paper it is", () => {
  const { p, dom } = fresh();
  p.setBrailleData(EMBOSS);
  p.toggleBraille(true);
  assert.match(dom.slot.querySelector("#braille-sheet-desc").textContent,
               /40 cells x 25 lines/);
});

test("a second page can be turned to, and the first cannot be turned back past", () => {
  const { p, dom } = fresh();
  p.setBrailleData(EMBOSS);
  p.toggleBraille(true);
  const page = dom.slot.querySelector("#braille-page");
  const label = dom.slot.querySelector("#braille-page-label");
  const [back, forward] = dom.slot.querySelectorAll(".braille-page-btn");

  forward.click();
  assert.equal(page.textContent, "⠠⠏⠁⠛⠑⠀⠞⠺⠕");
  assert.match(label.textContent, /Page 2 of 2/);
  forward.click();
  assert.match(label.textContent, /Page 2 of 2/, "there is no third page to turn to");
  back.click();
  assert.match(label.textContent, /Page 1 of 2/);
  back.click();
  assert.match(label.textContent, /Page 1 of 2/, "and none before the first");
});

test("grade 1 is shown as cells, because the embosser laid out grade 2", () => {
  const { p, dom } = fresh();
  p.setBrailleData(EMBOSS);
  p.toggleBraille(true);
  dom.slot.querySelector('[data-grade="1"]').click();
  const page = dom.slot.querySelector("#braille-page");
  assert.equal(page.textContent, EMBOSS.braille_g1);
  assert.ok(page.classList.contains("as-cells"), "cells must not pretend to be a page");
  assert.match(dom.slot.querySelector("#braille-page-label").textContent, /Uncontracted/);
  assert.ok(dom.slot.querySelectorAll(".braille-page-btn").every((b) => b.disabled),
            "there are no pages to turn in a row of cells");
});

test("the grade it opens on is the one that is embossed", () => {
  const { p, dom } = fresh();
  p.setBrailleData(EMBOSS);
  p.toggleBraille(true);
  assert.equal(dom.slot.querySelector('[data-grade="2"]').getAttribute("aria-pressed"), "true");
});

test("the file offered is the embosser's own, not one this page assembled", () => {
  const { p, dom } = fresh();
  p.setBrailleData(EMBOSS);
  p.toggleBraille(true);
  let downloaded = null;
  p._downloadBRF = (content) => { downloaded = content; };
  dom.slot.querySelector(".btn-download-brf").click();
  assert.equal(downloaded, EMBOSS.emboss.brf,
               "the preview and the file would otherwise be able to disagree");
  assert.ok(downloaded.includes("\f"), "a form feed is where the page ends on paper");
});

test("without a layout the card still shows cells rather than an empty sheet", () => {
  const { p, dom } = fresh();
  p.setBrailleData({ braille_g1: "⠁⠃⠉" });
  p.toggleBraille(true);
  assert.equal(dom.slot.querySelector("#braille-page").textContent, "⠁⠃⠉");
  assert.match(dom.slot.querySelector("#braille-sheet-desc").textContent, /not laid out/);
});

test("braille from the server is text, not markup", () => {
  const { p, dom } = fresh();
  p.setBrailleData({ braille_g1: '<img src=x onerror="alert(1)">' });
  p.toggleBraille(true);
  assert.ok(!dom.slot.innerHTML.includes("<img"), "the server's cells became an element");
});

test("even a page count from the server is text", () => {
  const { p, dom } = fresh();
  p.setBrailleData({ braille_g1: "⠁", emboss: { ...EMBOSS.emboss, cells_per_line: '"><img>' } });
  p.toggleBraille(true);
  assert.ok(!dom.slot.innerHTML.includes("<img"));
});

test("the braille card goes away when it is closed, and takes its room with it", () => {
  const { p, dom } = fresh();
  p.setBrailleData(EMBOSS);
  assert.equal(p.toggleBraille(), true);
  assert.ok(dom.slot.innerHTML.length > 0);
  assert.equal(p.toggleBraille(), false);
  assert.equal(dom.slot.innerHTML, "", "an empty slot is what the stylesheet collapses");
});

test("the close button on the card closes it", () => {
  const { p, dom } = fresh();
  p.toggleBraille(true);
  dom.slot.querySelector(".braille-close-btn").click();
  assert.equal(p.brailleVisible, false);
  assert.equal(dom.slot.innerHTML, "");
});

test("k and l are different letters", () => {
  const { p, dom } = fresh();
  p.setUserTranscript("kl");
  p.toggleBraille(true);
  assert.equal(dom.slot.querySelector("#braille-page").textContent, "⠅⠇",
               "k is dots 1 and 3; mapping it to l hides a letter");
});

test("the sheet is announced to a reader and can be reached by keyboard", () => {
  const { p, dom } = fresh();
  p.setBrailleData(EMBOSS);
  p.toggleBraille(true);
  assert.equal(dom.slot.querySelector(".braille-keynote-card").getAttribute("aria-live"), "polite");
  const sheet = dom.slot.querySelector(".braille-sheet");
  assert.equal(sheet.getAttribute("tabindex"), "0");
  assert.match(sheet.getAttribute("aria-label"), /2 pages/);
});

test("a turn that only acknowledges does not read the previous answer out again", async () => {
  const { p, dom } = fresh();
  p.streamAssistantToken("The perimeter is the way round.");
  p.endTurn();
  await sleep(120);
  assert.equal(dom.announcer.textContent, "The perimeter is the way round.");

  // The braille turn: an acknowledgement, no new answer, then the turn ends.
  p.announceAction("Here is the braille transcription of our last explanation.");
  await sleep(120);
  assert.match(dom.announcer.textContent, /braille transcription/);
  p.endTurn();
  await sleep(150);
  assert.match(dom.announcer.textContent, /braille transcription/,
               "the whole previous answer was read out a second time");
});

test("an acknowledgement is spoken, never written over the explanation", async () => {
  const { p, dom } = fresh();
  for (const token of ["The perimeter ", "is the way round."]) p.streamAssistantToken(token);
  p.endTurn();
  await sleep(120);

  const badgeBefore = dom.badge.innerHTML;
  p.announceAction("Here is the braille transcription of our last explanation.");
  assert.equal(dom.text.textContent, "The perimeter is the way round.",
               "the explanation the cells hold must stay on the prompter");
  assert.equal(dom.badge.innerHTML, badgeBefore, "nothing is drawn for it at all");
  await sleep(120);
  assert.equal(dom.announcer.textContent,
               "Here is the braille transcription of our last explanation.");
});

test("reset puts the stage back where it started", () => {
  const { p, dom } = fresh();
  p.setUserTranscript("Hello");
  p.toggleBraille(true);
  p.reset();
  assert.equal(p.activeText, "");
  assert.equal(p.brailleVisible, false);
  assert.equal(dom.slot.innerHTML, "");
  assert.ok(dom.text.classList.contains("empty"));
  assert.match(dom.badge.innerHTML, /Waiting for voice/);
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
