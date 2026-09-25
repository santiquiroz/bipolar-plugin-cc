import json
import os
import re
import unittest

from harness import StubServer, UNREACHABLE_URL, command, compact_json, curl_calls, output, run

SUBMIT = "bipolar-delegate-submit"
JOBS_PATH = "/api/delegate/jobs"
WORKSPACE = "C:/personal/some repo"
TRICKY_TASK = "\n".join([
    "don't touch `x` $(id) \"q\" and ${HOME}",
    "it's JS: const s = 'a' + `${b}`; path C:\\tmp\\$USER \\n stays",
    "line3 ünïcode",
])
QUEUED = (200, compact_json({"id": "job-1", "status": "queued"}))
BROKER_REFUSALS = [
    (400, compact_json({"detail": "workspace_not_allowed"})),
    (400, compact_json({"detail": {
        "detail": "no_agent_available",
        "reasons": ["codex: exhausted:quota_exhausted"],
        "skipped": {"codex": "exhausted:quota_exhausted", "agy": "busy"},
    }})),
    (409, compact_json({"detail": "recursion_guard"})),
    (429, compact_json({"detail": "too_many_jobs"})),
]
BODY_ARGUMENT = re.compile(r"--data-binary @(\S+)")
NODE_MISSING = "node() { return 127; }\nexport -f node\n"


def submit(*flags, task=TRICKY_TASK, prelude="", reply=QUEUED, **overrides):
    with StubServer({("POST", JOBS_PATH): reply}) as server:
        result = run(command(SUBMIT, "--workspace", WORKSPACE, *flags), stdin=task + "\n",
                     prelude=prelude, **{"BIPOLAR_URL": server.url, **overrides})
    return result, server.requests


def posted_body(requests):
    return json.loads(requests[0].body)


def posted_body_path(result):
    return BODY_ARGUMENT.search(curl_calls(result)[0]).group(1)


class DelegateJsonBodyTest(unittest.TestCase):
    def test_task_is_posted_byte_for_byte(self):
        result, requests = submit()

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertEqual(posted_body(requests)["task"], TRICKY_TASK)

    def test_body_is_sent_from_a_file_not_inline(self):
        result, _ = submit()

        self.assertIsNotNone(posted_body_path(result))
        self.assertNotIn("don't", "\n".join(result.calls))

    def test_default_body_carries_only_task_workspace_and_mode(self):
        _, requests = submit()

        self.assertEqual(posted_body(requests), {"task": TRICKY_TASK, "workspace": WORKSPACE, "mode": "task"})

    def test_flags_add_their_optional_fields(self):
        _, requests = submit("--mode", "text", "--agent", "codex", "--tier", "complex", "--dry-run")

        self.assertEqual(posted_body(requests), {
            "task": TRICKY_TASK,
            "workspace": WORKSPACE,
            "mode": "text",
            "agent_id": "codex",
            "tier_hint": "complex",
            "dry_run": True,
        })

    def test_python_builds_the_same_body_when_node_is_missing(self):
        result, requests = submit("--agent", "claude", prelude=NODE_MISSING)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertEqual(posted_body(requests), {
            "task": TRICKY_TASK, "workspace": WORKSPACE, "mode": "task", "agent_id": "claude",
        })

    def test_timeout_flag_adds_an_integer_timeout_s(self):
        _, requests = submit("--timeout", "1800")

        self.assertEqual(posted_body(requests)["timeout_s"], 1800)

    def test_python_adds_the_same_integer_timeout_s(self):
        result, requests = submit("--timeout", "1800", prelude=NODE_MISSING)

        self.assertEqual(result.completed.returncode, 0, output(result.completed))
        self.assertEqual(posted_body(requests)["timeout_s"], 1800)

    def test_temporary_files_are_removed_after_posting(self):
        result, _ = submit()

        self.assertFalse(os.path.exists(posted_body_path(result)))


class DelegateSubmitReplyTest(unittest.TestCase):
    def test_prints_the_job_and_its_http_code(self):
        result, _ = submit()

        self.assertEqual(result.completed.stdout.splitlines()[-2:], [QUEUED[1], "HTTP 200"])

    def test_shows_a_rejected_key_as_http_401(self):
        result, _ = submit(reply=(401, compact_json({"detail": "API key inválida o faltante"})))

        self.assertEqual(result.completed.stdout.splitlines()[-1], "HTTP 401")

    def test_passes_the_brokers_refusals_through_intact(self):
        for code, payload in BROKER_REFUSALS:
            with self.subTest(code=code, payload=payload):
                result, _ = submit(reply=(code, payload))

                self.assertEqual(result.completed.returncode, 0, output(result.completed))
                self.assertEqual(result.completed.stdout.splitlines()[-2:], [payload, f"HTTP {code}"])

    def test_reports_an_unreachable_server(self):
        result, _ = submit(BIPOLAR_URL=UNREACHABLE_URL)

        self.assertEqual(result.completed.returncode, 82, output(result.completed))
        self.assertIn("unreachable", result.completed.stdout)


class DelegateSubmitUsageTest(unittest.TestCase):
    def assert_refused_before_any_request(self, result, requests, message):
        self.assertEqual(result.completed.returncode, 64, output(result.completed))
        self.assertIn(message, result.completed.stdout)
        self.assertEqual(requests, [])

    def test_timeout_outside_the_brokers_range_is_refused(self):
        for value in ("59", "3601", "1.5", "abc"):
            with self.subTest(value=value):
                result, requests = submit("--timeout", value)

                self.assert_refused_before_any_request(result, requests, "60 to 3600")

    def test_an_empty_task_is_refused(self):
        result, requests = submit(task=" \n")

        self.assert_refused_before_any_request(result, requests, "empty task")

    def test_an_unknown_flag_is_refused(self):
        result, requests = submit("--model", "x")

        self.assert_refused_before_any_request(result, requests, "unknown argument: --model")


if __name__ == "__main__":
    unittest.main()
