"""Entry point for APU Live Voice Lab.

Usage:
  uv run python -m apu.ui.live.proxy
"""

import uvicorn
from apu.ui.live.server import app

__all__ = ["app"]

if __name__ == "__main__":
    uvicorn.run(
        "apu.ui.live.server:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="info",
    )
