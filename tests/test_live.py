"""
Tests for APU Live Voice Lab (apu.ui.live).

Target:
  - apu.ui.live.intents
  - apu.ui.live.pipeline
  - apu.ui.live.server
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from apu.notebook.store import EntryKind, EntryOrigin, NotebookStore, new_entry
from apu.ui.live.intents import (
    compute_braille,
    handle_save_notebook,
    handle_summary_notebook,
    is_braille_intent,
    is_save_notebook_intent,
    is_summary_notebook_intent,
)
from apu.ui.live.pipeline import (
    _load_learning_preferences,
    _load_student_profile,
    call_guard_and_tutor,
    safe_push,
)
from apu.ui.live.server import app
from apu.ui.turn import TurnResult


# ==============================================================================
# 1. Voice Intents Tests
# ==============================================================================

def test_is_save_notebook_intent_english_and_french():
    # English positive
    assert is_save_notebook_intent("Please save this to my notebook")
    assert is_save_notebook_intent("Keep this note in my notes")
    assert is_save_notebook_intent("Write this down in my notebook")

    # French positive
    assert is_save_notebook_intent("Enregistre cela dans mon cahier")
    assert is_save_notebook_intent("Ajoute cette explication à mes notes")
    assert is_save_notebook_intent("Sauvegarde dans mon carnet")

    # Negatives
    assert not is_save_notebook_intent("What is a fraction?")
    assert not is_save_notebook_intent("Explain the French revolution")


def test_is_summary_notebook_intent_english_and_french():
    # English positive
    assert is_summary_notebook_intent("Can you summarize my notebook?")
    assert is_summary_notebook_intent("What is in my notes?")
    assert is_summary_notebook_intent("Give me a recap of my notebook")

    # French positive
    assert is_summary_notebook_intent("Fais-moi un résumé de mon cahier")
    assert is_summary_notebook_intent("Que contient mon carnet de notes ?")
    assert is_summary_notebook_intent("Résume mon cahier s'il te plaît")

    # Negatives
    assert not is_summary_notebook_intent("Tell me a story")
    assert not is_summary_notebook_intent("I want to do math exercises")


def test_is_braille_intent_english_and_french():
    # English positive
    assert is_braille_intent("Can you format this in braille?")
    assert is_braille_intent("Show me the braille code")
    assert is_braille_intent("Translate to braille please")

    # French positive
    assert is_braille_intent("Traduis en braille")
    assert is_braille_intent("Donne-moi le code braille")
    assert is_braille_intent("Affiche le braille de cette réponse")

    # Negatives
    assert not is_braille_intent("Speak louder please")
    assert not is_braille_intent("Save to my notebook")


def test_compute_braille_returns_tuple():
    g1, g2 = compute_braille("Hello world")
    assert isinstance(g1, str) and len(g1) > 0
    assert isinstance(g2, str) and len(g2) > 0


def test_handle_save_notebook(tmp_path):
    store_file = str(tmp_path / "test_notebook.sqlite3")
    custom_store = NotebookStore(store_file)

    history = [
        {"role": "user", "content": "How do I calculate speed?"},
        {"role": "assistant", "content": "Speed is distance divided by time."},
    ]

    with patch("apu.tools.notebook.NotebookStore", return_value=custom_store):
        result = handle_save_notebook(
            student_id="eleve-aya",
            history=history,
            prompt="Please save that to my notebook",
        )

    assert "Speed is distance divided by time." in result["content"]
    assert "Speed is distance divided by time" in result["title"]
    assert "Saved in your notebook" in result["ack_text"]

    entries = custom_store.entries("eleve-aya")
    assert len(entries) == 1
    assert entries[0].text == "Speed is distance divided by time."


def test_handle_summary_notebook_empty(tmp_path):
    store_file = str(tmp_path / "test_notebook_empty.sqlite3")
    custom_store = NotebookStore(store_file)

    with patch("apu.tools.notebook.NotebookStore", return_value=custom_store):
        summary = handle_summary_notebook("eleve-aya")

    assert "empty" in summary.lower() or "cahier" in summary.lower()


def test_handle_summary_notebook_with_entries(tmp_path):
    store_file = str(tmp_path / "test_notebook_entries.sqlite3")
    custom_store = NotebookStore(store_file)
    custom_store.add(
        new_entry(
            student_id="eleve-aya",
            class_level="3e",
            subject="math",
            kind=EntryKind.FULL,
            text="Fractions must have common denominators to be added.",
            source_answer="Fractions must have common denominators to be added.",
            origin=EntryOrigin.CHAT,
        )
    )

    with patch("apu.tools.notebook.NotebookStore", return_value=custom_store):
        summary = handle_summary_notebook("eleve-aya")

    assert isinstance(summary, str) and len(summary) > 0


# ==============================================================================
# 2. Pipeline Core Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_safe_push():
    # Success case
    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()
    ok = await safe_push(mock_ws, {"type": "ping"})
    assert ok is True

    # Disconnect case
    mock_ws.send_json = AsyncMock(side_effect=WebSocketDisconnect)
    ok = await safe_push(mock_ws, {"type": "ping"})
    assert ok is False

    # Generic error case
    mock_ws.send_json = AsyncMock(side_effect=RuntimeError("Pipe broken"))
    ok = await safe_push(mock_ws, {"type": "ping"})
    assert ok is False


def test_load_student_profile_and_preferences():
    from apu.mmu import cache_l1

    cache_l1.flush_all()
    # Initially empty
    assert _load_student_profile("eleve-aya", "3eA") == {}
    assert _load_learning_preferences("eleve-aya", "3eA") == {}

    # Populated in cache
    cache_l1.set("student_profile", "Aya, 3eme, loves science", block_type="fondamental")
    cache_l1.set("learning_preferences", "Prefers visual and audio examples", block_type="fondamental")

    p = _load_student_profile("eleve-aya", "3eA")
    assert p.get("content") == "Aya, 3eme, loves science"

    pref = _load_learning_preferences("eleve-aya", "3eA")
    assert pref.get("content") == "Prefers visual and audio examples"

    cache_l1.flush_all()


@pytest.mark.asyncio
async def test_call_guard_and_tutor_on_topic():
    with patch("apu.ui.turn.run_turn", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = TurnResult(
            content="Water boils at 100 degrees Celsius.",
            spoken="Water boils at 100 degrees Celsius.",
            off_topic=False,
            guard_outcome="on_topic",
        )

        reply, action, status, subject = await call_guard_and_tutor(
            student_id="eleve-aya",
            class_id="lycee-cocody:3eA",
            user_text="At what temperature does water boil?",
            history=[],
            session_context={"session_id": "test-live-session"},
        )

        assert reply == "Water boils at 100 degrees Celsius."
        assert action == "pass"
        assert status == "approved"
        assert subject != ""


@pytest.mark.asyncio
async def test_call_guard_and_tutor_off_topic():
    with patch("apu.ui.turn.run_turn", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = TurnResult(
            content="Let's focus on schoolwork.",
            spoken="Let's focus on schoolwork.",
            off_topic=True,
            guard_outcome="off_topic",
        )

        reply, action, status, subject = await call_guard_and_tutor(
            student_id="eleve-aya",
            class_id="lycee-cocody:3eA",
            user_text="Who won the football match?",
            history=[],
            session_context={"session_id": "test-live-session"},
        )

        assert reply == "Let's focus on schoolwork."
        assert action == "block"
        assert status == "blocked"


# ==============================================================================
# 3. Live Server Endpoint Tests
# ==============================================================================

def test_server_http_endpoints():
    client = TestClient(app)

    # 1. GET / serves HTML
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "text/html" in res_index.headers.get("content-type", "")

    # 2. GET /api/students returns student list
    res_students = client.get("/api/students")
    assert res_students.status_code == 200
    students = res_students.json()
    assert isinstance(students, list)
    assert len(students) > 0
    assert "id" in students[0]
    assert "name" in students[0]


def test_server_websocket_unknown_model():
    client = TestClient(app)
    with client.websocket_connect("/ws/invalid-model-name") as ws:
        msg = ws.receive_json()
        assert msg.get("type") == "error"
        assert "Unknown model" in msg.get("message", "")




# ==============================================================================
# 5. Gemini Live runner: multi-turn survival and the guard gate
# ==============================================================================
#
# The audio-to-audio runner is experimental and not always installed, so these skip
# where it is absent. What they pin down is the pair of rules that make it usable at
# all: the session has to survive past the first answer, and nothing the model says
# may reach the pupil before the guard has ruled on the question.

def _fake_gemini_session(turns):
    """A Gemini Live session whose receive() ends at each turn boundary, as the real one does."""
    class Server:
        def __init__(self, **kwargs):
            self.__dict__.update({"interim_input_transcription": None, "input_transcription": None,
                                  "output_transcription": None, "model_turn": None,
                                  "turn_complete": False, **kwargs})

    class Message:
        def __init__(self, server_content):
            self.server_content = server_content

    def spoken(text, audio=b"\x00\x01" * 100):
        part = type("Part", (), {"inline_data": type("Blob", (), {"data": audio})()})()
        return [Message(Server(output_transcription=type("T", (), {"text": text})())),
                Message(Server(model_turn=type("Turn", (), {"parts": [part]})())),
                Message(Server(turn_complete=True))]

    pending = [spoken(text) for text in turns]

    class Session:
        def __init__(self):
            self.sent = []
            self.asked = asyncio.Event()

        async def send_client_content(self, **kwargs):
            self.sent.append(("client_content", kwargs))
            self.asked.set()

        async def send_realtime_input(self, **kwargs):
            self.sent.append(("realtime_input", kwargs))
            if "activity_end" in kwargs:
                self.asked.set()

        async def receive(self):
            # One call, one turn: exactly the behaviour that used to silence turn two. The
            # model only answers once the turn has actually been closed, so a test sees the
            # same ordering as a browser does.
            await self.asked.wait()
            self.asked.clear()
            if not pending:
                await asyncio.sleep(3600)
            for message in pending.pop(0):
                yield message

    return Session()


def _run_live_turns(monkeypatch, prompts, turns, verdicts, speech=None):
    """
    Drive the runner over a websocket with a faked Gemini and a faked guard.

    `prompts` are typed; `speech` is raw PCM sent as a browser records it, ending with the
    END_OF_TURN marker. The fake session is returned so a test can inspect what was sent.
    """
    runner = pytest.importorskip("apu.ui.live.runner_gemini_live")
    session = _fake_gemini_session(turns)

    class Connect:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(runner, "GEMINI_KEY", "test-key")
    monkeypatch.setattr(runner.genai, "Client", lambda **kwargs: type(
        "C", (), {"aio": type("A", (), {"live": type("L", (), {"connect": Connect})()})()})())
    monkeypatch.setattr(runner, "_guard_verdict", AsyncMock(side_effect=list(verdicts)))
    monkeypatch.setattr(runner, "synthesize_and_send", AsyncMock())

    received = []
    with TestClient(app).websocket_connect("/ws/gemini-3.8-live") as ws:
        for turn_input in (prompts or speech):
            if prompts:
                ws.send_text(json.dumps({"type": "text_prompt", "text": turn_input}))
            else:
                ws.send_bytes(turn_input)
                ws.send_bytes(b"END_OF_TURN")
            while True:
                message = ws.receive_json()
                received.append(message)
                if message["type"] == "turn_complete":
                    break
    return received, session


def test_the_live_session_survives_past_the_first_answer(monkeypatch):
    """The regression this runner was shelved for: turn two used to come back silent."""
    received, _ = _run_live_turns(
        monkeypatch,
        prompts=["What is one half plus one quarter?", "Give me another example"],
        turns=["Three quarters. How did we get there?", "Try one half plus one eighth."],
        verdicts=[(True, ""), (True, "")],
    )

    completions = [m for m in received if m["type"] == "turn_complete"]
    assert len(completions) == 2, "the second turn never completed"
    assert [m["status"] for m in completions] == ["approved", "approved"]
    assert len([m for m in received if m["type"] == "audio_response"]) == 2, "turn two was silent"


def test_a_blocked_live_turn_never_plays_what_the_model_said(monkeypatch):
    """An audio-to-audio model answers on its own, so its answer is dropped, not forwarded."""
    received, _ = _run_live_turns(
        monkeypatch,
        prompts=["Who won the match last night?"],
        turns=["The final score was two one."],
        verdicts=[(False, "Let us get back to your lessons.")],
    )

    assert [m["type"] for m in received if m["type"] == "audio_response"] == [], \
        "the model's own audio must not reach a pupil on a blocked turn"
    spoken = [m["token"] for m in received if m["type"] == "assistant_token"]
    assert spoken == ["Let us get back to your lessons."]
    assert "two one" not in " ".join(spoken), "the blocked answer leaked as text"
    assert received[-1] == {"type": "turn_complete", "status": "blocked"}


async def test_the_guard_verdict_fails_closed():
    """No transcript, or a guard that cannot answer, both block the turn."""
    runner = pytest.importorskip("apu.ui.live.runner_gemini_live")

    allowed, reply = await runner._guard_verdict("session", "")
    assert not allowed and reply, "a turn nobody could classify is refused, and the pupil is told"

    with patch("apu.guardrails.guard.get_topical_guard", side_effect=RuntimeError("guard is down")):
        allowed, reply = await runner._guard_verdict("session", "Explain fractions")
    assert not allowed and reply


def test_a_spoken_turn_is_bounded_by_activity_markers(monkeypatch):
    """
    The browser knows when the pupil pressed and released the button, so the turn boundary
    is sent explicitly. Left to the server's own voice activity detection, the session
    answered the first turn and then ignored every one that followed.
    """
    runner = pytest.importorskip("apu.ui.live.runner_gemini_live")
    monkeypatch.setattr(runner.voice, "transcribe", lambda *args, **kwargs: "What is one half?")

    _, session = _run_live_turns(
        monkeypatch, prompts=None, speech=[b"\x00\x01" * 1600, b"\x00\x01" * 1600],
        turns=["One half is one part in two.", "Here is another one."],
        verdicts=[(True, ""), (True, "")],
    )

    kinds = [kwargs for name, kwargs in session.sent if name == "realtime_input"]
    assert [name for name, _ in session.sent if name == "client_content"] == [], \
        "an empty client_content is what used to desynchronise the session"
    assert sum("activity_start" in k for k in kinds) == 2, "each spoken turn opens explicitly"
    assert sum("activity_end" in k for k in kinds) == 2, "and closes explicitly"
    assert sum("audio" in k for k in kinds) == 2, "the audio itself still goes through"


def test_a_turn_without_a_live_transcription_falls_back_to_batch_stt(monkeypatch):
    """
    Gemini does not always return an input transcription. Without one the guard has nothing
    to classify and would refuse a perfectly good question, so the pupil's own audio is kept
    and transcribed the ordinary way.
    """
    runner = pytest.importorskip("apu.ui.live.runner_gemini_live")
    monkeypatch.setattr(runner.voice, "transcribe",
                        lambda *args, **kwargs: "What is one half plus one quarter?")
    received, _ = _run_live_turns(
        monkeypatch, prompts=None, speech=[b"\x00\x01" * 1600],
        turns=["Three quarters."], verdicts=[(True, "")],
    )

    heard = [m["text"] for m in received if m["type"] == "user_transcript"]
    assert heard == ["What is one half plus one quarter?"], \
        "the pupil's question has to reach the guard, and the screen, even so"
    assert [m["status"] for m in received if m["type"] == "turn_complete"] == ["approved"]
