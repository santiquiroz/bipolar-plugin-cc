import unittest

from harness import StubServer, command, compact_json, curl_calls, output, run

UNUSED_URL = "http://from-file.invalid:8000"
FILE_KEY = "file-key"
ENV_KEY = "env-key"
JOBS_PATH = "/api/delegate/jobs"
STATUS_PATH = "/api/llamacpp/status"
NOT_CONFIGURED = {"BIPOLAR_URL": "", "BIPOLAR_API_KEY": ""}
QUEUED = (200, compact_json({"id": "job-1", "status": "queued"}))
READY = (200, compact_json({"running": True, "healthy": True}))


def config_file(url, key=FILE_KEY):
    return (
        'mkdir -p "$HOME/.config/bipolar-cc"\n'
        f'printf "BIPOLAR_URL=%s\nBIPOLAR_API_KEY=%s\n" "{url}" "{key}" > "$HOME/.config/bipolar-cc/env"\n'
    )


def run_against(script, routes, file_url=None, stdin="", **overrides):
    with StubServer(routes) as server:
        prelude = config_file(file_url or server.url)
        env = {key: value.replace("{server}", server.url) for key, value in overrides.items()}
        result = run(script, stdin=stdin, prelude=prelude, **env)
    return result, server.requests


def submit(**overrides):
    return run_against(command("bipolar-delegate-submit"), {("POST", JOBS_PATH): QUEUED}, stdin="task\n", **overrides)


def rescue_check(**overrides):
    return run_against(command("bipolar-rescue-check"), {("GET", STATUS_PATH): READY}, **overrides)


def only_env():
    return {"BIPOLAR_URL": "{server}", "BIPOLAR_API_KEY": ENV_KEY}


class DelegateSubmitConfigTest(unittest.TestCase):
    def test_submit_reads_the_config_file_written_by_setup(self):
        result, requests = submit(**NOT_CONFIGURED)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertEqual([(r.method, r.path, r.api_key) for r in requests], [("POST", JOBS_PATH, FILE_KEY)])

    def test_submit_keeps_environment_variables_over_the_file(self):
        _, requests = submit(file_url=UNUSED_URL, **only_env())

        self.assertEqual([(r.path, r.api_key) for r in requests], [(JOBS_PATH, ENV_KEY)])

    def test_submit_refuses_without_any_config_before_any_request(self):
        result = run(command("bipolar-delegate-submit"), stdin="task\n", **NOT_CONFIGURED)

        self.assertEqual(result.completed.returncode, 78, output(result.completed))
        self.assertIn("/bipolar:setup", result.completed.stdout)
        self.assertEqual(curl_calls(result), [])


class RescueConfigTest(unittest.TestCase):
    def test_health_check_keeps_environment_variables_over_the_file(self):
        _, requests = rescue_check(file_url=UNUSED_URL, **only_env())

        self.assertEqual([(r.path, r.api_key) for r in requests], [(STATUS_PATH, ENV_KEY)])

    def test_health_check_reads_the_config_file_written_by_setup(self):
        result, requests = rescue_check(**NOT_CONFIGURED)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertEqual([(r.path, r.api_key) for r in requests], [(STATUS_PATH, FILE_KEY)])

    def test_health_check_refuses_without_any_config_before_any_request(self):
        result = run(command("bipolar-rescue-check"), **NOT_CONFIGURED)

        self.assertEqual(result.completed.returncode, 78, output(result.completed))
        self.assertIn("/bipolar:setup", result.completed.stdout)
        self.assertEqual(curl_calls(result), [])

    def test_child_keeps_environment_variables_over_the_file(self):
        result = run(command("bipolar-rescue-run"), stdin="task\n", prelude=config_file(UNUSED_URL),
                     BIPOLAR_URL="http://from-env:8000", BIPOLAR_API_KEY=ENV_KEY)

        self.assertIn("claude ANTHROPIC_BASE_URL=http://from-env:8000", result.calls)
        self.assertIn(f"claude ANTHROPIC_API_KEY={ENV_KEY}", result.calls)

    def test_child_reads_the_config_file_written_by_setup(self):
        result = run(command("bipolar-rescue-run"), stdin="task\n", prelude=config_file(UNUSED_URL), **NOT_CONFIGURED)

        self.assertIn(f"claude ANTHROPIC_BASE_URL={UNUSED_URL}", result.calls)
        self.assertIn(f"claude ANTHROPIC_API_KEY={FILE_KEY}", result.calls)

    def test_child_refuses_without_any_config_before_running_claude(self):
        result = run(command("bipolar-rescue-run"), stdin="task\n", **NOT_CONFIGURED)

        self.assertEqual(result.completed.returncode, 78, output(result.completed))
        self.assertEqual(result.claude_args, [])


if __name__ == "__main__":
    unittest.main()
