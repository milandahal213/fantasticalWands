"""Tiny dev server for the noWand PyScript app.

Use this instead of `python3 -m http.server` while developing. It sends
`Cache-Control: no-store` on every response, so the browser always fetches the
latest main.py / behaviors / lego_ble.py — no more editing a file and seeing the
old version because PyScript reused a cached copy.

    python3 serve.py            # serves this folder on http://localhost:8000
    python3 serve.py 8003       # ...or on a port you choose

Web Bluetooth needs a secure context, and http://localhost counts as one, so
this is all you need for local testing in Chrome or Edge.
"""
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Serving with no-store caching on http://localhost:{port}  (Ctrl-C to stop)")
    HTTPServer(("", port), NoCacheHandler).serve_forever()


if __name__ == "__main__":
    main()
