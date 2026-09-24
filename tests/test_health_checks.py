import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shell_blocks import REPO, block_containing, run_with_real_curl

RESCUE = "agents/bipolar-rescue.md"
DELEGATE = "commands/delegate.md"
SETUP = "commands/setup.md"
KEY_CHECK_PATH = "/api/delegate/jobs?limit=1"
STATUS_PATH = "/api/llamacpp/status"
LOCAL_ROUTE = "tier=simple;score=12;intent=code;target=provider:llamacpp;model=qwen;src=smart;mode=auto;id=d1"
PAID_ROUTE = "tier=complex;score=80;intent=code;target=provider:anthropic;model=claude;src=smart;mode=auto;id=d2"


def compact_json(value):
    # Starlette's JSONResponse serializes without spaces
    return json.dumps(value, separators=(",", ":"))


def llama_status(running, healthy):
    return 200, compact_json({
        "running": running, "pid": 4242 if running else None, "port": 8080,
        "model_path": "C:/models/qwen.gguf", "healthy": healthy, "busy_slots": 0,
    })


HEALTH = (200, compact_json({
    "status": "ok", "version": "2.13.0", "api_key_configured": True,
    "smart_routing": {"enabled": True, "mode": "auto"}, "delegation_enabled": True,
}))
UNAUTHORIZED = (401, compact_json({"detail": "API key inválida o faltante"}))
EMPTY_JOBS = (200, compact_json({"jobs": []}))
STATIC_MODELS = (200, compact_json({"object": "list", "data": [{"id": "claude-sonnet-4-20250514"}]}))
SMOKE_REPLY = 'event: message_stop\ndata: {"type":"message_stop"}\n\n'


class RoutedServer:
    def __init__(self, routes, headers=None):
        self.routes = routes
        self.headers = headers or {}
        self.requests = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self._answer()

            def do_POST(self):
                length = int(self.headers.get("content-length") or 0)
                self.rfile.read(length)
                self._answer()

            def _answer(self):
                server.requests.append((self.command, self.path, self.headers.get("x-api-key")))
                code, body = server.routes.get((self.command, self.path), (404, '{"detail":"Not Found"}'))
                payload = body.encode("utf-8")
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                for name, value in server.headers.get((self.command, self.path), {}).items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        return Handler

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def __enter__(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def closed_port_url():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{probe.getsockname()[1]}"


def run_against(block, routes, headers=None):
    with RoutedServer(routes, headers) as server:
        completed = run_with_real_curl(block, BIPOLAR_URL=server.url)
    return completed, server.requests


def output(completed):
    return completed.stdout + completed.stderr


def rescue_health_block():
    return block_containing(RESCUE, "exit 77")


def delegate_health_block():
    return block_containing(DELEGATE, "exit 77")


class RescueHealthCheckTest(unittest.TestCase):
    def test_proceeds_when_llama_server_runs_and_is_healthy(self):
        completed, requests = run_against(rescue_health_block(), {("GET", STATUS_PATH): llama_status(True, True)})

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertIn(("GET", STATUS_PATH, "test-key"), requests)

    def test_a_static_model_list_does_not_count_as_a_running_llama_server(self):
        routes = {("GET", "/v1/models"): STATIC_MODELS, ("GET", STATUS_PATH): llama_status(False, False)}

        completed, _ = run_against(rescue_health_block(), routes)

        self.assertEqual(completed.returncode, 83, output(completed))
        self.assertIn("not running", completed.stdout)

    def test_stops_while_llama_server_is_not_healthy_yet(self):
        completed, _ = run_against(rescue_health_block(), {("GET", STATUS_PATH): llama_status(True, False)})

        self.assertEqual(completed.returncode, 83, output(completed))
        self.assertIn("not healthy", completed.stdout)

    def test_reports_a_rejected_key(self):
        completed, _ = run_against(rescue_health_block(), {("GET", STATUS_PATH): UNAUTHORIZED})

        self.assertEqual(completed.returncode, 81, output(completed))
        self.assertIn("/bipolar:setup", completed.stdout)

    def test_reports_an_unreachable_server(self):
        completed = run_with_real_curl(rescue_health_block(), BIPOLAR_URL=closed_port_url())

        self.assertEqual(completed.returncode, 82, output(completed))
        self.assertIn("unreachable", completed.stdout)

    def test_reports_any_other_answer_with_its_http_code(self):
        completed, _ = run_against(rescue_health_block(), {})

        self.assertEqual(completed.returncode, 84, output(completed))
        self.assertIn("HTTP 404", completed.stdout)

    def test_static_model_list_is_no_longer_the_go_signal(self):
        block = rescue_health_block()

        self.assertNotIn("/v1/models", block)
        self.assertIn(STATUS_PATH, block)


class DelegateHealthCheckTest(unittest.TestCase):
    def test_validates_the_key_on_the_api_after_the_public_health(self):
        routes = {("GET", "/api/health"): HEALTH, ("GET", KEY_CHECK_PATH): EMPTY_JOBS}

        completed, requests = run_against(delegate_health_block(), routes)

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertIn(("GET", KEY_CHECK_PATH, "test-key"), requests)
        self.assertIn('"delegation_enabled":true', completed.stdout)

    def test_stops_when_the_api_rejects_the_key(self):
        routes = {("GET", "/api/health"): HEALTH, ("GET", KEY_CHECK_PATH): UNAUTHORIZED}

        completed, _ = run_against(delegate_health_block(), routes)

        self.assertEqual(completed.returncode, 81, output(completed))
        self.assertIn("/bipolar:setup", completed.stdout)

    def test_stops_when_the_server_is_unreachable(self):
        completed = run_with_real_curl(delegate_health_block(), BIPOLAR_URL=closed_port_url())

        self.assertEqual(completed.returncode, 82, output(completed))
        self.assertIn("unreachable", completed.stdout)

    def test_reports_a_server_without_the_broker(self):
        completed, _ = run_against(delegate_health_block(), {("GET", "/api/health"): HEALTH})

        self.assertEqual(completed.returncode, 84, output(completed))
        self.assertIn("HTTP 404", completed.stdout)


class DelegateResponseTableTest(unittest.TestCase):
    def setUp(self):
        self.text = (REPO / DELEGATE).read_text(encoding="utf-8")

    def test_does_not_expect_a_202_from_the_broker(self):
        self.assertNotIn("202", self.text)

    def test_a_submitted_job_is_a_200_with_status_queued(self):
        self.assertRegex(self.text, r"- 200 .*`status: queued`")

    def test_has_a_row_for_a_rejected_key(self):
        self.assertRegex(self.text, r"(?m)^- 401 .*/bipolar:setup")


def with_config_file(block):
    write_config = (
        'mkdir -p "$HOME/.config/bipolar-cc"\n'
        'printf "BIPOLAR_URL=%s\\nBIPOLAR_API_KEY=%s\\n" "$BIPOLAR_URL" "$BIPOLAR_API_KEY" > "$HOME/.config/bipolar-cc/env"\n'
    )
    return write_config + block


def setup_routes():
    return {
        ("GET", "/api/health"): HEALTH,
        ("GET", KEY_CHECK_PATH): EMPTY_JOBS,
        ("GET", STATUS_PATH): llama_status(True, True),
        ("POST", "/v1/messages"): (200, SMOKE_REPLY),
    }


def setup_verify_block():
    return with_config_file(block_containing(SETUP, "/v1/messages"))


class SetupVerificationTest(unittest.TestCase):
    def test_checks_the_key_where_the_delegate_and_the_rescue_use_it(self):
        completed, requests = run_against(setup_verify_block(), setup_routes())

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertIn(("GET", KEY_CHECK_PATH, "test-key"), requests)
        self.assertIn(("GET", STATUS_PATH, "test-key"), requests)

    def test_reports_version_and_delegation_switch(self):
        completed, _ = run_against(setup_verify_block(), setup_routes())

        self.assertIn('"version":"2.13.0"', completed.stdout)
        self.assertIn('"delegation_enabled":true', completed.stdout)

    def test_shows_which_provider_answered_the_smoke(self):
        headers = {("POST", "/v1/messages"): {"X-Bipolar-Route": PAID_ROUTE}}

        completed, _ = run_against(setup_verify_block(), setup_routes(), headers)

        self.assertRegex(completed.stdout, r"(?im)^x-bipolar-route: .*target=provider:anthropic")

    def test_explains_a_smoke_not_served_by_llamacpp(self):
        text = (REPO / SETUP).read_text(encoding="utf-8")

        self.assertIn("X-Bipolar-Route", text)
        self.assertIn("target=provider:llamacpp", text)
        self.assertNotIn("/v1/models", text)

    def test_final_reminder_mentions_both_lanes(self):
        reminder = (REPO / SETUP).read_text(encoding="utf-8").strip().splitlines()[-1]

        self.assertIn("/bipolar:rescue", reminder)
        self.assertIn("/bipolar:delegate", reminder)


if __name__ == "__main__":
    unittest.main()
