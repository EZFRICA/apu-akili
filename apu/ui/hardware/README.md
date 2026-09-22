# APU Pocket Akili · 3D Tactile Hardware Prototype

3D Interactive Hardware Specification & Tactile Companion Prototype for students with visual impairments and motor disabilities.

## Overview

The `apu/ui/hardware` directory contains the technical specification and interactive 3D prototype of **Pocket Akili**: a lightweight, ultra-portable handheld hardware companion designed for school children with disabilities. 

Drawing inspiration from tactile portable tape recorders and dictaphones, the physical device eliminates touchscreens in favor of high-relief tactile geometric buttons, embossed Braille markings, mechanical feedback, and dedicated assistive connectors.

---

## Interactive 3D Studio

An interactive WebGL 3D hardware viewer (powered by Three.js) is included in this directory. It allows 360° inspection, component-by-component focus, simulated haptic audio clicks, exploded CAD viewing, and high-contrast accessibility rendering.

### Launching the 3D Viewer

Start the standalone hardware viewer with `uv`:

```bash
uv run python -m apu.ui.hardware.app
```

The viewer will automatically launch at **http://localhost:8766**.

---

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
   - Direct hardware hook to the [`save_to_notebook`](../../../apu/tools/notebook.py) tool, persisting key lesson takeaways into the SQLite student notebook without needing verbal instructions.
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

## Files in this Directory

- [`app.py`](./app.py): Standalone local server runner (`uv run python -m apu.ui.hardware.app`).
- [`index.html`](./index.html): WebGL 3D Studio application shell and accessible HUD overlay.
- [`styles.css`](./styles.css): Glassmorphic dark UI, telemetry indicators, and high-contrast styling.
- [`viewer.js`](./viewer.js): Three.js procedural 3D model, mechanical sound engine, raycasting, and exploded view animations.
