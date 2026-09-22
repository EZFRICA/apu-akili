"""
One student turn, as an interface runs it.

Target: apu/ui/turn.py

The turn lives outside the pages that show it, so it is tested once here rather than through
a user interface. A second, chat-first interface shares the same turn; the checks that concern it skip
where chainlit is not installed.
"""

import pytest

from apu.ui import turn as turn_service
from tests.conftest import OFF_TOPIC_MARKER, SCHOOL_QUERY_VERDICT, TEST_SESSION_ID, WELFARE_MARKER

ANSWER = "To add two fractions, put them over the same denominator."


async def run(prompt, **kwargs):
    return await turn_service.run_turn(
        prompt, session_id=TEST_SESSION_ID, class_level="6eme", subject="math", **kwargs)


async def test_a_turn_returns_what_an_interface_needs_to_show(akili_paths, no_network,
                                                              stub_embeddings, fake_llm):
    fake_llm.main_replies = [ANSWER]
    fake_llm.extraction_replies = ["{}"]

    result = await run("How do I add two fractions?")

    assert not result.failed
    assert result.content == ANSWER and result.answer_text == ANSWER
    assert result.guard_outcome == "on_topic" and not result.off_topic
    assert result.savable, "a real answer can go to the notebook"
    assert result.duration > 0


async def test_an_off_topic_turn_is_marked_and_not_savable(akili_paths, no_network,
                                                           stub_embeddings, fake_llm):
    from apu.guardrails.actions import GENTLE_REPLY

    result = await run(f"{OFF_TOPIC_MARKER} Who won the match?")

    assert result.off_topic and result.guard_outcome == "off_topic"
    assert result.content == GENTLE_REPLY
    assert not result.savable, "the guard's own reply must never enter the notebook"
    assert result.answer_text == ""
    assert fake_llm.calls == [], "no model call for an off-topic turn"


async def test_a_disclosure_comes_back_as_welfare(akili_paths, no_network, stub_embeddings, fake_llm):
    result = await run(f"{WELFARE_MARKER} My father hits me.")

    assert result.guard_outcome == "welfare" and result.off_topic
    assert not result.savable
    assert "trust" in result.content


async def test_a_spoken_turn_carries_the_spoken_and_written_forms(akili_paths, no_network,
                                                                  stub_embeddings, fake_llm):
    fake_llm.main_replies = [ANSWER]
    fake_llm.extraction_replies = ["{}"]

    result = await run("Explain fractions", input_channel="voice", output_channel="voice",
                       text_display=False)

    assert result.spoken == ANSWER
    assert result.written is None, "no screen in this session, so nothing written"


async def test_searches_and_refusals_are_reported(akili_paths, no_network, stub_embeddings,
                                                  fake_llm, monkeypatch):
    from tests.conftest import tool_call_reply

    class Tool:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, payload):
            return {"results": [{"title": "Fraction", "url": "https://en.wikipedia.org/wiki/Fraction",
                                 "content": "..."}]}

    from apu.tools import web_search
    monkeypatch.setattr(web_search, "_web_search", web_search.TavilySearch(tool_factory=Tool))
    fake_llm.main_replies = [tool_call_reply("web_search", {"query": "fractions"}), ANSWER]
    fake_llm.extraction_replies = [SCHOOL_QUERY_VERDICT, "{}"]

    result = await run("Look up fractions for me")

    assert result.searches == ["fractions"] and result.refused_searches == []
    assert [source["title"] for source in result.sources] == ["Fraction"]


async def test_a_broken_turn_is_reported_not_raised(akili_paths, no_network, stub_embeddings,
                                                    fake_llm, monkeypatch):
    from apu.guardrails import guard
    from apu.guardrails.guard import TopicalGuard
    from tests.conftest import make_classifier_llm

    monkeypatch.setattr(guard, "_guard",
                        TopicalGuard(llm=make_classifier_llm(error=ConnectionError("401"))))

    result = await run("Explain fractions")

    assert result.failed and "401" in str(result.error)
    assert result.content == "", "the interface decides what to show for a failure"


def test_the_chat_interface_wires_the_same_turn():
    """
    The chat has no headless test harness, so what is checked is how it is wired: it must
    run the shared turn rather than the graph, and a recording must become text first.
    """
    import inspect

    pytest.importorskip("chainlit", reason="chainlit is not installed")
    chainlit_app = pytest.importorskip("apu.ui.chainlit_app")

    source = inspect.getsource(chainlit_app)
    assert "turn_service.run_turn" in source, "the chat must not build its own turn"
    assert "planner_node" not in source and "create_agent_graph" not in source
    # A recording becomes text, and that text takes the normal path.
    assert "voice.transcribe" in source
    assert source.index("voice.transcribe") < source.index("await answer(transcript")
    for handler in ("on_chat_start", "on_message", "on_audio_end", "action_callback"):
        assert f"@cl.{handler}" in source, handler


@pytest.mark.parametrize("mode,channels", [("Text", ("text", "text")), ("Voice", ("voice", "voice")),
                                           ("Braille", ("braille", "braille"))])
def test_the_chat_offers_the_supported_modes(mode, channels):
    from apu.modality.mode import SUPPORTED_COMBINATIONS

    pytest.importorskip("chainlit", reason="chainlit is not installed")
    chainlit_app = pytest.importorskip("apu.ui.chainlit_app")

    assert chainlit_app.MODES[mode] == channels
    assert channels in {(i.value, o.value) for i, o in SUPPORTED_COMBINATIONS}
