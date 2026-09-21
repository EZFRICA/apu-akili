"""
Tests for APU Live Voice Lab (apu.ui.live).

Target:
  - apu.ui.live.intents
  - apu.ui.live.pipeline
  - apu.ui.live.server
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

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


