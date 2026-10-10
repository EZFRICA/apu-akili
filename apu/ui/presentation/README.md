# Pocket Akili · the keynote stage

A product keynote for Pocket Akili: the presenter's camera in a large capsule, a teleprompter
across its top, and the tactile device rendered in 3D at its foot. **Pressing a key on the device
runs a real turn** through the live lab, exactly as the lab's own page does.

```bash
uv run python -m apu.ui.live.proxy
```

The lab is the only server: it serves this stage at `http://localhost:8765/presentation/`, its
own page at `/`, and the socket and microphone code both use at `/shared/`. Files are sent with
`no-store`, so an edit shows on the next reload. Serving the page from anywhere else means adding
that origin to `APU_LIVE_ALLOWED_ORIGINS`.

## On the stage

- **The teleprompter** shows only the turn being spoken: the pupil's words, then the tutor's
  reply, never the turn before. An acknowledgement ("Here is the braille transcription...") is
  spoken, not written over the lesson the braille holds.
- **The braille card** is what an embosser would print: 40 cells by 25 lines, words wrapped at
  spaces, page by page, grade 2 as embossed (grade 1 as plain cells). The lab lays it out with the
  same code that writes the `.BRF` file, so preview and file cannot disagree. It embosses the
  last lesson, never an acknowledgement, and with nothing yet to emboss it says so instead of
  inventing cells.
- **A picture** the pupil asks for ("draw it for me") appears under the teleprompter, with two
  lines of the tutor's description; the whole description is its alt. While it is drawn, the
  tutor's waiting sentence takes its place, spoken and announced. The braille card covers it
  while open, and the next answer takes it away.
- **The device**, in Three.js, settles its floating motion as a pointer approaches. Each key is
  aimed at through an invisible disc wider than the key, and where two discs overlap the press
  goes to the nearest key's centre.

| Key | What a press does |
|---|---|
| **Mic / PTT** | opens the microphone and streams 16 kHz PCM to the lab |
| **Notebook** | sends "Save that in my notebook", written to `data/notebook.sqlite3` |
| **Summary** | sends "Summarize my notebook", read back out loud |
| **Braille** | lays the last lesson out as it would be embossed, with its `.BRF` file |

The ports and the volume wheel have no software behind them: selecting one shows its
specification.

## Physical Specifications

| Parameter | Specification | Purpose |
|---|---|---|
| **Form factor** | Tactile dictaphone, 130 × 70 × 22 mm | a secure one-hand grip for a child |
| **Weight** | **165 g**, composite chassis | all-day wear on a neck lanyard |
| **Battery** | 3,200 mAh Li-Po, about 18 h of speech | several days where electricity is intermittent |
| **Charging** | **USB-C**, USB-PD 20 W | reversible, with a tactile funnel for blind insertion |
| **Audio** | **3.5 mm** TRRS headphone jack | private listening, headphones or bone conduction |
| **Braille Dock** | 14-pin magnetic connector | snaps onto a refreshable braille display (Orbit, Brailliant) |
| **Grips** | ribbed silicone side rails | against drops, and steadying a hand tremor |
| **Lanyard eyelet** | reinforced corner eyelet | for a neck lanyard or a wheelchair mount |

## Tactile interface layout

```
         ┌──────────────────────────────────────┐
         │ [Mic L]       [Lanyard]     [Mic R]  │  ◄ Top: dual beamforming mics
         ├──────────────────────────────────────┤
         │         [=== STATUS LED ===]         │  ◄ High-contrast LED bar
         │           ╭────────────╮             │
         │           │  SPEAKER   │             │  ◄ Front voice grille
         │           ╰────────────╯             │
         │     [Socratic]   ( PTT )   [★ Note]  │  ◄ Main deck: push-to-talk,
         │       Slider     RECORD     Button   │    notebook (braille "N" ⠝)
[Vol]    │      [<< Rew]   [►|| Play]   [>> Fwd]│  ◄ 15 s skip back and forward
wheel    ├──────────────────────────────────────┤
         │  (O) Jack    [=== USB-C ===]   [:::] │  ◄ Bottom: 3.5 mm jack, USB-C,
         └──────────────────────────────────────┘    14-pin braille dock
```

The push-to-talk key has high-relief concentric rings and an embossed dot; the notebook key,
an embossed star and the braille letter N, calls the
[`save_to_notebook`](../../tools/notebook.py) tool with no spoken instruction needed. The jack
and the USB-C port have chamfered funnels to be found by touch, the volume wheel 24 detents.

## Accessibility

This stage is for pupils who may not see it at all.

- The finished sentence of each turn, and any failure, is written **once** to a polite live
  region, rather than streamed word by word.
- **The 3D device is a canvas**, hidden from the accessibility tree. The component list beside
  it is its equivalent: eight real buttons, each named, each firing the same action. Collapsed
  side panels leave the reading order too.
- **M** opens or closes the microphone and **Escape** closes the braille card; both are ignored
  in a text field or with a modifier held.
- Every control shows a focus ring; the header's icon buttons are 40 pixels.
  `prefers-reduced-motion` stops the floating, pulsing and glowing, inside the WebGL canvas too.
- A picture's alt is the tutor's description of it, and its visible caption is hidden from the
  reader, so the description is heard once.
- The braille cells sit at 13:1 contrast, above the strictest 7:1 threshold; the rest of the
  card is quieter, so the cells are what stands out.

On a narrower window the side panels narrow below 1180 px and leave below 900 px; below 680 px
of height the braille card gives its room back first.

## Files

`index.html` and `styles.css` are the stage, `presentation.js` turns events into what is on
screen, `prompter.js` holds the teleprompter, the braille card and the picture, `hardware3d.js` the device
and its presses, `camera.js` the webcam and its stand-in, and `bridge.js` what each key means.
The socket, the microphone and the picture card are in `apu/ui/shared/`, shared with the lab's
own page.
