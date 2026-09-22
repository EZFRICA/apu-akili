"""Gemini Live Multimodal runner for APU Live Lab.

Models:
  - gemini-3.8-live
  - gemini-3.8-live-extended-thinking
Architecture:
  Direct Bidirectional Multimodal Live (response_modalities=["AUDIO"]).
  Streams PCM 16kHz audio in -> streams PCM 24kHz audio + output transcription out.

Two things this runner has to get right, and both were wrong before:

  * The session outlives one turn. `session.receive()` ends its iteration as soon as the
    model completes a turn, so a single `async for` over it answers once and then goes
    quiet. It is driven here by an outer loop, and the send and receive halves supervise
    each other so neither is left awaiting a socket the other has already lost.

  * Nothing the model says reaches the pupil before the guard has classified what the
    pupil said. An audio-to-audio model starts answering on its own, so the answer is held
    here (audio and transcription both) until the guard has ruled on the transcript. On a
    refusal the model's audio is dropped and the guard's own reply is spoken instead.
    A guard that cannot reach a verdict blocks the turn: the failure is closed, as it is
    everywhere else in APU.
"""

import asyncio
import base64
import io
import json
import os
import time
import wave
from starlette.websockets import WebSocket, WebSocketDisconnect

from google import genai
from google.genai import types

from apu.logger import get_logger
from apu.modality import voice
from apu.ui.live.pipeline import safe_push, synthesize_and_send
from apu.ui.live.intents import (
    compute_braille,
    is_save_notebook_intent,
    handle_save_notebook,
)

logger = get_logger(__name__)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")


def _pcm24k_to_wav(pcm_bytes: bytes) -> bytes:
    """Convert raw 24kHz 16-bit mono PCM into a standard playable WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _build_system_instruction(student_id: str, class_id: str) -> str:
    return (
        f"You are APU, a supportive, Socratic AI school tutor for a student ({student_id}) "
        f"in class {class_id}.\n"
        "PEDAGOGICAL RULES AND SAFEGUARDS:\n"
        "1. Language: Always respond in clear, accessible, and warm English.\n"
        "2. Brevity: Your spoken answers must be very concise (1 to 3 sentences maximum), optimized for voice.\n"
        "3. Pedagogy: Never give the direct answer. Guide the student step-by-step with engaging questions.\n"
        "4. Safety: Stay strictly within the school curriculum (math, English, science, history, geography). "
        "If the student strays off topic, politely redirect them back to their lessons."
    )


async def _guard_verdict(session_id: str, user_text: str) -> tuple[bool, str]:
    """
    Classify what the pupil said, before a word of the model's answer is released.

    Returns (allowed, reply_to_speak_instead). Everything that is not a clear "on topic"
    blocks the turn: an empty transcript (nothing was classified), a guard that cannot
    reach a verdict, or a guard that is down. The pupil always hears something.
    """
    from apu.guardrails import guard as topical_guard
    from apu.guardrails.actions import GENTLE_REPLY

    if not user_text:
        logger.info("No transcript for this turn, so nothing could be classified; turn dropped.")
        return False, "I did not catch that. Could you say it again?"
    try:
        decision = await topical_guard.get_topical_guard().check(session_id, user_text)
    except Exception as error:
        logger.warning("The guard could not classify a live turn: %s", error)
        return False, "I cannot check that this is about your schoolwork right now, so let us try again in a moment."
    if decision.allowed:
        return True, ""
    return False, decision.reply or GENTLE_REPLY


async def run_gemini_live(
    client_ws: WebSocket,
    model_id: str,
    session_id: str,
    student_id: str,
    class_id: str,
    history: list[dict],
    session_context: dict,
) -> None:
    """Run bidirectional Gemini Live session with real-time audio, transcription, and multi-turn stability."""
    if not GEMINI_KEY:
        await safe_push(client_ws, {"type": "error", "message": "Missing GEMINI_API_KEY"})
        return

    # The guard keeps per-session state (the off-topic count, the validated turn), so the
    # session has to exist before the first question is classified.
    from apu.guardrails.session import UnknownSession
    from apu.guardrails.session import sessions as guard_sessions
    try:
        guard_sessions.get(session_id)
    except UnknownSession:
        guard_sessions.open_session(student_id=student_id, class_id=class_id, session_id=session_id)

    gemini_client = genai.Client(api_key=GEMINI_KEY)
    thinking = "thinking" in model_id

    sys_instruction = _build_system_instruction(student_id, class_id)

    live_config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=types.Content(parts=[types.Part.from_text(text=sys_instruction)]),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        # The browser already knows when the pupil pressed and released the button, so the
        # turn boundary is sent explicitly. Left to its own voice activity detection, the
        # server answered the first turn and then ignored everything that followed: the
        # empty client_content used to mark the end of a turn desynchronised the session.
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=True),
        ),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        thinking_config=types.ThinkingConfig(
            thinking_level=types.ThinkingLevel.HIGH,
            include_thoughts=False,
        ) if thinking else None,
    )

    t_start = [time.perf_counter()]
    current_user_transcript = [""]
    accumulated_text: list[str] = []
    accumulated_audio = bytearray()
    user_audio = bytearray()       # what the pupil said, kept until the guard has a transcript
    speaking = [False]

    try:
        async with gemini_client.aio.live.connect(model=model_id, config=live_config) as session:
            logger.info("Gemini Live connected: %s (student=%s, class=%s)", model_id, student_id, class_id)

            async def send_incoming() -> None:
                while True:
                    msg = await client_ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break

                    chunk = msg.get("bytes")
                    if chunk is not None:
                        if chunk == b"END_OF_TURN":
                            t_start[0] = time.perf_counter()
                            try:
                                if speaking[0]:
                                    await session.send_realtime_input(activity_end=types.ActivityEnd())
                                    speaking[0] = False
                            except Exception as e:
                                logger.debug("Error closing the turn on Gemini: %s", e)
                        else:
                            if not speaking[0]:
                                await session.send_realtime_input(activity_start=types.ActivityStart())
                                speaking[0] = True
                                user_audio.clear()
                            user_audio.extend(chunk)
                            await session.send_realtime_input(
                                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                            )

                    text_data = msg.get("text")
                    if text_data:
                        try:
                            parsed = json.loads(text_data)
                            if parsed.get("type") == "text_prompt":
                                prompt = parsed.get("text", "").strip()
                                if prompt:
                                    t_start[0] = time.perf_counter()
                                    current_user_transcript[0] = prompt
                                    user_audio.clear()
                                    await safe_push(client_ws, {
                                        "type": "user_transcript",
                                        "text": prompt,
                                        "replace": True,
                                    })
                                    await session.send_client_content(
                                        turns=[types.Content(
                                            role="user",
                                            parts=[types.Part.from_text(text=prompt)],
                                        )],
                                        turn_complete=True,
                                    )
                        except Exception as e:
                            logger.debug("Non-JSON text msg: %s", e)

            async def receive_responses() -> None:
                # session.receive() stops iterating at the end of a model turn, so a single
                # pass over it serves one answer and then goes silent. This outer loop is
                # what keeps the conversation alive across turns.
                while True:
                    async for response in session.receive():
                        await handle_response(response)

            async def handle_response(response) -> None:
                sc = getattr(response, "server_content", None)
                if not sc:
                    return

                # 1. User input transcription from Gemini STT in real-time
                interim = getattr(sc, "interim_input_transcription", None)
                if interim and getattr(interim, "text", None):
                    txt = interim.text.strip()
                    if txt:
                        current_user_transcript[0] = txt
                        await safe_push(client_ws, {
                            "type": "user_transcript",
                            "text": txt,
                            "replace": True,
                        })

                final_user = getattr(sc, "input_transcription", None)
                if final_user and getattr(final_user, "text", None):
                    txt = final_user.text.strip()
                    if txt:
                        current_user_transcript[0] = txt
                        await safe_push(client_ws, {
                            "type": "user_transcript",
                            "text": txt,
                            "replace": True,
                        })

                # 2. Output transcription (model speech-to-text tokens in real-time)
                # Held, not forwarded: the pupil sees these words only once the guard
                # has ruled on the question that produced them.
                ot = getattr(sc, "output_transcription", None)
                if ot and getattr(ot, "text", None):
                    accumulated_text.append(ot.text)

                # 3. Audio output chunks (raw PCM 24kHz)
                mt = getattr(sc, "model_turn", None)
                if mt and getattr(mt, "parts", None):
                    for part in mt.parts:
                        inline = getattr(part, "inline_data", None)
                        if inline and getattr(inline, "data", None):
                            raw_audio = inline.data
                            accumulated_audio.extend(raw_audio)

                # 4. Turn complete: the model has finished, nothing has been shown yet.
                if getattr(sc, "turn_complete", False):
                    await close_turn()

            async def close_turn() -> None:
                """Release the held turn, or replace it with the guard's reply."""
                spoken_audio = bytes(accumulated_audio)
                full_reply = "".join(accumulated_text).strip()
                user_text = current_user_transcript[0].strip()
                spoken_by_the_pupil = bytes(user_audio)
                accumulated_audio.clear()
                accumulated_text.clear()
                current_user_transcript[0] = ""
                user_audio.clear()

                # Gemini does not always return an input transcription, and without one the
                # guard has nothing to classify and would refuse a perfectly good question.
                # The pupil's own audio was kept for exactly this case.
                if not user_text and len(spoken_by_the_pupil) >= 3200:
                    try:
                        wav = voice.wav_from_pcm(spoken_by_the_pupil, 16000)
                        user_text = (await asyncio.to_thread(voice.transcribe, wav, "audio/wav")).strip()
                        logger.info("No live transcription; fell back to batch STT.")
                    except Exception as error:
                        logger.warning("Fallback transcription failed: %s", error)
                if user_text:
                    await safe_push(client_ws, {"type": "user_transcript", "text": user_text,
                                                "replace": True})

                allowed, refusal = await _guard_verdict(session_id, user_text)
                if not allowed:
                    # The model's answer is dropped unheard, and the guard speaks instead.
                    logger.info("Live turn blocked by the guard (student=%s)", student_id)
                    await safe_push(client_ws, {"type": "assistant_token", "token": refusal,
                                                "guard_status": "blocked", "subject": "live"})
                    await synthesize_and_send(client_ws, refusal, t_start[0])
                    await safe_push(client_ws, {"type": "turn_complete", "status": "blocked"})
                    return

                history.append({"role": "user", "content": user_text})

                if full_reply:
                    await safe_push(client_ws, {"type": "assistant_token", "token": full_reply,
                                                "guard_status": "approved", "subject": "live"})
                if spoken_audio:
                    await safe_push(client_ws, {
                        "type": "audio_response",
                        "audio": base64.b64encode(_pcm24k_to_wav(spoken_audio)).decode("ascii"),
                        "mime": "audio/wav",
                        "duration": round(len(spoken_audio) / (24000 * 2), 2),
                        "total_latency_ms": round((time.perf_counter() - t_start[0]) * 1000),
                    })

                if full_reply:
                    g1, g2 = compute_braille(full_reply)
                    await safe_push(client_ws, {"type": "braille_format", "original_text": full_reply,
                                                "braille_g1": g1, "braille_g2": g2})
                    history.append({"role": "assistant", "content": full_reply})

                # Voice shortcuts, on a question the guard has already allowed.
                if is_save_notebook_intent(user_text):
                    try:
                        nb_res = await asyncio.to_thread(handle_save_notebook, student_id, history, user_text)
                        await safe_push(client_ws, {
                            "type": "notebook_saved", "title": nb_res["title"],
                            "content": nb_res["content"], "entry_id": nb_res["entry_id"],
                            "text": nb_res["ack_text"],
                        })
                    except Exception as nb_err:
                        logger.warning("Notebook save error in live runner: %s", nb_err)

                await safe_push(client_ws, {"type": "turn_complete", "status": "approved"})

            # Whichever half ends first, the other is awaiting a socket that is going away:
            # a browser that disconnects leaves the receiver blocked on Gemini, and a Gemini
            # socket that closes leaves the sender blocked on the browser.
            tasks = [asyncio.create_task(send_incoming()), asyncio.create_task(receive_responses())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()   # re-raise whatever ended the session

    except (WebSocketDisconnect, ConnectionResetError, asyncio.CancelledError):
        logger.info("Client disconnected (Gemini Live %s)", model_id)
    except Exception as exc:
        logger.warning("Gemini Live error (%s): %s", model_id, exc)
        await safe_push(client_ws, {"type": "error", "message": f"Gemini Live ({model_id}): {exc}"})
