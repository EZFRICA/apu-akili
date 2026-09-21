"""A print text as a braille sheet: Unicode braille for a screen or display, BRF for an embosser."""

from dataclasses import dataclass

from apu.modality.braille.embosser_simulator import SimulatedEmbosser
from apu.modality.braille.translator import BrailleEncoding, BrailleGrade, BrailleTranslator
from apu.modality.plain_text import plain_text


@dataclass(frozen=True)
class BrailleSheet:
    text: str               # the print text the braille was made from
    unicode_braille: str    # for a screen or a braille display
    brf: str                # Braille ASCII pages, for an embosser
    pages: int


def braille_sheet(text: str, grade: BrailleGrade = BrailleGrade.GRADE_2, language: str = "en") -> BrailleSheet:
    """
    Translate a print text to braille. Raises the translator's errors (liblouis missing,
    translation failure) so the caller can say braille is unavailable.
    """
    printable = plain_text(text)
    unicode_braille = BrailleTranslator(grade, language=language).translate(printable)
    ascii_braille = BrailleTranslator(grade, BrailleEncoding.EMBOSSER, language=language).translate(printable)
    job = SimulatedEmbosser().emboss(ascii_braille)
    return BrailleSheet(printable, unicode_braille, job.to_brf(), len(job.pages))
