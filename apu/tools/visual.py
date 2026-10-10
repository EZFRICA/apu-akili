"""draw_visual: the tutor draws a picture when the student asks for one.

"Can you show me?", "draw it", "fais-moi un schéma": a picture often says what a paragraph
cannot. Offered on validated turns only, like web search, and only when the student has a
screen: a picture is no help to a pupil reading braille or listening without one.

Three things set it apart from the other tools:

  - It is slow. A picture takes 10 to 34 seconds (measured), against one or two for an
    answer. So the student is told it is coming, in their own words, before it is drawn:
    the tutor writes that sentence as an argument of the call, and the interface shows or
    says it through `on_progress` while the picture is being made.
  - What the tutor asks to draw goes through a second gate, as a search query does
    (apu.guardrails.classifier.classify_visual_request).
  - The picture is never stored. It goes back to the interface with the turn, and the
    description the tutor wrote is kept with it as its text alternative.
"""

import asyncio
import inspect
import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from apu import config
from apu.guardrails.classifier import classify_visual_request
from apu.guardrails.session import TurnOutcome, ValidatedTurn
from apu.logger import get_logger

logger = get_logger(__name__)

DRAW_VISUAL_TOOL_NAME = "draw_visual"

DRAW_VISUAL_TOOL = {
    "type": "function",
    "function": {
        "name": DRAW_VISUAL_TOOL_NAME,
        "description": (
            "Draw an educational picture (diagram, schema, worked example) for the student, "
            "ONLY when the student asks to see something: a picture, a drawing, a diagram, a "
            "schema, or 'show me'. Drawing takes several seconds."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "What to draw, in the student's language: the concept, the exact "
                        "numbers, labels and steps to show. Every value must be correct."
                    ),
                },
                "waiting_message": {
                    "type": "string",
                    "description": (
                        "One short, warm sentence in the student's language telling them you "
                        "are drawing it and that it takes a few seconds."
                    ),
                },
            },
            "required": ["description", "waiting_message"],
        },
    },
}

VISUAL_INSTRUCTIONS = """
PICTURES: when the student asks to see something (a picture, a drawing, a diagram, a schema, "show me", "draw it"), call draw_visual once with what to draw and a short waiting message. Never draw without being asked. Once the picture is drawn, answer in a few sentences that walk the student through it: the student sees the picture next to your answer.
"""

# For a student without a screen. Found live: asked to "draw a right triangle" on a braille
# display, the tutor drew one out of slashes and pipes, which reaches the pupil's fingers as
# a column of meaningless cells.
NO_PICTURE_INSTRUCTIONS = """
PICTURES: this student cannot see pictures. If they ask for a drawing, a diagram or a schema, describe it in words, step by step, as you would to someone who cannot see it. Never draw with characters, symbols or ASCII art.
"""

# Used when the tutor leaves the waiting message out. English, because the tutor writes the
# real one in the student's language and this is only the floor.
DEFAULT_WAITING_MESSAGE = "I am drawing it for you, it takes a few seconds."

DRAWING_PROMPT = """An educational illustration for a student ({class_level}, {subject}).

{description}

Every number, label and step in the picture must be correct. Write the labels in the language
of the description above. Clear, uncluttered and readable on a small screen."""

# Called with (kind, message) when something slow starts. May be a coroutine function.
ProgressCallback = Callable[[str, str], object]

VISUAL_STARTED = "visual_started"


@dataclass(frozen=True)
class Visual:
    data: bytes
    mime_type: str
    description: str        # what the tutor asked for, which is also the picture's text alternative
    seconds: float


class VisualUnavailable(RuntimeError):
    """The picture could not be drawn: no key, the model unreachable, nothing returned."""


class VisualGateError(PermissionError):
    """A picture was requested without a validated turn."""


_client = None


def _gemini_client():
    """The Gemini client, built on first use: a device without the key still answers."""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise VisualUnavailable("GEMINI_API_KEY is not set, so pictures cannot be drawn.")
        from google import genai  # imported here: only a turn that draws needs the SDK
        from google.genai import types
        _client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
            timeout=int(config.VISUAL_TIMEOUT_SECONDS * 1000)))
    return _client


def generate_image(prompt: str) -> tuple[bytes, str]:
    """
    One picture from the model, as (bytes, mime type). Blocking: run it in a thread.

    TEXT and IMAGE are both requested. Asking for IMAGE alone returns a picture with no word
    of explanation, and asking for TEXT alone is ignored by this model, which draws anyway.
    The text it writes is not used: the tutor's answer is what the student reads.
    """
    from google.genai import types

    response = _gemini_client().models.generate_content(
        model=config.VISUAL_MODEL, contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]))
    for candidate in response.candidates or []:
        for part in (candidate.content.parts if candidate.content else None) or []:
            blob = getattr(part, "inline_data", None)
            if blob and blob.data:
                return blob.data, blob.mime_type or "image/jpeg"
    raise VisualUnavailable("the model returned no picture")


async def _notify(on_progress: ProgressCallback | None, message: str) -> None:
    """Tell the interface. A notice that fails must not cost the student the picture."""
    if on_progress is None:
        return
    try:
        outcome = on_progress(VISUAL_STARTED, message)
        if inspect.isawaitable(outcome):
            await outcome
    except Exception as error:
        logger.warning("The waiting notice could not be shown: %s", error)


async def draw(arguments: dict, *, validated_turn: ValidatedTurn | None, class_level: str,
               subject: str, on_progress: ProgressCallback | None = None) -> Visual:
    """
    Check the request, tell the student, draw.

    Raises ValueError for arguments the model can fix, PermissionError when the second gate
    refuses the picture, and VisualUnavailable when it could not be drawn.
    """
    if validated_turn is None:
        raise VisualGateError("draw_visual needs the turn the topical rail validated.")
    description = str(arguments.get("description") or "").strip()
    if not description:
        raise ValueError("draw_visual needs a non-empty 'description'.")

    if await classify_visual_request(description) is not TurnOutcome.ON_TOPIC:
        raise PermissionError("this picture is not school use")

    message = str(arguments.get("waiting_message") or "").strip() or DEFAULT_WAITING_MESSAGE
    prompt = DRAWING_PROMPT.format(class_level=class_level, subject=subject,
                                   description=description)
    started = time.monotonic()
    # The notice runs while the picture is drawn, not before it: speaking the sentence takes
    # a second, and there is no reason to add that second to the wait it announces.
    notice = asyncio.ensure_future(_notify(on_progress, message))
    try:
        data, mime_type = await asyncio.wait_for(asyncio.to_thread(generate_image, prompt),
                                                 config.VISUAL_TIMEOUT_SECONDS)
    except VisualUnavailable:
        raise
    except Exception as error:  # timeout, network, quota: the provider's own exceptions
        raise VisualUnavailable(str(error) or type(error).__name__) from error
    finally:
        await notice
    return Visual(data, mime_type, description, time.monotonic() - started)
