"""
The demo interface, run headless with Streamlit's AppTest.

Target: apu/ui/app.py, apu/ui/views/*.py, apu/ui/common.py

AppTest executes each view in-process, so the storage redirection, the stub embedder, the
scripted topical guard, the fake Nebius client and the fake registry all apply to it.
"""

import pathlib
from datetime import UTC, datetime, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from apu.escalation.models import EscalationEvent
from apu.mmu.escalation_store import EscalationStore
from apu.ui.common import DemoIdentity
from tests.conftest import OFF_TOPIC_MARKER, SCHOOL_QUERY_VERDICT, tool_call_reply
from tests.registry_fakes import install_fake_registry, manifest

UI = pathlib.Path(__file__).resolve().parent.parent / "apu" / "ui"
PROF = DemoIdentity("teacher", "prof-kouassi", "prof-kouassi", "lycee-cocody", "lycee-cocody:3eA")
ADMIN = DemoIdentity("establishment_admin", "admin-cocody", "admin-cocody", "lycee-cocody")


def view(name, identity=None):
    app = AppTest.from_file(str(UI / "views" / f"{name}.py"), default_timeout=60)
    if identity is not None:
        app.session_state["identity"] = identity
    return app


def texts(app):
    return " ".join(m.value for m in app.markdown) + " " + " ".join(c.value for c in app.caption)


@pytest.fixture
def ui(akili_paths, stub_embeddings, no_network):
    return akili_paths


# ── navigation ───────────────────────────────────────────────────────────────

def test_the_app_boots_on_the_student_page(ui):
    app = AppTest.from_file(str(UI / "app.py"), default_timeout=60).run()
    assert not app.exception, app.exception
    assert any("Sign in as" in s.label for s in app.sidebar.selectbox)
    assert any("Akili, your tutor" in t.value for t in app.title)


# ── student view ─────────────────────────────────────────────────────────────

def test_the_student_view_shows_the_guard_state(ui):
    app = view("student").run()
    assert not app.exception, app.exception
    assert app.metric[0].value == "0 / 3", "lycee-cocody:3eA threshold from the class policy"


def test_a_question_is_answered_with_its_search_and_sources(ui, fake_llm, monkeypatch):
    from apu.tools import web_search

    class Tool:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, payload):
            return {"results": [{"title": "Fraction — Wikipedia",
                                 "url": "https://fr.wikipedia.org/wiki/Fraction", "content": "..."}]}

    monkeypatch.setattr(web_search, "_web_search", web_search.TavilySearch(tool_factory=Tool))
    fake_llm.main_replies = [tool_call_reply("web_search", {"query": "fractions"}), "A fraction is a share of a whole."]
    # The query gate answers first, then the memory write-back.
    fake_llm.extraction_replies = [SCHOOL_QUERY_VERDICT, "{}"]

    app = view("student").run()
    app.chat_input[0].set_value("Explain fractions to me").run()

    assert not app.exception, app.exception
    shown = texts(app)
    assert "A fraction is a share of a whole." in shown
    assert "https://fr.wikipedia.org/wiki/Fraction" in shown
    assert "“fractions”" in shown


def test_off_topic_questions_move_the_counter_and_show_the_guard(ui, fake_llm):
    app = view("student").run()
    app.chat_input[0].set_value(f"{OFF_TOPIC_MARKER} Who won the match?").run()

    assert not app.exception, app.exception
    assert app.metric[0].value == "1 / 3"
    assert "Guard: 🛡️ off-topic" in texts(app)
    assert fake_llm.calls == []


def test_braille_output_is_rendered_and_downloadable(ui, fake_llm):
    from apu.modality.braille import _liblouis
    try:
        _liblouis.load_library()
    except _liblouis.LiblouisUnavailable as error:
        pytest.skip(str(error))

    fake_llm.main_replies = ["Hello class"]
    fake_llm.extraction_replies = ["{}"]
    app = view("student")
    app.session_state["mode_label"] = "Braille → braille"
    app.run()
    app.chat_input[0].set_value("Hello").run()

    assert not app.exception, app.exception
    assert any("braille-block" in m.value and any(0x2800 <= ord(c) <= 0x28FF for c in m.value)
               for m in app.markdown)


def test_voice_output_shows_the_spoken_answer(ui, fake_llm):
    fake_llm.main_replies = ["Fractions split a whole into parts."]
    fake_llm.extraction_replies = ["{}"]
    app = view("student")
    app.session_state["mode_label"] = "Voice → voice"
    app.run()
    app.chat_input[0].set_value("Explain fractions").run()

    assert not app.exception, app.exception
    assert "🔊 *Fractions split a whole into parts.*" in [m.value for m in app.markdown]


def test_an_answer_is_saved_to_the_notebook_from_its_save_control(ui, fake_llm):
    from apu.notebook.store import EntryKind, NotebookStore

    fake_llm.main_replies = ["To add fractions, use a common denominator."]
    fake_llm.extraction_replies = ["{}"]
    app = view("student").run()
    app.chat_input[0].set_value("How do I add fractions?").run()

    app.button(key="save-1").click().run()

    assert not app.exception, app.exception
    [saved] = NotebookStore().entries("eleve-aya")
    assert (saved.kind, saved.text) == (EntryKind.FULL, "To add fractions, use a common denominator.")
    assert "📓 saved: full answer" in texts(app)


def test_the_notebook_tab_makes_a_braille_sheet_from_the_selected_entries(ui):
    from apu.demo import seed
    from apu.modality.braille import _liblouis
    try:
        _liblouis.load_library()
    except _liblouis.LiblouisUnavailable as error:
        pytest.skip(str(error))

    seed.seed_notebook(progress=lambda message: None)
    app = view("student").run()
    assert "A fraction a/b means a parts out of b equal parts." in texts(app)

    next(b for b in app.button if b.label == "Generate the braille sheet").click().run()

    assert not app.exception, app.exception
    assert any("braille-block" in m.value for m in app.markdown)
    assert any(d.label == "⬇ Embosser file (BRF)" for d in app.get("download_button"))


def test_a_spoken_answer_is_read_out_when_the_voice_provider_answers(ui, fake_llm, monkeypatch):
    import struct

    from apu import config
    from apu.modality import voice
    from tests.test_voice import FakeHTTP

    monkeypatch.setenv(config.ELEVENLABS_API_KEY_ENV, "test-key-not-real")
    voice.set_http(FakeHTTP(content=struct.pack("<h", 3) * 24000 * 3))
    fake_llm.main_replies = ["Fractions split a whole into parts."]
    fake_llm.extraction_replies = ["{}"]

    app = view("student")
    app.session_state["mode_label"] = "Voice → voice"
    app.run()
    app.chat_input[0].set_value("Explain fractions").run()

    assert not app.exception, app.exception
    spoken_message = app.session_state["chat"][-1]
    assert spoken_message["audio"].startswith(b"RIFF") and spoken_message["audio_type"] == "audio/wav"
    voice.set_http(None)


def test_without_working_speech_the_browser_voice_still_reads_the_answer(ui, fake_llm, monkeypatch):
    """
    Speech out can fail for more than a missing key: the provider is down, or the fallback
    to the other provider fails too. Whatever the cause, the answer still reaches the pupil
    and the page says why it is not being read by the chosen voice.
    """
    from apu import config
    from apu.modality import voice

    monkeypatch.delenv(config.ELEVENLABS_API_KEY_ENV, raising=False)
    voice.set_http(None)
    fake_llm.main_replies = ["Fractions split a whole into parts."]
    fake_llm.extraction_replies = ["{}"]

    app = view("student")
    app.session_state["mode_label"] = "Voice → voice"
    app.run()
    app.chat_input[0].set_value("Explain fractions").run()

    assert not app.exception, app.exception
    spoken_message = app.session_state["chat"][-1]
    assert "audio" not in spoken_message
    assert spoken_message["voice_problem"], "a failed synthesis has to be reported, not swallowed"
    assert "using the browser voice" in texts(app)


def test_a_teacher_identity_is_sent_away_from_the_student_page(ui):
    app = view("student", PROF).run()
    assert any("student page" in i.value for i in app.info)


def test_the_cloud_registry_is_only_read_on_demand(ui, monkeypatch):
    requested = install_fake_registry(monkeypatch, ui, manifest(catalog={"6eme": ["math"]}))
    app = view("student").run()
    assert requested == [], "no registry call on page load"

    next(b for b in app.button if b.label == "Browse the cloud registry").click().run()
    assert not app.exception, app.exception
    assert requested == ["manifest.json"]
    assert any(s.label == "Registry courses" for s in app.selectbox)


# ── teacher / admin view ─────────────────────────────────────────────────────

def _seed_event(event_id, class_id="lycee-cocody:3eA", text="Who won the match?"):
    EscalationStore().append_event(EscalationEvent(
        event_id, "eleve-aya", class_id, "s1", 3, text, datetime.now(UTC) - timedelta(minutes=5)))


def test_a_teacher_sees_and_resolves_their_class_escalations(ui):
    _seed_event("e1")
    _seed_event("e2", class_id="lycee-cocody:4eB", text="other class")
    app = view("teacher", PROF).run()

    assert not app.exception, app.exception
    assert [s.options for s in app.selectbox if s.label == "Class"] == [["lycee-cocody:3eA"]]
    assert "Who won the match?" in texts(app) and "other class" not in texts(app)

    app.button(key="FormSubmitter:resolve-e1-Mark as resolved").click().run()
    assert not app.exception, app.exception
    [(_, resolution)] = EscalationStore().list_events_with_resolutions("lycee-cocody:3eA")
    assert resolution.resolved_by == "prof-kouassi"


def test_an_admin_sees_every_class_of_the_establishment(ui):
    app = view("teacher", ADMIN).run()
    assert [s.options for s in app.selectbox if s.label == "Class"] == [["lycee-cocody:3eA", "lycee-cocody:4eB"]]


def test_access_outside_the_scope_is_refused_on_screen(ui):
    app = view("teacher", PROF).run()
    app.text_input(key="access_target").set_value("college-yopougon:6eC")
    next(b for b in app.button if b.label == "Open this class").click().run()
    assert any("403" in e.value and "teacher's scope" in e.value for e in app.error)


def test_a_student_identity_is_sent_away_from_the_teacher_page(ui):
    app = view("teacher").run()
    assert any("teacher / admin page" in i.value for i in app.info)


# ── demo page ────────────────────────────────────────────────────────────────

def test_the_demo_page_lists_checks_and_seeds_example_escalations(ui):
    app = view("demo").run()
    assert not app.exception, app.exception
    shown = texts(app)
    assert "gemini key" in shown and "Models per role" in shown and "liblouis" in shown

    next(b for b in app.button if b.label == "Example escalations only").click().run()
    assert not app.exception, app.exception
    assert len(EscalationStore().events_for_class("lycee-cocody:3eA")) == 6


def test_preparing_the_demo_requires_confirmation(ui):
    app = view("demo").run()
    prepare = next(b for b in app.button if b.label == "Prepare the demo")
    assert prepare.disabled


# ── rendering helpers ────────────────────────────────────────────────────────

def test_the_interface_reuses_one_event_loop_across_turns():
    """
    Pins the fix measured in docs/measurements.md: a fresh loop per turn made the guard
    1.48 s instead of 0.98 s, because its cached client had to recover from a closed loop.
    """
    import asyncio
    import threading

    from apu.ui import common

    async def which_loop():
        return asyncio.get_running_loop()

    first = common.run(which_loop())
    assert common.run(which_loop()) is first, "the loop survived the turn"

    from_another_thread = []
    thread = threading.Thread(target=lambda: from_another_thread.append(common.run(which_loop())))
    thread.start()
    thread.join()
    assert from_another_thread == [first], "a Streamlit rerun on a new thread reuses it too"
    assert not first.is_closed()


# ── accessibility ────────────────────────────────────────────────────────────

def test_the_page_ships_the_accessibility_patch():
    """
    Streamlit gives no way to set ARIA on its own DOM, so this is injected. Measured with
    axe-core before and after (docs/accessibility.md): 1 critical violation and 16 elements
    outside any landmark, down to none, with the answer announced to a screen reader.
    """
    import pathlib as _pathlib

    from apu.ui.common import ACCESSIBILITY_SCRIPT, CHAT_LOG_ANCHOR

    for needed in ("role', 'main", "aria-live", "aria-label', 'Conversation with the tutor",
                   "apu-skip", "KeyQ", "removeAttribute('aria-expanded')"):
        assert needed in ACCESSIBILITY_SCRIPT, needed

    # The loop this avoids hung the page: the observer must not rebuild what it observes.
    observer_target = ACCESSIBILITY_SCRIPT.split("new MutationObserver(")[1].split(")")[0]
    assert observer_target == "applyLandmarks", observer_target
    assert "apu-skip" not in ACCESSIBILITY_SCRIPT.split("function applyLandmarks")[1].split("function install")[0]

    app = (_pathlib.Path(__file__).resolve().parent.parent / "apu" / "ui" / "app.py").read_text()
    assert "inject_accessibility()" in app, "the patch must run on every page"
    student = (_pathlib.Path(__file__).resolve().parent.parent / "apu" / "ui" / "views" / "student.py").read_text()
    assert "CHAT_LOG_ANCHOR" in student, "the live region is found through this marker"
    assert CHAT_LOG_ANCHOR.startswith("<div id=\"apu-chat-log\"")


def test_nemotron_latex_delimiters_become_streamlit_math():
    from apu.ui.common import math_for_streamlit

    assert math_for_streamlit(r"Let us add \( \frac{1}{4} + \frac{1}{6} \).") == r"Let us add $\frac{1}{4} + \frac{1}{6}$."
    assert math_for_streamlit(r"\[ \frac{3}{12} + \frac{2}{12} \]") == "\n$$\n\\frac{3}{12} + \\frac{2}{12}\n$$\n"


def test_braille_text_is_stripped_of_markdown_and_math_delimiters():
    from apu.ui.common import plain_text

    assert plain_text("**Step 1**: compute \\(1/4\\) and `$x$`") == "Step 1: compute 1/4 and x"
