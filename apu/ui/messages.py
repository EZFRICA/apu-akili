"""What a pupil is told when something fails.

Every interface hits the same question: an operation failed, and the pupil is waiting. Some
failures are theirs to hear, because they can act on them: a notebook that is full, a
selection too large for one sheet. The rest are faults of this software or of a provider,
and a driver's error text read out to a child who may have no screen helps nobody and
exposes internals to whoever is in the room.

One rule, one place, so the three interfaces cannot drift apart on it.
"""

from apu.logger import get_logger

logger = get_logger(__name__)


def pupil_facing_reason(error: Exception, fallback: str) -> str:
    """
    The sentence a pupil gets for `error`, and nothing more.

    A limit the pupil reached is quoted as raised, because those messages are written for
    them. Anything else returns `fallback` and the real error goes to the log.
    """
    from apu.notebook.store import NotebookFull

    if isinstance(error, (NotebookFull, ValueError)):
        return str(error)
    logger.warning("Reported to a pupil as a generic message: %r", error)
    return fallback
