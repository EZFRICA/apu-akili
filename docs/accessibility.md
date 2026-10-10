# Accessibility of the interface

A tutor whose point is that a blind pupil can use it has to be measured on that. The Streamlit
student page was audited with axe-core 4.10 on 2026-09-19, plus DOM reads after a real turn,
since what matters most, whether the answer is announced, is not something axe checks:

```bash
uv run streamlit run apu/ui/app.py
# then, in the browser console, with axe-core loaded:
axe.run(document, { resultTypes: ['violations'] })
```

## Found, and fixed

| Finding | Whose | After the fix |
|---|---|---|
| The tutor's answer was in no live region: a screen reader announced **nothing** | ours | `role="log"`, `aria-live="polite"` |
| The question box was the 20th of 22 focusable elements | ours | a skip link first, and **Alt+Q** from anywhere |
| No `main` landmark: 16 elements outside any region | Streamlit | main, navigation and a labelled question region |
| `aria-expanded` on the sidebar's `<section>`: **critical**, invalid ARIA | Streamlit | removed |

axe went from one critical and one moderate violation to **none**, checked again after a real
turn so the attributes survive a rerun. Streamlit offers no way to set ARIA on its own DOM, so
the fix is a script injected on every page (`ACCESSIBILITY_SCRIPT` in `apu/ui/common.py`); the
conversation is found through a marker the page renders itself (`CHAT_LOG_ANCHOR`), not through
Streamlit's class names, which change between versions.

## Three traps, all pinned by one test

`test_the_page_ships_the_accessibility_patch` holds all three:

- **A rerun kills the script's listeners but keeps its DOM**, so a guard that skipped
  re-registration left Alt+Q silently dead. Each run now removes its previous listener and skip
  link before adding its own.
- **An observer that rebuilds what it observes hangs the page.** The observer only calls an
  idempotent function that fixes attributes; nodes are created once, elsewhere.
- **On macOS, Alt+Q types `œ`**, so `event.key === 'q'` never matched. It matches
  `event.code === 'KeyQ'`.

## Still open

- **An automated audit catches about a third of real problems.** Nothing replaces a session with
  a pupil who uses a screen reader daily; the braille block, the mode selector and the notebook
  tab have not had one.
- **On the Streamlit page, braille is a styled `div`**, read as plain text by a screen reader.
  Whether it should carry a language or a role is undecided.
- **The patch depends on Streamlit's DOM**, re-applied on every rerun; a new version could change
  what it looks for. The test pins the patch, not Streamlit.
- **Voice input is not testable in AppTest**, which has no `audio_input`; it is checked live only.

## Pictures

A picture is drawn only for a pupil who can see it. In braille, or by voice without a screen,
the tutor is told to describe instead: found live, asked to "draw a right triangle" on a braille
display, it drew one out of slashes and pipes, a column of meaningless cells under the fingers.
The tutor's description of what it drew is the picture's text alternative everywhere. On the
Streamlit page `st.image` writes `alt="0"`, read aloud as "zero", so the patch above copies the
caption into the alt and hides the caption from the reader. While a picture is drawn, the
waiting sentence is spoken in voice modes, and is a `role="status"` card in the lab and on the
stage, where the announcer reads it once.

## The keynote stage

Built later, it has its own account in
[its README](../apu/ui/presentation/README.md#accessibility): the 3D device is hidden from the
accessibility tree with eight named buttons as its equivalent, each turn is announced once, `M`
and `Escape` work without a mouse, reduced motion reaches inside the WebGL canvas, and the
braille card shows the page an embosser would print. It has not been through an axe-core audit.
