"""Run the SAME Lambda handler locally (in-memory store). Phase 1 only - not AWS.
   cd backend && python local_server.py   -> http://localhost:8787"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qsl
from handler import lambda_handler


class H(BaseHTTPRequestHandler):
    def _go(self, method):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        ev = {"requestContext": {"http": {"method": method}}, "rawPath": u.path,
              "queryStringParameters": dict(parse_qsl(u.query)), "body": self.rfile.read(n).decode() if n else None}
        r = lambda_handler(ev) if method != "OPTIONS" else {"statusCode": 204, "body": ""}
        self.send_response(r["statusCode"])
        for k, v in {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*",
                     "Access-Control-Allow-Headers": "content-type", "Access-Control-Allow-Methods": "GET,POST,OPTIONS"}.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(r["body"].encode())
    do_GET = lambda self: self._go("GET")
    do_POST = lambda self: self._go("POST")
    do_OPTIONS = lambda self: self._go("OPTIONS")


if __name__ == "__main__":
    print("Local API on http://localhost:8787 (in-memory, NOT AWS)")
    HTTPServer(("", 8787), H).serve_forever()
