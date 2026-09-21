"""Shared pieces of the demo interface: identity selector (stub), guard session, styling.

IDENTITY IS A STUB. The sidebar lets anyone act as any demo student, teacher or admin; no
password, no token. What IS real: a teacher's or admin's rights come from the assignment
registry through the same service functions as the API (apu.api.service), and a student's
class policy comes from the class policy registry.
"""

import asyncio
import json
import os
import re
import sys
import threading
from dataclasses import dataclass

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from apu import config  # noqa: E402
from apu.auth import assignments  # noqa: E402
from apu.demo.seed import load_demo_students  # noqa: E402
from apu.guardrails.policy import get_class_policy_registry  # noqa: E402
from apu.guardrails.session import UnknownSession  # noqa: E402
from apu.guardrails.session import sessions as guard_sessions  # noqa: E402
from apu.modality.plain_text import plain_text  # noqa: E402,F401  (re-exported for the views)

ROLE_LABELS = {
    "student": "Student",
    "teacher": "Teacher",
    "establishment_admin": "School admin",
}


@dataclass(frozen=True)
class DemoIdentity:
    role: str                 # student | teacher | establishment_admin
    person_id: str
    display_name: str
    establishment_id: str
    class_id: str | None = None

    @property
    def label(self) -> str:
        scope = self.class_id or self.establishment_id
        return f"{ROLE_LABELS[self.role]} — {self.display_name} ({scope})"


_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def run(coroutine):
    """
    Run one coroutine on a long-lived event loop.

    Not asyncio.run: that closes the loop after every call, and the clients underneath
    (NeMo Guardrails in particular) cache connections bound to the loop that created them.
    Measured on the topical guard: 1.48 s median with a fresh loop per call against 0.98 s
    on a shared one, because each call first hits a stale binding and retries. Streamlit
    reruns the script, often on a new thread, so the loop is kept at module level and the
    lock serialises turns, which are sequential for one student anyway.
    """
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        return _loop.run_until_complete(coroutine)


def available_identities() -> list[DemoIdentity]:
    identities = [
        DemoIdentity("student", s["student_id"], s["display_name"],
                     s["class_id"].split(":", 1)[0], s["class_id"])
        for s in load_demo_students()
    ]
    identities += [
        DemoIdentity(a.role, a.requester_id, a.requester_id, a.establishment_id, a.class_id)
        for a in assignments.get_assignment_registry().all()
    ]
    return identities


def default_identity() -> DemoIdentity:
    identities = available_identities()
    return next((i for i in identities if i.person_id == config.DEMO_STUDENT_ID), identities[0])


def current_identity() -> DemoIdentity:
    if "identity" not in st.session_state:
        st.session_state.identity = default_identity()
    return st.session_state.identity


def reset_conversation() -> None:
    st.session_state.chat = []
    st.session_state.last_turn = None
    st.session_state.pop("guard_session_id", None)
    st.session_state.pop("notebook_sheet", None)


def identity_sidebar() -> DemoIdentity:
    identities = available_identities()
    current = current_identity()
    labels = [identity.label for identity in identities]
    index = labels.index(current.label) if current.label in labels else 0
    choice = st.selectbox("Sign in as", labels, index=index, key="identity_choice")
    chosen = identities[labels.index(choice)]
    if chosen != current:
        st.session_state.identity = chosen
        # A new person is a new connection: new guard session, counter back to zero.
        reset_conversation()
        st.rerun()
    st.caption("⚠️ Simulated sign-in for the demo (insecure stub). "
               "Permissions still come from the registries.")
    return chosen


def ensure_guard_session(identity: DemoIdentity) -> str:
    """The student's guard session, reopened if it vanished (demo reset, new identity)."""
    session_id = st.session_state.get("guard_session_id")
    if session_id:
        try:
            guard_sessions.get(session_id)
            return session_id
        except UnknownSession:
            pass
    session = guard_sessions.open_session(student_id=identity.person_id, class_id=identity.class_id)
    st.session_state.guard_session_id = session.session_id
    return session.session_id


def class_threshold(class_id: str) -> int:
    return get_class_policy_registry().get(class_id).escalation_threshold


def speak_button(text: str, key: str, autoplay: bool = False) -> None:
    """Read text aloud with the browser's speech synthesis."""
    payload = json.dumps(text)
    autoplay_js = "speak();" if autoplay else ""
    components.html(
        f"""
        <button id="speak-{key}" style="background:#0f172a;color:#7dd3fc;border:1px solid #38bdf8;
          border-radius:8px;padding:6px 14px;font-family:sans-serif;cursor:pointer;">▶ Listen</button>
        <script>
          const text = {payload};
          function speak() {{
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = "en-US";
            window.speechSynthesis.speak(utterance);
          }}
          document.getElementById("speak-{key}").onclick = speak;
          {autoplay_js}
        </script>
        """,
        height=48,
    )


# Streamlit renders its own DOM and gives no way to set ARIA attributes or landmarks on it,
# so the gaps an audit found on the student page are patched from the browser. Measured
# before this ran (axe-core plus a DOM read after a real turn): the tutor's answer landed in
# no live region, so a screen reader announced nothing when it arrived; the question box was
# the 20th focusable element; the page had no main landmark, leaving 16 elements outside any
# region; and Streamlit's own sidebar carried aria-expanded on a <section>, which is invalid.
# See docs/accessibility.md.
ACCESSIBILITY_SCRIPT = """
<script>
// This script runs inside a component iframe that Streamlit destroys and recreates on every
// rerun. Anything it registers on the parent page (listeners, observers) belongs to the
// destroyed realm and stops working, while the DOM it created stays. So each run replaces
// its own registrations instead of skipping them when they already "exist": guarding with a
// flag made the keyboard shortcut die after the first rerun, silently.
const win = window.parent;
const doc = win.document;

function focusQuestion() {
  const box = doc.querySelector('[data-testid="stChatInputTextArea"]')
           || doc.querySelector('[data-testid="stChatInput"] textarea');
  if (box) { box.focus(); box.scrollIntoView({block: 'center'}); }
}

// Idempotent: it only writes an attribute that is missing or wrong, so the observer below
// cannot trigger itself. An earlier version rebuilt the skip link here and hung the page.
function applyLandmarks() {
  const main = doc.querySelector('[data-testid="stMainBlockContainer"]')
            || doc.querySelector('[data-testid="stAppViewContainer"]');
  if (main && main.getAttribute('role') !== 'main') {
    main.setAttribute('role', 'main');
    main.setAttribute('aria-label', 'Tutor');
  }

  const sidebar = doc.querySelector('[data-testid="stSidebar"]');
  if (sidebar) {
    // aria-expanded is not allowed on a section and is Streamlit's own markup; the role
    // gives screen readers the navigation landmark the page otherwise lacks.
    if (sidebar.hasAttribute('aria-expanded')) sidebar.removeAttribute('aria-expanded');
    if (sidebar.getAttribute('role') !== 'navigation') {
      sidebar.setAttribute('role', 'navigation');
      sidebar.setAttribute('aria-label', 'Pages and sign-in');
    }
  }

  // Streamlit renders the question box in a fixed block outside the main container, so it
  // needs a landmark of its own or it is unreachable by region navigation.
  const bottom = doc.querySelector('[data-testid="stBottomBlockContainer"]');
  if (bottom && bottom.getAttribute('role') !== 'region') {
    bottom.setAttribute('role', 'region');
    bottom.setAttribute('aria-label', 'Ask a question');
  }

  // The conversation is a log: appended answers are announced without stealing focus. The
  // container is found through a marker the page renders itself (CHAT_LOG_ANCHOR), because
  // Streamlit's own class names and test ids change between versions.
  const anchor = doc.getElementById('apu-chat-log');
  const chat = anchor && (anchor.closest('[data-testid="stVerticalBlockBorderWrapper"]')
                          || anchor.closest('[data-testid="stVerticalBlock"]'));
  if (chat && chat.getAttribute('aria-live') !== 'polite') {
    chat.setAttribute('role', 'log');
    chat.setAttribute('aria-live', 'polite');
    chat.setAttribute('aria-relevant', 'additions text');
    chat.setAttribute('aria-label', 'Conversation with the tutor');
  }
}

// Once per run of this iframe, because these hold handlers from this realm.
function install() {
  const previous = doc.getElementById('apu-skip-nav');
  if (previous) previous.remove();
  const nav = doc.createElement('nav');
  nav.id = 'apu-skip-nav';
  nav.setAttribute('aria-label', 'Skip links');
  const link = doc.createElement('a');
  link.id = 'apu-skip';
  link.href = '#';
  link.textContent = 'Skip to the question box';
  link.style.cssText = 'position:absolute;left:-9999px;top:0;z-index:99999;background:#0f172a;' +
    'color:#fff;padding:8px 14px;border-radius:0 0 8px 0;';
  link.addEventListener('focus', () => { link.style.left = '0'; });
  link.addEventListener('blur', () => { link.style.left = '-9999px'; });
  link.addEventListener('click', (event) => { event.preventDefault(); focusQuestion(); });
  nav.appendChild(link);
  doc.body.insertBefore(nav, doc.body.firstChild);

  if (win.__apuKeydown) doc.removeEventListener('keydown', win.__apuKeydown);
  win.__apuKeydown = (event) => {
    // event.code, not event.key: on macOS Alt+Q produces 'œ', so matching the character
    // silently breaks the shortcut on the machines this was first tried on.
    if (event.altKey && event.code === 'KeyQ') {
      event.preventDefault();
      focusQuestion();
    }
  };
  doc.addEventListener('keydown', win.__apuKeydown);

  // Streamlit rebuilds its DOM while the page lives, which drops the attributes above.
  if (win.__apuObserver) win.__apuObserver.disconnect();
  win.__apuObserver = new MutationObserver(applyLandmarks);
  win.__apuObserver.observe(doc.body, {childList: true, subtree: true});
}

install();
applyLandmarks();
</script>
"""


# Rendered inside the conversation container so the script above can find it whatever
# Streamlit calls its own elements this version.
CHAT_LOG_ANCHOR = '<div id="apu-chat-log" style="display:none"></div>'


def inject_accessibility() -> None:
    """Add the landmarks, the live region and the skip link Streamlit does not provide."""
    components.html(ACCESSIBILITY_SCRIPT, height=0)


def inject_css() -> None:
    st.markdown(
        """
        <style>
          .braille-block { font-size: 1.9rem; line-height: 2.6rem; letter-spacing: 0.08rem;
            background: #0f172a; border: 1px solid #334155; border-radius: 12px; padding: 14px 18px;
            white-space: pre-wrap; word-break: break-word; }
          .apu-badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.8rem;
            font-weight:600; margin-right:6px; }
          .apu-badge.ok { background:rgba(74,222,128,.15); color:#86efac; border:1px solid rgba(74,222,128,.4); }
          .apu-badge.warn { background:rgba(251,146,60,.15); color:#fdba74; border:1px solid rgba(251,146,60,.4); }
          .apu-badge.info { background:rgba(56,189,248,.15); color:#7dd3fc; border:1px solid rgba(56,189,248,.4); }
          .apu-quote { border-left: 3px solid #38bdf8; padding: 4px 12px; color: #cbd5e1; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, kind: str = "info") -> str:
    return f'<span class="apu-badge {kind}">{text}</span>'


_BLOCK_MATH = re.compile(r"\\\[(.+?)\\\]", re.S)
_INLINE_MATH = re.compile(r"\\\((.+?)\\\)", re.S)


def math_for_streamlit(text: str) -> str:
    """
    Convert LaTeX delimiters to the ones Streamlit's Markdown renders.

    The tutor models write math as \\( ... \\) and \\[ ... \\]; Streamlit only renders $ ... $
    and $$ ... $$, so without this a formula shows up as raw backslash commands.
    """
    text = _BLOCK_MATH.sub(lambda match: f"\n$$\n{match.group(1).strip()}\n$$\n", text)
    return _INLINE_MATH.sub(lambda match: f"${match.group(1).strip()}$", text)
