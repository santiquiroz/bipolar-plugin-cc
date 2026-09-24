import json
import re
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shell_blocks import block_containing, run_with_fakes, run_with_real_curl

DELEGATE = "commands/delegate.md"
JOB_ID = "job-7f3a"
FAST_POLL = {"POLL_S": "0"}


def compact_json(value):
    # Starlette's JSONResponse serializes without spaces
    return json.dumps(value, separators=(",", ":"))


def job(status, **fields):
    return 200, compact_json({"id": JOB_ID, "status": status, "output_tail": "", "error": "", **fields})


NOT_FOUND = (404, compact_json({"detail": "Job no encontrado"}))
SERVER_ERROR = (502, "<html>Bad Gateway</html>")


class ScriptedJobServer:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())

    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                server.requests.append((self.command, self.path, self.headers.get("x-api-key")))
                code, body = server.responses.pop(0) if len(server.responses) > 1 else server.responses[0]
                payload = body.encode("utf-8")
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
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


def poll_block(**variables):
    block = block_containing(DELEGATE, "/api/delegate/jobs/").replace("<id>", JOB_ID)
    for name, value in {**FAST_POLL, **variables}.items():
        block = re.sub(rf"(?<![\w$]){name}=\S*", f"{name}={value}", block, count=1)
    return block


def poll(responses, **variables):
    with ScriptedJobServer(responses) as server:
        completed = run_with_real_curl(poll_block(**variables), BIPOLAR_URL=server.url)
    return completed, server.requests


def final_status(completed):
    return json.loads(completed.stdout.strip().splitlines()[-1])["status"]


class DelegatePollingTest(unittest.TestCase):
    def test_polls_while_running_until_the_job_succeeds(self):
        completed, requests = poll([job("running")] * 3 + [job("succeeded", output_tail="done")])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(final_status(completed), "succeeded")
        self.assertEqual(len(requests), 4)
        self.assertEqual(requests[0], ("GET", f"/api/delegate/jobs/{JOB_ID}", "test-key"))

    def test_keeps_polling_after_a_failed_status_read(self):
        completed, requests = poll([SERVER_ERROR, (200, ""), job("queued"), job("failed", error="max_attempts")])

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(final_status(completed), "failed")
        self.assertEqual(len(requests), 4)

    def test_gives_up_after_three_failed_status_reads_in_a_row(self):
        completed, requests = poll([SERVER_ERROR])

        self.assertEqual(completed.returncode, 74, completed.stdout + completed.stderr)
        self.assertEqual(len(requests), 3)
        self.assertIn("502", completed.stdout)

    def test_gives_up_when_the_server_is_unreachable(self):
        completed = run_with_real_curl(poll_block(), BIPOLAR_URL=closed_port_url())

        self.assertEqual(completed.returncode, 74, completed.stdout + completed.stderr)

    def test_reports_a_missing_job_as_lost_without_retrying(self):
        completed, requests = poll([NOT_FOUND])

        self.assertEqual(completed.returncode, 76, completed.stdout + completed.stderr)
        self.assertEqual(len(requests), 1)
        self.assertIn("restarted", completed.stdout)

    def test_ends_the_segment_with_the_job_still_running(self):
        completed, requests = poll([job("running")], SEGMENT_S="0")

        self.assertEqual(completed.returncode, 75, completed.stdout + completed.stderr)
        self.assertEqual(len(requests), 1)
        self.assertIn("run this block again", completed.stdout)

    def test_segment_fits_inside_the_bash_tool_ceiling(self):
        block = block_containing(DELEGATE, "/api/delegate/jobs/")
        segment = int(re.search(r"SEGMENT_S=(\d+)", block).group(1))
        request_cap = int(re.search(r"--max-time (\d+)", block).group(1))
        poll_interval = int(re.search(r"POLL_S=(\d+)", block).group(1))

        self.assertLessEqual(segment + poll_interval + request_cap, 600)


class DelegateCancelTest(unittest.TestCase):
    def test_cancel_sends_delete_for_the_job(self):
        block = block_containing(DELEGATE, "-X DELETE").replace("<id>", JOB_ID)

        run = run_with_fakes(block)

        curl_call = next(call for call in run.calls if call.startswith("curl "))
        self.assertEqual(run.completed.returncode, 0, run.completed.stderr)
        self.assertIn("-X DELETE", curl_call)
        self.assertIn("x-api-key: test-key", curl_call)
        self.assertTrue(curl_call.endswith(f"http://bipolar.invalid:8000/api/delegate/jobs/{JOB_ID}"))


if __name__ == "__main__":
    unittest.main()
