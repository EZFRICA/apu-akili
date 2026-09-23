"""APU Live turn processing pipeline.

Orchestrates:
  1. Safe WebSocket communication (guards against broken pipe / disconnect).
  2. Voice intents: notebook save, notebook summary, braille generation.
  3. NeMo Guardrails + Pedagogical Tutor + DLL retrieval + Student profile.
  4. Spoken audio synthesis (TTS) & Braille translation streaming.
"""

import asyncio
import base64
import time
from starlette.websockets import WebSocket, WebSocketDisconnect

from apu import config
from apu.guardrails import guard as topical_guard
from apu.guardrails.actions import GENTLE_REPLY
from apu.guardrails.classifier import preceding_exchange
from apu.guardrails.session import UnknownSession
from apu.guardrails.session import sessions as guard_sessions
from apu.logger import get_logger
from apu.mmu import dll as mmu
from apu.modality.voice import synthesize
from apu.ui.messages import pupil_facing_reason
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
        # A socket being torn down raises whatever the server stack happens to raise, and
        # a pupil who closed their browser is not an incident. DEBUG, and carry on.
        logger.debug("safe_push exception: %s", exc)
        return False


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
    # Deferred on purpose: importing the tutor graph pulls langgraph and the whole runtime
    # into a process that may only ever serve the page.
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
        audio_b64 = base64.b64encode(spoken_audio.data).decode("ascii")

        await safe_push(client_ws, {
            "type": "audio_response",
            "audio": audio_b64,
            "mime": spoken_audio.mime_type,
            "duration": audio_dur,
            "total_latency_ms": total_lat,
        })
    except Exception as exc:
        # Broad on purpose: speech crosses the network to a provider, and every layer of
        # that has its own exceptions. The turn keeps its text either way.
        logger.warning("Speech synthesis failed: %s", exc)
        await safe_push(client_ws, {"type": "tts_unavailable", "reason": str(exc)})


async def push_braille(client_ws: WebSocket, text: str) -> bool:
    """
    The answer as braille cells. Returns whether any were sent.

    Silence beats a card of empty or apologetic cells: a pupil reading with their fingers
    would take whatever is in it for the answer. The caller uses the return value to avoid
    announcing braille that is not there.
    """
    grade_1, grade_2 = compute_braille(text)
    if not grade_1:
        return False
    await safe_push(client_ws, {"type": "braille_format", "original_text": text,
                                "braille_g1": grade_1, "braille_g2": grade_2})
    return True


async def classify(session_id: str, student_id: str, class_id: str, prompt: str,
                   history: list[dict] | None = None) -> tuple[bool, str, str]:
    """
    Classify what the pupil said. Returns (allowed, reply_to_speak_instead, outcome).

    A voice intent acts on the pupil's words without the tutor ever being called, so without
    this the phrase "save in my notes that <anything>" reached the notebook unclassified.
    Anything other than a clear allow blocks the turn, including a guard that is unavailable.
    """
    try:
        guard_sessions.get(session_id)
    except UnknownSession:
        guard_sessions.open_session(student_id=student_id, class_id=class_id, session_id=session_id)
    try:
        decision = await topical_guard.get_topical_guard().check(
            session_id, prompt, preceding_exchange(history))
    except Exception as error:
        # Broad and deliberate: whatever went wrong, an unclassified turn is not answered.
        logger.warning("The guard could not classify this turn: %s", error)
        return False, ("I cannot check that this is about your schoolwork right now, "
                       "so let us try again in a moment."), "error"
    if decision.allowed:
        return True, "", decision.outcome.value
    # off_topic and welfare both stop the turn, and a child who has just disclosed distress
    # must not be shown the badge meant for somebody asking about football.
    return False, decision.reply or GENTLE_REPLY, decision.outcome.value


async def refuse(client_ws: WebSocket, reply: str, t_start: float, outcome: str = "blocked") -> None:
    """Speak the guard's own reply, and close the turn without the tutor being called."""
    await safe_push(client_ws, {"type": "assistant_token", "token": reply,
                                "guard_status": outcome})
    await synthesize_and_send(client_ws, reply, t_start)
    await safe_push(client_ws, {"type": "turn_complete", "status": outcome})


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

    # DEBUG, not INFO: the log file outlives the process and the pupils are minors, so it
    # carries what happened, never what a child wrote. See apu/logger.py.
    logger.info("Processing a turn for %s (%d characters)", student_id, len(prompt))
    logger.debug("Turn text for %s: %r", student_id, prompt)

    intent = (is_save_notebook_intent(prompt) or is_summary_notebook_intent(prompt)
              or is_braille_intent(prompt))
    if intent:
        # An intent bypasses the tutor, so it bypasses the guard that the tutor runs. It is
        # classified here instead. A turn without an intent is classified by run_turn.
        allowed, reply, outcome = await classify(session_id, student_id, class_id, prompt,
                                                 history)
        if not allowed:
            logger.info("Voice intent stopped by the guard (student=%s, outcome=%s)",
                        student_id, outcome)
            await refuse(client_ws, reply, t_start, outcome=outcome)
            return

    # 1. Handle Voice Intent: Save to Notebook
    if is_save_notebook_intent(prompt):
        logger.info("Voice intent: Save notebook (student=%s)", student_id)
        try:
            nb_res = await asyncio.to_thread(handle_save_notebook, student_id, history, prompt)
        except Exception as error:
            # A full notebook raises NotebookFull. Unreported, it left the pupil waiting for
            # a turn_complete that never came, with no way to know why.
            logger.warning("Notebook save failed for %s: %s", student_id, error)
            await refuse(client_ws, pupil_facing_reason(error, "I could not save that just now. "
                                                  "Let us try again in a moment."),
                         t_start, outcome="error")
            return
        ack_text = nb_res["ack_text"]

        await safe_push(client_ws, {
            "type": "notebook_saved",
            "title": nb_res["title"],
            "content": nb_res["content"],
            "entry_id": nb_res["entry_id"],
            "text": ack_text,
        })
        await safe_push(client_ws, {"type": "assistant_token", "token": ack_text})

        await push_braille(client_ws, ack_text)
        await synthesize_and_send(client_ws, ack_text, t_start)
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": ack_text})
        await safe_push(client_ws, {"type": "turn_complete", "status": "approved"})
        return

    # 2. Handle Voice Intent: Summarize Notebook
    if is_summary_notebook_intent(prompt):
        logger.info("Voice intent: Summarize notebook (student=%s)", student_id)
        try:
            summary_text = await handle_summary_notebook(student_id)
        except Exception as error:
            # Reading the notebook and summarising it crosses sqlite and the network, and
            # the pupil asked out loud: they are told, rather than left with silence.
            logger.warning("Notebook summary failed for %s: %s", student_id, error)
            await refuse(client_ws, pupil_facing_reason(error, "I could not read your notebook just "
                                                  "now. Let us try again in a moment."),
                         t_start, outcome="error")
            return

        await safe_push(client_ws, {
            "type": "notebook_summary",
            "student_id": student_id,
            "text": summary_text,
        })
        await safe_push(client_ws, {"type": "assistant_token", "token": summary_text})

        await push_braille(client_ws, summary_text)
        await synthesize_and_send(client_ws, summary_text, t_start)
        history.append({"role": "user", "content": prompt})
        history.append({"role": "assistant", "content": summary_text})
        await safe_push(client_ws, {"type": "turn_complete", "status": "approved"})
        return

    # 3. Handle Voice Intent: Braille translation
    if is_braille_intent(prompt):
        logger.info("Voice intent: Braille format (student=%s)", student_id)
        target_text = next((entry["content"] for entry in reversed(history)
                            if entry.get("role") == "assistant" and entry.get("content")), "")

        # What is said out loud has to match what was actually produced: announcing a
        # transcription that liblouis could not make would send a pupil to an empty card.
        if not target_text:
            ack = "There is nothing to put into braille yet. Ask me about your lesson first."
        elif await push_braille(client_ws, target_text):
            ack = "Here is the braille transcription of our last explanation."
        else:
            ack = "Braille is not available on this device at the moment."

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
        # The last net before the pupil: the turn ends with something they can act on
        # rather than silence, and the trace goes to the log for whoever reads it.
        logger.error("The turn could not be completed: %s", exc, exc_info=True)
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

    await push_braille(client_ws, tutor_reply)
    await synthesize_and_send(client_ws, tutor_reply, t_start)

    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": tutor_reply})

    await safe_push(client_ws, {
        "type": "turn_complete",
        "status": guard_status,
        "action": guard_action,
    })
