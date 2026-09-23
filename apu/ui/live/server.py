"""FastAPI Live Server for APU Live Voice Lab.

Exposes:
  - GET /               : HTML frontend (modular Lego components)
  - /static/*           : Static CSS & JS Lego components
  - GET /api/students   : List of students from demo registry
  - WebSocket /ws/{model_id} : Dispatches to ElevenLabs STS or Gemini Live runners
"""

import os
from pathlib import Path
from uuid import uuid4

from dotenv import find_dotenv, load_dotenv

# uvicorn imports this module directly, so the keys have to be in the environment before the
# runners below read them at import time. Hence the imports after this call, and the noqa.
load_dotenv(find_dotenv())

from fastapi import FastAPI, Query  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.websockets import WebSocket, WebSocketDisconnect  # noqa: E402

from apu.demo import seed  # noqa: E402
from apu.logger import get_logger  # noqa: E402
from apu.ui.live.runner_elevenlabs import run_elevenlabs_sts  # noqa: E402
from apu.ui.live.runner_gemini_transcribe import run_gemini_transcribe_live  # noqa: E402

logger = get_logger("live_server")

STATIC_DIR = Path(__file__).parent / "static"

# A websocket is not covered by the browser's same-origin policy: without this check, any
# page the pupil happens to visit while this server runs could open a socket to it, drive
# the tutor on the account of any pupil it names, and read that pupil's notebook back. Set
# APU_LIVE_ALLOWED_ORIGINS (comma separated) to serve the lab from anywhere else.
ALLOWED_ORIGINS = {
    origin.strip()
    for origin in os.environ.get(
        "APU_LIVE_ALLOWED_ORIGINS",
        "http://localhost:8765,http://127.0.0.1:8765").split(",")
    if origin.strip()
}


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    # No Origin header at all is a non-browser client (a test, a script), which the browser
    # threat this check addresses does not cover.
    return origin is None or origin in ALLOWED_ORIGINS


def _roster() -> list[dict]:
    """
    The pupils this device serves, or nothing at all.

    One source for both the list the page offers and the check the socket makes: a page
    that offers a pupil the socket would refuse is worse than a page that offers none.
    """
    try:
        return list(seed.load_demo_students())
    except (OSError, ValueError, KeyError) as error:
        logger.warning("Could not read the roster: %s", error)
        return []


def _known_student(student_id: str, class_id: str) -> tuple[str, str] | None:
    """
    Resolve the pupil against that roster.

    This is NOT authentication: identity is a stub across the whole project, and anyone who
    can reach this port can still pick any pupil on the roster. What it does stop is an
    arbitrary identifier arriving in a query string and creating or reading a notebook under
    a name nobody on this device knows.
    """
    roster = {pupil["student_id"]: pupil.get("class_id", "") for pupil in _roster()}
    if student_id not in roster:
        return None
    return student_id, roster[student_id] or class_id

app = FastAPI(title="APU Live Voice Lab")

# Mount modular static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def get_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/students")
async def list_students() -> list[dict]:
    """The pupils the selector offers. Empty when the roster cannot be read, never invented."""
    return [{"id": pupil["student_id"],
             "name": pupil.get("display_name", pupil["student_id"]),
             "class_id": pupil.get("class_id", "")}
            for pupil in _roster()]


@app.websocket("/ws/{model_id:path}")
async def ws_proxy(
    client_ws: WebSocket,
    model_id: str,
    student_id: str = Query(default="eleve-aya"),
    class_id: str = Query(default="lycee-cocody:3eA"),
):
    """WebSocket router for live voice sessions."""
    if not _origin_allowed(client_ws):
        logger.warning("Refused a websocket from origin %r", client_ws.headers.get("origin"))
        await client_ws.close(1008)
        return

    await client_ws.accept()

    known = _known_student(student_id, class_id)
    if known is None:
        await client_ws.send_json({"type": "error",
                                   "message": f"Unknown student: '{student_id}'."})
        await client_ws.close(1008)
        return
    student_id, class_id = known

    # The session identifier keys the guard's own state, including how many off-topic turns
    # a pupil has had. Taking it from the client would let a page rotate it each turn and
    # never reach an escalation, so it is issued here.
    session_id = f"live-lab-{uuid4().hex[:8]}"

    logger.info(
        "WebSocket connection received: model=%s session=%s student=%s class=%s",
        model_id, session_id, student_id, class_id
    )

    history: list[dict] = []
    session_context: dict = {
        "session_id": session_id,
        "mode": "live_voice",
        "model_id": model_id,
    }

    try:
        if model_id == "eleven_english_sts_v2":
            await run_elevenlabs_sts(
                client_ws, session_id, student_id, class_id, history, session_context
            )
        elif model_id == "gemini-3.5-transcribe-live":
            await run_gemini_transcribe_live(
                client_ws, session_id, student_id, class_id, history, session_context
            )
        elif model_id == "gemini-3.8-live":
            # Imported here rather than at the top: the audio-to-audio runner is the one
            # piece of this lab an installation may choose to leave out, and the server has
            # to start without it.
            try:
                from apu.ui.live.runner_gemini_live import run_gemini_live
            except ModuleNotFoundError:
                await client_ws.send_json({
                    "type": "error",
                    "message": (f"'{model_id}' is an experimental runner that is not part of "
                                "this installation. See apu/ui/live/README.md."),
                })
                await client_ws.close(1008)
                return
            await run_gemini_live(
                client_ws, model_id, session_id, student_id, class_id, history, session_context
            )
        else:
            await client_ws.send_json({
                "type": "error",
                "message": f"Unknown model: '{model_id}'"
            })
            await client_ws.close(1008)
    except WebSocketDisconnect:
        logger.info("Client disconnected: %s (%s)", model_id, student_id)
    except Exception as exc:
        # The outermost net: a runner that raises must not take the server down with it,
        # and the trace goes to the log for whoever reads it afterwards.
        logger.error("The %s session ended on an error: %s", model_id, exc, exc_info=True)
