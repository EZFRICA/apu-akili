"""APU Live turn processing pipeline.

Orchestrates:
  1. Safe WebSocket communication (guards against broken pipe / disconnect).
  2. Voice intents: notebook save, notebook summary, braille generation.
  3. NeMo Guardrails + Pedagogical Tutor + DLL retrieval + Student profile.
  4. Spoken audio synthesis (TTS) & Braille translation streaming.
"""

import asyncio
import time
from starlette.websockets import WebSocket, WebSocketDisconnect

from apu import config
from apu.logger import get_logger
from apu.modality.voice import synthesize
from apu.ui.live.intents import (
    is_save_notebook_intent,
    is_summary_notebook_intent,
    is_braille_intent,
    handle_save_notebook,
    handle_summary_notebook,
    compute_braille,
)

logger = get_logger(__name__)


async def safe_push(ws: WebSocket, payload: dict) -> bool:
    """Send JSON payload to client WebSocket without crashing on disconnect."""
    try:
        await ws.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError, ConnectionResetError):
        return False
    except Exception as exc:
        logger.debug("safe_push exception: %s", exc)
        return False


def _load_student_profile(student_id: str = "", class_id: str = "") -> dict:
    """Read student profile from MMU L1 RAM cache."""
    try:
        from apu.mmu import cache_l1
        content = cache_l1.get("student_profile")
        return {"content": content, "student_id": student_id} if content else {}
    except Exception as exc:
        logger.debug("Could not load student profile %s: %s", student_id, exc)
        return {}


def _load_learning_preferences(student_id: str = "", class_id: str = "") -> dict:
    """Read learning preferences from MMU L1 RAM cache."""
    try:
        from apu.mmu import cache_l1
        content = cache_l1.get("learning_preferences")
        return {"content": content, "student_id": student_id} if content else {}
    except Exception as exc:
        logger.debug("Could not load learning preferences %s: %s", student_id, exc)
        return {}


async def call_guard_and_tutor(
    student_id: str,
    class_id: str,
    user_text: str,
    history: list[dict],
    session_context: dict,
) -> tuple[str, str, str, str]:
    """
    Pass user text through NeMo Guardrails + APU tutor pipeline.
    Returns: (final_response, guard_action, guard_status, subject)
    """
    from apu.guardrails.session import UnknownSession
    from apu.guardrails.session import sessions as guard_sessions
    from apu.mmu import dll as mmu
    from apu.ui.turn import run_turn

    session_id = session_context.get("session_id") or f"live-{student_id}"
    try:
        guard_sessions.get(session_id)
    except UnknownSession:
        guard_sessions.open_session(student_id=student_id, class_id=class_id, session_id=session_id)

    dll_state = await mmu.load_dll()
    course = dll_state.get("course_selection", {})
    class_level = session_context.get("class_level") or course.get("class") or config.EDU_DEFAULT_CLASS
    subject = session_context.get("subject") or course.get("subject") or config.EDU_DEFAULT_SUBJECT
    agent_id = dll_state.get("agent_id")

    previous_answer = next(
        (m["content"] for m in reversed(history) if m.get("role") == "assistant" and m.get("content")),
        "",
    )

    turn_result = await run_turn(
        prompt=user_text,
        session_id=session_id,
        class_level=class_level,
        subject=subject,
        agent_id=agent_id,
        history=history,
        history_turns=3,
        input_channel="voice",
        output_channel="voice",
        text_display=True,
        previous_answer=previous_answer,
    )

    if turn_result.failed and turn_result.error:
        raise turn_result.error

    tutor_reply = turn_result.spoken or turn_result.content or ""
    guard_action = "block" if turn_result.off_topic else "pass"
    guard_status = "blocked" if turn_result.off_topic else "approved"

    return tutor_reply, guard_action, guard_status, subject


async def synthesize_and_send(client_ws: WebSocket, text: str, t_start: float) -> None:
    """Synthesize speech via voice.synthesize (ElevenLabs or Gemini fallback) and send to client."""
    try:
        spoken_audio = await asyncio.to_thread(synthesize, text)
        audio_dur = round(len(spoken_audio.data) / (24000 * 2), 2)
        total_lat = round((time.perf_counter() - t_start) * 1000)

        import base64
        audio_b64 = base64.b64encode(spoken_audio.data).decode("ascii")

        await safe_push(client_ws, {
            "type": "audio_response",
            "audio": audio_b64,
            "mime": spoken_audio.mime_type,
            "duration": audio_dur,
            "total_latency_ms": total_lat,
        })
    except Exception as exc:
        logger.warning("TTS failed: %s", exc)
        await safe_push(client_ws, {"type": "tts_unavailable", "reason": str(exc)})


async def process_turn(
    client_ws: WebSocket,
    prompt: str,
    session_id: str,
    student_id: str,
    class_id: str,
    history: list[dict],
    t_start: float,
    session_context: dict,
) -> None:
    """Full turn execution: Voice Intents -> NeMo Guardrails -> Tutor -> TTS + Braille."""
    prompt = prompt.strip()
    if not prompt:
        return

    logger.info("Processing turn for %s: '%s'", student_id, prompt)

    # 1. Handle Voice Intent: Save to Notebook
    if is_save_notebook_intent(prompt):
        logger.info("Voice intent: Save notebook (student=%s)", student_id)
        nb_res = await asyncio.to_thread(handle_save_notebook, student_id, history, prompt)
        ack_text = nb_res["ack_text"]

        await safe_push(client_ws, {
            "type": "notebook_saved",
            "title": nb_res["title"],
            "content": nb_res["content"],
            "entry_id": nb_res["entry_id"],
            "text": ack_text,
        })
        await safe_push(client_ws, {"type": "assistant_token", "token": ack_text})

        g1, g2 = compute_braille(ack_text)
        await safe_push(client_ws, {
            "type": "braille_format",
            "original_text": ack_text,
            "braille_g1": g1,
            "braille_g2": g2,
        })

        await synthesize_and_send(client_ws, ack_text, t_start)
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": ack_text})
        await safe_push(client_ws, {"type": "turn_complete", "status": "approved"})
        return

    # 2. Handle Voice Intent: Summarize Notebook
    if is_summary_notebook_intent(prompt):
        logger.info("Voice intent: Summarize notebook (student=%s)", student_id)
        summary_text = await asyncio.to_thread(handle_summary_notebook, student_id)

        await safe_push(client_ws, {
            "type": "notebook_summary",
            "student_id": student_id,
            "text": summary_text,
        })
        await safe_push(client_ws, {"type": "assistant_token", "token": summary_text})

        g1, g2 = compute_braille(summary_text)
        await safe_push(client_ws, {
            "type": "braille_format",
            "original_text": summary_text,
            "braille_g1": g1,
            "braille_g2": g2,
        })

        await synthesize_and_send(client_ws, summary_text, t_start)
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": summary_text})
        await safe_push(client_ws, {"type": "turn_complete", "status": "approved"})
        return

    # 3. Handle Voice Intent: Braille translation
    if is_braille_intent(prompt):
        logger.info("Voice intent: Braille format (student=%s)", student_id)
        target_text = ""
        for msg in reversed(history):
            if msg.get("role") == "assistant" and msg.get("content"):
                target_text = msg["content"]
                break
        if not target_text:
            target_text = "Hello! Here is the APU tutor in Braille."

        g1, g2 = compute_braille(target_text)
        ack = "Here is the Braille transcription of our last explanation."

        await safe_push(client_ws, {
            "type": "braille_format",
            "original_text": target_text,
            "braille_g1": g1,
            "braille_g2": g2,
        })
        await safe_push(client_ws, {"type": "assistant_token", "token": ack})

        await synthesize_and_send(client_ws, ack, t_start)
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": ack})
        await safe_push(client_ws, {"type": "turn_complete", "status": "approved"})
        return

    # 4. Standard Pedagogical Turn through NeMo Guardrails + Tutor
    t_pipeline_start = time.perf_counter()
    try:
        tutor_reply, guard_action, guard_status, subject = await call_guard_and_tutor(
            student_id, class_id, prompt, history, session_context
        )
    except Exception as exc:
        logger.error("Error executing APU pipeline: %s", exc, exc_info=True)
        tutor_reply = "I am experiencing a temporary issue. Could you please repeat your question?"
        guard_action = "error"
        guard_status = "error"
        subject = "error"

    pipeline_lat = round((time.perf_counter() - t_pipeline_start) * 1000)

    # Stream the assistant tokens to client
    await safe_push(client_ws, {
        "type": "assistant_token",
        "token": tutor_reply,
        "guard_status": guard_status,
        "guard_action": guard_action,
        "subject": subject,
        "pipeline_ms": pipeline_lat,
    })

    # Generate Braille cards automatically for any assistant response
    g1, g2 = compute_braille(tutor_reply)
    await safe_push(client_ws, {
        "type": "braille_format",
        "original_text": tutor_reply,
        "braille_g1": g1,
        "braille_g2": g2,
    })

    # Synthesize audio (TTS)
    await synthesize_and_send(client_ws, tutor_reply, t_start)

    # Append to history as clean role/content dictionaries
    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": tutor_reply})

    await safe_push(client_ws, {
        "type": "turn_complete",
        "status": guard_status,
        "action": guard_action,
    })
