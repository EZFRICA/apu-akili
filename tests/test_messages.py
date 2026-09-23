"""
What a pupil is told when something fails.

Target: apu/ui/messages.py, and the three interfaces that have to obey it.

A pupil using this may have no screen: everything they are told is read out loud, in a room
that may hold other people. So a limit they reached is theirs to hear, and a fault of ours
is not.
"""

import pathlib
import sqlite3

import pytest

from apu.notebook.store import NotebookFull
from apu.ui.messages import pupil_facing_reason

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_a_limit_the_pupil_reached_is_quoted_as_written():
    error = NotebookFull("Your notebook is full (200 entries). Delete something first.")

    assert pupil_facing_reason(error, "generic") == str(error)
    assert pupil_facing_reason(ValueError("Choose at most 25 entries for one sheet."),
                               "generic") == "Choose at most 25 entries for one sheet."


@pytest.mark.parametrize("error", [
    sqlite3.OperationalError("database is locked"),
    RuntimeError("ConnectionResetError(54, 'Connection reset by peer')"),
    KeyError("student_id"),
])
def test_a_fault_of_ours_is_not_read_out_to_a_child(error, caplog):
    with caplog.at_level("WARNING"):
        spoken = pupil_facing_reason(error, "I could not save that just now.")

    assert spoken == "I could not save that just now."
    assert str(error) not in spoken
    assert any("generic message" in record.message for record in caplog.records), \
        "the real error still has to reach whoever reads the log"


@pytest.mark.parametrize("interface", [
    "apu/ui/live/pipeline.py",
    "apu/ui/chainlit_app.py",
    "apu/ui/live/runner_gemini_live.py",
])
def test_no_interface_puts_a_raw_exception_in_front_of_a_pupil(interface):
    """
    The pattern this forbids is f"...: {error}" in something sent to the pupil. Each of
    these three sent one before: a transcription error, a save failure, a dead session.
    """
    source = (REPO_ROOT / interface).read_text(encoding="utf-8")

    for marker in ('content=f"', 'token": f"', '"message": f"', 'content, f"'):
        offending = [line.strip() for line in source.splitlines()
                     if marker in line and "{error" in line or (marker in line and "{exc" in line)]
        assert not offending, f"{interface} shows an exception to a pupil: {offending}"
