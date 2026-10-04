"""Custom NeMo Guardrails actions for the topical rail.

They receive the session and turn ids through the rails context, and resolve everything
else (policy, counter) from the in-memory session registry, so the threshold used is the one
captured when the session opened, never a value supplied with the request.

Every action records the turn's outcome on the session. The guard reads that record rather
than NeMo's response text, because NeMo turns an exception inside an action into a generic
"internal error" reply that would otherwise be indistinguishable from a blocked turn.
"""

import uuid
from datetime import UTC, datetime

from apu import config
from apu.core.scheduler import DeferredWriteScheduler
from apu.escalation.jobs import submit_escalation_event
from apu.escalation.models import EscalationEvent
from apu.guardrails.classifier import build_classifier_prompt, parse_verdict
from apu.guardrails.session import SessionRegistry, TurnOutcome
from apu.logger import get_logger

logger = get_logger(__name__)

# A refusal that does not change is not a conversation, it is a wall, and it was written up
# as exactly that (docs/security.md: "A firm refusal is repeated identically"). The session
# already counts the attempts; these use that count, so a pupil who asks a second time is
# answered as a pupil who asked a second time rather than as a stranger.
#
# None of them repeats the question back. What the pupil typed is not echoed into a reply:
# it is their text, and a refusal is not the place to quote it.
GENTLE_REPLIES = (
    "That one is outside what I can do, but schoolwork I am good at. "
    "What are you working on today?",
    "Still not something I can help with, I am afraid. "
    "Give me a lesson or an exercise and we can get going.",
    "I can tell you would rather talk about something else, and I understand. "
    "Schoolwork is the only thing I know how to do though. Which subject is giving you trouble?",
)
# The first rung, and what callers fall back to when they have no decision to show.
GENTLE_REPLY = GENTLE_REPLIES[0]

# At the threshold, and only there, an escalation is recorded. The pupil is told so: being
# quietly written down is worse than being told, and a pupil who knows can stop.
FIRM_REPLY = (
    "I am going to stop here. I can only help with schoolwork, and because we have come "
    "back to this a few times your teacher will see it. That is not a punishment, it is "
    "just how this works. Whenever you want a hand with a lesson, I am right here."
)
FIRM_AGAIN_REPLY = (
    "Same answer, I am afraid: schoolwork is all I can do. "
    "Tell me a subject and you will have my full attention."
)


def off_topic_reply(attempt: int, threshold: int) -> str:
    """
    What a pupil hears on their nth off-topic attempt.

    Before the threshold the tone softens rather than repeating; at it, the firm reply that
    also says an adult will see this; after it, a short version, because a pupil who has
    already been told does not need the whole sentence again.
    """
    if attempt < threshold:
        return GENTLE_REPLIES[min(attempt, len(GENTLE_REPLIES)) - 1]
    return FIRM_REPLY if attempt == threshold else FIRM_AGAIN_REPLY
# A pupil who says they are being hurt, or that they do not want to live, used to receive
# FIRM_REPLY and have it counted as misbehaviour (measured, see docs/security.md). This is
# what they receive instead. It does not try to be a counsellor: it points to a person.
WELFARE_REPLY = (
    "Thank you for telling me. That sounds really hard, and you should not have to deal "
    "with it on your own. I am only a school tutor, so I cannot help with this properly, "
    "but a grown-up you trust can: a teacher, the school nurse or counsellor, a parent, or "
    "another adult close to you. Please talk to one of them today. When you feel ready to "
    "go back to your schoolwork, I am here."
)


def welfare_reply() -> str:
    """The welfare reply, plus whatever contact the school configured."""
    contact = config.WELFARE_CONTACT_TEXT.strip()
    return f"{WELFARE_REPLY}\n\n{contact}" if contact else WELFARE_REPLY


def build_actions(sessions: SessionRegistry, scheduler: DeferredWriteScheduler | None = None) -> dict:
    async def check_school_topic(llm=None, context: dict | None = None) -> str:
        context = context or {}
        session = sessions.get(context["session_id"])
        turn_id = context["turn_id"]
        try:
            response = await llm.generate_async(
                build_classifier_prompt(context.get("user_message") or "",
                                        context.get("preceding_exchange") or ""),
                temperature=0.0
            )
        except Exception as error:
            # Recorded, not raised: NeMo would swallow the exception into a generic reply.
            logger.error("Topical classifier call failed: %s", error)
            session.record_turn_outcome(turn_id, TurnOutcome.CLASSIFIER_ERROR, error=str(error))
            return "error"

        outcome = parse_verdict(response.content)
        if outcome is TurnOutcome.UNCERTAIN:
            logger.warning("Topical classifier gave no usable verdict: %r", response.content)
            session.record_turn_outcome(turn_id, TurnOutcome.UNCERTAIN)
        return outcome.value

    async def handle_off_topic_attempt(context: dict | None = None) -> str:
        context = context or {}
        session = sessions.get(context["session_id"])
        turn_id = context["turn_id"]

        session.invalidate_current_turn()
        session.off_topic_count += 1
        attempt = session.off_topic_count
        threshold = session.policy.escalation_threshold
        session.record_turn_outcome(turn_id, TurnOutcome.OFF_TOPIC)

        # Persist the crossing only, once per session: attempts below the threshold are
        # never stored, and attempts after it keep the firmer tone without adding events.
        if attempt == threshold:
            event = EscalationEvent(
                event_id=str(uuid.uuid4()),
                student_id=session.student_id,
                class_id=session.class_id,
                session_id=session.session_id,
                attempt_number_in_session=attempt,
                off_topic_request_text=context.get("user_message") or "",
                triggered_at=datetime.now(UTC),
            )
            submit_escalation_event(event, scheduler)
        return off_topic_reply(attempt, threshold)

    async def handle_welfare_disclosure(context: dict | None = None) -> str:
        """
        A disclosure of distress or danger. Answered with care, and deliberately NOT:
        not counted as an off-topic attempt, not escalated as a discipline event, and the
        text is not written anywhere. What a child says about being hurt does not belong in
        a behaviour record, and routing it to the right adult is a school policy decision
        that this device cannot make on its own (see docs/security.md).
        """
        context = context or {}
        session = sessions.get(context["session_id"])
        session.invalidate_current_turn()
        session.record_turn_outcome(context["turn_id"], TurnOutcome.WELFARE)
        logger.info("Welfare disclosure in session %s (text not recorded).", session.session_id)
        return welfare_reply()

    async def mark_turn_validated(context: dict | None = None) -> bool:
        context = context or {}
        session = sessions.get(context["session_id"])
        turn_id = context["turn_id"]
        session.validate_turn(turn_id, context.get("user_message") or "")
        session.record_turn_outcome(turn_id, TurnOutcome.ON_TOPIC)
        return True

    return {
        "check_school_topic": check_school_topic,
        "handle_off_topic_attempt": handle_off_topic_attempt,
        "handle_welfare_disclosure": handle_welfare_disclosure,
        "mark_turn_validated": mark_turn_validated,
    }
