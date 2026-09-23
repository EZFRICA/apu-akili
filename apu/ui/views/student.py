"""Student view: the tutor, with the topical guard, web search sources, output modalities and
the student's notebook with its braille sheets."""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import streamlit as st  # noqa: E402

from apu import config  # noqa: E402
from apu.demo.seed import loaded_courses  # noqa: E402
from apu.guardrails.session import sessions as guard_sessions  # noqa: E402
from apu.mmu import cache_l1  # noqa: E402
from apu.mmu import dll as mmu  # noqa: E402
from apu.modality.braille import _liblouis  # noqa: E402
from apu.modality import voice  # noqa: E402
from apu.modality.braille.sheet import braille_sheet  # noqa: E402
from apu.modality.braille.translator import BrailleGrade  # noqa: E402
from apu.notebook import service as notebook  # noqa: E402
from apu.notebook.store import KIND_DESCRIPTIONS, KIND_LABELS, EntryKind, EntryOrigin, NotebookStore  # noqa: E402
from apu.storage import lance_driver  # noqa: E402
from apu.sync import sync_manager  # noqa: E402
from apu.ui import common  # noqa: E402
from apu.ui import turn as turn_service  # noqa: E402  ('turn' is a local name below)

MODES = {
    "Text → text": ("text", "text"),
    "Voice → voice": ("voice", "voice"),
    "Voice → text": ("voice", "text"),
    "Text → voice": ("text", "voice"),
    "Braille → braille": ("braille", "braille"),
}
OUTCOME_LABELS = {
    "on_topic": ("✅ school work", "ok"),
    "off_topic": ("🛡️ off-topic", "warn"),
    "welfare": ("💛 personal, not schoolwork", "info"),
    "uncertain": ("❔ uncertain", "info"),
}

identity = common.current_identity()
if identity.role != "student":
    st.info("This is the student page. Pick a **Student** profile in the sidebar.")
    st.stop()

st.session_state.setdefault("chat", [])
st.session_state.setdefault("last_turn", None)
session_id = common.ensure_guard_session(identity)
session = guard_sessions.get(session_id)
threshold = session.policy.escalation_threshold

if st.session_state.pop("toast", None):
    st.toast("Threshold reached: an escalation event was recorded for the teacher.", icon="🛡️")
if saved_label := st.session_state.pop("notebook_toast", None):
    st.toast(f"Saved to your notebook: {saved_label.lower()}.", icon="📓")

# ── header ───────────────────────────────────────────────────────────────────
st.title("💬 Akili, your tutor")
st.caption(f"{identity.display_name} · class {identity.class_id} · "
           f"answers by {config.MAIN_MODEL}, memory by {config.EXTRACTION_MODEL}")

# Full width: the five modes stay readable on a small projected screen.
mode_label = st.segmented_control("Interaction mode", list(MODES), default="Text → text",
                                  key="mode_label") or "Text → text"
input_channel, output_channel = MODES[mode_label]
controls = st.columns(2)
with controls[0]:
    text_display = True
    if (input_channel, output_channel) == ("voice", "voice"):
        text_display = st.toggle("Screen available", value=False, key="text_display",
                                 help="With a screen, sources are also shown in writing.")
    braille_grade = BrailleGrade.GRADE_1
    if output_channel == "braille":
        grade_label = st.segmented_control("Braille", ["Grade 1", "Grade 2"], default="Grade 2",
                                           key="braille_grade") or "Grade 2"
        braille_grade = BrailleGrade.GRADE_2 if grade_label == "Grade 2" else BrailleGrade.GRADE_1
with controls[1]:
    history_turns = st.slider("Exchanges sent to the model", 0, 10, 3, key="history_turns")

# ── guard status ─────────────────────────────────────────────────────────────
count = session.off_topic_count
status_columns = st.columns(4)
status_columns[0].metric("Off-topic attempts", f"{count} / {threshold}")
status_columns[1].metric("Class threshold", threshold)
status_columns[2].metric("Escalation", "Recorded" if count >= threshold else "No")
last_outcome = (st.session_state.last_turn or {}).get("guard_outcome")
outcome_text, outcome_kind = OUTCOME_LABELS.get(last_outcome, ("—", "info"))
status_columns[3].markdown(f"**Last guard verdict**<br>{common.badge(outcome_text, outcome_kind)}",
                           unsafe_allow_html=True)
st.progress(min(count / threshold, 1.0))

# ── course selection ─────────────────────────────────────────────────────────
dll_state = common.run(mmu.load_dll())
course = dll_state.get("course_selection", {"class": config.EDU_DEFAULT_CLASS, "subject": config.EDU_DEFAULT_SUBJECT})
courses = loaded_courses()
with st.expander(f"📚 Active course: {course['class']} / {course['subject']}", expanded=False):
    local_column, registry_column = st.columns(2)
    with local_column:
        st.markdown("**On this device**")
        if not courses:
            st.warning("No course loaded. Download one from the cloud registry, or use the "
                       "**Demo setup** page.")
        else:
            current = f"{course['class']}/{course['subject']}"
            choice = st.selectbox("Available courses", courses,
                                  index=courses.index(current) if current in courses else 0)
            if choice != current and st.button("Activate this course", type="primary"):
                class_level, subject = choice.split("/", 1)
                cache_l1.flush_all()
                common.run(mmu.switch_course(class_level, subject))
                common.reset_conversation()
                st.rerun()
    with registry_column:
        st.markdown("**Cloud registry (GCS)**")
        # Fetched on demand only: an unreachable registry costs a Google auth attempt, which
        # must not slow down every interaction during a live demo.
        if st.button("Browse the cloud registry"):
            with st.spinner("Reading the manifest…"):
                st.session_state.remote_catalog = common.run(sync_manager.get_remote_catalog())
            if not st.session_state.remote_catalog:
                st.error("Registry unreachable (Google credentials, network or REGISTRY_MANIFEST_URL).")
        remote_catalog = st.session_state.get("remote_catalog") or {}
        remote_courses = sorted(f"{c}/{s}" for c, subjects in remote_catalog.items() for s in subjects)
        if remote_courses:
            remote_choice = st.selectbox("Registry courses", remote_courses, key="remote_choice")
            class_level, subject = remote_choice.split("/", 1)
            if sync_manager.is_course_available_locally(class_level, subject):
                st.caption("💾 Already downloaded.")
            elif st.button("⬇️ Download and activate", type="primary"):
                with st.spinner(f"Downloading {remote_choice}…"):
                    ok, message = common.run(sync_manager.download_course(class_level, subject))
                if ok:
                    cache_l1.flush_all()
                    common.run(mmu.switch_course(class_level, subject))
                    common.reset_conversation()
                    st.rerun()
                st.error(message)
        if st.button("🔄 Check for updates (prompts)"):
            ok, message = common.run(sync_manager.sync_with_registry())
            (st.success if ok else st.error)(message)
    # Akili's "Reset Memory": wipes L1 and L2 for this student; rows already archived in L3 stay.
    if st.button("🗑️ Reset the student's memory (L1 + L2)"):
        cache_l1.flush_all()
        common.run(mmu.force_reinit_dll())
        common.reset_conversation()
        st.rerun()


# ── rendering ────────────────────────────────────────────────────────────────
def braille_for(message: dict, grade: BrailleGrade) -> tuple[str | None, str | None, str | None]:
    """(unicode braille, BRF text, error) for a message, cached per grade."""
    cache = message.setdefault("braille", {})
    if int(grade) not in cache:
        try:
            sheet = braille_sheet(message.get("written") or message["content"], grade)
            cache[int(grade)] = (sheet.unicode_braille, sheet.brf, None)
        except (_liblouis.LiblouisUnavailable, _liblouis.LiblouisTranslationError, ValueError) as error:
            cache[int(grade)] = (None, None, str(error))
    return cache[int(grade)]


def render_assistant(message: dict, index: int) -> None:
    if message.get("off_topic"):
        # A welfare reply is not a blocked turn and must not be badged as misbehaviour.
        label, kind = OUTCOME_LABELS.get(message.get("guard_outcome"), ("🛡️ off-topic", "warn"))
        st.markdown(common.badge(f"Guard: {label}", kind), unsafe_allow_html=True)
    output = message["output_channel"]
    if output == "voice":
        spoken = message.get("spoken") or message["content"]
        st.markdown(f"🔊 *{spoken}*")
        if message.get("audio"):
            st.audio(message["audio"], format=message.get("audio_type", "audio/wav"),
                     autoplay=message.pop("autoplay", False))
        else:
            # No Gemini key, or speech failed: the browser's own voice still reads the answer.
            if message.get("voice_problem"):
                st.caption(f"Gemini voice unavailable ({message['voice_problem']}); using the browser voice.")
            common.speak_button(spoken, key=f"msg{index}", autoplay=message.pop("autoplay", False))
        if message.get("written"):
            with st.expander("Text shown on screen"):
                st.markdown(common.math_for_streamlit(message["written"]))
    elif output == "braille":
        unicode_braille, brf, error = braille_for(message, braille_grade)
        if error:
            st.warning(f"Braille unavailable: {error}")
            st.markdown(message["content"])
        else:
            st.markdown(f'<div class="braille-block">{unicode_braille}</div>', unsafe_allow_html=True)
            if st.toggle("Show in print (for the audience)", key=f"plain{index}"):
                st.markdown(common.math_for_streamlit(message.get("written") or message["content"]))
            st.download_button("⬇ Embosser file (BRF)", brf, file_name=f"akili-{index}.brf",
                               mime="text/plain", key=f"brf{index}")
    else:
        st.markdown(common.math_for_streamlit(message.get("written") or message["content"]))
    details = []
    if message.get("searches"):
        details.append("🔎 " + " · ".join(f"“{query}”" for query in message["searches"]))
    if message.get("duration") is not None:
        details.append(f"⏱ {message['duration']:.1f} s")
    if message.get("saved"):
        details.append("📓 saved: " + ", ".join(KIND_LABELS[EntryKind(kind)].lower() for kind in message["saved"]))
    if details:
        st.caption("   ".join(details))
    if message.get("answer"):
        save_control(message, index)


def save_control(message: dict, index: int) -> None:
    """Keep this answer in the notebook: in full, as key points, or an excerpt the student picks."""
    with st.popover("💾 Save to notebook"):
        kind_label = st.radio("What do you want to keep in your notebook?", [KIND_LABELS[kind] for kind in EntryKind],
                              captions=[KIND_DESCRIPTIONS[kind] for kind in EntryKind], key=f"save-kind-{index}")
        kind = next(kind for kind in EntryKind if KIND_LABELS[kind] == kind_label)
        excerpt = None
        if kind is EntryKind.EXCERPT:
            excerpt = st.text_area("The part to keep (edit it down)", value=common.plain_text(message["answer"]),
                                   key=f"save-excerpt-{index}")
        if st.button("Save", key=f"save-{index}", type="primary"):
            try:
                with st.spinner("Saving…" if kind is not EntryKind.KEY_POINTS else "The tutor is condensing the key points…"):
                    entry = common.run(notebook.save_entry(
                        student_id=identity.person_id, class_level=course["class"], subject=course["subject"],
                        kind=kind, answer=message["answer"], excerpt=excerpt, origin=EntryOrigin.BUTTON,
                    ))
            except Exception as error:  # shown next to the control rather than as a traceback
                st.error(f"Not saved: {error}")
                return
            message.setdefault("saved", []).append(entry.kind.value)
            st.session_state.notebook_toast = KIND_LABELS[entry.kind]
            st.rerun()


tab_chat, tab_notebook, tab_turn, tab_memory = st.tabs(
    ["💬 Conversation", "📓 Notebook", "🔍 Last turn", "🧠 APU memory"])

with tab_chat:
    chat_box = st.container(height=440)
    with chat_box:
        # Marks this container for the accessibility script: it becomes the live region that
        # announces an answer to a screen reader (apu/ui/common.py).
        st.markdown(common.CHAT_LOG_ANCHOR, unsafe_allow_html=True)
        if not st.session_state.chat:
            st.caption("Ask a question about your lessons. Try an off-topic question too, "
                       "to see the guard at work.")
        for index, message in enumerate(st.session_state.chat):
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.markdown(message["content"])
                else:
                    render_assistant(message, index)

    if input_channel == "voice":
        recorded = st.audio_input("🎙️ Record your question", key="voice_recording")
        if recorded is not None:
            # One transcription per recording: the widget keeps returning the same file on
            # every rerun, and a transcript is a paid call.
            fingerprint = (getattr(recorded, "file_id", None), recorded.size)
            if st.session_state.get("voice_recording_done") != fingerprint:
                st.session_state.voice_recording_done = fingerprint
                with st.spinner("Transcribing your question…"):
                    try:
                        st.session_state.voice_prompt = voice.transcribe(
                            recorded.getvalue(), recorded.type or "audio/wav")
                    except voice.VoiceUnavailable as error:
                        st.warning(f"{error} You can still type your question below.")
        st.caption("The transcript is sent as your question, and goes through the guard like "
                   "any other. You can also type instead.")
    elif input_channel == "braille":
        st.caption("⠿ Braille keyboard: input reaches the app as text through the system.")

with tab_notebook:
    notebook_store = NotebookStore()
    scope = st.segmented_control("Show", ["This course", "All courses"], default="This course",
                                 key="notebook_scope") or "This course"
    if scope == "This course":
        entries = notebook_store.entries(identity.person_id, course["class"], course["subject"])
    else:
        entries = notebook_store.entries(identity.person_id)
    st.caption("What you chose to keep. The tutor never reads your notebook; braille sheets are made from it.")
    if not entries:
        st.info("Nothing saved yet. Use **💾 Save to notebook** under an answer, or ask the tutor: "
                "“save the key points of your answer”.")
    for entry in entries:
        with st.container(border=True):
            top = st.columns([5, 1])
            top[0].markdown(
                common.badge(KIND_LABELS[entry.kind], "info")
                + f" {entry.course} · {entry.created_at.astimezone().strftime('%d %b %H:%M')}"
                + (" · asked in chat" if entry.origin is EntryOrigin.CHAT else ""),
                unsafe_allow_html=True)
            if top[1].button("🗑️", key=f"delete-{entry.entry_id}", help="Remove from the notebook"):
                notebook_store.delete(identity.person_id, entry.entry_id)
                st.rerun()
            st.markdown(common.math_for_streamlit(entry.text))

    if entries:
        st.markdown("**⠿ Braille sheet**")
        from_summary_label = "A summary written by the tutor"
        sheet_source = st.radio("Made from", ["The selected entries, as written", from_summary_label],
                                key="sheet_source", horizontal=True)
        labels = {entry.entry_id: f"{KIND_LABELS[entry.kind]} · {entry.course} · {entry.text[:60]}"
                  for entry in entries}
        # Entries can be deleted or filtered out between runs; a stale selection would raise.
        if "sheet_entries" in st.session_state:
            st.session_state.sheet_entries = [i for i in st.session_state.sheet_entries if i in labels]
        else:
            st.session_state.sheet_entries = list(labels)
        selected = st.multiselect("Entries", list(labels), format_func=labels.get, key="sheet_entries")
        sheet_grade = BrailleGrade.GRADE_2 if (st.segmented_control(
            "Braille grade", ["Grade 1", "Grade 2"], default="Grade 2", key="sheet_grade") or "Grade 2") == "Grade 2" \
            else BrailleGrade.GRADE_1
        if st.button("Generate the braille sheet", type="primary", disabled=not selected):
            chosen = [entry for entry in entries if entry.entry_id in selected]
            try:
                if sheet_source == from_summary_label:
                    with st.spinner("The tutor is writing the revision summary…"):
                        sheet_text = common.run(notebook.summarize_entries(chosen))
                else:
                    sheet_text = notebook.entries_as_text(chosen)
                st.session_state.notebook_sheet = braille_sheet(sheet_text, sheet_grade)
            except Exception as error:  # liblouis missing, the model unreachable
                st.session_state.pop("notebook_sheet", None)
                st.error(f"Braille sheet unavailable: {error}")
        sheet = st.session_state.get("notebook_sheet")
        if sheet is not None:
            st.markdown(f'<div class="braille-block">{sheet.unicode_braille}</div>', unsafe_allow_html=True)
            st.caption(f"{sheet.pages} embosser page(s)")
            if st.toggle("Show in print (for the audience)", key="sheet_plain"):
                st.text(sheet.text)
            st.download_button("⬇ Embosser file (BRF)", sheet.brf, file_name="akili-notebook.brf",
                               mime="text/plain", key="sheet_brf")

with tab_turn:
    turn = st.session_state.last_turn
    if not turn:
        st.caption("No turn yet.")
    else:
        columns = st.columns(3)
        columns[0].metric("Turn duration", f"{turn['duration']:.1f} s")
        columns[1].metric("Web searches", len(turn.get("searches") or []))
        columns[2].metric("Sources", len(turn.get("sources") or []))
        st.markdown("**Guard verdict** " + common.badge(*OUTCOME_LABELS.get(
            turn.get("guard_outcome"), ("—", "info"))), unsafe_allow_html=True)
        for query in turn.get("searches") or []:
            st.markdown(f"- Tavily query: `{query}`")
        for source in turn.get("sources") or []:
            st.markdown(f"- [{source['title']}]({source['url']})")
        for kind in ("memory_problems", "tool_problems", "answer_problems"):
            for problem in turn.get(kind) or []:
                st.warning(f"{kind.replace('_', ' ')}: {problem}")

with tab_memory:
    cached = cache_l1.get_all_cached()
    st.markdown("**L1 · RAM cache**")
    if cached:
        metrics = cache_l1.get_metrics()
        st.dataframe([{"block": block_id, "hit rate": f"{metrics.get(block_id, {}).get('hit_rate', 0):.0%}",
                       "content": str(content)[:120]} for block_id, content in cached.items()],
                     hide_index=True, width="stretch")
    else:
        st.caption("Empty: blocks arrive here when the agent reads them.")
    st.markdown("**L2 · DLL (HEAD → TAIL)**")
    st.dataframe([{"block": node["label"], "type": node.get("type"),
                   "content": (node.get("content") or ", ".join(node.get("keywords", [])))[:120]}
                  for node in mmu.get_all_nodes(dll_state)], hide_index=True, width="stretch")
    st.markdown("**L3 · LanceDB**")
    try:
        db = lance_driver.get_db()
        st.dataframe([{"table": name, "rows": db.open_table(name).count_rows()}
                      for name in lance_driver.list_table_names(db)], hide_index=True, width="stretch")
    except Exception as error:   # an inspector panel: it reports, it never stops the page
        st.error(f"LanceDB: {error}")

# ── a turn ───────────────────────────────────────────────────────────────────
placeholder = {
    "text": "Ask your question…",
    "voice": "Transcript of your question…",
    "braille": "Braille input (text)…",
}[input_channel]
# A transcript enters here, not further down: it takes the same path as a typed question,
# guard included. Nothing is answered from the audio itself.
prompt = st.chat_input(placeholder) or st.session_state.pop("voice_prompt", None)
if prompt:
    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.chat]
    previous_answer = next((m["answer"] for m in reversed(st.session_state.chat) if m.get("answer")), "")
    count_before = session.off_topic_count
    with st.spinner("Akili is thinking (guard, search if needed, answer, memory)…"):
        # The turn itself lives in apu/ui/turn.py, shared with the Chainlit interface.
        result = common.run(turn_service.run_turn(
            prompt,
            session_id=session_id,
            agent_id=dll_state.get("agent_id"),
            class_level=course["class"],
            subject=course["subject"],
            history=history,
            history_turns=history_turns,
            input_channel=input_channel,
            output_channel=output_channel,
            text_display=text_display,
            previous_answer=previous_answer,
        ))

    st.session_state.chat.append({"role": "user", "content": prompt})
    if result.failed:
        st.session_state.chat.append({
            "role": "assistant", "output_channel": "text", "duration": result.duration,
            "content": f"⚠️ This turn could not be completed: {result.error}",
        })
        st.session_state.last_turn = None
    else:
        st.session_state.chat.append({
            "role": "assistant",
            "content": result.content,
            "written": result.written,
            "spoken": result.spoken,
            "off_topic": result.off_topic,
            "guard_outcome": result.guard_outcome,
            "answer": result.answer_text or None,
            "saved": [save["kind"] for save in result.notebook_saves],
            "searches": result.searches,
            "output_channel": output_channel,
            "duration": result.duration,
            "autoplay": output_channel == "voice",
        })
        if output_channel == "voice":
            try:
                with st.spinner("Reading the answer out…"):
                    audio = voice.synthesize(result.spoken or result.content)
                st.session_state.chat[-1]["audio"] = audio.data
                st.session_state.chat[-1]["audio_type"] = audio.mime_type
            except voice.VoiceUnavailable as error:
                st.session_state.chat[-1]["voice_problem"] = str(error)
        st.session_state.last_turn = {
            "guard_outcome": result.guard_outcome, "searches": result.searches,
            "sources": result.sources, "memory_problems": result.memory_problems,
            "tool_problems": result.tool_problems, "answer_problems": result.answer_problems,
            "refused_searches": result.refused_searches, "duration": result.duration,
        }
        if result.notebook_saves:
            st.session_state.notebook_toast = KIND_LABELS[EntryKind(result.notebook_saves[-1]["kind"])]
        if count_before < threshold <= session.off_topic_count:
            st.session_state.toast = True
    st.rerun()
