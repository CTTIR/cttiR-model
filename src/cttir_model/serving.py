"""Loopback development service with bounded admission and no inference runtime."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from .broker import Broker, FixtureEndpoint
from .config import Config
from .corpus import Corpus
from .errors import ProjectError
from .provenance import canonical, decode_json


ERROR_HTTP = {"busy": 429, "duplicate_request": 409, "corpus_pin": 409,
              "package_pin": 409, "missing_corpus": 503, "model_unavailable": 503,
              "timeout": 504, "cancelled": 409, "input_limit": 413,
              "schema_invalid": 422, "unknown_evidence": 422}


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 4

    def __init__(self, address, broker):
        if address[0] != "127.0.0.1":
            raise ProjectError("bind_policy", "Development service binds only to literal loopback.")
        self.broker = broker
        self.slots = threading.BoundedSemaphore(4)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Neither raw request text nor stack traces should enter user logs.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "cttir-model/0.1"

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def send_json(self, code, value):
        raw = canonical(value)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def boundary(self):
        host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != host or self.headers.get("Origin"):
            raise ProjectError("origin_policy", "Only direct loopback clients are accepted.")
        if self.headers.get("Transfer-Encoding"):
            raise ProjectError("request_encoding", "Chunked request bodies are not supported.")

    def handle_operation(self, operation):
        try:
            self.boundary()
            operation()
        except ProjectError as exc:
            self.send_json(ERROR_HTTP.get(exc.code, 400), {"status": "failed",
                           "error": {"code": exc.code, "message": str(exc)}})
        except (TimeoutError, ConnectionError, BrokenPipeError):
            self.close_connection = True
        except Exception:
            self.send_json(500, {"status": "failed", "error": {"code": "internal", "message": "Internal service failure."}})

    def do_GET(self):
        def operation():
            if self.path != "/health":
                self.send_json(404, {"error": {"code": "not_found"}})
                return
            self.send_json(200, self.server.broker.health())
        self.handle_operation(operation)

    def do_POST(self):
        def operation():
            if self.path not in {"/v1/specialist", "/v1/consult"}:
                self.send_json(404, {"error": {"code": "not_found"}})
                return
            if self.headers.get_content_type() != "application/json":
                raise ProjectError("content_type", "Expected application/json.")
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) != 1 or not lengths[0].isdigit():
                raise ProjectError("content_length", "Expected one Content-Length header.")
            length = int(lengths[0])
            if not 0 < length <= 65536:
                raise ProjectError("input_limit", "Request body exceeds the size budget.")
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ProjectError("invalid_json", "Incomplete request body.")
            response = self.server.broker.run(decode_json(raw), self.path == "/v1/consult")
            self.send_json(200, response)
        self.handle_operation(operation)

    def do_DELETE(self):
        def operation():
            if not self.path.startswith("/v1/requests/"):
                self.send_json(404, {"error": {"code": "not_found"}})
                return
            identity = unquote(self.path[len("/v1/requests/"):])
            self.send_json(200, {"cancelled": self.server.broker.cancel(identity)})
        self.handle_operation(operation)


def serve(config: Config, fixture: bool = False) -> dict:
    corpus = Corpus.from_config(config) if config.values["corpus"]["path"] else None
    if fixture and (corpus is None or not corpus.fixture_only):
        raise ProjectError("fixture_policy", "Fixture service requires an explicitly synthetic corpus.")
    endpoint = FixtureEndpoint() if fixture else None
    settings = config.values["serving"]
    with LocalServer((settings["host"], settings["port"]), Broker(corpus, endpoint, endpoint)) as server:
        print(json.dumps({"status": "listening", "host": settings["host"], "port": settings["port"],
                          "mode": "fixture" if fixture else "unavailable", "model_ready": False}), flush=True)
        try:
            server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            pass
    return {"status": "stopped"}
