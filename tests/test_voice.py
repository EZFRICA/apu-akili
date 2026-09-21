"""
Speech in and speech out, and the rule that speech changes nothing about the turn.

Target: apu/modality/voice.py

Both providers are replaced by in-process fakes, so these tests never reach the network and
need no key. What they pin is the shape of each call and what the module refuses. The Gemini
tests force that provider, since the shipped default is ElevenLabs.
"""

import struct
from types import SimpleNamespace

import pytest

from apu import config
from apu.modality import voice
from apu.modality.voice import VoiceUnavailable

# Three seconds of audio: long enough that the truncation check below leaves it alone.
PCM = struct.pack("<h", 1234) * 24000 * 3
ANSWER = "To add 1/4 and 1/6, put both over 12."


class FakeGemini:
    """Stands in for google.genai.Client: records calls, returns scripted responses."""

    def __init__(self, response=None, error=None):
        self.calls = []
        self.response = response
        self.error = error
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.error is not None:
            raise self.error
        return self.response


def text_response(text):
    return SimpleNamespace(text=text, candidates=[])


def transcription_response(text):
    """The shape gemini-3.5-transcribe really answers with: an audio_transcription part."""
    part = SimpleNamespace(audio_transcription=SimpleNamespace(text=text), text=None, inline_data=None)
    return SimpleNamespace(text=None, candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


def audio_response(data=PCM, mime_type="audio/L16;codec=pcm;rate=24000"):
    part = SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type=mime_type))
    return SimpleNamespace(text=None, candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


class FakeHTTP:
    """Stands in for httpx.Client: records requests, returns scripted responses."""

    def __init__(self, payload=None, content=b"", status=200, error=None):
        self.calls = []
        self.payload = payload or {}
        self.content = content
        self.status = status
        self.error = error

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        fake = self

        class Response:
            status_code = fake.status
            content = fake.content

            def json(self):
                return fake.payload

            def raise_for_status(self):
                if fake.status >= 400:
                    raise RuntimeError(f"HTTP {fake.status}")

        return Response()


@pytest.fixture
def elevenlabs(monkeypatch):
    """The shipped default provider, with a fake HTTP client."""
    monkeypatch.setenv(config.ELEVENLABS_API_KEY_ENV, "test-key-not-real")
    monkeypatch.setattr(config, "VOICE_TTS_PROVIDER", "elevenlabs")
    monkeypatch.setattr(config, "VOICE_STT_PROVIDER", "elevenlabs")

    def install(**kwargs):
        client = FakeHTTP(**kwargs)
        voice.set_http(client)
        return client

    yield install
    voice.set_http(None)


@pytest.fixture
def gemini(monkeypatch):
    """Install a fake Gemini client, and force that provider for both directions."""
    monkeypatch.setenv(config.GEMINI_API_KEY_ENV, "test-key-not-real")
    monkeypatch.setattr(config, "VOICE_TTS_PROVIDER", "gemini")
    monkeypatch.setattr(config, "VOICE_STT_PROVIDER", "gemini")
    installed = []

    def install(response=None, error=None):
        client = FakeGemini(response=response, error=error)
        voice.set_client(client)
        installed.append(client)
        return client

    yield install
    voice.set_client(None)


# ── speech in ────────────────────────────────────────────────────────────────

def test_a_recording_is_transcribed_to_the_words_it_holds(gemini):
    client = gemini(text_response("  How do I add two fractions?  "))

    assert voice.transcribe(voice.silence(), "audio/wav") == "How do I add two fractions?"

    [call] = client.calls
    assert call["model"] == config.GEMINI_TRANSCRIBE_MODEL
    instruction, audio_part = call["contents"]
    assert "word for word" in instruction and "do not answer" in instruction, (
        "the model must return the question, not an answer to it"
    )
    assert audio_part.inline_data.mime_type == "audio/wav"


def test_a_dedicated_speech_model_answers_with_a_transcription_part(gemini):
    """Measured live: the transcript is in audio_transcription, and response.text is empty."""
    gemini(transcription_response("How do I add two fractions?"))
    assert voice.transcribe(voice.silence()) == "How do I add two fractions?"


def test_an_empty_or_oversized_recording_never_leaves_the_device(gemini, monkeypatch):
    client = gemini(text_response("x"))
    with pytest.raises(VoiceUnavailable, match="empty"):
        voice.transcribe(b"")
    monkeypatch.setattr(config, "VOICE_MAX_RECORDING_BYTES", 128)
    with pytest.raises(VoiceUnavailable, match="too long"):
        voice.transcribe(voice.silence())
    assert client.calls == [], "nothing was sent"


def test_an_empty_transcript_is_reported_rather_than_answered(gemini):
    gemini(transcription_response("   "))
    with pytest.raises(VoiceUnavailable, match="Nothing was transcribed"):
        voice.transcribe(voice.silence())


def test_a_transcription_error_is_wrapped(gemini):
    gemini(error=ConnectionError("503"))
    with pytest.raises(VoiceUnavailable, match="503"):
        voice.transcribe(voice.silence())


# ── speech out ───────────────────────────────────────────────────────────────

def test_the_answer_is_read_out_as_plain_text_in_the_configured_voice(gemini):
    client = gemini(audio_response())

    spoken = voice.synthesize(f"**{ANSWER}** `x`")

    assert spoken.mime_type == "audio/wav" and spoken.data.startswith(b"RIFF")
    [call] = client.calls
    assert call["model"] == config.GEMINI_TTS_MODEL
    assert call["contents"] == f"{ANSWER} x", "Markdown is noise once it is spoken"
    assert call["config"].response_modalities == ["AUDIO"]
    assert call["config"].speech_config.voice_config.prebuilt_voice_config.voice_name == config.GEMINI_TTS_VOICE


def test_raw_pcm_becomes_a_playable_wav_and_other_formats_pass_through(gemini):
    gemini(audio_response())
    wav = voice.synthesize(ANSWER)
    assert wav.data[:4] == b"RIFF" and len(wav.data) > len(PCM), "a header was added"

    voice.set_client(FakeGemini(response=audio_response(b"ID3mp3", "audio/mpeg")))
    passed_through = voice.synthesize(ANSWER)
    assert (passed_through.data, passed_through.mime_type) == (b"ID3mp3", "audio/mpeg")


def test_audio_that_stops_early_is_read_again(gemini, monkeypatch):
    """Seen live: 1367 characters came back as 22 s of audio instead of 90 s, once."""
    long_answer = "This is a sentence about fractions. " * 20
    short_pcm = struct.pack("<h", 1) * 24000          # 1 s, far too short for that text
    long_pcm = struct.pack("<h", 1) * 24000 * 60      # 60 s, what it should sound like

    client = gemini(audio_response(short_pcm))
    client.response = audio_response(short_pcm)
    calls = []

    def answer(model, contents, config=None):
        calls.append(model)
        return audio_response(short_pcm if len(calls) == 1 else long_pcm)

    client.models.generate_content = answer
    spoken = voice.synthesize(long_answer)

    assert len(calls) == 2, "the short reading was retried"
    assert len(spoken.data) > len(short_pcm), "the fuller reading is the one returned"


def test_audio_of_a_believable_length_is_not_read_twice(gemini):
    client = gemini(audio_response(struct.pack("<h", 1) * 24000 * 3))   # 3 s for 30 characters
    voice.synthesize("Five twelfths is the answer.")
    assert len(client.calls) == 1


def test_a_long_answer_is_cut_before_it_is_read_out(gemini, monkeypatch):
    client = gemini(audio_response())
    monkeypatch.setattr(config, "VOICE_MAX_SPOKEN_CHARS", 20)
    voice.synthesize("word " * 100)
    assert len(client.calls[0]["contents"]) == 20


def test_an_answerless_response_is_reported(gemini):
    gemini(SimpleNamespace(text=None, candidates=[]))
    with pytest.raises(VoiceUnavailable, match="no audio"):
        voice.synthesize(ANSWER)
    with pytest.raises(VoiceUnavailable, match="nothing to read"):
        voice.synthesize("   ")


# ── the shipped provider ─────────────────────────────────────────────────────

def test_elevenlabs_transcribes_the_recording(elevenlabs):
    client = elevenlabs(payload={"text": "  How do I add two fractions?  "})

    assert voice.transcribe(voice.silence(), "audio/wav") == "How do I add two fractions?"

    [call] = client.calls
    assert call["url"].endswith("/speech-to-text")
    assert call["data"]["model_id"] == config.VOICE_STT_MODEL
    assert call["headers"]["xi-api-key"] == "test-key-not-real"


def test_elevenlabs_reads_the_answer_as_a_playable_wav(elevenlabs):
    client = elevenlabs(content=struct.pack("<h", 7) * 24000 * 3)

    spoken = voice.synthesize(f"**{ANSWER}**")

    assert spoken.mime_type == "audio/wav" and spoken.data.startswith(b"RIFF")
    [call] = client.calls
    assert config.ELEVENLABS_VOICE_ID in call["url"]
    assert call["json"] == {"text": ANSWER, "model_id": config.VOICE_TTS_MODEL}
    assert call["params"]["output_format"] == "pcm_24000", "raw PCM, so the duration is known"


def test_an_elevenlabs_failure_is_reported_not_raised_raw(elevenlabs, monkeypatch):
    # ElevenLabs errors are caught, Gemini fallback also fails → VoiceUnavailable in the end.
    monkeypatch.setattr(config, "VOICE_TTS_PROVIDER", "elevenlabs")
    gemini_client = FakeGemini(error=RuntimeError("gemini-down"))
    voice.set_client(gemini_client)
    elevenlabs(error=ConnectionError("503"))
    with pytest.raises(VoiceUnavailable):
        voice.synthesize(ANSWER)
    voice.set_client(None)
    elevenlabs(payload={"text": "   "})
    with pytest.raises(VoiceUnavailable, match="Nothing was transcribed"):
        voice.transcribe(voice.silence())


def test_without_an_elevenlabs_key_speech_is_unavailable(monkeypatch):
    # No ElevenLabs key: fallback fires and also fails (no Gemini client) → VoiceUnavailable.
    monkeypatch.setattr(config, "VOICE_TTS_PROVIDER", "elevenlabs")
    monkeypatch.delenv(config.ELEVENLABS_API_KEY_ENV, raising=False)
    voice.set_http(None)
    gemini_client = FakeGemini(error=RuntimeError("gemini-down"))
    voice.set_client(gemini_client)
    with pytest.raises(VoiceUnavailable):
        voice.synthesize(ANSWER)
    voice.set_client(None)


# ── the device without a key ─────────────────────────────────────────────────

def test_without_a_key_speech_is_unavailable_and_the_rest_still_runs(monkeypatch):
    monkeypatch.setattr(config, "VOICE_TTS_PROVIDER", "gemini")
    monkeypatch.setattr(config, "VOICE_STT_PROVIDER", "gemini")
    monkeypatch.delenv(config.GEMINI_API_KEY_ENV, raising=False)
    voice.set_client(None)
    with pytest.raises(VoiceUnavailable, match=config.GEMINI_API_KEY_ENV):
        voice.transcribe(voice.silence())
    with pytest.raises(VoiceUnavailable, match=config.GEMINI_API_KEY_ENV):
        voice.synthesize(ANSWER)


# ── speech is a shell around the turn, never a shortcut through it ───────────

def test_the_voice_module_cannot_answer_a_student():
    """
    Pins the rule: every exchange goes through the topical guard, whatever the modality.

    Speech in produces a transcript that the guard then classifies; speech out reads an
    answer the tutor already produced. So this module must not reach the runtime, the guard
    or an inference client of its own.
    """
    import pathlib
    import re

    source = pathlib.Path(voice.__file__).read_text(encoding="utf-8")
    forbidden = re.compile(r"^\s*(from|import)\s+apu\.(runtime|guardrails|inference)\b", re.M)
    assert not forbidden.search(source)
    assert "generate_content" in source and "planner_node" not in source
