# Accessibility of the interface

A tutor whose point is that a blind pupil can use it has to be measured on that, not assumed
to be fine. This is what an audit of the running interface found, what was fixed, and what
the framework still costs.

Audited with axe-core 4.10 against the student page served by Streamlit 1.64, on 2026-09-19,
plus DOM reads after a real turn, because the thing that matters most (is the answer
announced?) is not something axe checks.

```bash
uv run streamlit run apu/ui/app.py
# then, in the browser console, with axe-core loaded:
axe.run(document, { resultTypes: ['violations'] })
```

## What the audit found

| Finding | Impact | Whose |
|---|---|---|
| The tutor's answer arrived in no live region, so a screen reader announced **nothing** when it appeared | the product's central promise | ours |
| The question box was the **20th** focusable element of 22 | keyboard users | ours |
| No `main` landmark: **16 elements** outside any region | navigation by landmarks | Streamlit |
| `aria-expanded` on a `<section>` (the sidebar) | **critical**, invalid ARIA | Streamlit |

The first one is the one that matters. A pupil who cannot see the screen typed a question,
the answer appeared, and nothing told them. They had to go looking for it.

## What was changed

Streamlit renders its own DOM and offers no way to set ARIA attributes or landmarks on it, so
the patch is a small script injected on every page (`ACCESSIBILITY_SCRIPT` in
`apu/ui/common.py`, called from `apu/ui/app.py`). It:

- marks the conversation as `role="log"` with `aria-live="polite"`, so an answer is announced
  as it arrives without stealing focus. The container is found through a marker the page
  renders itself (`CHAT_LOG_ANCHOR`), not through Streamlit's class names, which change
  between versions;
- adds the `main` landmark, makes the sidebar `navigation`, and gives the fixed bottom block
  holding the question box its own labelled region, since Streamlit renders it outside main;
- removes the invalid `aria-expanded` from the sidebar;
- inserts a skip link as the first focusable element, inside its own `navigation` landmark,
  and binds **Alt+Q** to focus the question box from anywhere.

## After

| | Before | After |
|---|---|---|
| axe violations | 1 critical, 1 moderate (16 nodes) | **none** |
| Landmarks | header only | skip links, navigation, header, main, question region |
| Answer announced | no | yes, `aria-live="polite"` on `role="log"` |
| Reaching the question box | 20 tabs | 1 tab, or Alt+Q |

Verified after a real turn, so the attributes survive a Streamlit rerun.

## Two traps this uncovered, both worth knowing

**Everything a component attaches to the page dies on the next rerun.** The script runs inside
a component iframe that Streamlit destroys and recreates on each rerun. The DOM it created
stays, but its event listeners and observers belong to a destroyed JavaScript realm and stop
working. The first version guarded registration with a flag on the parent page, so after one
rerun the keyboard shortcut was silently dead while looking present. Each run now replaces its
own previous registrations instead of skipping them.

**A MutationObserver that rebuilds what it observes hangs the page.** The first version
rebuilt the skip link inside the observer callback, which triggered the observer, which
rebuilt it again. The browser stopped responding. The work is now split: an idempotent
function that only writes an attribute when it is missing or wrong, which the observer may
call freely, and a one-off function that creates nodes and listeners.

**Alt+Q was matched on the character, not the key.** On macOS, Alt+Q produces `œ`, so
`event.key === 'q'` never matched and the shortcut did nothing on the machine it was written
on. It matches `event.code === 'KeyQ'` now.

Both traps are pinned by a test (`test_the_page_ships_the_accessibility_patch`), which checks
that the observer calls only the idempotent function and that node creation stays out of it.

## What is still open

- **An automated audit catches roughly a third of accessibility problems.** Nothing here
  replaces a session with a real screen reader, ideally with a pupil who uses one daily. The
  braille block, the mode selector and the notebook tab have not been tested that way.
- **The braille output is a styled `div`**, announced as plain text by a screen reader and
  meaningful only on a braille display. Whether it should carry a language or a role is
  undecided.
- **Streamlit's own widgets** are out of reach: the sidebar markup is patched from outside on
  every rerun rather than fixed, and a future version could change what the patch looks for.
  The test pins the patch, not Streamlit's DOM.
- **Voice input is not testable** in AppTest, which has no `audio_input`, so that path is
  covered only by live checks.
