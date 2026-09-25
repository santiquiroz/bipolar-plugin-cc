import unittest

from harness import BIN, REPO, StubServer, closed_port_url, command, compact_json, output, run

DELEGATE = "commands/delegate.md"
SETUP = "commands/setup.md"
KEY_CHECK_PATH = "/api/delegate/jobs?limit=1"
STATUS_PATH = "/api/llamacpp/status"
PAID_ROUTE = "tier=complex;score=80;intent=code;target=provider:anthropic;model=claude;src=smart;mode=auto;id=d2"


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


def write_config(url="$BIPOLAR_URL"):
    return (
        'mkdir -p "$HOME/.config/bipolar-cc"\n'
        f'printf "BIPOLAR_URL=%s\\nBIPOLAR_API_KEY=%s\\n" "{url}" "$BIPOLAR_API_KEY" > "$HOME/.config/bipolar-cc/env"\n'
    )


def run_against(script_name, routes, headers=None, prelude=""):
    with StubServer(routes, headers) as server:
        completed = run(command(script_name), prelude=prelude, BIPOLAR_URL=server.url).completed
    return completed, [(r.method, r.path, r.api_key) for r in server.requests]


def run_unreachable(script_name):
    return run(command(script_name), BIPOLAR_URL=closed_port_url()).completed


class RescueHealthCheckTest(unittest.TestCase):
    def test_proceeds_when_llama_server_runs_and_is_healthy(self):
        completed, requests = run_against("bipolar-rescue-check", {("GET", STATUS_PATH): llama_status(True, True)})

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertIn(("GET", STATUS_PATH, "test-key"), requests)

    def test_a_static_model_list_does_not_count_as_a_running_llama_server(self):
        routes = {("GET", "/v1/models"): STATIC_MODELS, ("GET", STATUS_PATH): llama_status(False, False)}

        completed, _ = run_against("bipolar-rescue-check", routes)

        self.assertEqual(completed.returncode, 83, output(completed))
        self.assertIn("not running", completed.stdout)

    def test_stops_while_llama_server_is_not_healthy_yet(self):
        completed, _ = run_against("bipolar-rescue-check", {("GET", STATUS_PATH): llama_status(True, False)})

        self.assertEqual(completed.returncode, 83, output(completed))
        self.assertIn("not healthy", completed.stdout)

    def test_reports_a_rejected_key(self):
        completed, _ = run_against("bipolar-rescue-check", {("GET", STATUS_PATH): UNAUTHORIZED})

        self.assertEqual(completed.returncode, 81, output(completed))
        self.assertIn("/bipolar:setup", completed.stdout)

    def test_reports_an_unreachable_server(self):
        completed = run_unreachable("bipolar-rescue-check")

        self.assertEqual(completed.returncode, 82, output(completed))
        self.assertIn("unreachable", completed.stdout)

    def test_reports_any_other_answer_with_its_http_code(self):
        completed, _ = run_against("bipolar-rescue-check", {})

        self.assertEqual(completed.returncode, 84, output(completed))
        self.assertIn("HTTP 404", completed.stdout)

    def test_static_model_list_is_no_longer_the_go_signal(self):
        script = (BIN / "bipolar-rescue-check").read_text(encoding="utf-8")

        self.assertNotIn('/v1/models"', script)
        self.assertIn(STATUS_PATH, script)


class DelegateHealthCheckTest(unittest.TestCase):
    def test_validates_the_key_on_the_api_after_the_public_health(self):
        routes = {("GET", "/api/health"): HEALTH, ("GET", KEY_CHECK_PATH): EMPTY_JOBS}

        completed, requests = run_against("bipolar-delegate-check", routes)

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertIn(("GET", KEY_CHECK_PATH, "test-key"), requests)
        self.assertIn('"delegation_enabled":true', completed.stdout)

    def test_stops_when_the_api_rejects_the_key(self):
        routes = {("GET", "/api/health"): HEALTH, ("GET", KEY_CHECK_PATH): UNAUTHORIZED}

        completed, _ = run_against("bipolar-delegate-check", routes)

        self.assertEqual(completed.returncode, 81, output(completed))
        self.assertIn("/bipolar:setup", completed.stdout)

    def test_stops_when_the_server_is_unreachable(self):
        completed = run_unreachable("bipolar-delegate-check")

        self.assertEqual(completed.returncode, 82, output(completed))
        self.assertIn("unreachable", completed.stdout)

    def test_reports_a_server_without_the_broker(self):
        completed, _ = run_against("bipolar-delegate-check", {("GET", "/api/health"): HEALTH})

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


def setup_routes():
    return {
        ("GET", "/api/health"): HEALTH,
        ("GET", KEY_CHECK_PATH): EMPTY_JOBS,
        ("GET", STATUS_PATH): llama_status(True, True),
        ("POST", "/v1/messages"): (200, SMOKE_REPLY),
    }


def run_setup_verify(headers=None):
    return run_against("bipolar-setup-verify", setup_routes(), headers, prelude=write_config())


class SetupVerificationTest(unittest.TestCase):
    def test_checks_the_key_where_the_delegate_and_the_rescue_use_it(self):
        completed, requests = run_setup_verify()

        self.assertEqual(completed.returncode, 0, output(completed))
        self.assertIn(("GET", KEY_CHECK_PATH, "test-key"), requests)
        self.assertIn(("GET", STATUS_PATH, "test-key"), requests)

    def test_reports_version_and_delegation_switch(self):
        completed, _ = run_setup_verify()

        self.assertIn('"version":"2.13.0"', completed.stdout)
        self.assertIn('"delegation_enabled":true', completed.stdout)

    def test_shows_which_provider_answered_the_smoke(self):
        completed, _ = run_setup_verify({("POST", "/v1/messages"): {"X-Bipolar-Route": PAID_ROUTE}})

        self.assertRegex(completed.stdout, r"(?im)^x-bipolar-route: .*target=provider:anthropic")

    def test_verifies_the_file_it_just_wrote_not_the_environment(self):
        with StubServer(setup_routes()) as server:
            prelude = write_config(url=server.url)
            completed = run(command("bipolar-setup-verify"), prelude=prelude, BIPOLAR_URL=closed_port_url()).completed

        self.assertEqual(len(server.requests), 4, output(completed))

    def test_stops_when_the_config_file_is_missing(self):
        completed = run(command("bipolar-setup-verify")).completed

        self.assertEqual(completed.returncode, 78, output(completed))

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
