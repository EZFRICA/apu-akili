"""
Tests for APU Live Voice Lab (apu.ui.live).

Target:
  - apu.ui.live.intents
  - apu.ui.live.pipeline
  - apu.ui.live.server
"""

import asyncio
import json
import pathlib
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from apu import config
from apu.notebook.store import EntryKind, EntryOrigin, NotebookStore, new_entry
from apu.ui.live.intents import (
    compute_braille,
    handle_save_notebook,
    handle_summary_notebook,
    is_braille_intent,
    is_save_notebook_intent,
    is_summary_notebook_intent,
)
from apu.ui.live.pipeline import call_guard_and_tutor, safe_push
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


async def test_handle_summary_notebook_empty(tmp_path):
    store_file = str(tmp_path / "test_notebook_empty.sqlite3")
    custom_store = NotebookStore(store_file)

    with patch("apu.notebook.store.NotebookStore", return_value=custom_store):
        summary = await handle_summary_notebook("eleve-aya")

    assert "empty" in summary.lower() or "cahier" in summary.lower()


async def test_handle_summary_notebook_with_entries(tmp_path):
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

    with patch("apu.notebook.store.NotebookStore", return_value=custom_store), \
            patch("apu.notebook.service.summarize_entries",
                  AsyncMock(return_value="You revised adding fractions.")) as summarize:
        summary = await handle_summary_notebook("eleve-aya")

    assert summary == "You revised adding fractions."
    sent = summarize.await_args.args[0]
    assert len(sent) <= config.NOTEBOOK_MAX_SHEET_ENTRIES, \
        "the service caps how much of a notebook may be sent to a model, and it is applied here"


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

def _fake_gemini_session(turns, audio_parts=1, part_bytes=200):
    """
    A Gemini Live session whose receive() ends at each turn boundary, as the real one does.

    `audio_parts` and `part_bytes` shape the answer's audio, so a test can push a turn past
    the runner's ceiling the way a model that will not stop talking would.
    """
    class Server:
        def __init__(self, **kwargs):
            self.__dict__.update({"interim_input_transcription": None, "input_transcription": None,
                                  "output_transcription": None, "model_turn": None,
                                  "turn_complete": False, **kwargs})

    class Message:
        def __init__(self, server_content):
            self.server_content = server_content

    def spoken(text):
        def part():
            blob = type("Blob", (), {"data": b"\x00\x01" * (part_bytes // 2)})()
            return type("Part", (), {"inline_data": blob})()

        messages = [Message(Server(output_transcription=type("T", (), {"text": text})()))]
        messages += [Message(Server(model_turn=type("Turn", (), {"parts": [part()]})()))
                     for _ in range(audio_parts)]
        return messages + [Message(Server(turn_complete=True))]

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


def _run_live_turns(monkeypatch, prompts, turns, verdicts, speech=None, audio_parts=1,
                    part_bytes=200):
    """
    Drive the runner over a websocket with a faked Gemini and a faked guard.

    `prompts` are typed; `speech` is raw PCM sent as a browser records it, ending with the
    END_OF_TURN marker. The fake session is returned so a test can inspect what was sent.
    """
    runner = pytest.importorskip("apu.ui.live.runner_gemini_live")
    session = _fake_gemini_session(turns, audio_parts=audio_parts, part_bytes=part_bytes)

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
        verdicts=[(True, "", "on_topic"), (True, "", "on_topic")],
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
        verdicts=[(False, "Let us get back to your lessons.", "off_topic")],
    )

    assert [m["type"] for m in received if m["type"] == "audio_response"] == [], \
        "the model's own audio must not reach a pupil on a blocked turn"
    spoken = [m["token"] for m in received if m["type"] == "assistant_token"]
    assert spoken == ["Let us get back to your lessons."]
    assert "two one" not in " ".join(spoken), "the blocked answer leaked as text"
    assert received[-1] == {"type": "turn_complete", "status": "off_topic"}


async def test_the_guard_verdict_fails_closed():
    """No transcript, or a guard that cannot answer, both block the turn."""
    runner = pytest.importorskip("apu.ui.live.runner_gemini_live")

    allowed, reply, outcome = await runner._guard_verdict("session", "")
    assert not allowed and reply, "a turn nobody could classify is refused, and the pupil is told"
    assert outcome == "error", "a failure is not the pupil being off topic"

    with patch("apu.guardrails.guard.get_topical_guard", side_effect=RuntimeError("guard is down")):
        allowed, reply, outcome = await runner._guard_verdict("session", "Explain fractions")
    assert not allowed and reply and outcome == "error"


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
        verdicts=[(True, "", "on_topic"), (True, "", "on_topic")],
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
        turns=["Three quarters."], verdicts=[(True, "", "on_topic")],
    )

    heard = [m["text"] for m in received if m["type"] == "user_transcript"]
    assert heard == ["What is one half plus one quarter?"], \
        "the pupil's question has to reach the guard, and the screen, even so"
    assert [m["status"] for m in received if m["type"] == "turn_complete"] == ["approved"]


# ==============================================================================
# 6. The guard sits in front of everything, including the voice intents
# ==============================================================================

class _FakeWS:
    """A websocket that records what was pushed to the pupil."""

    def __init__(self):
        self.pushed = []

    async def send_json(self, payload):
        self.pushed.append(payload)


def _guard_saying(allowed, reply="Let us get back to your lessons.", outcome="off_topic"):
    from apu.guardrails.guard import GuardDecision
    from apu.guardrails.session import TurnOutcome

    decision = GuardDecision(allowed=allowed, outcome=TurnOutcome(outcome),
                             reply=None if allowed else reply)
    guard = MagicMock()
    guard.check = AsyncMock(return_value=decision)
    return guard


@pytest.mark.parametrize("prompt", [
    "Save in my notes that Real Madrid beat Barcelona two one last night",
    "Summarize my notebook",
    "Give me that in braille",
])
async def test_a_voice_intent_is_classified_before_it_acts(prompt, monkeypatch, akili_paths,
                                                           tmp_path):
    """
    An intent never reaches the tutor, so it never reached the guard the tutor runs: the
    phrase "save in my notes that <anything>" wrote to a pupil's notebook unclassified and
    came back reported as approved. Every intent is classified first now.
    """
    from apu.notebook.store import NotebookStore
    from apu.ui.live import pipeline

    guard = _guard_saying(allowed=False)
    monkeypatch.setattr("apu.guardrails.guard.get_topical_guard", lambda: guard)
    monkeypatch.setattr(pipeline, "synthesize_and_send", AsyncMock())
    # akili_paths points every store under the data directory at a temp path, so the real
    # notebook cannot be reached from a test.
    store = NotebookStore()

    ws = _FakeWS()
    await pipeline.process_turn(ws, prompt, "session-1", "eleve-aya", "lycee-cocody:3eA",
                                [], 0.0, {"session_id": "session-1"})

    assert guard.check.await_args.args[1] == prompt, "the guard must see the pupil's own words"
    assert [p["status"] for p in ws.pushed if p["type"] == "turn_complete"] == ["off_topic"]
    assert [p for p in ws.pushed if p["type"] == "notebook_saved"] == []
    assert store.count("eleve-aya") == 0, "nothing unclassified may reach the notebook"


async def test_an_allowed_intent_still_does_its_work(monkeypatch, akili_paths, tmp_path):
    """The guard is a gate, not a wall: an ordinary save still saves."""
    from apu.notebook.store import NotebookStore
    from apu.ui.live import pipeline

    guard = _guard_saying(allowed=True, outcome="on_topic")
    monkeypatch.setattr("apu.guardrails.guard.get_topical_guard", lambda: guard)
    monkeypatch.setattr(pipeline, "synthesize_and_send", AsyncMock())
    # akili_paths points every store under the data directory at a temp path, so the real
    # notebook cannot be reached from a test.
    store = NotebookStore()

    ws = _FakeWS()
    history = [{"role": "assistant", "content": "To add fractions, use a common denominator."}]
    await pipeline.process_turn(ws, "Save that in my notebook", "session-2", "eleve-aya",
                                "lycee-cocody:3eA", history, 0.0, {"session_id": "session-2"})

    assert [p["status"] for p in ws.pushed if p["type"] == "turn_complete"] == ["approved"]
    assert store.count("eleve-aya") == 1


async def test_a_full_notebook_is_reported_instead_of_hanging(monkeypatch, akili_paths):
    """NotebookFull used to escape into a bare task, leaving the pupil waiting for ever."""
    from apu.notebook.store import NotebookFull
    from apu.ui.live import pipeline

    monkeypatch.setattr("apu.guardrails.guard.get_topical_guard",
                        lambda: _guard_saying(allowed=True, outcome="on_topic"))
    monkeypatch.setattr(pipeline, "synthesize_and_send", AsyncMock())
    monkeypatch.setattr(pipeline, "handle_save_notebook",
                        MagicMock(side_effect=NotebookFull("Your notebook is full (200 entries).")))

    ws = _FakeWS()
    await pipeline.process_turn(ws, "Save that in my notebook", "session-3", "eleve-aya",
                                "lycee-cocody:3eA", [], 0.0, {"session_id": "session-3"})

    assert [p["status"] for p in ws.pushed if p["type"] == "turn_complete"] == ["error"]
    spoken = " ".join(p["token"] for p in ws.pushed if p["type"] == "assistant_token")
    assert "full" in spoken, "the pupil is told why, out loud, because they may not see a screen"


async def test_an_internal_fault_is_not_read_out_to_a_pupil(monkeypatch, akili_paths):
    """
    A pupil's own limit is theirs to hear. A driver error is not: it is read aloud to a
    child who may have no screen, and it says nothing they can act on.
    """
    from apu.ui.live import pipeline

    monkeypatch.setattr("apu.guardrails.guard.get_topical_guard",
                        lambda: _guard_saying(allowed=True, outcome="on_topic"))
    monkeypatch.setattr(pipeline, "synthesize_and_send", AsyncMock())
    monkeypatch.setattr(pipeline, "handle_save_notebook",
                        MagicMock(side_effect=sqlite3.OperationalError("database is locked")))

    ws = _FakeWS()
    await pipeline.process_turn(ws, "Save that in my notebook", "session-4", "eleve-aya",
                                "lycee-cocody:3eA", [], 0.0, {"session_id": "session-4"})

    spoken = " ".join(p["token"] for p in ws.pushed if p["type"] == "assistant_token")
    assert "database is locked" not in spoken and "sqlite" not in spoken.lower()
    assert "try again" in spoken, "the pupil still hears something they can act on"
    assert [p["status"] for p in ws.pushed if p["type"] == "turn_complete"] == ["error"]


# ==============================================================================
# 7. Who may open a socket, and as whom
# ==============================================================================

def test_a_socket_from_another_site_is_refused():
    """
    A websocket is not covered by the same-origin policy. Without this check any page the
    pupil visits, while this server runs, could drive the tutor and read a notebook back.
    """
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/gemini-3.5-transcribe-live",
                                      headers={"Origin": "https://evil.example"}) as ws:
            ws.receive_json()


def test_an_unknown_student_cannot_open_a_session():
    """Identity is a stub, but an identifier nobody on this device knows is still refused."""
    client = TestClient(app)
    with client.websocket_connect("/ws/gemini-3.5-transcribe-live?student_id=not-a-pupil") as ws:
        message = ws.receive_json()
    assert message["type"] == "error" and "not-a-pupil" in message["message"]


def test_the_session_identifier_is_issued_by_the_server(monkeypatch):
    """
    The guard counts off-topic turns per session. A client that chose its own identifier
    could rotate it every turn and never reach an escalation.
    """
    import inspect

    from apu.ui.live import server

    source = inspect.getsource(server.ws_proxy)
    assert "session_id: str = Query" not in source, "the client must not name the session"
    assert "uuid4()" in source


# ==============================================================================
# 8. Nothing held in memory may grow without bound
# ==============================================================================
#
# This runner holds a whole turn before anything is played: the pupil's audio until the
# guard has a transcript, and the model's answer until the guard has ruled. Both are fed
# by a socket the server does not control, so both need a ceiling.

def test_the_held_answer_stops_growing_at_the_ceiling(monkeypatch, caplog):
    import base64

    runner = pytest.importorskip("apu.ui.live.runner_gemini_live")
    monkeypatch.setattr(runner, "MAX_ANSWER_AUDIO_BYTES", 1000)

    with caplog.at_level("WARNING", logger=runner.logger.name):
        received, _ = _run_live_turns(
            monkeypatch, prompts=["Explain fractions"], turns=["A long answer."],
            verdicts=[(True, "", "on_topic")], audio_parts=5, part_bytes=600,
        )

    played = [m for m in received if m["type"] == "audio_response"]
    assert len(played) == 1
    # 44 bytes of WAV header around the PCM that was kept: two parts, not five.
    pcm = len(base64.b64decode(played[0]["audio"])) - 44
    assert pcm == 1200, f"kept {pcm} bytes, so the ceiling did not hold"
    assert sum("the rest is dropped" in r.message for r in caplog.records) == 1, \
        "reported once for the turn, not once per chunk"


def test_the_pupils_own_audio_stops_growing_at_the_ceiling(monkeypatch):
    from apu import config

    runner = pytest.importorskip("apu.ui.live.runner_gemini_live")
    monkeypatch.setattr(config, "VOICE_MAX_RECORDING_BYTES", 3200)

    transcribed = []

    def fake_transcribe(wav, mime="audio/wav"):
        transcribed.append(len(wav))
        return "What is one half?"

    monkeypatch.setattr(runner.voice, "transcribe", fake_transcribe)

    _run_live_turns(monkeypatch, prompts=None, speech=[b"\x00\x01" * 1600 * 3],
                    turns=["One half is one part in two."], verdicts=[(True, "", "on_topic")])

    assert transcribed, "no live transcription arrived, so the fallback had to run"
    # The WAV header is 44 bytes; the pupil's audio inside it is what the ceiling bounds.
    assert transcribed[0] - 44 == 3200, "one very large frame must be truncated, not accepted"


def test_a_socket_from_the_lab_itself_is_accepted():
    """
    The origin check must not lock out the page the server serves. A refused origin is
    closed before the handshake completes, so reaching the dispatcher at all is the proof:
    an unknown model answers, a refused origin never would.
    """
    client = TestClient(app)
    with client.websocket_connect("/ws/not-a-model",
                                  headers={"Origin": "http://localhost:8765"}) as ws:
        message = ws.receive_json()
    assert message["type"] == "error" and "not-a-model" in message["message"]


async def test_the_guard_is_not_shown_the_question_it_is_classifying(monkeypatch, akili_paths):
    """
    The exchange is the turns BEFORE this one. Passing the current question inside it too
    would let a message argue its own case in the part the prompt calls background.
    """
    from apu.ui.live import pipeline

    guard = _guard_saying(allowed=True, outcome="on_topic")
    monkeypatch.setattr("apu.guardrails.guard.get_topical_guard", lambda: guard)
    monkeypatch.setattr(pipeline, "synthesize_and_send", AsyncMock())
    history = [{"role": "user", "content": "Explain fractions"},
               {"role": "assistant", "content": "How many quarters are in one half?"}]

    await pipeline.process_turn(_FakeWS(), "Save that in my notebook", "session-x", "eleve-aya",
                                "lycee-cocody:3eA", history, 0.0, {"session_id": "session-x"})

    message, exchange = guard.check.await_args.args[1], guard.check.await_args.args[2]
    assert message == "Save that in my notebook"
    assert "Save that in my notebook" not in exchange
    assert exchange.splitlines() == ["Tutor: How many quarters are in one half?",
                                     "Student: Explain fractions"]


def test_the_badge_shown_to_a_pupil_is_never_built_from_the_message():
    """
    An interpolated server field in innerHTML is one refactor away from an injection, and
    the outcomes a pupil can be shown are a closed set anyway.
    """
    chat_js = (pathlib.Path(__file__).resolve().parents[1]
               / "apu/ui/live/static/js/chat.js").read_text(encoding="utf-8")

    assert "${meta.guard_status}" not in chat_js
    assert "GUARD_BADGES" in chat_js
    for outcome in ("on_topic", "off_topic", "welfare", "error", "uncertain"):
        assert f"{outcome}:" in chat_js, f"{outcome} has no badge, so it would show none"
    assert "welfare: { css: \"welfare\"" in chat_js, "a disclosure is not badged as a refusal"


# ==============================================================================
# 9. What the log is allowed to carry
# ==============================================================================

def test_the_chatty_clients_are_silenced_by_name(akili_paths):
    """
    These libraries log every request and response header at DEBUG. One of those headers
    is a provider API key, and the audio frames are a pupil's own voice. The names carry
    the client's major version, so silencing "httpx" alone leaves "httpx2" talking, which
    is exactly what happened.
    """
    import logging

    from apu import logger as apu_logger

    for handler in logging.getLogger().handlers[:]:
        logging.getLogger().removeHandler(handler)
    apu_logger.configure_root_logger()

    for name in ("httpx", "httpx2", "httpcore", "httpcore2", "websockets", "google_genai",
                 "openai", "nemoguardrails"):
        assert logging.getLogger(name).level >= logging.WARNING, f"{name} still logs at DEBUG"


def test_a_pupils_words_do_not_reach_the_persistent_log(akili_paths, caplog):
    """
    The log file outlives the process and the pupils are minors, so INFO carries what
    happened and DEBUG carries what was said. The file handler is INFO.
    """
    import inspect
    import logging

    from apu.ui.live import pipeline

    source = inspect.getsource(pipeline.process_turn)
    info_line = next(line for line in source.splitlines() if "logger.info(\"Processing" in line)
    assert "len(prompt)" in info_line and "prompt)" not in info_line.replace("len(prompt)", "")

    file_handlers = [h for h in logging.getLogger().handlers
                     if isinstance(h, logging.FileHandler)]
    assert file_handlers, "the runtime log file is what this test is about"
    assert all(h.level >= logging.INFO for h in file_handlers)


def test_the_page_never_offers_a_pupil_the_socket_would_refuse(monkeypatch):
    """
    The selector and the socket check read one roster. When it cannot be read the page
    offers nobody, rather than three invented names that cannot then connect.
    """
    from apu.ui.live import server

    monkeypatch.setattr(server.seed, "load_demo_students",
                        MagicMock(side_effect=OSError("registry missing")))
    client = TestClient(app)

    assert client.get("/api/students").json() == []
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/gemini-3.5-transcribe-live?student_id=eleve-aya") as ws:
            assert ws.receive_json()["type"] == "error"
            ws.receive_json()


def test_the_page_offers_exactly_the_pupils_the_socket_accepts():
    client = TestClient(app)
    offered = {pupil["id"] for pupil in client.get("/api/students").json()}

    assert offered, "the demo registry should list pupils"
    for student_id in offered:
        with client.websocket_connect(f"/ws/not-a-model?student_id={student_id}") as ws:
            message = ws.receive_json()
        assert "not-a-model" in message["message"], f"{student_id} was refused as unknown"


# ==============================================================================
# 10. Braille: what is announced is what was produced
# ==============================================================================

async def test_no_braille_card_is_sent_when_there_are_no_cells(monkeypatch):
    """
    A pupil reading with their fingers takes whatever is in the card for the answer, so an
    empty or apologetic card is worse than none.
    """
    from apu.ui.live import pipeline

    monkeypatch.setattr(pipeline, "compute_braille", lambda text: ("", ""))
    ws = _FakeWS()

    assert await pipeline.push_braille(ws, "Three quarters.") is False
    assert ws.pushed == []


async def test_the_braille_intent_does_not_announce_what_liblouis_could_not_make(monkeypatch,
                                                                                 akili_paths):
    from apu.ui.live import pipeline

    monkeypatch.setattr("apu.guardrails.guard.get_topical_guard",
                        lambda: _guard_saying(allowed=True, outcome="on_topic"))
    monkeypatch.setattr(pipeline, "synthesize_and_send", AsyncMock())
    monkeypatch.setattr(pipeline, "compute_braille", lambda text: ("", ""))
    history = [{"role": "assistant", "content": "A fraction is a part of a whole."}]

    ws = _FakeWS()
    await pipeline.process_turn(ws, "Give me that in braille", "session-b", "eleve-aya",
                                "lycee-cocody:3eA", history, 0.0, {"session_id": "session-b"})

    spoken = " ".join(p["token"] for p in ws.pushed if p["type"] == "assistant_token")
    assert "not available" in spoken
    assert [p for p in ws.pushed if p["type"] == "braille_format"] == []


async def test_the_braille_intent_says_so_when_there_is_nothing_to_translate(monkeypatch,
                                                                             akili_paths):
    from apu.ui.live import pipeline

    monkeypatch.setattr("apu.guardrails.guard.get_topical_guard",
                        lambda: _guard_saying(allowed=True, outcome="on_topic"))
    monkeypatch.setattr(pipeline, "synthesize_and_send", AsyncMock())

    ws = _FakeWS()
    await pipeline.process_turn(ws, "Give me that in braille", "session-c", "eleve-aya",
                                "lycee-cocody:3eA", [], 0.0, {"session_id": "session-c"})

    spoken = " ".join(p["token"] for p in ws.pushed if p["type"] == "assistant_token")
    assert "nothing to put into braille" in spoken
