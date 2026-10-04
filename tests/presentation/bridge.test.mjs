/** The socket to the live lab, and the microphone it carries, run rather than read. */
import assert from "node:assert/strict";
import { installDom, installSocket } from "./dom_stub.mjs";

installDom();
const FakeSocket = installSocket();
const { KeynoteBridge, HARDWARE_ACTIONS } = await import("../../apu/ui/presentation/bridge.js");

// The microphone needs a device this stub has not got. Every test that opens it says so.
function fakeMicrophone(bridge, { opens = true } = {}) {
  bridge.microphone.start = async () => {
    bridge.microphone.isRecording = opens;
    return opens;
  };
  bridge.microphone.stop = () => { bridge.microphone.isRecording = false; };
}

const cases = [];
const test = (name, fn) => cases.push([name, fn]);
const tick = () => new Promise((r) => setTimeout(r, 0));

function fresh() {
  FakeSocket.instances = [];
  const events = [];
  const bridge = new KeynoteBridge({ onEvent: (type, payload) => events.push([type, payload]) });
  return { bridge, events, sockets: FakeSocket.instances };
}
const types = (events) => events.map(([t]) => t);

test("the socket carries the model, the pupil and the class", async () => {
  const { bridge, sockets } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  assert.equal(await opening, true);
  assert.match(sockets[0].url, /^ws:\/\/localhost:8765\/ws\/gemini-3\.5-transcribe-live\?/);
  assert.match(sockets[0].url, /student_id=eleve-aya/);
  assert.match(sockets[0].url, /class_id=lycee-cocody%3A3eA/);
});

test("two keys pressed before the lab answers open one socket, not two", async () => {
  const { bridge, sockets } = fresh();
  const first = bridge.connect();
  const second = bridge.connect();
  await tick();
  assert.equal(sockets.length, 1, "a second socket means the lab answers the turn twice");
  sockets[0].open();
  assert.deepEqual(await Promise.all([first, second]), [true, true]);
});

test("the late close of a replaced socket does not take the live one with it", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;

  bridge.setModel("gemini-3.8-live");          // closes the first, opens the second
  await tick();
  assert.equal(sockets.length, 2);
  sockets[1].open();
  await tick();
  sockets[0].onclose();                        // the first one's close, arriving late
  assert.equal(bridge.isConnected, true, "the new socket was dropped by the old one's close");
  assert.ok(!types(events).includes("closed") || bridge.isConnected);
});

test("a closed socket is reported closed and lets go of the microphone", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  sockets[0].close();
  assert.equal(bridge.isConnected, false);
  assert.ok(types(events).includes("closed"));
  assert.equal(bridge.isRecordingMic, false);
});

test("a lab that never answers is reported offline rather than waited on forever", async () => {
  const { bridge, events } = fresh();
  const result = bridge.connect();
  await new Promise((r) => setTimeout(r, 4100));
  assert.equal(await result, false);
  const offline = events.find(([t]) => t === "offline");
  assert.ok(offline, "the status pill has nothing to say without this event");
  assert.match(offline[1].reason, /did not answer/);
});

test("the notebook key sends the words that save a note", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;

  assert.equal(await bridge.triggerHardwareAction("btn_notebook"), true);
  assert.deepEqual(JSON.parse(sockets[0].sent[0]),
                   { type: "text_prompt", text: "Save that in my notebook" });
  assert.deepEqual(types(events).slice(-1), ["action_start"]);
});

test("the same key pressed twice stops rather than asking twice", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  await bridge.triggerHardwareAction("btn_summary");
  assert.equal(await bridge.triggerHardwareAction("btn_summary"), false);
  assert.equal(sockets[0].sent.length, 1, "the second press must not send a second turn");
  assert.deepEqual(types(events).slice(-1), ["action_stop"]);
});

test("a key pressed with no lab on the other end says so and goes back to rest", async () => {
  const { bridge, events } = fresh();
  const pressed = bridge.triggerHardwareAction("btn_notebook");
  await new Promise((r) => setTimeout(r, 4100));
  assert.equal(await pressed, false);
  const after = types(events);
  assert.ok(after.includes("error"), "the pupil is told");
  assert.equal(after[after.length - 1], "action_stop", "and the key stops glowing");
  assert.equal(bridge.activeIntent, null);
});

test("a microphone that opens onto no lab is closed again, not left recording", async () => {
  const { bridge, events } = fresh();
  fakeMicrophone(bridge);
  const pressed = bridge.triggerHardwareAction("btn_ptt");
  await new Promise((r) => setTimeout(r, 4200));
  assert.equal(await pressed, false);
  assert.equal(bridge.isRecordingMic, false,
               "the recording light stays on over a socket that is not there");
  const after = types(events);
  assert.ok(after.includes("ptt_start") && after.includes("ptt_stop"));
  assert.ok(after.includes("error"));
});

test("a refused microphone is reported and nothing else happens", async () => {
  const { bridge, events, sockets } = fresh();
  fakeMicrophone(bridge, { opens: false });
  assert.equal(await bridge.triggerHardwareAction("btn_ptt"), false);
  assert.deepEqual(types(events), ["error"]);
  assert.equal(sockets.length, 0, "no socket is opened for a microphone that did not open");
});

test("pressing the microphone again stops the turn", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  fakeMicrophone(bridge);
  await bridge.triggerHardwareAction("btn_ptt");
  events.length = 0;
  assert.equal(await bridge.triggerHardwareAction("btn_ptt"), false);
  assert.equal(bridge.isRecordingMic, false);
  assert.equal(new TextDecoder().decode(sockets[0].sent.at(-1)), "END_OF_TURN");
  assert.deepEqual(types(events), ["ptt_stop"]);
});

test("the microphone key never sends a written prompt in place of a voice", () => {
  assert.equal(HARDWARE_ACTIONS.btn_ptt.prompt, undefined,
               "a dead prompt on the voice key reads as a hidden question it never asks");
});

test("a port is a specification, not an action", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  await bridge.triggerHardwareAction("port_usbc");
  assert.equal(sockets[0].sent.length, 0);
  assert.deepEqual(types(events).slice(-1), ["inspected"]);
});

test("an unknown part does nothing at all", async () => {
  const { bridge, events } = fresh();
  assert.equal(await bridge.triggerHardwareAction("btn_launch_rocket"), false);
  assert.deepEqual(events, []);
});

test("the braille cells stop the braille key, once", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  await bridge.triggerHardwareAction("btn_braille");
  events.length = 0;
  sockets[0].deliver({ type: "braille_format", braille_g1: "⠁" });
  assert.deepEqual(types(events), ["action_stop", "braille_format"],
                   "the key stops when its cells arrive, not when the turn ends");
});

test("the end of a turn releases whichever key was waiting on it", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  await bridge.triggerHardwareAction("btn_summary");
  events.length = 0;
  sockets[0].deliver({ type: "turn_complete" });
  assert.deepEqual(types(events), ["action_stop", "turn_complete"]);
  assert.equal(bridge.activeIntent, null);
});

test("an error from the lab releases the key as well", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  await bridge.triggerHardwareAction("btn_notebook");
  events.length = 0;
  sockets[0].deliver({ type: "error", message: "the notebook is full" });
  assert.deepEqual(types(events), ["action_stop", "error"]);
});

test("a message that is not json is dropped instead of breaking the stage", async () => {
  const { bridge, sockets, events } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  events.length = 0;
  sockets[0].onmessage({ data: "<html>a proxy error page</html>" });
  sockets[0].onmessage({ data: new ArrayBuffer(8) });
  assert.deepEqual(events, []);
});

test("the end of turn marker is sent as bytes, the way the lab reads it", async () => {
  const { bridge, sockets } = fresh();
  const opening = bridge.connect();
  sockets[0].open();
  await opening;
  bridge.sendEndOfTurn();
  const sent = sockets[0].sent[0];
  assert.ok(sent instanceof Uint8Array);
  assert.equal(new TextDecoder().decode(sent), "END_OF_TURN");
});

test("every key the drawer offers is a key the bridge knows", async () => {
  const drawerParts = ["btn_ptt", "btn_notebook", "btn_summary", "btn_braille",
                       "port_usbc", "port_jack", "port_braille", "volume_wheel"];
  for (const part of drawerParts) {
    assert.ok(HARDWARE_ACTIONS[part], `${part} is in the drawer and nowhere else`);
  }
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
