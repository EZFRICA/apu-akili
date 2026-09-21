"""Voice intents detection and execution for APU Live Lab.

Handles:
  1. Save to pupil's notebook ("save to my notebook", "add to my notes")
  2. Summarize notebook ("summarize my notebook", "what is in my notes")
  3. Braille conversion & download ("format in braille", "give me the braille format")
"""

import os
import re
import time
from apu.logger import get_logger

logger = get_logger(__name__)

# Intent regex patterns (supports English and French)
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
    """True if text asks to save content to notebook."""
    return bool(NOTEBOOK_SAVE_RE.search(text))


def is_summary_notebook_intent(text: str) -> bool:
    """True if text asks for a summary of the notebook."""
    return bool(NOTEBOOK_SUMMARY_RE.search(text))


def is_braille_intent(text: str) -> bool:
    """True if text asks for Braille representation."""
    return bool(BRAILLE_INTENT_RE.search(text))


def compute_braille(text: str) -> tuple[str, str]:
    """Return (grade_1, grade_2) Braille translation."""
    try:
        from apu.modality.braille.translator import BrailleTranslator, BrailleGrade, BrailleEncoding
        t1 = BrailleTranslator(grade=BrailleGrade.GRADE_1, encoding=BrailleEncoding.UNICODE)
        g1 = t1.translate(text)
        try:
            t2 = BrailleTranslator(grade=BrailleGrade.GRADE_2, encoding=BrailleEncoding.UNICODE)
            g2 = t2.translate(text)
        except Exception:
            g2 = g1
        return g1, g2
    except Exception as exc:
        logger.warning("liblouis unavailable: %s", exc)
        return "⠃⠗⠁⠊⠇⠇⠑ (unavailable)", "⠃⠗⠁⠊⠇⠇⠑"


def handle_save_notebook(student_id: str, history: list[dict], prompt: str) -> dict:
    """Save the last tutor note or current prompt into the pupil's notebook."""
    from apu.tools.notebook import append_to_notebook

    # Find the last tutor response in history
    content_to_save = ""
    for msg in reversed(history):
        if msg.get("role") == "assistant" and msg.get("content"):
            content_to_save = msg["content"]
            break

    if not content_to_save:
        # Fallback to the prompt itself without the intent phrase
        clean = NOTEBOOK_SAVE_RE.sub("", prompt).strip(" :,-.")
        content_to_save = clean or "Voice note recorded."

    # Generate a brief title
    title = content_to_save.split(".")[0][:40].strip() or "Live Note"
    result = append_to_notebook(student_id=student_id, title=title, content=content_to_save)
    logger.info("Notebook updated for %s: '%s'", student_id, title)

    ack_text = f"Saved in your notebook: \"{title}\"."
    return {
        "title": title,
        "content": content_to_save,
        "entry_id": result.get("entry_id", ""),
        "ack_text": ack_text,
    }


def handle_summary_notebook(student_id: str) -> str:
    """Fetch all entries from the student's notebook and generate a spoken summary."""
    from apu.tools.notebook import read_notebook
    from apu.inference.llm import get_client
    from apu import config

    nb = read_notebook(student_id=student_id)
    entries = nb.get("entries", [])
    if not entries:
        return "Your notebook is currently empty. You can ask me to save notes whenever you like!"

    # Compile the entries into a brief prompt
    notes_text = "\n".join(
        f"- {e.get('title', 'Note')}: {e.get('content', '')}" for e in entries[-5:]
    )
    prompt = (
        f"Here are recent notes from the student's notebook ({student_id}):\n{notes_text}\n\n"
        "Provide a very concise (2 to 3 sentences maximum) and warm spoken summary of what the student learned. "
        "Do not use asterisks or markdown formatting; write smooth plain text for speech synthesis."
    )

    try:
        client = get_client(config.EXTRACTION_PROVIDER)
        response = client.chat.completions.create(
            model=config.EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": "You are APU, a warm and supportive tutor summarizing the student's notebook out loud."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Could not generate LLM notebook summary: %s", exc)
        last_note = entries[-1].get("content", "")[:120]
        return f"You have {len(entries)} notes in your notebook. Your most recent note is: {last_note}."

