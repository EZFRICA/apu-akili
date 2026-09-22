"""Hardware 3D Viewer Server for APU Akili Portable Tactile Device.

Run with:
    uv run python -m apu.ui.hardware.app [--port 8766]
"""

import argparse
import sys
import webbrowser
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler


class HardwareHTTPHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        directory = str(Path(__file__).parent)
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, format, *args):
        # Keep terminal output clean
        sys.stderr.write(f"[APU Hardware 3D] {self.address_string()} - {format % args}\n")


def main():
    parser = argparse.ArgumentParser(description="APU Akili Hardware 3D Viewer")
    parser.add_argument("--port", type=int, default=8766, help="Port to serve 3D viewer on (default: 8766)")
    parser.add_argument("--open", action="store_true", default=True, help="Open browser automatically")
    args = parser.parse_args()

    server_address = ("", args.port)
    httpd = HTTPServer(server_address, HardwareHTTPHandler)
    url = f"http://localhost:{args.port}/"
    print("==================================================")
    print(" APU Akili · 3D Tactile Hardware Studio")
    print(f" URL: {url}")
    print(" Press Ctrl+C to stop.")
    print("==================================================")

    if args.open:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping hardware viewer server.")
        httpd.server_close()


if __name__ == "__main__":
    main()
