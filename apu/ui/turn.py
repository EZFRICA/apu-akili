"""One student turn, independent of the interface that shows it.

Both front ends call this: the Streamlit pages and the Chainlit chat. Keeping the turn here
means the rules that matter (the guard runs first, the transcript of a recording is treated
exactly like typed text, the answer is rendered for the channel) are written once and tested
once, rather than drifting between two user interfaces.

Nothing here talks to a widget. It takes what the student said and returns what happened.
"""

import time
from dataclasses import dataclass, field

from apu import config
from apu.modality.mode import InteractionMode
from apu.runtime.agent import build_message_window, create_agent_graph


@dataclass
class TurnResult:
    """What one turn produced, in the form any interface needs to show it."""

    content: str                       # what to display, already rendered for the channel
    answer_text: str = ""              # the answer without the appended source list
    written: str | None = None
    spoken: str | None = None
    off_topic: bool = False
    guard_outcome: str | None = None
    sources: list = field(default_factory=list)
    searches: list = field(default_factory=list)
    refused_searches: list = field(default_factory=list)
    notebook_saves: list = field(default_factory=list)
    memory_problems: list = field(default_factory=list)
    tool_problems: list = field(default_factory=list)
    answer_problems: list = field(default_factory=list)
    duration: float = 0.0
    error: Exception | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None

    @property
    def savable(self) -> bool:
        """Whether this answer can go into the notebook: a guard reply cannot."""
        return bool(self.answer_text) and not self.off_topic


async def run_turn(
    prompt: str,
    *,
    session_id: str,
    class_level: str,
    subject: str,
    agent_id: str | None = None,
    history: list | None = None,
    history_turns: int = 3,
    input_channel: str = "text",
    output_channel: str = "text",
    text_display: bool = True,
    previous_answer: str = "",
) -> TurnResult:
    """
    Run one turn through the graph and report it.

    `prompt` is what the student said, typed or transcribed: a recording is turned into text
    before this point, so the topical guard classifies the same thing either way.
    """
    mode = InteractionMode(input_channel, output_channel, text_display_available=text_display)
    state = {
        "messages": build_message_window(history or [], prompt, history_turns),
        "session_id": session_id,
        "agent_id": agent_id,
        "class_level": class_level or config.EDU_DEFAULT_CLASS,
        "subject": subject or config.EDU_DEFAULT_SUBJECT,
        "memory_only_mode": history_turns == 0,
        "needs_new_block": "False",
        "proposed_block_config": {},
        "previous_answer": previous_answer,
        "interaction_mode": {
            "input_channel": mode.input_channel.value,
            "output_channel": mode.output_channel.value,
            "text_display_available": mode.text_display_available,
        },
    }

    started = time.monotonic()
    try:
        result = await create_agent_graph().ainvoke(state)
    except Exception as error:  # reported to the student, never raised into the interface
        return TurnResult(content="", duration=time.monotonic() - started, error=error)

    duration = time.monotonic() - started
    rendered = result.get("rendered_answer") or {}
    content = result["messages"][-1].content
    off_topic = bool(result.get("off_topic"))
    return TurnResult(
        content=content,
        answer_text="" if off_topic else (result.get("answer_text") or ""),
        written=content if off_topic else rendered.get("written"),
        spoken=content if off_topic else rendered.get("spoken"),
        off_topic=off_topic,
        guard_outcome=result.get("guard_outcome"),
        sources=result.get("sources") or [],
        searches=result.get("searches") or [],
        refused_searches=result.get("refused_searches") or [],
        notebook_saves=result.get("notebook_saves") or [],
        memory_problems=result.get("memory_problems") or [],
        tool_problems=result.get("tool_problems") or [],
        answer_problems=result.get("answer_problems") or [],
        duration=duration,
    )
