"""ElevenLabs Speech-to-Text runner for APU Live Lab.

Model: eleven_english_sts_v2
Architecture: Browser PCM 16kHz -> ElevenLabs STT WebSocket (per-turn) -> process_turn (Guardrails + Tutor + TTS).
"""

import asyncio
import base64
import json
import os
import time
from starlette.websockets import WebSocket, WebSocketDisconnect

from elevenlabs.client import ElevenLabs
from elevenlabs.realtime import AudioFormat, CommitStrategy, RealtimeEvents

from apu.logger import get_logger
from apu.modality import voice
from apu.ui.live.pipeline import safe_push, process_turn

logger = get_logger(__name__)

ELEVEN_KEY = os.environ.get("ELEVENLABS_API_KEY", "")


async def run_elevenlabs_sts(
    client_ws: WebSocket,
    session_id: str,
    student_id: str,
    class_id: str,
    history: list[dict],
    session_context: dict,
) -> None:
    """Stream browser audio to ElevenLabs STT per turn, dispatch transcriptions to pipeline."""
    if not ELEVEN_KEY:
        await safe_push(client_ws, {"type": "error", "message": "Missing ELEVENLABS_API_KEY"})
        return

    client = ElevenLabs(api_key=ELEVEN_KEY)
    loop = asyncio.get_running_loop()

    current_connection = None
    audio_buffer = bytearray()
    t_start = [time.perf_counter()]
    committed_text = [""]

    async def start_stt_session():
        nonlocal current_connection
        committed_text[0] = ""
        try:
            conn = await client.speech_to_text.realtime.connect({
                "model_id": "scribe_v2_realtime",
                "audio_format": AudioFormat.PCM_16000,
                "sample_rate": 16000,
                "commit_strategy": CommitStrategy.MANUAL,
            })

            def on_partial(data: dict):
                text = data.get("text") or data.get("transcript") or ""
                if text:
                    asyncio.run_coroutine_threadsafe(
                        safe_push(client_ws, {
                            "type": "user_transcript",
                            "text": text,
                            "replace": True,
                        }),
                        loop,
                    )

            def on_committed(data: dict):
                text = (data.get("text") or data.get("transcript") or "").strip()
                if text:
                    committed_text[0] = text

            def on_error(data: dict):
                err = str(data.get("error") or data.get("message") or data)
                if "commit_throttled" not in err and "0.3s" not in err:
                    logger.warning("ElevenLabs realtime error: %s", err)

            conn.on(RealtimeEvents.PARTIAL_TRANSCRIPT, on_partial)
            conn.on(RealtimeEvents.COMMITTED_TRANSCRIPT, on_committed)
            conn.on(RealtimeEvents.ERROR, on_error)

            current_connection = conn
            logger.info("ElevenLabs STT session active (turn start)")
            return conn
        except Exception as exc:
            # Broad: a third party SDK opening a socket, with no documented exception
            # surface. The turn falls back to batch transcription below.
            logger.warning("Could not connect ElevenLabs realtime STT: %s", exc)
            current_connection = None
            return None

    try:
        while True:
            msg = await client_ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            chunk = msg.get("bytes")
            if chunk is not None:
                if chunk == b"END_OF_TURN":
                    # End of speech for current turn
                    final_text = ""
                    if current_connection:
                        try:
                            await current_connection.commit()
                            await asyncio.sleep(0.35)
                        except Exception as exc:
                            # The transcript already collected is used either way, and the
                            # batch fallback below covers an empty one.
                            logger.debug("Committing the STT turn raised: %s", exc)
                        try:
                            await current_connection.close()
                        except Exception as exc:   # closing a dead socket, nothing to do
                            logger.debug("Closing the STT socket raised: %s", exc)
                        current_connection = None

                    final_text = committed_text[0].strip()

                    # Fallback to batch transcription if realtime did not yield text
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
                    # Incoming PCM audio chunk
                    if not audio_buffer:
                        # First chunk of a new turn
                        t_start[0] = time.perf_counter()
                        await start_stt_session()

                    audio_buffer.extend(chunk)

                    if current_connection:
                        try:
                            b64 = base64.b64encode(chunk).decode("utf-8")
                            await current_connection.send({"audio_base_64": b64})
                        except Exception as exc:
                            # One frame of a live stream. Losing it degrades the transcript
                            # rather than the turn, and the socket is checked again next.
                            logger.debug("Sending an audio frame raised: %s", exc)

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
        logger.info("Client disconnected (ElevenLabs)")
    finally:
        if current_connection:
            try:
                await current_connection.close()
            except Exception as exc:   # the session is over either way
                logger.debug("Closing the STT socket raised: %s", exc)
