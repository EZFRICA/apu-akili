"""The student tutor as a Chainlit chat.

    uv run chainlit run apu/ui/chainlit_app.py -w

A second front end for the pupil, beside the Streamlit pages. Chainlit is chat-first: it has
a real message stream, recording built into the composer, file elements, and buttons under a
message, which is most of what this channel needs and what Streamlit's rerun model makes
awkward. The Streamlit app keeps the teacher, admin and demo pages, which are not chats.

Nothing about the tutor changes here. The turn runs through apu.ui.turn, the same code the
Streamlit page calls, so the guard classifies every exchange first and a recording is
transcribed into text before anything sees it.
"""

import asyncio
import base64
import os
import sys
from typing import Callable, Optional

# chainlit runs this file as a script, not as part of the package, so the repository root has
# to be on the path before anything from apu is imported (the Streamlit pages do the same).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import chainlit as cl  # noqa: E402

from apu import config  # noqa: E402
from apu.demo.seed import load_demo_students  # noqa: E402
from apu.guardrails.session import sessions as guard_sessions  # noqa: E402
from apu.logger import get_logger  # noqa: E402
from apu.modality import voice  # noqa: E402
from apu.modality.braille.sheet import braille_sheet  # noqa: E402
from apu.modality.braille.translator import BrailleGrade  # noqa: E402
from apu.modality.plain_text import plain_text  # noqa: E402
from apu.notebook.service import save_entry  # noqa: E402
from apu.notebook.store import KIND_LABELS, EntryKind, EntryOrigin  # noqa: E402
from apu.ui import turn as turn_service  # noqa: E402
from apu.ui.messages import pupil_facing_reason  # noqa: E402

logger = get_logger(__name__)

MODES = {
    "Text": ("text", "text"),
    "Voice": ("voice", "voice"),
    "Braille": ("braille", "braille"),
}
OUTCOME_NOTE = {
    "off_topic": "🛡️ Off topic: this one is not schoolwork.",
    "welfare": "💛 Personal, not schoolwork.",
    "uncertain": "❔ The guard could not classify this one, so no web search was allowed.",
}


def _student():
    """The demo pupil this chat runs as. Identity is a stub, as in the other interface."""
    students = {s["student_id"]: s for s in load_demo_students()}
    return students.get(config.DEMO_STUDENT_ID) or next(iter(students.values()))


def _settings_widgets():
    return [
        cl.input_widget.Select(id="mode", label="How you work", values=list(MODES), initial_index=0),
        cl.input_widget.Select(id="grade", label="Braille grade", values=["Grade 1", "Grade 2"],
                               initial_index=1),
        cl.input_widget.Slider(id="history", label="Exchanges sent to the model", initial=3,
                               min=0, max=10, step=1),
    ]


@cl.on_chat_start
async def start():
    student = _student()
    session = guard_sessions.open_session(student["student_id"], student["class_id"])
    cl.user_session.set("student", student)
    cl.user_session.set("guard_session", session.session_id)
    cl.user_session.set("history", [])
    cl.user_session.set("settings", {"mode": "Text", "grade": "Grade 2", "history": 3})

    await cl.ChatSettings(_settings_widgets()).send()
    await cl.Message(
        content=(
            f"Hello {student['display_name']}. Ask me about your lessons, your exercises or "
            "your revision.\n\n"
            "You can type, or record your question with the microphone. Every question goes "
            "through the school-use check first, exactly the same way."
        ),
        author="Akili",
    ).send()


@cl.on_settings_update
async def settings_changed(settings):
    cl.user_session.set("settings", settings)


class ElevenLabsRealtimeSTT:
    """
    Manages a live WebSocket session with ElevenLabs scribe_v2_realtime.

    Streams PCM chunks received from Chainlit on the fly and collects
    partial and committed transcriptions.
    """

    def __init__(
        self,
        sample_rate: int = config.VOICE_SAMPLE_RATE,
        model_id: str = "scribe_v2_realtime",
        on_partial: Optional[Callable[[str], None]] = None,
    ):
        self.sample_rate = sample_rate
        self.model_id = model_id
        self.on_partial = on_partial
        self.connection = None
        self._committed_texts: list[str] = []
        self._latest_partial: str = ""
        self._error: Optional[str] = None
        self._is_active = False

    async def start(self) -> bool:
        """Connect to ElevenLabs Realtime STT WebSocket."""
        api_key = os.environ.get(config.ELEVENLABS_API_KEY_ENV)
        if not api_key:
            self._error = "ELEVENLABS_API_KEY is not set."
            logger.warning("No ElevenLabs API key found for realtime STT.")
            return False

        try:
            from elevenlabs.client import ElevenLabs
            from elevenlabs.realtime import AudioFormat, CommitStrategy, RealtimeEvents

            client = ElevenLabs(api_key=api_key)

            fmt_str = f"pcm_{self.sample_rate}"
            try:
                audio_format = AudioFormat(fmt_str)
            except ValueError:
                audio_format = AudioFormat.PCM_24000
                self.sample_rate = 24000

            self.connection = await client.speech_to_text.realtime.connect({
                "model_id": self.model_id,
                "audio_format": audio_format,
                "sample_rate": self.sample_rate,
                "commit_strategy": CommitStrategy.MANUAL,
            })

            def handle_partial(data):
                text = data.get("text") or data.get("transcript") or ""
                self._latest_partial = text
                if self.on_partial and text:
                    self.on_partial(text)

            def handle_committed(data):
                text = data.get("text") or data.get("transcript") or ""
                if text:
                    self._committed_texts.append(text)
                    self._latest_partial = ""

            def handle_error(data):
                err = data.get("error") or data.get("message") or str(data)
                logger.warning("ElevenLabs Realtime STT error: %s", err)
                self._error = str(err)

            self.connection.on(RealtimeEvents.PARTIAL_TRANSCRIPT, handle_partial)
            self.connection.on(RealtimeEvents.COMMITTED_TRANSCRIPT, handle_committed)
            self.connection.on(RealtimeEvents.ERROR, handle_error)

            self._is_active = True
            return True
        except Exception as e:
            # Broad: a provider SDK opening a socket. The recording is still buffered, and
            # the batch transcription below is what actually has to work.
            logger.warning("Could not connect to ElevenLabs Realtime STT: %s", e)
            self._error = str(e)
            return False

    async def send_chunk(self, pcm_bytes: bytes) -> None:
        """Send a chunk of raw PCM bytes to the active WebSocket session."""
        if not self._is_active or not self.connection:
            return
        try:
            b64 = base64.b64encode(pcm_bytes).decode("utf-8")
            await self.connection.send({"audio_base_64": b64})
        except Exception as e:
            # One frame of a live stream. The session is marked dead and the turn falls
            # back to transcribing the buffer.
            logger.warning("Sending an audio frame to Realtime STT raised: %s", e)
            self._error = str(e)
            self._is_active = False

    async def stop(self) -> str:
        """Commit the audio, wait briefly for transcription, and close the session."""
        if not self.connection:
            return ""

        try:
            if self._is_active:
                await self.connection.commit()
                await asyncio.sleep(0.35)
        except Exception as e:
            # Whatever was committed so far is still used, and an empty result falls back
            # to batch transcription.
            logger.warning("Committing the STT turn raised: %s", e)
        finally:
            try:
                await self.connection.close()
            except Exception as exc:   # closing a dead socket, nothing to do
                logger.debug("Closing the STT socket raised: %s", exc)
            self._is_active = False

        full_text = " ".join(self._committed_texts).strip()
        if not full_text and self._latest_partial:
            full_text = self._latest_partial.strip()
        return full_text


async def synthesize_speech(text: str) -> voice.SpokenAudio | None:
    """
    Real-time response TTS: synthesizes tutor response for immediate playback.
    Delegates to voice.synthesize() which tries ElevenLabs then falls back to Gemini.
    """
    try:
        return await cl.make_async(voice.synthesize)(text)
    except voice.VoiceUnavailable as exc:
        logger.warning("TTS synthesis failed entirely: %s", exc)
        return None


@cl.on_audio_start
async def audio_start():
    """Initializes live audio recording and starts the Scribe v2 Realtime WebSocket session."""
    cl.user_session.set("audio", bytearray())
    cl.user_session.set("audio_mime", "audio/wav")

    # Display live listening message that will be updated in real time as the pupil speaks
    live_msg = cl.Message(content="🎙️ *Listening...*", author="You")
    await live_msg.send()
    cl.user_session.set("live_msg", live_msg)

    def on_partial(text: str):
        if text:
            asyncio.create_task(update_live_msg(text))

    stt = ElevenLabsRealtimeSTT(
        sample_rate=config.VOICE_SAMPLE_RATE,
        model_id="scribe_v2_realtime",
        on_partial=on_partial,
    )
    started = await stt.start()
    cl.user_session.set("stt_session", stt if started else None)
    return True


async def update_live_msg(text: str):
    """Updates the live preview message with current partial transcription."""
    live_msg = cl.user_session.get("live_msg")
    if live_msg and text:
        live_msg.content = f"🎙️ *{text}*"
        await live_msg.update()


@cl.on_audio_chunk
async def audio_chunk(chunk: cl.InputAudioChunk):
    """Stream incoming PCM chunks to Scribe v2 Realtime and buffer locally for fallback."""
    buffer = cl.user_session.get("audio") or bytearray()
    buffer.extend(chunk.data)
    cl.user_session.set("audio", buffer)
    cl.user_session.set("audio_mime", chunk.mimeType or "audio/wav")

    stt = cl.user_session.get("stt_session")
    if stt:
        await stt.send_chunk(chunk.data)


@cl.on_audio_end
async def audio_end():
    """Finalize transcription, ensure topical guard validation, and run the APU turn."""
    buffer = cl.user_session.get("audio")
    cl.user_session.set("audio", None)
    stt = cl.user_session.get("stt_session")
    cl.user_session.set("stt_session", None)
    live_msg = cl.user_session.get("live_msg")
    cl.user_session.set("live_msg", None)

    transcript = ""
    if stt:
        try:
            transcript = await stt.stop()
        except Exception as error:
            # The buffer is still there: the fallback below is what decides this turn.
            logger.warning("Finalising the realtime transcript raised: %s", error)

    # Fallback to standard batch transcription if realtime streaming did not produce a transcript
    if not transcript and buffer:
        try:
            wav_data = voice.wav_from_pcm(bytes(buffer), config.VOICE_SAMPLE_RATE)
            async with cl.Step(name="Transcribing (fallback)", type="tool"):
                transcript = await cl.make_async(voice.transcribe)(wav_data, "audio/wav")
        except voice.VoiceUnavailable as error:
            # VoiceUnavailable explains itself to whoever installed this ("set
            # ELEVENLABS_API_KEY..."), which is not the child sitting in front of it.
            logger.warning("Speech to text is unavailable: %s", error)
            if live_msg:
                await live_msg.remove()
            await cl.Message(content="I cannot hear you at the moment. You can type your "
                                     "question instead.", author="Akili").send()
            return
        except Exception as error:
            # The last chance at hearing this turn, so the pupil is told. What they are
            # told is a sentence, not a provider's exception text.
            logger.warning("Batch transcription failed: %s", error)
            if live_msg:
                await live_msg.remove()
            await cl.Message(content="I could not hear that. Could you say it again?",
                             author="Akili").send()
            return

    if not transcript:
        if live_msg:
            await live_msg.remove()
        return

    # Update the live message to finalize the user's spoken question
    if live_msg:
        live_msg.content = transcript
        await live_msg.update()
    else:
        await cl.Message(content=transcript, type="user_message").send()

    # The transcript now enters the standard APU turn:
    # 1. Guard evaluates whether it is school-appropriate (NeMo / topical guard)
    # 2. Tutor responds if approved, or politely refuses if off-topic
    # 3. Real-time TTS response is spoken aloud (is_voice=True)
    await answer(transcript, is_voice=True)


@cl.on_message
async def on_message(message: cl.Message):
    await answer(message.content)


async def answer(prompt: str, is_voice: bool = False):
    settings = cl.user_session.get("settings") or {}
    mode = ("voice", "voice") if is_voice else MODES.get(settings.get("mode", "Text"), ("text", "text"))
    history = cl.user_session.get("history") or []
    previous = next((entry["content"] for entry in reversed(history)
                     if entry["role"] == "assistant"), "")

    async with cl.Step(name="Akili", type="run") as step:
        result = await turn_service.run_turn(
            prompt,
            session_id=cl.user_session.get("guard_session"),
            class_level=config.EDU_DEFAULT_CLASS,
            subject=config.EDU_DEFAULT_SUBJECT,
            history=history,
            history_turns=int(settings.get("history", 3)),
            input_channel=mode[0],
            output_channel=mode[1],
            previous_answer=previous,
        )
        step.output = f"{result.duration:.1f} s, guard: {result.guard_outcome}"

    if result.failed:
        await cl.Message(content=f"⚠️ This turn could not be completed: {result.error}",
                         author="Akili").send()
        return

    history.append({"role": "user", "content": prompt})
    history.append({"role": "assistant", "content": result.answer_text or result.content})
    cl.user_session.set("history", history)

    elements, actions = [], []
    note = OUTCOME_NOTE.get(result.guard_outcome or "") if result.off_topic else None
    body = result.written or result.content

    if mode[1] == "braille":
        body, braille_elements = await braille_body(result)
        elements += braille_elements
    elif mode[1] == "voice":
        elements += await spoken_elements(result)

    if result.sources:
        elements.append(cl.Text(
            name="Sources",
            content="\n".join(f"{index}. [{source['title']}]({source['url']})"
                              for index, source in enumerate(result.sources, start=1)),
            display="side",
        ))
    if result.savable:
        cl.user_session.set("last_answer", result.answer_text)
        actions = [
            cl.Action(name="save_full", label="💾 Save the answer", payload={"kind": "full"}),
            cl.Action(name="save_points", label="💾 Save the key points", payload={"kind": "key_points"}),
        ]

    footer = []
    if result.searches:
        footer.append("🔎 " + " · ".join(f"“{query}”" for query in result.searches))
    if result.refused_searches:
        footer.append("🛡️ a search was refused as not school use")
    footer.append(f"⏱ {result.duration:.1f} s")

    await cl.Message(
        content="\n\n".join(part for part in [note, body, "*" + "   ".join(footer) + "*"] if part),
        author="Akili", elements=elements, actions=actions,
    ).send()


async def braille_body(result):
    """Braille cells in the message, and the embosser file beside it."""
    settings = cl.user_session.get("settings") or {}
    grade = BrailleGrade.GRADE_2 if settings.get("grade") == "Grade 2" else BrailleGrade.GRADE_1
    try:
        sheet = braille_sheet(result.written or result.content, grade)
    except Exception as error:   # liblouis missing, or a text it cannot translate
        logger.warning("Braille is unavailable: %s", error)
        return f"{result.content}\n\n*Braille is not available on this device.*", []
    return (
        f"{sheet.unicode_braille}\n\n<details><summary>Show in print</summary>\n\n"
        f"{plain_text(result.written or result.content)}\n\n</details>",
        [cl.File(name="akili.brf", content=sheet.brf.encode("ascii", "replace"),
                 display="inline", mime="text/plain")],
    )


async def spoken_elements(result):
    """The answer read out loud in real time, attached to the message and auto-played."""
    text_to_speak = result.spoken or result.content
    try:
        audio = await synthesize_speech(text_to_speak)
        if audio:
            return [cl.Audio(name="Answer", content=audio.data, mime=audio.mime_type, display="inline",
                             auto_play=True)]
    except Exception as error:
        # Broad: speech crosses the network to a provider. The answer's text is already in
        # the message, so what is missing is only the reason it was not read out.
        logger.warning("Speech synthesis failed: %s", error)
        return [cl.Text(name="Voice unavailable",
                        content="The answer could not be read out loud just now.",
                        display="inline")]
    return []


@cl.action_callback("save_full")
async def save_full(action: cl.Action):
    await save(action.payload["kind"])


@cl.action_callback("save_points")
async def save_points(action: cl.Action):
    await save(action.payload["kind"])


async def save(kind: str):
    answer_text = cl.user_session.get("last_answer")
    student = cl.user_session.get("student")
    if not answer_text:
        await cl.Message(content="There is nothing to save yet.", author="Akili").send()
        return
    try:
        entry = await save_entry(
            student_id=student["student_id"], class_level=config.EDU_DEFAULT_CLASS,
            subject=config.EDU_DEFAULT_SUBJECT, kind=kind, answer=answer_text,
            origin=EntryOrigin.BUTTON,
        )
    except Exception as error:
        # A full notebook is the pupil's own limit and is quoted; anything else is a fault
        # of ours, and its text is not for a child (see apu/ui/messages.py).
        logger.warning("Notebook save failed for %s: %s", student["student_id"], error)
        await cl.Message(content=pupil_facing_reason(error, "I could not save that just now."),
                         author="Akili").send()
        return
    await cl.Message(
        content=f"📓 Saved to your notebook ({KIND_LABELS[EntryKind(entry.kind)].lower()}).",
        author="Akili",
    ).send()


@cl.set_starters
async def starters():
    return [
        cl.Starter(label="Explain fractions", message="Explain simple fractions to me."),
        cl.Starter(label="Check my exercise",
                   message="I got 5/12 for 1/4 + 1/6. Is that right, and why?"),
        cl.Starter(label="Revise for a test",
                   message="Help me prepare for my history test on the Middle Ages."),
        cl.Starter(label="Keep this in my notebook",
                   message="Save the key points of your last answer in my notebook."),
    ]
