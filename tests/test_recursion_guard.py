import unittest

from harness import StubServer, command, compact_json, curl_calls, output, run

JOBS_PATH = "/api/delegate/jobs"
HEALTH = (200, compact_json({"status": "ok", "version": "2.13.0", "delegation_enabled": True}))
EMPTY_JOBS = (200, compact_json({"jobs": []}))
QUEUED = (200, compact_json({"id": "job-1", "status": "queued"}))


def assert_refused_before_any_request(test, result):
    test.assertEqual(result.completed.returncode, 77, output(result.completed))
    test.assertIn("recursion", result.completed.stdout.lower())
    test.assertEqual(curl_calls(result), [])


def submit(depth=None):
    with StubServer({("POST", JOBS_PATH): QUEUED}) as server:
        run(command("bipolar-delegate-submit"), stdin="task\n", depth=depth, BIPOLAR_URL=server.url)
    return server.requests[0].headers


class DelegateRecursionGuardTest(unittest.TestCase):
    def test_config_step_refuses_inside_a_delegated_child_before_any_request(self):
        assert_refused_before_any_request(self, run(command("bipolar-delegate-check"), depth="1"))

    def test_config_step_reaches_the_server_at_top_level(self):
        routes = {("GET", "/api/health"): HEALTH, ("GET", f"{JOBS_PATH}?limit=1"): EMPTY_JOBS}
        with StubServer(routes) as server:
            result = run(command("bipolar-delegate-check"), BIPOLAR_URL=server.url)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertEqual(len(server.requests), 2)

    def test_submit_forwards_the_inherited_depth(self):
        self.assertEqual(submit(depth="1")["x-bipolar-depth"], "1")

    def test_submit_sends_depth_zero_at_top_level(self):
        self.assertEqual(submit()["x-bipolar-depth"], "0")


class RescueRecursionGuardTest(unittest.TestCase):
    def test_health_check_refuses_inside_a_delegated_child_before_any_request(self):
        assert_refused_before_any_request(self, run(command("bipolar-rescue-check"), depth="1"))

    def test_run_refuses_inside_a_delegated_child_before_launching_claude(self):
        result = run(command("bipolar-rescue-run"), stdin="task\n", depth="1")

        self.assertEqual(result.completed.returncode, 77, output(result.completed))
        self.assertEqual(result.claude_args, [])

    def test_child_claude_is_marked_as_delegated(self):
        result = run(command("bipolar-rescue-run"), stdin="task\n")

        self.assertIn("claude depth=1", result.calls)


if __name__ == "__main__":
    unittest.main()
