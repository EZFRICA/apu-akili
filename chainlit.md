# APU Akili · Student Tutor

Welcome to **Akili**, your supportive AI school tutor powered by the Agent Processor Unit (APU). Ask about a lesson, an exercise, or your revision—by typing or by speaking into your microphone.

---

### How to use Akili

- 🛡️ **School-focused & Safe**: Every question passes through a topical safety guard before the tutor answers. Off-topic queries are gently redirected back to your studies.
- 🎙️ **Voice & Speech**: Tap the microphone button to ask out loud. Your voice is transcribed in real time, and tutor responses can be read back to you.
- ⠃⠗⠁⠊⠇⠇⠑ **Braille Support**: Access Grade 1 and Grade 2 Braille translations for every explanation, formatted for screen readers and refreshable displays.
- 📓 **Student Notebook**: Save important concepts directly with the action buttons under each answer:
  - **💾 Save full answer**: keeps the complete explanation in your personal notebook.
  - **📝 Save key points**: extracts and stores the core rules and summaries.
  - **✂️ Save excerpt**: highlights and notes specific passages.
- 🔍 **Web Citations**: Whenever verified educational sources are consulted, citations appear directly alongside the response.

---

### Settings & Controls

Click the **Settings** gear icon below the chat to customize your session:
- **How you work**: Switch between `Text`, `Voice`, and `Braille` modes.
- **Braille grade**: Select `Grade 1` (uncontracted) or `Grade 2` (contracted).
- **Conversation depth**: Adjust the number of previous exchanges given to the tutor model.

---

### Other interfaces

- **Teacher & Admin dashboard**: `uv run streamlit run apu/ui/app.py`
- **Live Voice Lab (FastAPI / WebSockets)**: `uv run python -m apu.ui.live.proxy`
