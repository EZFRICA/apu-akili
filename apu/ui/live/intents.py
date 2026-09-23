"""The three things a pupil can ask for by voice that the tutor does not answer.

Saving to the notebook, hearing it summarised back, and asking for braille are actions on
the pupil's own data, not questions. They are matched here by pattern rather than by the
model, because they must work the same way every time and cost nothing.

Matching is deliberately generous, since a child speaking is not a command line and the
transcription is imperfect. That generosity is why the caller classifies the utterance with
the topical guard BEFORE running any of this: a pattern that catches "note that PSG won"
must not be what decides that something is written down (see pipeline.process_turn).
"""

import asyncio
import re

from apu import config
from apu.logger import get_logger
from apu.modality.braille._liblouis import LiblouisTranslationError, LiblouisUnavailable
from apu.modality.braille.translator import (
    BrailleEncoding,
    BrailleEncodingError,
    BrailleGrade,
    BrailleTranslator,
)
# Modules, not the names inside them: a test that redirects the notebook store away from a
# real pupil's data does it by patching the module attribute, which only works if the lookup
# happens at call time.
from apu.notebook import service, store
from apu.tools import notebook as notebook_tool

logger = get_logger(__name__)

# English and French, because that is what a pupil here speaks, and the transcription may
# come back in either.
NOTEBOOK_SAVE_RE = re.compile(
    r"\b(save|add|record|write|keep|note|enregistre|sauvegarde|ajoute|mets?)\b.*?\b(notebook|notes?|cahier|carnet)\b",
    re.IGNORECASE,
)
NOTEBOOK_SUMMARY_RE = re.compile(
    r"\b(summarize|summary|recap|what's in|what is in|résum[ée]|resum[ée]|resumer|résumer|récapitule|fais-moi un résumé|que contient|qu'y a-t-il dans)\b.*?\b(notebook|notes?|cahier|carnet)\b",
    re.IGNORECASE,
)
BRAILLE_INTENT_RE = re.compile(
    r"\b(braille|format braille|in braille|braille code|translate to braille|en braille|code braille|traduis en braille|affiche le braille|donne.*braille)\b",
    re.IGNORECASE,
)


def is_save_notebook_intent(text: str) -> bool:
    return bool(NOTEBOOK_SAVE_RE.search(text))


def is_summary_notebook_intent(text: str) -> bool:
    return bool(NOTEBOOK_SUMMARY_RE.search(text))


def is_braille_intent(text: str) -> bool:
    return bool(BRAILLE_INTENT_RE.search(text))


def compute_braille(text: str) -> tuple[str, str]:
    """
    The same text in grade 1 and grade 2 braille cells.

    Grade 2 falls back to grade 1 rather than failing: a contraction table may reject text
    grade 1 accepts, and a pupil reading cells is better served by uncontracted braille than
    by nothing. When liblouis itself is missing, both come back empty, and the caller decides
    what to say: cells that spell the word "braille" would be read as an answer.
    """
    try:
        grade_1 = BrailleTranslator(grade=BrailleGrade.GRADE_1,
                                    encoding=BrailleEncoding.UNICODE).translate(text)
    except (LiblouisUnavailable, LiblouisTranslationError, BrailleEncodingError, ValueError) as error:
        logger.warning("Braille is unavailable: %s", error)
        return "", ""
    try:
        grade_2 = BrailleTranslator(grade=BrailleGrade.GRADE_2,
                                    encoding=BrailleEncoding.UNICODE).translate(text)
    except (LiblouisTranslationError, BrailleEncodingError, ValueError) as error:
        logger.info("Grade 2 refused this text, sending grade 1: %s", error)
        grade_2 = grade_1
    return grade_1, grade_2


def handle_save_notebook(student_id: str, history: list[dict], prompt: str) -> dict:
    """
    Keep the tutor's last answer in the pupil's notebook.

    What is saved is the explanation, not the request: a pupil who says "save that" means
    the thing they were just told. Only when there is nothing to point at does the pupil's
    own sentence get saved, stripped of the words that asked for the saving.

    Raises whatever the store raises, NotebookFull in particular. The caller turns that
    into something the pupil hears; swallowing it here would lose the save in silence.
    """
    content_to_save = next((entry["content"] for entry in reversed(history)
                            if entry.get("role") == "assistant" and entry.get("content")), "")
    if not content_to_save:
        content_to_save = NOTEBOOK_SAVE_RE.sub("", prompt).strip(" :,-.") or "Voice note recorded."

    title = content_to_save.split(".")[0][:40].strip() or "Live Note"
    result = notebook_tool.append_to_notebook(student_id=student_id, title=title,
                                              content=content_to_save)
    # The title is the first words of what a pupil chose to keep, so it belongs in the
    # DEBUG stream with the rest of their words, not in the log file (see apu/logger.py).
    logger.info("Notebook updated for %s", student_id)
    logger.debug("Notebook entry title for %s: %r", student_id, title)

    ack_text = f"Saved in your notebook: \"{title}\"."
    return {
        "title": title,
        "content": content_to_save,
        "entry_id": result.get("entry_id", ""),
        "ack_text": ack_text,
    }


async def handle_summary_notebook(student_id: str) -> str:
    """
    A spoken revision sheet from the pupil's notebook.

    Goes through apu.notebook.service rather than calling a model here: the notebook holds
    text a pupil wrote, it is sent to a model, and the service is where the limits on how
    many entries and how many characters may leave the device are enforced.
    """
    entries = await asyncio.to_thread(store.NotebookStore().entries, student_id)
    if not entries:
        return "Your notebook is currently empty. You can ask me to save notes whenever you like!"

    chosen = entries[-config.NOTEBOOK_MAX_SHEET_ENTRIES:]
    try:
        return await service.summarize_entries(chosen)
    except Exception as exc:
        # Broad on purpose: this is a model call over the network, and the pupil asked to
        # hear their own notes. Telling them how many they have beats a silent failure.
        logger.warning("Could not summarize the notebook for %s: %s", student_id, exc)
        return (f"You have {len(entries)} notes in your notebook, and I could not read them "
                "out just now.")

