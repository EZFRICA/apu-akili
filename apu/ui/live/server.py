"""FastAPI Live Server for APU Live Voice Lab.

Exposes:
  - GET /               : HTML frontend (modular Lego components)
  - /static/*           : Static CSS & JS Lego components
  - GET /api/students   : List of students from demo registry
  - WebSocket /ws/{model_id} : Dispatches to ElevenLabs STS or Gemini Live runners
"""

import asyncio
from pathlib import Path
from uuid import uuid4

from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from apu.logger import get_logger
from apu.ui.live.runner_elevenlabs import run_elevenlabs_sts
from apu.ui.live.runner_gemini_transcribe import run_gemini_transcribe_live
from apu.ui.live.runner_gemini_live import run_gemini_live

logger = get_logger("live_server")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="APU Live Voice Lab")

# Mount modular static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def get_index() -> FileResponse:
    """Serve the modular index.html."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/students")
async def list_students():
    """List available students from demo registry."""
    try:
        from apu.demo.seed import load_demo_students
        students = load_demo_students()
        return [
            {"id": s["student_id"], "name": s.get("display_name", s["student_id"]), "class_id": s.get("class_id", "")}
            for s in students
        ]
    except Exception as exc:
        logger.warning("Error loading demo students: %s", exc)
        return [
            {"id": "eleve-aya", "name": "Aya", "class_id": "lycee-cocody:3eA"},
            {"id": "eleve-koffi", "name": "Koffi", "class_id": "lycee-cocody:3eA"},
            {"id": "eleve-fatou", "name": "Fatou", "class_id": "lycee-cocody:3eA"},
        ]


@app.websocket("/ws/{model_id:path}")
async def ws_proxy(
    client_ws: WebSocket,
    model_id: str,
    session_id: str = Query(default=None),
    student_id: str = Query(default="eleve-aya"),
    class_id: str = Query(default="lycee-cocody:3eA"),
):
    """WebSocket router for live voice sessions."""
    await client_ws.accept()
    session_id = session_id or f"live-lab-{uuid4().hex[:8]}"

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
        elif model_id in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
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
        logger.error("Unhandled exception on /ws/%s: %s", model_id, exc, exc_info=True)
