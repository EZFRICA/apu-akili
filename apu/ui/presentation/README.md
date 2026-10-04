# APU Akili · Keynote presentation interface

A product keynote for Pocket Akili: one large capsule holding the presenter's camera, a
teleprompter across the top of it, and the tactile device itself rendered in 3D at the foot
of the stage. Pressing a key on that device runs a real turn through the live lab, the same
way the lab's own page does.

## What is on the stage

**The capsule.** The camera feed, with a dark blurred band over the top third so the
teleprompter stays legible against whatever is behind it. Without a camera, the stage falls
back to the presenter view.

**The teleprompter.** Only the turn being spoken is on screen: the pupil's words while they
speak, the tutor's reply as it arrives, and nothing from the turn before. The state is shown
on a badge, and the finished sentence is announced once to screen readers.

A turn that only acknowledges an action is **spoken and not written**. "Here is the braille
transcription of our last explanation" is a sentence about the cells, not a lesson, and on
the prompter it replaced the explanation those very cells hold. The lab marks it as an
acknowledgement rather than leaving a front end to recognise the English sentence.

## Braille is printed, not displayed

The card under the prompter is not a row of cells on a screen, because that is a screen's
idea of braille. It is what an embosser would put on paper: **forty cells to a line,
twenty-five lines to a page**, words wrapped at spaces and a word longer than a line split,
since paper cannot overflow. The lab lays it out with the same embosser code that writes the
file, so the preview and the `.BRF` button cannot disagree, and the pages can be turned.

Grade 2 is what is laid out, because that is what is embossed. Grade 1 has no page layout of
its own and is shown as cells rather than as a page that would lie about where the lines
break. Opening the card shortens the prompter: the cells are what was asked for.

**What is embossed is the lesson, never the acknowledgement of a previous one.** The lab
answers an action with a sentence of its own, and those were stored in the history like any
tutor answer: pressing braille twice embossed "Here is the braille transcription of our last
explanation", which contracts to "the brl transcription of our last explanation" under a
reading finger. The same lookup decides what a pupil's notebook keeps, so "save that" after a
braille press would have kept that sentence as the lesson. An acknowledgement is marked in
the history now, and skipped by everything that asks for the last explanation.

**With nothing to emboss, nothing is shown.** The card used to fall back to cells spelling
the product name, and a pupil reading with their fingers takes whatever is under them for the
answer. It says there is nothing yet, which is the rule the lab already followed when
liblouis gave it none.

**The device.** Three.js, built from the dimensions below: slate
anodised chassis, silicone side grips, micro-perforated grille, keys in relief with textured
icons. The pointer becomes a hand near it, a press depresses the key and sends a shockwave
across the screen, and the floating motion settles while a hand is approaching so nobody has
to aim at a moving target.

Each key is aimed at through an invisible disc wider than the key itself, because the moulded
shapes are under fifty pixels across on screen. Where two of those discs overlap, the press
goes to the key whose centre the pointer passed closest to, not to the first surface the ray
crossed: the microphone's disc used to reach past the braille key below it, so pressing
braille opened the microphone.

| Key | What a press really does |
|---|---|
| **Mic / PTT** | opens the microphone and streams 16 kHz PCM to the lab |
| **Notebook** | sends "Save that in my notebook", which writes to `data/notebook.sqlite3` |
| **Summary** | sends "Summarize my notebook", read back out loud |
| **Braille** | lays the answer out as it would be embossed, and offers the .BRF file |

The ports and the volume wheel have no software behind them; selecting one shows its
specification and nothing more.

## Physical Specifications

| Parameter | Specification | Purpose / Accessibility Note |
|---|---|---|
| **Form Factor** | Ergonomic tactile dictaphone (130 × 70 × 22 mm) | Contoured for secure single-hand grip by children and students |
| **Weight** | **165 g** (ultralight composite chassis) | Comfortable for all-day neck lanyard wear without strain |
| **Battery Life** | 3,200 mAh Li-Po (~18 hours continuous speech) | Multi-day autonomy for schools with intermittent electricity |
| **Charging** | **USB-C Fast Charging (USB-PD 20W)** | Reversible port with tactile funnel for blind insertion |
| **Audio Output** | **3.5 mm TRRS gold-plated headphone jack** | Direct private listening via headphones or bone-conduction sets |
| **Braille Dock** | **14-pin magnetic high-density connector** | Snaps directly into refreshable Braille displays (Orbit, Brailliant) |
| **Tactile Grips** | Ribbed non-slip silicone side rails | Prevents accidental drops and stabilizes hand tremors |
| **Lanyard Eyelet**| Reinforced magnesium corner eyelet | Secure attachment for neck lanyards or wheelchair mounts |

---

## Tactile Interface Layout

```
         ┌──────────────────────────────────────┐
         │ [Mic L]       [Lanyard]     [Mic R]  │  ◄ Top: Dual Beamforming Mics
         ├──────────────────────────────────────┤
         │                                      │
         │         [=== STATUS LED ===]         │  ◄ Visual / High-Contrast LED Bar
         │                                      │
         │           ╭────────────╮             │
         │           │  SPEAKER   │             │  ◄ Front Acoustic Voice Grille
         │           │   GRILLE   │             │    (Tuned for vocal clarity)
         │           ╰────────────╯             │
         │                                      │
         │     [Socratic]   ( PTT )   [★ Note]  │  ◄ Main Control Deck:
         │       Slider     RECORD     Button   │    • Concentric PTT Record Button
[Vol]    │                  Button              │    • Star/Note Button (save_to_notebook)
Thumb-   │                                      │
wheel    │      [<< Rew]   [►|| Play]   [>> Fwd]│  ◄ Navigation Deck:
         │                                      │    • 15s Skip Backward & Forward
         ├──────────────────────────────────────┤
         │  (O) Jack    [=== USB-C ===]   [:::] │  ◄ Bottom Edge Ports:
         │  3.5mm       Charging Port    Braille│    • 3.5mm Audio Jack
         └──────────────────────────────────────┘    • USB-C Fast Charging
                                                     • 14-pin Braille Display Dock
```

### Key Controls Breakdown

1. **Push-To-Talk Tactile Record Button (`record_btn`)**:
   - Oversized central button with high-relief concentric rings and an embossed Braille dot.
   - Activates voice input to the APU Socratic tutor pipeline.
2. **Dedicated Notebook / Star Button (`notebook_btn`)**:
   - Embossed star shape with Braille letter **"N"** (⠝).
   - Direct hardware hook to the [`save_to_notebook`](../../tools/notebook.py) tool, persisting key lesson takeaways into the SQLite student notebook without needing verbal instructions.
3. **3.5mm Headphone Jack (`jack_port`)**:
   - Chamfered guide funnel allowing blind students to easily locate and plug in standard headphones or bone-conduction headsets.
4. **USB-C Charging Port (`usbc_port`)**:
   - Reversible charging port with tactile directional bevel for unassisted charging.
5. **Braille Display Connector (`braille_dock`)**:
   - Magnetic alignment pins connecting directly to external refreshable Braille displays, receiving live Grade 1 & Grade 2 Braille translated by liblouis.
6. **Tactile Knurled Volume Wheel (`volume_wheel`)**:
   - Mechanical rotary wheel with 24 click detents positioned naturally under the thumb.
7. **Reinforced Lanyard Loop (`lanyard_loop`)**:
   - Integrated eyelet for wearing around the neck or securing to a mobility device.

---

---

## Accessibility

This interface is aimed at pupils who may not see it at all.

The finished sentence of each turn is written **once** to a polite live region, rather than
streamed token by token, which a screen reader would read one word at a time. A failure is
written there too, so an error is not eleven characters of grey text in a corner.

**The device on stage is a canvas**, which has no accessible content and nothing a screen
reader can press. It is hidden from the accessibility tree, and the component list on the left
is its equivalent: eight real buttons, each named out loud, each firing the same action as the
key it stands for. Collapsing the side panels hides them from the reading order as well, not
only from view.

**Two keys**, for what a presenter does mid-sentence without looking:

| Key | What it does |
|---|---|
| **M** | opens or closes the microphone |
| **Escape** | closes the braille card |

Both are ignored while a text field or the pupil selector has focus, and while a browser
shortcut modifier is held.

Every control shows a focus ring, and the four icon buttons in the header are 40 pixels so a
trackpad can find them. `prefers-reduced-motion` stops the floating, the pulsing and the
glowing without removing a single function, and it is honoured **inside the WebGL canvas and
the camera stand-in as well**, which a stylesheet cannot reach.

The braille card spends its contrast where the contrast is information. The cells sit at 13:1
against the surface they are on, well above the 7:1 that is the strictest published threshold
for body text; the labels, the border and the glow around the card gave theirs back, because
white on black on every element at once is hard to sit in front of.

## A window smaller than the stage

Below **1180 px** the side panels narrow and the hint at the foot of the stage goes. Below
**900 px** both panels and the model switcher leave the stage altogether, since the capsule is
the presentation and the panels are a convenience. Below **680 px of height** the braille card
gives its room back first, and the camera angles bar goes.

## Running it

The stage needs the live lab for anything to happen:

```bash
uv run python -m apu.ui.live.proxy
```

That is the only server there is. It serves this stage at

```
http://localhost:8765/presentation/
```

alongside its own page at `/`, and the shared layer both of them run on at `/shared/`. There
was a second static server here that served these files on port 8767; it is gone. It could
serve the page but never make it work, since every key needs the lab, and keeping it meant a
second command and a second origin on the allowlist for no gain.

The files are sent with `no-store`, because they exist to be looked at while they are being
changed and a cached `presentation.js` silently shows yesterday's work.

A websocket is not covered by the browser's same-origin policy, so the lab checks the origin
of every connection. Serving this page from anywhere other than the lab means adding that
origin to `APU_LIVE_ALLOWED_ORIGINS`.

## Files

- `index.html`, `styles.css`: the stage.
- `presentation.js`: the glue, from events to the screen.
- `prompter.js`: the teleprompter and the braille card.
- `hardware3d.js`: the device, its materials and its presses.
- `camera.js`: the webcam feed and its fallback.
- `bridge.js`: what a key means. Which key sends which words, and which key stops glowing
  when which answer comes back.

The socket, the microphone and the loudspeaker are not here. They are in `apu/ui/shared/`,
because the lab's own page needs exactly the same three and used to carry its own copy: two
defects fixed in one copy were still running in the other months later.
