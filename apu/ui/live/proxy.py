"""Entry point for the APU live voice lab.

    uv run python -m apu.ui.live.proxy [--host 127.0.0.1] [--port 8765]

It serves the lab's own page, the keynote stage and the layer under both, and it carries the
websocket every front end talks to.
"""

import argparse

import uvicorn

from apu.ui.live.server import app

__all__ = ["app"]

# Loopback, not every interface. This process holds the API keys and the pupils' notebooks,
# and its only gate is a check on where a connection comes from. Bound to 0.0.0.0, as it was,
# every machine on the same school wifi could reach it.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def main() -> None:
    parser = argparse.ArgumentParser(description="APU live voice lab")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"Interface to bind (default: {DEFAULT_HOST}, loopback only)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port to serve on (default: {DEFAULT_PORT})")
    args = parser.parse_args()

    if args.host not in ("127.0.0.1", "::1", "localhost"):
        # Said out loud, because opening this to a network is a decision and not a flag.
        print(f"Serving on {args.host}: every machine that can reach this one can open a "
              "socket. Add their origins to APU_LIVE_ALLOWED_ORIGINS, and remember the "
              "pupil roster and the notebooks are behind this.")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
