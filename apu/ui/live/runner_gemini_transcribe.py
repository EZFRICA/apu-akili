"""Gemini Live Transcribe runner for APU Live Lab.

Model: gemini-3.5-transcribe-live
Architecture: Browser PCM 16kHz -> Gemini Live STT (per-turn) -> process_turn (Guardrails + Tutor + TTS).
"""

import asyncio
import json
import os
import time
from starlette.websockets import WebSocket, WebSocketDisconnect

from google import genai
from google.genai import types

from apu.logger import get_logger
from apu.modality import voice
from apu.ui.live.pipeline import safe_push, process_turn

logger = get_logger(__name__)

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")


async def run_gemini_transcribe_live(
    client_ws: WebSocket,
    session_id: str,
    student_id: str,
    class_id: str,
    history: list[dict],
    session_context: dict,
) -> None:
    """Stream browser audio to Gemini Live STT, feed transcripts to process_turn."""
    if not GEMINI_KEY:
        await safe_push(client_ws, {"type": "error", "message": "Missing GEMINI_API_KEY"})
        return

    gemini_client = genai.Client(api_key=GEMINI_KEY)
    live_config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
    )

    t_start = [time.perf_counter()]
    audio_buffer = bytearray()
    current_transcript = [""]

    active_session = None
    receive_task = None

    async def start_gemini_session():
        nonlocal active_session, receive_task
        current_transcript[0] = ""
        try:
            ctx = gemini_client.aio.live.connect(model="gemini-3.5-transcribe-live", config=live_config)
            session = await ctx.__aenter__()
            active_session = (ctx, session)

            async def _receive():
                try:
                    async for response in session.receive():
                        sc = getattr(response, "server_content", None)
                        if not sc:
                            continue
                        interim = getattr(sc, "interim_input_transcription", None)
                        if interim and getattr(interim, "text", None):
                            text = interim.text.strip()
                            if text:
                                current_transcript[0] = text
                                await safe_push(client_ws, {
                                    "type": "user_transcript",
                                    "text": text,
                                    "replace": True,
                                })
                        final = getattr(sc, "input_transcription", None)
                        if final and getattr(final, "text", None):
                            text = final.text.strip()
                            if text:
                                current_transcript[0] = text
                                await safe_push(client_ws, {
                                    "type": "user_transcript",
                                    "text": text,
                                    "replace": True,
                                })
                except Exception as exc:
                    # Includes the cancellation this task gets at the end of every turn.
                    logger.debug("The STT stream ended: %s", exc)

            receive_task = asyncio.create_task(_receive())
            return session
        except Exception as exc:
            # Broad: a provider SDK opening a socket. The turn falls back to batch STT.
            logger.warning("Could not connect Gemini Live STT: %s", exc)
            active_session = None
            return None

    try:
        while True:
            msg = await client_ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            chunk = msg.get("bytes")
            if chunk is not None:
                if chunk == b"END_OF_TURN":
                    final_text = ""
                    if active_session:
                        ctx, session = active_session
                        try:
                            await session.send_client_content(turns=[], turn_complete=True)
                            await asyncio.sleep(0.35)
                        except Exception as exc:
                            # The transcript collected so far is used either way, and the
                            # batch fallback below covers an empty one.
                            logger.debug("Closing the STT turn raised: %s", exc)
                        if receive_task:
                            receive_task.cancel()
                        try:
                            await ctx.__aexit__(None, None, None)
                        except Exception as exc:   # a socket per turn, closed per turn
                            logger.debug("Closing the STT session raised: %s", exc)
                        active_session = None

                    final_text = current_transcript[0].strip()

                    # Fallback to batch transcription if Gemini live did not yield text
                    if not final_text and len(audio_buffer) >= 3200:
                        try:
                            wav_data = voice.wav_from_pcm(bytes(audio_buffer), 16000)
                            final_text = await asyncio.to_thread(voice.transcribe, wav_data, "audio/wav")
                        except Exception as err:
                            # The last chance at hearing this turn. Nothing is classified
                            # or answered without a transcript, so the turn simply ends.
                            logger.warning("Fallback transcription failed: %s", err)

                    audio_buffer.clear()

                    if final_text:
                        await safe_push(client_ws, {
                            "type": "user_transcript",
                            "text": final_text,
                            "replace": True,
                        })
                        asyncio.create_task(
                            process_turn(
                                client_ws, final_text, session_id, student_id,
                                class_id, history, t_start[0], session_context
                            )
                        )
                else:
                    if not audio_buffer:
                        t_start[0] = time.perf_counter()
                        await start_gemini_session()

                    audio_buffer.extend(chunk)

                    if active_session:
                        _, session = active_session
                        try:
                            await session.send_realtime_input(
                                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                            )
                        except Exception as err:
                            # One frame of a live stream: degrades the transcript, not the
                            # turn. The socket is checked again on the next frame.
                            logger.debug("Sending an audio frame raised: %s", err)

            text_data = msg.get("text")
            if text_data:
                # Only the parsing is guarded: wrapping the turn as well would report a
                # fault inside the tutor as "not JSON" and lose it.
                try:
                    parsed = json.loads(text_data)
                except (json.JSONDecodeError, TypeError) as error:
                    logger.debug("Ignoring a text frame that is not JSON: %s", error)
                    continue
                if parsed.get("type") == "text_prompt" and parsed.get("text", "").strip():
                    asyncio.create_task(
                        process_turn(
                            client_ws, parsed["text"].strip(), session_id, student_id,
                            class_id, history, time.perf_counter(), session_context
                        )
                    )

    except (WebSocketDisconnect, ConnectionResetError):
        logger.info("Client disconnected (Gemini Transcribe)")
    finally:
        if active_session:
            ctx, _ = active_session
            try:
                await ctx.__aexit__(None, None, None)
            except Exception as exc:   # the session is over either way
                logger.debug("Closing the STT session raised: %s", exc)
