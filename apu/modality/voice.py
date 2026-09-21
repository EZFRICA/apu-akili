"""Speech in and speech out, with the topical guard still in front of the turn.

The tutor itself never changes: audio is only a shell around the same turn. Speech in is
transcribed to text FIRST, then that text goes through the topical guard exactly like a typed
question, and only then does the tutor answer. Speech out reads the answer the tutor already
produced. Nothing here answers the student.

This is why a real-time speech-to-speech model is not used: it would answer the student
directly, bypassing the guard, the class policy, the off-topic counter and the escalations.

Two jobs, two models, each with its own provider in the configuration:
  - transcription: a speech-to-text model, given one recorded file per question;
  - speech: a text-to-speech model, given the answer to read out.

ElevenLabs is the default for both, by measurement rather than preference: it synthesises an
answer in 0.87 s where the Gemini batch model takes 11.55 s, and its scribe_v1 keeps every
number in a spoken French maths question, which is the payload a maths tutor cannot lose.
Gemini remains available for either job by changing one setting. See docs/models.md.
"""

import io
import os
import re
import struct
import wave
from dataclasses import dataclass

from apu import config
from apu.logger import get_logger
from apu.modality.plain_text import plain_text

logger = get_logger(__name__)

# Asks for the words only. Without it a multimodal model tends to describe the recording
# ("The speaker asks...") or to answer the question it just heard, and what the guard would
# then classify would not be what the student said.
TRANSCRIPTION_PROMPT = (
    "Transcribe the speech in this audio exactly as it was spoken, word for word. "
    "Return only the transcript, with no quotation marks, no translation, no commentary, "
    "and do not answer what is said."
)

# Sample format the Gemini speech models return when they send raw PCM: the mime type says
# audio/L16 with a rate, which browsers cannot play as is, so it is wrapped into a WAV file.
_PCM_MIME = re.compile(r"^audio/(l16|pcm)(;|$)", re.I)
_RATE_IN_MIME = re.compile(r"rate=(\d+)")
_DEFAULT_PCM_RATE = 24000


class VoiceUnavailable(RuntimeError):
    """Speech in or speech out could not be produced (no key, model error, empty result)."""


@dataclass(frozen=True)
class SpokenAudio:
    data: bytes
    mime_type: str


_client = None
_http = None


def get_http():
    """The HTTP client for providers that are not the Gemini SDK, built on first use."""
    global _http
    if _http is None:
        import httpx

        _http = httpx.Client(timeout=120)
    return _http


def set_http(client) -> None:
    """Swap the HTTP client, for tests."""
    global _http
    _http = client


def _elevenlabs_key() -> str:
    api_key = os.environ.get(config.ELEVENLABS_API_KEY_ENV)
    if not api_key:
        raise VoiceUnavailable(
            f"{config.ELEVENLABS_API_KEY_ENV} is not set, so speech is unavailable. "
            "Add it to .env, switch the provider in the configuration, or use text or braille."
        )
    return api_key


def get_client():
    """
    The Gemini client, built on first use.

    Built lazily, like the Nebius client: a device without a Gemini key must still start,
    run in text and braille, and fail only when someone actually asks for speech.
    """
    global _client
    if _client is None:
        api_key = os.environ.get(config.GEMINI_API_KEY_ENV)
        if not api_key:
            raise VoiceUnavailable(
                f"{config.GEMINI_API_KEY_ENV} is not set, so speech is unavailable. "
                "Add it to .env, or use the text or braille modes."
            )
        from google import genai  # imported here: the SDK is only needed for speech

        _client = genai.Client(api_key=api_key)
    return _client


def set_client(client) -> None:
    """Swap the client, for tests and for a device that builds its own."""
    global _client
    _client = client


def transcribe(audio: bytes, mime_type: str = "audio/wav") -> str:
    """
    One recording to the words it holds. The result is a student question like any other:
    it still goes through the topical guard before anything answers it.
    """
    if not audio:
        raise VoiceUnavailable("The recording is empty.")
    if len(audio) > config.VOICE_MAX_RECORDING_BYTES:
        raise VoiceUnavailable(
            f"The recording is too long ({len(audio) // 1024} kB, limit "
            f"{config.VOICE_MAX_RECORDING_BYTES // 1024} kB). Ask a shorter question."
        )
    if config.VOICE_STT_PROVIDER == "elevenlabs":
        text = _transcribe_elevenlabs(audio, mime_type)
        if not text:
            raise VoiceUnavailable("Nothing was transcribed. Record the question again.")
        return text
    from google.genai import types

    try:
        response = get_client().models.generate_content(
            model=config.GEMINI_TRANSCRIBE_MODEL,
            contents=[
                TRANSCRIPTION_PROMPT,
                types.Part.from_bytes(data=audio, mime_type=mime_type),
            ],
        )
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Transcription failed: %s", error)
        raise VoiceUnavailable(f"Transcription failed: {error}") from error

    text = _transcript_from_response(response)
    if not text:
        raise VoiceUnavailable("Nothing was transcribed. Record the question again.")
    return text


def _transcribe_elevenlabs(audio: bytes, mime_type: str) -> str:
    extension = "mp3" if "mpeg" in mime_type else "wav"
    try:
        response = get_http().post(
            f"{config.ELEVENLABS_URL}/speech-to-text",
            headers={"xi-api-key": _elevenlabs_key()},
            data={"model_id": config.VOICE_STT_MODEL},
            files={"file": (f"question.{extension}", audio, mime_type)},
        )
        response.raise_for_status()
        return (response.json().get("text") or "").strip()
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Transcription failed: %s", error)
        raise VoiceUnavailable(f"Transcription failed: {error}") from error


def _transcript_from_response(response) -> str:
    """
    The transcript, wherever this model puts it.

    Measured live against gemini-3.5-transcribe: a dedicated speech model answers with an
    `audio_transcription` part, not a text one, and `response.text` is then empty (the SDK
    even warns about the non-text part). A general multimodal model used in its place would
    answer with plain text instead, so both are read.
    """
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            transcription = getattr(part, "audio_transcription", None)
            spoken_text = (getattr(transcription, "text", None) or "").strip() if transcription else ""
            if spoken_text:
                return spoken_text
            part_text = (getattr(part, "text", None) or "").strip()
            if part_text:
                return part_text
    return (getattr(response, "text", None) or "").strip()


def synthesize(text: str, voice: str | None = None) -> SpokenAudio:
    """
    The tutor's answer read out loud. The text is whatever the tutor already said.

    Retried once when the audio comes back too short for the text, because the model
    sometimes stops early and a student listening has no way to know what was cut.
    """
    spoken = plain_text(text).strip()
    if not spoken:
        raise VoiceUnavailable("There is nothing to read out.")
    spoken = spoken[: config.VOICE_MAX_SPOKEN_CHARS]
    audio = _synthesize_once(spoken, voice)
    if _sounds_truncated(spoken, audio):
        logger.warning("Spoken answer looks cut (%s); reading it again.", _audio_seconds(audio))
        second_try = _synthesize_once(spoken, voice)
        return second_try if len(second_try.data) > len(audio.data) else audio
    return audio


def _synthesize_once(spoken: str, voice: str | None) -> SpokenAudio:
    if config.VOICE_TTS_PROVIDER == "elevenlabs":
        try:
            return _synthesize_elevenlabs(spoken, voice)
        except Exception as exc:
            logger.warning("ElevenLabs TTS failed (%s); falling back to Gemini.", exc)
    return _synthesize_gemini(spoken, voice)


def _synthesize_elevenlabs(spoken: str, voice: str | None) -> SpokenAudio:
    """Raw PCM rather than mp3, so the player gets the same WAV whatever the provider is."""
    try:
        response = get_http().post(
            f"{config.ELEVENLABS_URL}/text-to-speech/{voice or config.ELEVENLABS_VOICE_ID}",
            params={"output_format": "pcm_24000"},
            headers={"xi-api-key": _elevenlabs_key()},
            json={"text": spoken, "model_id": config.VOICE_TTS_MODEL},
        )
        response.raise_for_status()
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Speech synthesis failed: %s", error)
        raise VoiceUnavailable(f"Speech synthesis failed: {error}") from error
    if not response.content:
        raise VoiceUnavailable("The speech model returned no audio.")
    return SpokenAudio(wav_from_pcm(response.content, _DEFAULT_PCM_RATE), "audio/wav")


def _synthesize_gemini(spoken: str, voice: str | None) -> SpokenAudio:
    from google.genai import types

    try:
        response = get_client().models.generate_content(
            model=config.GEMINI_TTS_MODEL,
            contents=spoken,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice or config.GEMINI_TTS_VOICE
                        )
                    )
                ),
            ),
        )
    except VoiceUnavailable:
        raise
    except Exception as error:
        logger.warning("Speech synthesis failed: %s", error)
        raise VoiceUnavailable(f"Speech synthesis failed: {error}") from error

    return _audio_from_response(response)


def _audio_seconds(audio: SpokenAudio) -> float:
    """Duration of the WAV this module produces (16-bit mono at the model's rate)."""
    if not audio.mime_type.startswith("audio/wav") or len(audio.data) <= 44:
        return 0.0
    try:
        with wave.open(io.BytesIO(audio.data), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate() or _DEFAULT_PCM_RATE)
    except wave.Error:
        return 0.0


def _sounds_truncated(spoken: str, audio: SpokenAudio) -> bool:
    seconds = _audio_seconds(audio)
    if seconds <= 0:
        return False  # not a format this module can measure; take it as given
    expected = len(spoken) / config.VOICE_CHARS_PER_SECOND
    return seconds < expected * config.VOICE_MIN_AUDIO_RATIO


def _audio_from_response(response) -> SpokenAudio:
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline is not None and getattr(inline, "data", None):
                mime_type = getattr(inline, "mime_type", "") or "audio/wav"
                if _PCM_MIME.match(mime_type):
                    return SpokenAudio(wav_from_pcm(inline.data, _sample_rate(mime_type)), "audio/wav")
                return SpokenAudio(inline.data, mime_type)
    raise VoiceUnavailable("The speech model returned no audio.")


def _sample_rate(mime_type: str) -> int:
    match = _RATE_IN_MIME.search(mime_type)
    return int(match.group(1)) if match else _DEFAULT_PCM_RATE


def wav_from_pcm(pcm: bytes, sample_rate: int = _DEFAULT_PCM_RATE, channels: int = 1) -> bytes:
    """Wrap signed 16-bit PCM in a WAV container, which browsers and players accept."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def silence(seconds: float = 0.2, sample_rate: int = _DEFAULT_PCM_RATE) -> bytes:
    """A short silent WAV, used by the tests and as a placeholder recording."""
    frames = struct.pack("<h", 0) * int(seconds * sample_rate)
    return wav_from_pcm(frames, sample_rate)
