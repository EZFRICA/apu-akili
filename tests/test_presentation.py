"""
The keynote presentation interface.

Target: apu/ui/presentation/

This is the surface a pupil who cannot see the screen will be sitting in front of, so what
is checked here is not that it looks right, which a test cannot know, but the handful of
rules that made it unusable when they were broken: one turn on screen at a time, braille
that cannot push the prompter away, and words that reach a screen reader whole.
"""

import pathlib

import pytest


def _rule(stylesheet: str, selector: str) -> str:
    """One rule, to its closing brace. A fixed slice silently drops what a comment pushes out."""
    start = stylesheet.index(selector)
    return stylesheet[start:stylesheet.index("}", start) + 1]

UI = pathlib.Path(__file__).resolve().parents[1] / "apu/ui/presentation"
PROMPTER = (UI / "prompter.js").read_text(encoding="utf-8")
BRIDGE = (UI / "bridge.js").read_text(encoding="utf-8")
INDEX = (UI / "index.html").read_text(encoding="utf-8")
STYLES = (UI / "styles.css").read_text(encoding="utf-8")


def test_only_the_turn_being_spoken_is_on_screen():
    """
    The reply used to be appended to the one before it, because the caller set the speaker
    before streaming and the prompter decided to clear by comparing that same speaker. The
    turn boundary is the prompter's own state now.
    """
    assert "streamingReply" in PROMPTER
    assert "if (!this.streamingReply)" in PROMPTER, "a new reply starts a fresh line"
    assert 'if (this.currentSpeaker !== "assistant")' not in PROMPTER, \
        "clearing on the speaker is what let two turns pile up"


def test_the_braille_card_cannot_take_the_prompter_with_it():
    """A long answer in 28px cells pushed the prompter off the stage."""
    assert "max-height: clamp(" in STYLES
    sheet = _rule(STYLES, ".braille-sheet {")
    assert "max-height" in sheet and "overflow: auto" in sheet, \
        "the page scrolls inside its own box"
    assert "clamp(" in _rule(STYLES, ".braille-page {"), \
        "the cell size follows the window height"


def _relative_luminance(colour: str) -> float:
    channels = [int(colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    a, b = _relative_luminance(first), _relative_luminance(second)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def _braille_tokens() -> dict[str, str]:
    import re

    block = STYLES[STYLES.index("--braille-card:"):STYLES.index(".braille-keynote-card {")]
    return dict(re.findall(r"--(braille-[a-z-]+): (#[0-9a-f]{6});", block))


def test_the_cells_are_readable_without_being_the_brightest_thing_on_the_stage():
    """
    The card was white on black inside a black card, ringed in saturated purple and lit
    from behind: 21:1, the most a screen can do, spent on decoration as much as on the
    cells. Lower, but not so low that the one thing worth reading becomes hard to.
    """
    tokens = _braille_tokens()
    cells = _contrast(tokens["braille-cells"], tokens["braille-well"])
    assert cells >= 7.0, f"the cells are at {cells:.1f}:1, below the strictest threshold"
    assert cells <= 16.0, f"the cells are back at {cells:.1f}:1, which is what was too much"

    labels = _contrast(tokens["braille-label"], tokens["braille-card"])
    assert labels >= 4.5, f"the labels fell to {labels:.1f}:1"
    assert labels < cells, "a label must not shout as loudly as the cells"


def test_the_cells_sit_on_a_surface_rather_than_in_a_hole():
    """The well was darker than the card it was in, which is the jump the eye complained of."""
    tokens = _braille_tokens()
    assert _relative_luminance(tokens["braille-well"]) > _relative_luminance(tokens["braille-card"])

    card = _rule(STYLES, ".braille-keynote-card {")
    assert "rgba(168, 85, 247" not in card, "the purple ring and its glow are decoration"
    assert "0 0 28px" not in card, "a glow behind a card of text is a light pointed at a reader"

    braille_block = STYLES[STYLES.index(".braille-keynote-card {"):STYLES.index(".equipment-3d-stage {")]
    assert "#ffffff" not in braille_block, "pure white is the top of the scale, not a colour"


def test_the_prompter_takes_the_room_it_needs_and_no_more():
    """The top band was a fixed 52% of the capsule, empty under two lines of text."""
    overlay = _rule(STYLES, ".keynote-top-overlay {")
    assert "height: auto" in overlay and "max-height: 52%" in overlay
    assert ".prompter-card-slot:empty" in STYLES, "an empty slot kept its margin"


def test_a_pupil_who_cannot_see_the_screen_is_told_what_was_said():
    assert 'id="prompter-announcer"' in INDEX
    assert 'aria-live="polite"' in INDEX and 'aria-atomic="true"' in INDEX
    assert "_announce(" in PROMPTER
    # Announced at the end of the turn, not per token: a live region fed token by token
    # reads a sentence one word at a time.
    end_turn = PROMPTER[PROMPTER.index("endTurn()"):][:400]
    assert "_announce(this.activeText)" in end_turn


def test_motion_can_be_turned_off_and_focus_can_be_seen():
    assert "prefers-reduced-motion" in STYLES, "the stage floats, pulses and glows"
    assert "focus-visible" in STYLES, "the page is driven by keyboard too"


def test_the_interface_speaks_one_language():
    """
    Project rule: everything but our conversation is in English. The braille table keeps
    its accented French letters, which are data, not interface text.
    """
    import re

    for name, source in (("prompter.js", PROMPTER), ("bridge.js", BRIDGE), ("index.html", INDEX)):
        text = re.sub(r'"[éèêàùçâîô]": "[^"]*",?', "", source)   # the braille map
        leftovers = re.findall(r"[^\x00-\x7F]", text)
        accented = [c for c in leftovers if c in "éèêàùçœâîôÉÈÊÀÇ"]
        assert not accented, f"{name} still holds French interface text: {set(accented)}"


def test_the_lab_hands_the_stage_over_without_telling_the_browser_to_keep_it():
    """
    StaticFiles sends an etag and a last-modified date and no Cache-Control at all, which
    leaves a browser free to guess a freshness lifetime from the file's age. The lab is the
    documented way to open this page, and it is open while the page is being changed.
    """
    from fastapi.testclient import TestClient

    from apu.ui.live.server import app

    with TestClient(app) as client:
        for path in ("/presentation/styles.css", "/presentation/presentation.js"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "no-store" in response.headers.get("cache-control", ""), path


def test_each_server_message_is_handled_once():
    """
    `case "braille_format"` appeared twice in the same switch. JavaScript takes the first,
    so the second was dead code and the braille button stayed lit until the turn ended.
    """
    import re

    cases = re.findall(r'case "([a-z_]+)":', BRIDGE)
    duplicated = {c for c in cases if cases.count(c) > 1}
    assert not duplicated, f"these messages are handled by more than one case: {duplicated}"


HARDWARE3D = (UI / "hardware3d.js").read_text(encoding="utf-8")
PRESENTATION = (UI / "presentation.js").read_text(encoding="utf-8")


def test_the_stage_fits_the_window_it_is_given():
    """
    The capsule was 94vh under a 36px header padding, so it ran past the bottom of a
    laptop screen and took the ports and the braille key with it, on a page that cannot
    scroll.
    """
    capsule = _rule(STYLES, ".elevenlabs-capsule-frame {")
    assert "max-height: calc(100vh" in capsule
    assert "height: 94vh" not in capsule, "a fixed 94vh plus the header does not fit"


@pytest.mark.parametrize("part", ["btn_ptt", "btn_notebook", "btn_summary", "btn_braille"])
def test_every_tactile_key_has_a_target_wider_than_itself(part):
    """
    The moulded keys are 28 to 49 pixels across on screen. The pointer aims at an
    invisible disc in front of them instead, which is what makes them hittable.
    """
    assert '_addHitTarget(' in HARDWARE3D
    assert f'"{part}"' in HARDWARE3D
    targets = HARDWARE3D.count("_addHitTarget(")
    assert targets >= 5, "one helper and one call per tactile key"


def test_no_aiming_disc_reaches_another_key():
    """
    The discs are wider than the keys on purpose. The microphone's had a radius of 0.42
    and the braille key sat 0.40 below it, so the disc covered that key's own centre and
    pressing braille opened the microphone instead.
    """
    import math
    import re

    groups = dict(re.findall(r"(\w+G)\.position\.set\(([-\d., ]+)\);", HARDWARE3D))
    radii = dict((part, float(radius)) for _, part, radius in
                 re.findall(r'_addHitTarget\((\w+), "(\w+)", ([\d.]+)\)', HARDWARE3D))
    targets = {}
    for name, part, _ in re.findall(r'_addHitTarget\((\w+), "(\w+)", ([\d.]+)\)', HARDWARE3D):
        x, y, _z = (float(v) for v in groups[name].split(","))
        targets[part] = (x, y)

    assert len(targets) >= 4, targets
    for part, (x, y) in targets.items():
        for other, (ox, oy) in targets.items():
            if other == part:
                continue
            gap = math.dist((x, y), (ox, oy))
            assert radii[part] < gap, (
                f"{part}'s disc ({radii[part]}) reaches {other}'s centre, {gap:.2f} away"
            )


def test_the_key_a_press_lands_on_is_the_nearest_one_and_not_the_nearest_surface():
    """Where two discs do overlap, the first crossing is a surface, not an intention."""
    assert "_partUnderRay(" in HARDWARE3D
    assert "intersects[0].object" not in HARDWARE3D, \
        "the first crossing is the nearest surface, which is not the key being aimed at"
    picker = HARDWARE3D[HARDWARE3D.index("_partUnderRay(intersects) {"):][:900]
    assert "centre.distanceTo(hit.point)" in picker
    assert "distance < bestDistance" in picker


def test_the_device_holds_still_while_a_hand_approaches():
    assert "this.isNearDevice || still" in HARDWARE3D, \
        "the float moves every key by six pixels while it is being aimed at"


def test_the_stage_stops_moving_when_the_viewer_asks_it_to():
    """
    The stylesheet's reduced-motion rules cannot reach inside a canvas. The device kept
    floating and the keys kept pulsing for someone who had asked for none of it.
    """
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in HARDWARE3D
    assert "reducedMotion" in HARDWARE3D
    animate = HARDWARE3D[HARDWARE3D.index("_animate() {"):]
    assert "const still = this.reducedMotion.matches" in animate
    assert "still ? 1.4 :" in animate, "a key in use stays lit instead of throbbing"

    camera = (UI / "camera.js").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in camera, "the stand-in silhouette drifts and glows"


def test_the_canvas_resizes_with_the_capsule_and_not_only_with_the_window():
    """
    Collapsing the side panels changes the capsule without changing the window, and a
    canvas holding its old size put every key a few pixels from where the pointer aimed.
    """
    assert "if (window.ResizeObserver)" in HARDWARE3D, \
        "a window resize listener alone never hears the capsule change"
    assert "new ResizeObserver(() => this._onResize())" in HARDWARE3D
    assert "observe(this.container)" in HARDWARE3D


def test_the_canvas_is_not_announced_as_an_unlabelled_graphic():
    """
    A WebGL canvas has no accessible content at all. The component list beside it is the
    same device expressed as buttons, which is what a screen reader can actually press.
    """
    stage = INDEX[INDEX.index('id="equipment-3d-stage"'):][:260]
    assert 'aria-hidden="true"' in stage
    assert 'role="group"' in INDEX and "Press a key on Pocket Akili" in INDEX


def test_every_toggle_says_whether_it_is_on():
    """`class="active"` is a colour. aria-pressed is the state."""
    import re

    for selector in ("model-pill-btn", "view-shot-btn"):
        buttons = re.findall(rf'<button class="{selector}[^>]*>', INDEX)
        assert buttons, selector
        for button in buttons:
            assert "aria-pressed=" in button, button
    for toggle in ("toggle-mic-btn", "toggle-camera-btn", "toggle-mirror-btn",
                   "toggle-drawer-btn"):
        element = INDEX[INDEX.index(f'id="{toggle}"'):][:400]
        assert "aria-pressed=" in element, toggle
    assert "_setPressed(" in PRESENTATION, "the attribute has to follow the state"


def test_the_only_keyboard_path_to_the_device_has_buttons_with_names():
    """
    Read back from a real browser, the eight component buttons announced as "button" and
    nothing else: the emoji and the two nested spans computed to no accessible name. They
    are the whole keyboard and screen-reader path to a device that is a bare canvas.
    """
    parts = PRESENTATION[PRESENTATION.index("_renderPartsList() {"):][:2000]
    assert 'btn.setAttribute("aria-label"' in parts
    assert '${part.name}. ${part.sub}' in parts
    assert 'class="part-icon" aria-hidden="true"' in parts, "an emoji is not a label"


def test_a_panel_slid_off_the_stage_is_out_of_the_reading_order_too():
    """Collapsed by CSS alone, both side panels were still read and still focusable."""
    toggle = PRESENTATION[PRESENTATION.index("toggleDrawerBtn?.addEventListener"):][:800]
    assert "panel.hidden = Boolean(collapsed)" in toggle


def test_the_two_things_a_presenter_does_without_looking_have_keys():
    """The device is a canvas: no focus, no keys. These are its keyboard equivalent."""
    assert 'event.key === "Escape"' in PRESENTATION
    assert 'event.key === "m"' in PRESENTATION
    keys = PRESENTATION[PRESENTATION.index('window.addEventListener("keydown"'):][:900]
    assert 'tag === "INPUT"' in keys, "typing a pupil's name must not fire the microphone"
    assert "metaKey" in keys, "a browser shortcut is not ours to take"


def test_what_the_pupil_hears_when_something_breaks():
    """The failure used to be eleven characters of grey text in the corner of the stage."""
    assert "showNotice(" in PROMPTER
    notice = PROMPTER[PROMPTER.index("showNotice(message) {"):][:500]
    assert "_announce(message)" in notice
    assert "this.activeText = \"\"" in notice, "half an answer must not be read as a whole one"
    assert "this.prompter.showNotice(" in PRESENTATION


def test_the_pill_keeps_saying_whether_the_lab_is_there():
    """It used to fall back to a flat "Ready", losing the only thing it is there to say."""
    assert "_setIdleStatus" in PRESENTATION
    idle = PRESENTATION[PRESENTATION.index("_setIdleStatus() {"):][:400]
    assert "isConnected" in idle and "Live Connected" in idle
    assert '"connected", "Ready"' not in PRESENTATION


def test_the_specification_survived_the_move():
    """The device's dimensions outlive the viewer that drew it, so they moved with it."""
    readme = (UI / "README.md").read_text(encoding="utf-8")

    assert "## Physical Specifications" in readme
    for detail in ("165 g", "USB-C", "3.5 mm", "braille display", "Braille Dock"):
        assert detail.lower() in readme.lower(), f"{detail} was lost in the move"


def test_the_microphone_does_not_reach_the_speakers_it_is_recording():
    """
    The node that reads the microphone has to be pulled by something downstream, and it
    was wired to the output: a live microphone played into the room it is recording. It
    was wired that way in both front ends, which is why it now exists in only one place.
    """
    audio = SHARED_AUDIO[SHARED_AUDIO.index("async start()"):SHARED_AUDIO.index("  stop()")]
    assert "this.processor.connect(this.audioContext.destination)" not in audio
    assert "this.sink.gain.value = 0" in audio
    assert "this.processor.connect(this.sink)" in audio


def test_the_braille_table_gives_each_letter_its_own_cells():
    """k was mapped to l's cells and a circumflex i to a plain i: two letters read as one."""
    import re

    table = PROMPTER[PROMPTER.index("const BRAILLE_G1_MAP"):PROMPTER.index("function textToBrailleG1")]
    pairs = dict(re.findall(r'"?([a-z\u00e0-\u00ff])"?: "([^"]+)"', table))
    assert pairs["k"] == "\u2805" and pairs["l"] == "\u2807"
    assert pairs["\u00ee"] != pairs["i"]

    latin = [v for k, v in pairs.items() if k.isascii()]
    assert len(latin) == len(set(latin)), "two letters sharing one cell is a letter lost"


def test_nothing_the_server_sends_is_treated_as_markup():
    """
    The braille cells come from the lab and went into innerHTML unescaped, so whatever the
    lab sent was parsed as elements on a page holding a live microphone.
    """
    import re

    body = PROMPTER[PROMPTER.index("_renderBrailleCard() {"):PROMPTER.index("\n  _downloadBRF(")]
    # Only what reaches innerHTML. A value built elsewhere is escaped where it is used.
    template = body[body.index("card.innerHTML = `"):body.index("`;", body.index("card.innerHTML"))]
    interpolated = re.findall(r"\$\{([^}]+)\}", template)
    assert interpolated, "the card is built from a template"
    for expression in interpolated:
        assert "_escape(" in expression, f"${{{expression}}} reaches the parser unescaped"


# ── the same rules, run instead of read ──────────────────────────────────────

@pytest.mark.parametrize("suite", ["prompter", "bridge", "audio"])
def test_the_interface_behaves_the_way_it_reads(suite):
    """
    Grepping a file proves a line was typed. These two suites run the real prompter and
    the real bridge against a stub browser, which is what proves they work: one turn on
    screen, one socket, cells that stay text, audio that loses what it cannot carry.
    """
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    root = pathlib.Path(__file__).resolve().parents[1]
    result = subprocess.run([node, f"tests/presentation/{suite}.test.mjs"],
                            cwd=root, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert ", 0 failed" in result.stdout


# ── one backend, one copy of the plumbing, two front ends ────────────────────

SHARED = pathlib.Path(__file__).resolve().parents[1] / "apu/ui/shared"
SHARED_AUDIO = (SHARED / "audio.js").read_text(encoding="utf-8")
SHARED_SOCKET = (SHARED / "socket.js").read_text(encoding="utf-8")
LAB = pathlib.Path(__file__).resolve().parents[1] / "apu/ui/live/static"


def test_the_microphone_and_the_socket_exist_once():
    """
    They existed twice, written separately against the same server, and two defects fixed
    in one copy were still running in the other: the decimation with no low-pass, and the
    microphone wired to the speakers. One copy is the point of this directory.
    """
    assert not (LAB / "js/ws.js").exists(), "the lab's own websocket client"
    assert not (LAB / "js/audio.js").exists(), "the lab's own microphone"

    for name, source in (("the keynote bridge", BRIDGE), ("the lab", LAB_APP)):
        assert "createScriptProcessor" not in source, f"{name} opens its own microphone"
        assert "new WebSocket(" not in source, f"{name} opens its own socket"
        assert "_downsampleTo16k" not in source and "downsampleTo16k" not in source, \
            f"{name} carries its own resampler"


LAB_APP = (LAB / "js/app.js").read_text(encoding="utf-8")


@pytest.mark.parametrize("front, source", [
    ("presentation", (pathlib.Path(__file__).resolve().parents[1]
                      / "apu/ui/presentation/bridge.js").read_text(encoding="utf-8")),
    ("lab", (pathlib.Path(__file__).resolve().parents[1]
             / "apu/ui/live/static/js/app.js").read_text(encoding="utf-8")),
])
def test_both_front_ends_run_on_the_shared_layer(front, source):
    assert "shared/audio.js" in source, front
    assert "shared/socket.js" in source, front


def test_the_lab_hands_out_the_shared_layer_both_front_ends_import():
    """
    A relative import that resolves to nothing is a blank page. Both fronts reach /shared/
    from where the lab serves them, so the lab has to serve it.
    """
    from fastapi.testclient import TestClient

    from apu.ui.live.server import app

    with TestClient(app) as client:
        for path in ("/shared/audio.js", "/shared/socket.js"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert "no-store" in response.headers.get("cache-control", ""), path


def test_the_socket_cannot_report_its_own_failure_as_the_tutors():
    """
    The server sends a message of type "error" meaning the tutor could not answer. The
    socket reported its own failure to open under that same name, so a front end could not
    tell "the lab is not there" from "the lab refused that question".
    """
    import re

    server_types = set()
    for path in (pathlib.Path(__file__).resolve().parents[1] / "apu/ui/live").glob("*.py"):
        server_types |= set(re.findall(r'"type": *"([a-z_]+)"', path.read_text(encoding="utf-8")))
    assert "error" in server_types, "the premise of this test"

    lifecycle = set(re.findall(r'export const SOCKET_\w+ = "([^"]+)";', SHARED_SOCKET))
    assert len(lifecycle) == 4, lifecycle
    assert not (lifecycle & server_types), f"these names collide: {lifecycle & server_types}"


def test_the_socket_goes_back_to_wherever_the_page_came_from():
    """
    The keynote stage hardcoded ws://host:8765 because it could be served from its own
    port. There is no own port any more: the lab serves it, and a hardcoded port is the
    one thing that would break the day it moves.
    """
    assert ":8765" not in SHARED_SOCKET.replace("localhost:8765", ""), "no hardcoded port"
    assert "window.location.host" in SHARED_SOCKET
    assert 'protocol === "https:" ? "wss:"' in SHARED_SOCKET, "a page over https needs wss"


# ── braille is printed, not displayed ────────────────────────────────────────

def test_the_braille_the_lab_sends_is_laid_out_the_way_paper_holds_it():
    """
    A row of cells running off the side of a box is a screen's idea of braille. Braille is
    embossed: forty cells to a line, twenty-five lines to a page, words wrapped at spaces.
    The lab lays it out with the same embosser that writes the .BRF file.
    """
    from apu.modality.braille.translator import unicode_to_braille_ascii
    from apu.ui.live.intents import braille_ascii_to_unicode, compute_emboss_job

    text = ("The perimeter is the total distance all the way around the outside of a flat "
            "shape. To find it, add together the lengths of all of its sides. ") * 3
    job = compute_emboss_job(text)
    if job is None:
        pytest.skip("liblouis is not available on this machine")

    assert job["cells_per_line"] == 40 and job["lines_per_page"] == 25
    for page in job["pages"]:
        for line in page:
            assert len(line) <= 40, f"a line of {len(line)} cells does not fit the paper"
    for page in job["pages_unicode"]:
        for line in page:
            assert all(character == " " or 0x2800 <= ord(character) <= 0x28FF
                       for character in line), "the dots are what a person reads"

    # The two renderings are the same braille, so the preview cannot drift from the paper.
    for ascii_page, dot_page in zip(job["pages"], job["pages_unicode"]):
        for ascii_line, dot_line in zip(ascii_page, dot_page):
            assert unicode_to_braille_ascii(dot_line) == ascii_line
            assert braille_ascii_to_unicode(ascii_line) == dot_line

    assert job["brf"], "the file an embosser is actually fed"


def test_a_long_answer_becomes_more_than_one_page():
    """A page holds a thousand cells. A tutor's answer can be longer, and paper ends."""
    from apu.ui.live.intents import compute_emboss_job

    job = compute_emboss_job("Mathematics is the study of shape and number. " * 120)
    if job is None:
        pytest.skip("liblouis is not available on this machine")
    assert len(job["pages_unicode"]) > 1
    assert job["brf"].count("\f") == len(job["pages"]) - 1, "a form feed between pages"


def test_the_acknowledgement_is_marked_as_one_rather_than_matched_on_its_words():
    """
    "Here is the braille transcription of our last explanation" is a sentence about the
    cells, not a lesson, and it used to replace the explanation those cells hold. A front
    end has to be told which it is; pattern-matching an English sentence is not telling.
    """
    pipeline = (pathlib.Path(__file__).resolve().parents[1]
                / "apu/ui/live/pipeline.py").read_text(encoding="utf-8")
    assert '"announcement": True' in pipeline

    branch = PRESENTATION[PRESENTATION.index("if (payload.announcement) {"):]
    branch = branch[:branch.index("break;") + 6]
    assert "announceAction(payload.token)" in branch
    assert "streamAssistantToken" not in branch, \
        "an acknowledgement streamed onto the prompter is what this branch exists to stop"
    assert "announceAction(" in PROMPTER
    announce = PROMPTER[PROMPTER.index("announceAction(message) {"):][:400]
    assert "this.textEl" not in announce, "an acknowledgement does not touch the prompter"
    assert "this.badgeEl" not in announce, "nor the badge, which the turn's end overwrites"
    assert "_announce(message)" in announce, "but a reader is still told"


def test_the_file_offered_is_the_one_the_embosser_wrote():
    card = PROMPTER[PROMPTER.index("_renderBrailleCard() {"):PROMPTER.index("\n  _downloadBRF(")]
    assert "emboss ? emboss.brf :" in card, \
        "a file this page assembled could disagree with the page it is previewing"


def test_no_microphone_is_hidden_under_the_teleprompter():
    """
    A click anywhere on that band opened the microphone: an unlabelled target eight hundred
    pixels wide that a keyboard could not reach. When an answer arrived the band slid fifty
    pixels up under the pointer, so a click aimed at the badge opened the microphone.
    """
    assert '.prompter-text-window")?.addEventListener("click"' not in PRESENTATION
    assert 'querySelector(".prompter-text-window")' not in PRESENTATION

    # The three ways it does open, each of them labelled or pressed deliberately.
    assert "toggleMicBtn?.addEventListener" in PRESENTATION
    assert 'event.key === "m"' in PRESENTATION
    assert '"btn_ptt"' in HARDWARE3D


def test_the_prompter_gives_room_back_when_the_cells_are_what_was_asked_for():
    """
    Over a long answer the teleprompter kept its full height and pushed the page of cells
    down behind the device on the stage, so the one thing the pupil had asked for was the
    one thing they could not see.
    """
    assert ".prompter-container.braille-open .prompter-text-window" in STYLES
    opened = _rule(STYLES, ".prompter-container.braille-open .prompter-text-window {")
    assert "max-height" in opened
    assert 'classList.toggle("braille-open"' in PROMPTER, "nothing sets the class otherwise"


def test_the_lab_puts_the_page_on_the_socket_and_not_only_the_cells():
    """
    compute_emboss_job being right is worth nothing if what reaches the browser is still a
    row of cells. This is the message the front end actually receives.
    """
    import asyncio

    from apu.ui.live.intents import compute_emboss_job
    from apu.ui.live.pipeline import push_braille

    sent = []

    class FakeSocket:
        async def send_json(self, payload):
            sent.append(payload)

    text = ("The perimeter is the distance all the way around the outside of a flat shape. "
            "Add together the lengths of all of its sides. ") * 4
    assert asyncio.run(push_braille(FakeSocket(), text)) is True
    assert len(sent) == 1
    message = sent[0]

    assert message["type"] == "braille_format"
    assert message["braille_g1"] and message["braille_g2"]

    # Skipping only when there is genuinely no layout to be had. Asking the message itself
    # would let a pipeline that computes nothing skip its own test.
    if compute_emboss_job(text) is None:
        pytest.skip("liblouis laid out no pages on this machine")

    emboss = message.get("emboss")
    assert emboss is not None, "the layout was computed and then not sent"
    assert emboss["cells_per_line"] == 40 and emboss["lines_per_page"] == 25
    assert emboss["pages_unicode"] and emboss["pages"]
    assert emboss["brf"], "the file the .BRF button hands over"
    assert all(len(line) <= 40 for page in emboss["pages"] for line in page)


# ── an acknowledgement is not an explanation ─────────────────────────────────

def test_pressing_braille_twice_embosses_the_lesson_and_not_the_announcement():
    """
    Measured, before this: the second press embossed "here is the braille transcription of
    our last explanation", because the lab stored its own acknowledgement in the history as
    a tutor answer and the braille lookup took the last one. In contracted braille that
    sentence reads "the brl transcription of our last explanation", which is what a pupil
    found under their fingers in place of their lesson.
    """
    from apu.ui.live.intents import last_explanation

    lesson = "The perimeter is the distance all the way around a flat shape."
    history = [
        {"role": "user", "content": "What is a perimeter?"},
        {"role": "assistant", "content": lesson},
        {"role": "user", "content": "Give me that in braille"},
        {"role": "assistant",
         "content": "Here is the braille transcription of our last explanation.",
         "announcement": True},
    ]
    assert last_explanation(history) == lesson

    # And again after a notebook save, which acknowledges the same way.
    history += [
        {"role": "user", "content": "Save that in my notebook"},
        {"role": "assistant", "content": 'Saved in your notebook: "Perimeter".',
         "announcement": True},
    ]
    assert last_explanation(history) == lesson


def test_a_note_keeps_the_lesson_and_not_the_confirmation_of_the_last_one():
    """The same lookup decides what a pupil's notebook keeps, where it matters more."""
    from apu.ui.live.intents import last_explanation

    history = [
        {"role": "assistant", "content": "A fraction is a part of a whole."},
        {"role": "assistant", "content": 'Saved in your notebook: "Fractions".',
         "announcement": True},
    ]
    assert last_explanation(history) == "A fraction is a part of a whole."
    assert last_explanation([]) == ""
    assert last_explanation(None) == ""


def test_the_lab_marks_its_own_acknowledgements_in_the_history():
    pipeline = (pathlib.Path(__file__).resolve().parents[1]
                / "apu/ui/live/pipeline.py").read_text(encoding="utf-8")
    appended = [line for line in pipeline.splitlines()
                if 'history.append({"role": "assistant"' in line]
    assert len(appended) == 4, appended
    marked = [line for line in appended if '"announcement": True' in line]
    assert len(marked) == 2, f"the braille and notebook acknowledgements: {appended}"

    # And nothing looks for the last assistant turn without going through the helper.
    for module in ("apu/ui/live/pipeline.py", "apu/ui/live/intents.py"):
        source = (pathlib.Path(__file__).resolve().parents[1] / module).read_text(encoding="utf-8")
        body = source[source.index("def last_explanation") + 20:] if "def last_explanation" in source else source
        assert 'role") == "assistant"' not in body.replace(
            'if entry.get("role") != "assistant"', ""), f"{module} looks it up by hand"


def test_an_empty_card_shows_nothing_rather_than_inventing_cells():
    """
    With no lesson yet the card fell back to cells spelling the product name. A pupil
    reading with their fingers takes whatever is under them for the answer, which is why
    the lab sends no cells rather than apologetic ones.
    """
    card = PROMPTER[PROMPTER.index("_renderBrailleCard() {"):PROMPTER.index("\n  _downloadBRF(")]
    assert "APU Akili, tactile voice companion" not in card
    assert 'this.activeText ? textToBrailleG1(this.activeText) : ""' in card
    assert "nothing to emboss yet" in card
    assert "no embosser on this device" not in card, \
        "there is an embosser; what was missing was anything to put through it"


def test_saving_a_note_embosses_what_was_kept_not_the_confirmation():
    """
    The notebook turn embossed its own acknowledgement, so a pupil who saved a lesson and
    reached for the braille found "Saved in your notebook" under their fingers.
    """
    pipeline = (pathlib.Path(__file__).resolve().parents[1]
                / "apu/ui/live/pipeline.py").read_text(encoding="utf-8")
    save_branch = pipeline[pipeline.index("if is_save_notebook_intent(prompt):"):]
    save_branch = save_branch[:save_branch.index("# 2. Handle Voice Intent")]

    assert 'push_braille(client_ws, nb_res["content"])' in save_branch
    assert "push_braille(client_ws, ack_text)" not in save_branch
